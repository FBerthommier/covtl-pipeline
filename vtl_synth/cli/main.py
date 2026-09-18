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
    g.add_argument('--tcons', type=float, default=100.0, metavar='MS',
                   help='consonant duration in ms (default: 100)')
    g.add_argument('--tvoy', type=float, default=80.0, metavar='MS',
                   help='vowel duration in ms (default: 80)')
    g.add_argument('--tpause', type=float, default=200.0, metavar='MS',
                   help='short inter-word pause in ms (default: 200)')
    g.add_argument('--tpause-long', type=float, default=320.0, metavar='MS',
                   help='long (end of sentence) pause in ms (default: 320)')
    g.add_argument('-f0', '--f0', type=float, default=102.216,
                   help='fundamental frequency in Hz (default: 102.216, JD3)')
    g.add_argument('-s', '--speaker', default='JD3',
                   help='speaker name (default: JD3)')
    g.add_argument('--no-ortho', action='store_true',
                   help='disable the orthogonal branch')
    g.add_argument('--engine', default='syl', choices=['syl', 'legacy'],
                   help="trajectory engine (default: 'syl')")


def _make_pipeline(args: argparse.Namespace):
    from vtl_synth import Pipeline
    return Pipeline(
        f0_hz=args.f0,
        speaker=args.speaker,
        engine=args.engine,
        use_orthogonal=not args.no_ortho,
        t_cons_ms=args.tcons,
        t_voy_ms=args.tvoy,
        pause_short_ms=args.tpause,
        pause_long_ms=args.tpause_long,
    )


# ==========================================================================
# Subcommands
# ==========================================================================

def cmd_run(args: argparse.Namespace) -> int:
    pipe = _make_pipeline(args)
    result = pipe.run(args.text, output_dir=args.output_dir,
                      use_g2p=not args.phonetic, video=not args.no_video,
                      fps=args.fps, scale=args.scale, label=args.label)
    print()
    print('=' * 60)
    print('SUCCESS')
    print(f'  SAMPA     : {result.sampa}')
    print(f'  phrases   : {len(result.phrases)}')
    print(f'  tract     : {result.tract_path} '
          f'({result.n_frames} frames @400 Hz)')
    print(f'  wav       : {result.wav_path} ({result.duration_s:.2f} s)')
    if result.mp4_path is not None:
        print(f'  mp4       : {result.mp4_path}')
    print('=' * 60)
    return 0


def cmd_text_to_wav(args: argparse.Namespace) -> int:
    pipe = _make_pipeline(args)
    result = pipe.text_to_wav(args.text, output_dir=args.output_dir,
                              use_g2p=not args.phonetic, label=args.label)
    print()
    print(f'SUCCESS: {result.wav_path} ({result.duration_s:.2f} s)')
    return 0


def cmd_tract_to_mp4(args: argparse.Namespace) -> int:
    from vtl_synth import Pipeline
    Pipeline.tract_to_mp4(args.tract, args.wav, out_path=args.output,
                          fps=args.fps, scale=args.scale,
                          work_dir=Path(args.output).parent / 'temp_video')
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
