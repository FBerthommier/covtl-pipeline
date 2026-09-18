# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
main.py
=======
``vtl-synth`` command-line interface.

Subcommands (mirroring the vtl-pipeline reference layout)::

    vtl-synth run "this is easy for us" -o ./out
    vtl-synth text-to-wav "this is easy for us" -o ./out
    vtl-synth tract-to-mp4 out/output.tract out/output.wav -o out/output.mp4
    vtl-synth inspect out/output.tract --states 2 --ranges
    vtl-synth plot-tract out/output.tract --which all -o out/tract.png

``run`` produces the .tract (400 Hz tract+glottis vectors), .wav
(44.1 kHz), .mp4 (sagittal animation, 25 Hz) and the SAMPA
transcript; ``text-to-wav`` stops after the audio; input can also be
given directly as engine SAMPA with ``--phonetic``::

    vtl-synth run --phonetic "ba da ga | iowa a g" -o ./out
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_engine_options(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group('engine options (COVTL model parameters)')
    g.add_argument('--phonetic', action='store_true',
                   help='input is already engine SAMPA (skip g2p)')
    g.add_argument('-l', '--lang', default=None, metavar='CODE',
                   help="language override for this call only (default: "
                        "the active language set by setup_lang.py, cf. "
                        "`python setup_lang.py show`)")
    g.add_argument('--tcons', type=float, default=None, metavar='MS',
                   help='consonant duration in ms (default: the active '
                        'language profile, cf. constants.py LANG SECTION)')
    g.add_argument('--tvoy', type=float, default=None, metavar='MS',
                   help='vowel duration in ms (default: the active '
                        'language profile)')
    g.add_argument('--tpause', type=float, default=None, metavar='MS',
                   help='short inter-word pause in ms (default: the active '
                        'language profile)')
    g.add_argument('--tpause-long', type=float, default=None, metavar='MS',
                   help='long (end of sentence) pause in ms (default: the '
                        'active language profile)')
    g.add_argument('-f0', '--f0', type=float, default=None,
                   help='fundamental frequency in Hz (default: f0_default '
                        'of the active speaker constants, e.g. 102.216 '
                        'for JD3, 114.908 for s1, 181.008 for s2)')
    g.add_argument('-s', '--speaker', default='JD3',
                   help='speaker name (default: JD3)')
    g.add_argument('--no-ortho', action='store_true',
                   help='disable the orthogonal branch')
    g.add_argument('--engine', default='syl', choices=['syl', 'legacy'],
                   help="trajectory engine (default: 'syl')")
    g.add_argument('--expressive', action='store_true', default=False,
                   help='expressive prosody (v1.1.0): syntactic breathing '
                        '(short pauses at chunk boundaries) + sculpted F0 '
                        'contour (pitch accents, per-chunk reset, nuclear '
                        'fall). Default OFF (bit-identical monotone '
                        'declination)')
    g.add_argument('--no-expressive', dest='expressive',
                   action='store_false',
                   help='monotone declination (the default, stated '
                        'explicitly)')


def _resolve_lang(args: argparse.Namespace) -> str:
    """Language for this call: explicit --lang, else setup_lang's active one.

    Falls back to 'en' (the historical CMUdict gateway) when the
    language pack is not installed (native constants have no
    ACTIVE_LANG).
    """
    from vtl_synth.core import constants as _c
    lang = getattr(args, 'lang', None) or getattr(_c, 'ACTIVE_LANG', 'en')
    return lang


def _make_pipeline(args: argparse.Namespace):
    from vtl_synth import Pipeline
    from vtl_synth.core import constants as _c
    # args.f0 None -> f0_default of the active speaker constants
    # (resolved inside Pipeline; D14 fix).
    kwargs = dict(
        f0_hz=args.f0,
        speaker=args.speaker,
        engine=args.engine,
        use_orthogonal=not args.no_ortho,
        t_cons_ms=args.tcons,
        t_voy_ms=args.tvoy,
        pause_short_ms=args.tpause,
        pause_long_ms=args.tpause_long,
    )
    # lang= n'existe que lorsque le language pack est installe (le
    # Pipeline natif multi-speakers ne connait pas ce parametre)
    if args.lang is not None or hasattr(_c, 'ACTIVE_LANG'):
        kwargs['lang'] = _resolve_lang(args)
    else:
        # pipeline natif : pas de sentinelles None (defaults historiques)
        for key, default in (('t_cons_ms', 100.0), ('t_voy_ms', 80.0),
                             ('pause_short_ms', 200.0),
                             ('pause_long_ms', 320.0)):
            if kwargs[key] is None:
                kwargs[key] = default
    # expressive= n'existe que lorsque le language pack (>= v1.0.8) est
    # installe (Pipeline natif multi-speakers sans prosodie expressive)
    if getattr(args, 'expressive', False):
        kwargs['expressive'] = True
    return Pipeline(**kwargs)


def _print_lang(args: argparse.Namespace) -> None:
    try:
        from vtl_synth.utils.setlang import get_profile
    except ImportError:
        return          # language pack non installe : rien a afficher
    from vtl_synth.core import speaker_registry as sr
    lang = _resolve_lang(args)
    profile = get_profile(lang)
    extra = ''
    try:
        from vtl_synth.utils.lexicon_loader import LEXICONS, has_lexicon
        if lang in LEXICONS and has_lexicon(lang):
            from vtl_synth.utils.lexicon_loader import lexicon_size
            extra = f", lexique : {lexicon_size(lang)} entrées"
        elif lang in LEXICONS:
            extra = ', lexique : ABSENT (règles seules)'
    except Exception:
        extra = ', lexique : ERREUR de chargement'
    print(f'  langue    : {lang} ({profile.display_name}), '
          f'speaker {sr.active_name()} — g2p : '
          f'{profile.g2p_callable.__name__}{extra}')
    prosody = ('expressive (respiration syntaxique + accents de hauteur)'
               if getattr(args, 'expressive', False)
               else 'monotone (déclinaison, défaut)')
    print(f'  prosodie  : {prosody}')


# ==========================================================================
# Subcommands
# ==========================================================================

def cmd_run(args: argparse.Namespace) -> int:
    pipe = _make_pipeline(args)
    result = pipe.run(args.text, output_dir=args.output_dir,
                      use_g2p=not args.phonetic, video=not args.no_video,
                      fps=args.fps, scale=args.scale, label=args.label,
                      polar=args.polar)
    print()
    print('=' * 60)
    print('SUCCESS')
    _print_lang(args)
    print(f'  SAMPA     : {result.sampa}')
    print(f'  phrases   : {len(result.phrases)}')
    print(f'  tract     : {result.tract_path} '
          f'({result.n_frames} frames @400 Hz)')
    print(f'  wav       : {result.wav_path} ({result.duration_s:.2f} s)')
    if getattr(result, 'polar_path', None) is not None:
        print(f'  polar     : {result.polar_path}')
    if result.mp4_path is not None:
        print(f'  mp4       : {result.mp4_path}')
    print('=' * 60)
    return 0


def cmd_text_to_wav(args: argparse.Namespace) -> int:
    pipe = _make_pipeline(args)
    result = pipe.text_to_wav(args.text, output_dir=args.output_dir,
                              use_g2p=not args.phonetic, label=args.label)
    prosody = 'expressive' if getattr(args, 'expressive', False) else 'monotone'
    print()
    print(f'SUCCESS ({_resolve_lang(args)}, prosodie : {prosody}): '
          f'{result.wav_path} ({result.duration_s:.2f} s)')
    return 0


def cmd_tract_to_mp4(args: argparse.Namespace) -> int:
    from vtl_synth import Pipeline
    from vtl_synth.core.speaker_registry import announce
    announce()
    Pipeline.tract_to_mp4(args.tract, args.wav, out_path=args.output,
                          fps=args.fps, scale=args.scale,
                          work_dir=Path(args.output).parent / 'temp_video')
    return 0


def cmd_polar_video(args: argparse.Namespace) -> int:
    """Dual-panel MP4: sagittal tract (left) + dynamic polar figure (right).

    Requires a .polar intermediate file (100 Hz polar trajectories +
    phoneme targets + timing); ``vtl-synth run --polar`` produces it
    alongside the synthesis, or ``vtl-synth polar-build`` from a phrase.
    """
    from vtl_synth.video.polar_video import make_polar_video
    from vtl_synth.core.speaker_registry import announce
    announce()
    make_polar_video(args.tract, args.polar, wav_path=args.wav,
                     out_path=args.output, fps=args.fps, scale=args.scale,
                     work_dir=Path(args.output).parent / 'temp_video')
    return 0


def cmd_polar_build(args: argparse.Namespace) -> int:
    """Phrase (internal notation) -> .polar intermediate file."""
    from vtl_synth.video.polar_video import build_polar, write_polar
    from vtl_synth.utils.setlang import get_profile
    from vtl_synth.core.constants import SpeakerConfig

    profile = get_profile(_resolve_lang(args))
    t_cons_ms = args.tcons if args.tcons is not None else \
        (profile.t_cons_ms if profile is not None else 100.0)
    t_voy_ms = args.tvoy if args.tvoy is not None else \
        (profile.t_voy_ms if profile is not None else 80.0)
    pause_short_ms = args.tpause if args.tpause is not None else \
        (profile.pause_short_ms if profile is not None else 200.0)
    pause_long_ms = args.tpause_long if args.tpause_long is not None else \
        (profile.pause_long_ms if profile is not None else 320.0)
    f0 = args.f0 if args.f0 is not None else SpeakerConfig().f0_default
    del f0      # speaker/f0 do not change the polar geometry

    phrases = [p.strip() for p in args.phrase.split('|') if p.strip()]
    polar = build_polar(
        phrases,
        t_cons=max(1, round(t_cons_ms / 10.0)),
        t_voy=max(1, round(t_voy_ms / 10.0)),
        pause_short_ms=pause_short_ms, pause_long_ms=pause_long_ms)
    out = write_polar(args.output, polar)
    print(f'polar: {out} ({polar["n_steps"]} steps @100 Hz, '
          f'{polar["duration_s"]:.2f} s, {len(polar["phonemes"])} phonemes)')
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    import numpy as np
    from vtl_synth.core.constants import TRACT_PARAM_NAMES, N_TRACT_PARAMS
    from vtl_synth.video.renderer import read_tract

    path = Path(args.file)
    if not path.exists():
        print(f'not found: {path}')
        return 1
    suffix = path.suffix.lower()
    if suffix in ('.ges', '.seg'):
        print(f'{suffix} files belong to the native VTL gesture '
              f'pipeline of the reference repository; this engine '
              f'goes text -> tract directly (no .ges/.seg stage).')
        return 1

    data, sr = read_tract(path)
    print(f'file      : {path}')
    print(f'shape     : {data.shape}  ({data.shape[1] - 19} glottis cols)'
          if data.shape[1] > 19 else
          f'shape     : {data.shape}')
    print(f'rate      : {sr:.0f} Hz')
    print(f'duration  : {data.shape[0] / sr:.3f} s')

    names = list(TRACT_PARAM_NAMES)
    tract = data[:, :N_TRACT_PARAMS]

    if args.states:
        n = args.states
        idx = list(range(min(n, len(tract)))) \
            + list(range(max(0, len(tract) - n), len(tract)))
        seen = set()
        for i in idx:
            if i in seen:
                continue
            seen.add(i)
            print(f'\n--- frame {i} (t = {i / sr * 1000:.0f} ms) ---')
            for j, name in enumerate(names):
                print(f'  {name:<12s} {tract[i, j]:9.3f}')

    if args.ranges:
        print('\n--- tract parameter ranges ---')
        print(f'  {"param":<12s} {"min":>9s} {"max":>9s} {"mean":>9s}')
        for j, name in enumerate(names):
            col = tract[:, j]
            print(f'  {name:<12s} {col.min():9.3f} {col.max():9.3f} '
                  f'{col.mean():9.3f}')
    return 0


def cmd_plot_tract(args: argparse.Namespace) -> int:
    from vtl_synth.video.tract_figure import plot_tract_file
    path = Path(args.file)
    if not path.exists():
        print(f'not found: {path}')
        return 1
    plot_tract_file(path, out_path=args.output, which=args.which,
                    params=args.params, show_stats=args.ranges)
    return 0


# ==========================================================================
# Parser
# ==========================================================================

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog='vtl-synth',
        description='Articulatory synthesis (Berthommier COVTL model '
                    '+ VocalTractLab): text -> tract -> wav -> mp4',
    )
    sub = ap.add_subparsers(dest='command', required=True)

    # ---- run -------------------------------------------------------------
    p = sub.add_parser('run', help='text -> .tract + .wav + .mp4')
    p.add_argument('text', help='English text, or SAMPA with --phonetic')
    p.add_argument('-o', '--output-dir', default='out',
                   help='output directory (default: ./out)')
    p.add_argument('--label', default=None,
                   help='file stem (default: derived from the text)')
    p.add_argument('--no-video', action='store_true',
                   help='skip the MP4 rendering')
    p.add_argument('--polar', action='store_true',
                   help='also write the .polar intermediate file (100 Hz '
                        'polar trajectories + phoneme timing) and render '
                        'the dual-panel video (tract | polar figure)')
    p.add_argument('--fps', type=int, default=25,
                   help='video frame rate (default: 25)')
    p.add_argument('--scale', type=int, default=2,
                   help='pixels per SVG unit (default: 2 -> 960x840)')
    _add_engine_options(p)
    p.set_defaults(func=cmd_run)

    # ---- text-to-wav -----------------------------------------------------
    p = sub.add_parser('text-to-wav', help='text -> .wav only')
    p.add_argument('text', help='English text, or SAMPA with --phonetic')
    p.add_argument('-o', '--output-dir', default='out',
                   help='output directory (default: ./out)')
    p.add_argument('--label', default=None,
                   help='file stem (default: derived from the text)')
    _add_engine_options(p)
    p.set_defaults(func=cmd_text_to_wav)

    # ---- tract-to-mp4 ----------------------------------------------------
    p = sub.add_parser('tract-to-mp4',
                       help='existing .tract (+ .wav) -> .mp4')
    p.add_argument('tract', help='input .tract file (400 Hz)')
    p.add_argument('wav', nargs='?', default=None,
                   help='audio track (.wav); re-synthesized when omitted')
    p.add_argument('-o', '--output', default=None,
                   help='output .mp4 (default: stem of the .tract)')
    p.add_argument('--fps', type=int, default=25,
                   help='video frame rate (default: 25)')
    p.add_argument('--scale', type=int, default=2,
                   help='pixels per SVG unit (default: 2)')
    p.set_defaults(func=cmd_tract_to_mp4)

    # ---- polar-video -----------------------------------------------------
    p = sub.add_parser('polar-video',
                       help='.tract + .polar -> dual MP4 (tract | polar)')
    p.add_argument('tract', help='input .tract file (400 Hz)')
    p.add_argument('--polar', required=True,
                   help='.polar intermediate file (vtl-synth polar-build '
                        'or `vtl-synth run --polar`)')
    p.add_argument('wav', nargs='?', default=None,
                   help='audio track (.wav)')
    p.add_argument('-o', '--output', default=None,
                   help='output .mp4 (default: stem of the .tract)')
    p.add_argument('--fps', type=int, default=25,
                   help='video frame rate (default: 25)')
    p.add_argument('--scale', type=int, default=2,
                   help='pixels per SVG unit (default: 2)')
    p.set_defaults(func=cmd_polar_video)

    # ---- polar-build -----------------------------------------------------
    p = sub.add_parser('polar-build',
                       help='phrase (internal notation) -> .polar file')
    p.add_argument('phrase',
                   help='phrase in the internal notation (e.g. "ba.da.ga")')
    p.add_argument('-o', '--output', required=True, help='output .polar file')
    _add_engine_options(p)
    p.set_defaults(func=cmd_polar_build)

    # ---- plot-tract ------------------------------------------------------
    p = sub.add_parser('plot-tract',
                       help='figure (PNG) of a .tract file (400 Hz)')
    p.add_argument('file', help='input .tract file')
    p.add_argument('-o', '--output', default=None,
                   help='output figure (default: stem of the .tract, .png)')
    p.add_argument('--which', default='tract', choices=['tract', 'glottis', 'all'],
                   help="parameter blocks to plot (default: 'tract')")
    p.add_argument('--params', nargs='+', default=None, metavar='NAME',
                   help='restrict the tract block, e.g. --params JX JA TTX TTY')
    p.add_argument('--ranges', action='store_true',
                   help='also print the min/max/mean table (as inspect --ranges)')
    p.set_defaults(func=cmd_plot_tract)

    # ---- inspect ---------------------------------------------------------
    p = sub.add_parser('inspect', help='summarize a .tract file')
    p.add_argument('file', help='input .tract file')
    p.add_argument('--states', type=int, default=0, metavar='N',
                   help='print the first and last N tract states')
    p.add_argument('--ranges', action='store_true',
                   help='print min/max/mean per tract parameter')
    p.set_defaults(func=cmd_inspect)

    # ---- global options (before the subcommand on the command line) ----
    ap.add_argument('--debug', action='store_true',
                    help="show the full traceback on error")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        import traceback
        if getattr(args, 'debug', False) or '--debug' in (sys.argv or []):
            traceback.print_exc()
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
