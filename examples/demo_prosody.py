# -*- coding: utf-8 -*-
"""Expressive prosody demo: before/after per language (v1.0.8).

    python examples/demo_prosody.py            # the six languages
    python examples/demo_prosody.py --lang fr  # a single one

For each language, synthesizes into ``out_demo_prosody/``:

  * ``<lang>_mono.wav`` / ``<lang>_expr.wav``   — demo sentence (the
    orthographic equivalents of the ``out_demo/`` sentences),
    monotone/expressive pair;
  * ``<lang>_long_mono.wav`` / ``<lang>_long_expr.wav`` — a long
    sentence WITHOUT punctuation: the monotone version is one
    uninterrupted syllabic chain, the expressive one breathes at the
    syntactic boundaries.

and prints the objective measurements: number of word chains >
max_chain_words (before/after), F0 dynamics (standard deviation in
semitones), sustained pitch bumps (>+5 % of the local base),
smoothness (max jump per voiced frame), total duration.

The language is activated via ``setup_lang.py setlang`` (the LANG
SECTION block carries the vowel targets) — the demo drives the
switch itself and launches one subprocess per language.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'out_demo_prosody'

#: demo sentence (orthographic equivalents of out_demo/) and long
#: punctuation-free sentence, per language.
SENTENCES = {
    'en': {
        'demo': 'hello, this is easy for us',
        'long': 'the quick brown fox jumps over the lazy dog '
                'while the cat sleeps',
    },
    'fr': {
        'demo': 'bonjour, je cherche une belle route pour aller '
                'au travail',
        'long': 'je cherche une belle route pour aller au travail '
                'parce que le train ne marche plus',
    },
    'es': {
        'demo': 'hola, buenos días, me llamo Javier y vivo en Madrid',
        'long': 'me llamo Javier y vivo en Madrid con mi familia '
                'desde hace tres años',
    },
    'de': {
        'demo': 'guten Tag, ich suche eine schöne Straße '
                'in Königsberg',
        'long': 'ich suche eine schöne Straße in Königsberg weil '
                'ich die Stadt noch nicht kenne',
    },
    'it': {
        'demo': 'ciao, come stai, la famiglia vive in campagna',
        'long': 'la famiglia vive in campagna con nonna Giulia '
                'vicino al vecchio fiume',
    },
    'pt': {
        'demo': 'bom dia, o menino comeu o pão com manteiga',
        'long': 'o menino comeu o pão com manteiga que a mãe '
                'tinha preparado ontem',
    },
}


def _chains_over(text: str, lang: str, max_chain: int) -> int:
    """Number of coarticulated word chains longer than max_chain words.

    max_chain=10**6 (no breathing): every comma-free part is ONE
    single chain = the "before" state of the monotone g2p;
    max_chain=5: the "after" state (breath groups).
    """
    from vtl_synth.utils.chunking import chunk_sentence, split_sentences
    n = 0
    for sentence in split_sentences(text):
        for part in chunk_sentence(sentence, lang, max_chain=max_chain):
            for block in part:
                if len(block) > min(max_chain, 5):
                    n += 1
    return n


def run_language(lang: str) -> None:
    from vtl_synth import Pipeline
    from vtl_synth.core.constants import ACTIVE_LANG
    if ACTIVE_LANG != lang:
        raise SystemExit(
            f'active LANG SECTION = {ACTIVE_LANG!r}, requested = {lang!r}; '
            f'run via "python setup_lang.py setlang {lang}"')
    OUT.mkdir(exist_ok=True)
    print(f'=== {lang} ===')
    for kind in ('demo', 'long'):
        text = SENTENCES[lang][kind]
        for expressive in (False, True):
            tag = 'expr' if expressive else 'mono'
            label = f'{lang}_{kind}_{tag}'
            pipe = Pipeline(lang=lang, expressive=expressive)
            result = pipe.text_to_wav(
                text, output_dir=str(OUT), label=label)
            # before: chains without breathing; after: with the hard
            # limit of the expressive profile
            limit = 5 if expressive else 10 ** 6
            n_over = _chains_over(text, lang, limit)
            print(f'  {label:<18s} dur={result.duration_s:5.2f}s '
                  f'chains>5words={n_over} '
                  f'{"BREATHES" if expressive else "one-block"}')


def _f0_summary() -> None:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from f0_report import report
    print()
    print(f"{'file':<26s} {'dyn ST':>7s} {'peaks':>6s} "
          f"{'maxjump':>8s} {'range Hz':>16s}")
    for p in sorted(OUT.glob('*.tract')):
        r = report(str(p))
        print(f"{p.stem:<26s} {r['std_st']:7.2f} {r['n_peaks']:6d} "
              f"{r['max_jump']:8.2f} "
              f"{r['f0_min']:6.1f}-{r['f0_max']:6.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lang', choices=sorted(SENTENCES), default=None,
                    help='worker: synthesize ONE language (the LANG '
                         'SECTION block must already be active)')
    ap.add_argument('--summary-only', action='store_true',
                    help='print only the F0 table')
    args = ap.parse_args()

    if args.summary_only:
        _f0_summary()
        return

    if args.lang:
        # single-shot worker: the language is already active (switched
        # by the parent process) — synthesize and return
        run_language(args.lang)
        return

    for lang in sorted(SENTENCES):
        # switch the LANG SECTION block (per-language vowel targets)
        # then a subprocess: constants.py must be re-imported for the
        # section to take effect
        subprocess.run([sys.executable, str(ROOT / 'setup_lang.py'),
                        'setlang', lang], check=True,
                       cwd=str(ROOT))
        subprocess.run([sys.executable, str(Path(__file__)),
                        '--lang', lang], check=True, cwd=str(ROOT))
    _f0_summary()


if __name__ == '__main__':
    main()
