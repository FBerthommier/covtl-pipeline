# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_de.py
=========
Graphème-phonème allemand : texte orthographique → SAMPA moteur.
Même architecture que ``g2p_fr.py`` (v2) :

  lexique externe (priorité absolue) → dictionnaire d'exceptions →
  prétraitement contextuel (désvoisement final, ach/ich-laut,
  s sonore, réductions des finales non accentuées) → table de règles.

Lexique : ``vtl_synth/data/de_lexicon.tsv`` (Wikipron
``deu_latn_broad_filtered.tsv`` ; variable : ``$COVTL_DE_LEXICON``),
chargé par :mod:`vtl_synth.utils.lexicon_loader`.

Couverture graphémique (cf. cahier des charges) : ä ö ü ß, sch, ch
(ach/ich selon le contexte vocalique), ei, eu/äu, ie, au, h muet
(allongeant après voyelle), en plus du désvoisement final
(Auslautverhärtung), st-/sp- initiaux /ʃt ʃp/, s intervocalique /z/,
-z- /ts/ et des finales -er/-en/-el/-e réduites vers @.

Approximations documentées :
  * ö/ü toujours tendues (2/y) : la règle n'a pas de test de longueur
    (le lexique donne les réalisations brèves correctes 9/Y) ;
  * ʁ → ``R`` (seule rhotique du moteur) ; ɐ → ``@`` ;
  * pas de coup de glotte (ʔ absent de l'inventaire) ;
  * pas de réduction e → ə en dehors des finales -e/-er/-en/-el ;
  * les consonnes doubles sont émises deux fois (géminées).

Le prétraitement utilise des PLACEHOLDRES MAJUSCULES (ACH, ICH, TSCH,
SCH, SDT, SDP, SZ, SCHWA, ERFIN, ENFIN, ELFIN, IQ) : le mot est
mis en minuscules avant, donc ils ne peuvent pas entrer en collision
avec l'orthographie, et la table de règles les traduit vers les clés.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

from vtl_synth.core.phonemes import keys_to_connected
from vtl_synth.utils.lexicon_loader import lexicon_for


# ===========================================================================
# Tokenisation (miroir de g2p_fr.py)
# ===========================================================================

_SENT_PUNCT_RE = re.compile(r'[.!?;:]+\s*')
_COMMA_RE = re.compile(r'\s*[,–—]\s*')
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

_V = 'aeiouäöü'          # voyelles orthographiques


def _normalize_input(text: str) -> str:
    """NFC + apostrophes typographiques normalisés."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (mots fréquents irréguliers pour les règles)
# ===========================================================================

_DE_EXCEPTIONS: dict = {
    # mots-outils (voyelles pleines, pas de réduction finale)
    'der': 'd e R', 'die': 'd i', 'das': 'd a s', 'den': 'd e n',
    'dem': 'd e m', 'des': 'd e s', 'ein': 'a j n', 'eine': 'a j n @',
    'einen': 'a j n @ n', 'und': 'U n t', 'ist': 'I s t',
    'sind': 'z I n t', 'war': 'v a R', 'waren': 'v a R @ n',
    'von': 'f O n', 'mit': 'm I t', 'auf': 'a w f', 'aus': 'a w s',
    'bei': 'b a j', 'für': 'f y R', 'wie': 'v i', 'wo': 'v o',
    'was': 'v a s', 'wer': 'v e R', 'sehr': 'z e R',
    'ja': 'j a', 'nein': 'n a j n', 'nicht': 'n I C t',
    'noch': 'n O X', 'schon': 'S o n', 'auch': 'a w X',
    'wieder': 'v i d e R', 'über': 'y b e R', 'unter': 'U n t e R',
}


# ===========================================================================
# Prétraitement contextuel
# ===========================================================================

def _preprocess(word: str) -> str:
    """Normalisations contextuelles de l'orthographie allemande.

    Ordre : -ig final /ɪç/ → désvoisement final → affriquées/fricatives
    complexes en placeholders → ach/ich-laut selon la voyelle
    précédente → st/sp initiaux → s sonore → finales réduites.
    """
    # 1. -ig final → /ɪç/ (König, zufrieden…) — AVANT le désvoisement
    #    (sinon ig devient ik et le ich-laut est perdu)
    word = re.sub(r'ig$', 'IQ', word)
    # 2. Auslautverhärtung : b/d/g de fin de mot → p/t/k
    if len(word) > 2 and word[-1] in 'bdg':
        word = word[:-1] + {'b': 'p', 'd': 't', 'g': 'k'}[word[-1]]
    # 3. affriquées / groupes complexes en placeholders (tsch AVANT
    #    sch, chs AVANT ch)
    word = word.replace('tsch', 'TSCH').replace('sch', 'SCH')
    word = word.replace('chs', 'CHS')
    # 4. ach-laut (/x/) après a/o/u, sinon ich-laut (/ç/)
    word = re.sub(r'(?<=[aou])ch', 'ACH', word)
    word = word.replace('ch', 'ICH')
    # 5. st-/sp- INITIAUX seulement → /ʃt ʃp/
    word = re.sub(r'^st', 'SDT', word)
    word = re.sub(r'^sp', 'SDP', word)
    # 6. s sonore : initial devant voyelle, ou intervocalique
    word = re.sub(r'^s(?=[' + _V + r'])', 'SZ', word)
    word = re.sub(r'(?<=[' + _V + r'])s(?=[' + _V + r'])', 'SZ', word)
    # 7. finales non accentuées réduites (er > en > el > e, du plus
    #    long au plus court)
    word = re.sub(r'er$', 'ERFIN', word)
    word = re.sub(r'en$', 'ENFIN', word)
    word = re.sub(r'el$', 'ELFIN', word)
    word = re.sub(r'e$', 'SCHWA', word)
    return word


# ===========================================================================
# Table de règles (motif le plus long d'abord)
# ===========================================================================

_DE_RULES: list = [
    # --- placeholders du prétraitement ---
    ('TSCH', 'tS'), ('SCH', 'S'), ('ACH', 'X'), ('ICH', 'C'),
    ('CHS', 'k s'),
    ('SDT', 'S t'), ('SDP', 'S p'), ('SZ', 'z'),
    ('ERFIN', '@'), ('ENFIN', '@ n'), ('ELFIN', '@ l'),
    ('SCHWA', '@'), ('IQ', 'i C'),
    # --- groupes consonantiques ---
    ('tz', 't s'), ('ts', 't s'), ('ck', 'k'), ('pf', 'p f'),
    ('ng', 'N'), ('nk', 'N k'), ('qu', 'k v'),
    ('x', 'k s'),
    # --- diphtongues ---
    ('ei', 'a j'), ('ai', 'a j'), ('ey', 'a j'), ('ay', 'a j'),
    ('eu', 'O j'), ('äu', 'O j'), ('au', 'a w'), ('ie', 'i'),
    # --- voyelles longues écrites (h muet allongeant) ---
    ('ah', 'a'), ('eh', 'e'), ('ih', 'i'), ('oh', 'o'), ('uh', 'u'),
    ('äh', 'E'), ('öh', '2'), ('üh', 'y'),
    ('ee', 'e'), ('oo', 'o'),
    # --- umlauts et lettres simples ---
    ('ä', 'E'), ('ö', '2'), ('ü', 'y'), ('ß', 's'), ('ss', 's'),
    ('h', 'h'),           # h initial / après consonante
    ('v', 'f'), ('w', 'v'), ('j', 'j'), ('z', 't s'), ('c', 'k'),
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('d', 'd'), ('f', 'f'), ('g', 'g'), ('k', 'k'),
    ('l', 'l'), ('m', 'm'), ('n', 'n'), ('p', 'p'), ('r', 'R'),
    ('s', 's'), ('t', 't'),
]

_DE_RULES_SORTED: list = sorted(_DE_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Conversion mot → clés
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Convertit un mot allemand en liste de clés SAMPA moteur."""
    word_lc = word.lower().replace('’', "'")

    # (0) lexique externe — priorité absolue
    lex_keys = lexicon_for('de').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _DE_EXCEPTIONS:
        return _DE_EXCEPTIONS[word_lc].split()

    # (b) prétraitement + table de règles
    word_lc = _preprocess(word_lc)
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        for pat, repl in _DE_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:
                    keys.extend(repl.split())
                i += len(pat)
                break
        else:
            warnings.append(
                f"DE g2p: unknown character {word_lc[i]!r} in word {word!r}"
            )
            keys.append(word_lc[i])
            i += 1
    return [k for k in keys if k]


def _phrase_to_sampa(phrase: str, warnings: list) -> str:
    """Convertit un syntagme (mots seuls) en SAMPA."""
    words = _WORD_RE.findall(phrase)
    if not words:
        return ''
    tokens: List[str] = []
    for w in words:
        keys = _word_to_keys(w, warnings)
        if not keys:
            continue
        tokens.append(keys_to_connected(keys, cluster_onset=True))
    return '.'.join(tokens)


def text_to_sampa_de(text: str, warnings: list = None, **kwargs) -> str:
    """Convertit un texte allemand en séquence SAMPA moteur.

    Même contrat que ``g2p.text_to_sampa`` (anglais) : ponctuation de
    phrase → ``|``, virgule → pause courte, mots adjacents reliés
    par ``.`` (coarticulation).
    """
    own = warnings is None
    if own:
        warnings = []

    text = _normalize_input(text)

    phrases = _SENT_PUNCT_RE.split(text)
    out_phrases: List[str] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        parts = _COMMA_RE.split(phrase)
        sampa_parts = [_phrase_to_sampa(p, warnings) for p in parts]
        sampa_parts = [s for s in sampa_parts if s]
        if sampa_parts:
            out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p-de] {w}')
    return ' | '.join(out_phrases)


__all__ = ['text_to_sampa_de', '_DE_EXCEPTIONS', '_DE_RULES']
