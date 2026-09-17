# -*- coding: utf-8 -*-
"""Démo prosodie expressive : avant/après par langue (v1.0.8).

    python examples/demo_prosody.py            # les 6 langues
    python examples/demo_prosody.py --lang fr  # une seule

Pour chaque langue, synthétise dans ``out_demo_prosody/`` :

  * ``<lang>_mono.wav`` / ``<lang>_expr.wav``   — phrase de démo
    (l'équivalent orthographique des phrases de ``out_demo/``),
    paire monotone/expressive ;
  * ``<lang>_long_mono.wav`` / ``<lang>_long_expr.wav`` — phrase
    longue SANS ponctuation : la version monotone est une seule
    chaîne syllabique ininterrompue, l'expressive respire aux
    frontières syntaxiques.

et affiche les mesures objectives : nombre de chaînes de mots >
max_chain_words (avant/après), dynamique F0 (écart-type en
demi-tons), bosses de hauteur soutenues (>+5 % de la base locale),
douceur (saut max/frame voisée), durée totale.

La langue est activée via ``setup_lang.py setlang`` (le bloc LANG
SECTION porte les cibles vocaliques) — la démo pilote elle-même la
bascule et lance un sous-processus par langue.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'out_demo_prosody'

#: phrase de démo (équivalents orthographiques d'out_demo/) et phrase
#: longue sans ponctuation, par langue.
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
    """Nombre de chaînes de mots coarticulés > max_chain mots.

    max_chain=10**6 (sans respiration) : chaque partie sans virgule
    est UNE seule chaîne = l'état « avant » du g2p monotone ;
    max_chain=5 : l'état « après » (groupes de souffle).
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
            f'LANG SECTION active = {ACTIVE_LANG!r}, demande = {lang!r} ; '
            f'lancer via "python setup_lang.py setlang {lang}"')
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
            # avant : chaînes sans respiration ; après : avec la
            # limite dure du profil expressif
            limit = 5 if expressive else 10 ** 6
            n_over = _chains_over(text, lang, limit)
            print(f'  {label:<18s} dur={result.duration_s:5.2f}s '
                  f'chaines>5mots={n_over} '
                  f'{"RESPIRE" if expressive else "monobloc"}')


def _f0_summary() -> None:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from f0_report import report
    print()
    print(f"{'fichier':<26s} {'dyn ST':>7s} {'peaks':>6s} "
          f"{'maxjump':>8s} {'range Hz':>16s}")
    for p in sorted(OUT.glob('*.tract')):
        r = report(str(p))
        print(f"{p.stem:<26s} {r['std_st']:7.2f} {r['n_peaks']:6d} "
              f"{r['max_jump']:8.2f} "
              f"{r['f0_min']:6.1f}-{r['f0_max']:6.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lang', choices=sorted(SENTENCES), default=None,
                    help='worker : synthétiser UNE langue (le bloc LANG '
                         'SECTION doit déjà être actif)')
    ap.add_argument('--summary-only', action='store_true',
                    help='afficher seulement le tableau F0')
    args = ap.parse_args()

    if args.summary_only:
        _f0_summary()
        return

    if args.lang:
        # worker single-shot : la langue est déjà active (bascule par
        # le processus parent) — on synthétise et on rend la main
        run_language(args.lang)
        return

    for lang in sorted(SENTENCES):
        # bascule du bloc LANG SECTION (cibles vocaliques de la
        # langue) puis sous-processus : constants.py doit être
        # réimporté pour que la section prenne effet
        subprocess.run([sys.executable, str(ROOT / 'setup_lang.py'),
                        'setlang', lang], check=True,
                       cwd=str(ROOT))
        subprocess.run([sys.executable, str(Path(__file__)),
                        '--lang', lang], check=True, cwd=str(ROOT))
    _f0_summary()


if __name__ == '__main__':
    main()
