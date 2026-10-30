# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_es.py
=========
Graphème-phonème espagnol (castillan) : texte orthographique → SAMPA
moteur. Même architecture que ``g2p_fr.py`` (v2) :

  lexique externe (priorité absolue) → dictionnaire d'exceptions →
  prétraitement contextuel → table de règles (motif le plus long
  d'abord).

Lexique : ``vtl_synth/data/es_lexicon.tsv`` (Wikipron
``spa_latn_ca_broad_filtered.tsv`` — castillan AVEC distinción : c/z
devant e,i → /θ/ ; variable : ``$COVTL_ES_LEXICON``), chargé par le
module commun :mod:`vtl_synth.utils.lexicon_loader`.

Conventions phonétiques (approximations documentées) :
  * /ɾ/ et /r/ (vibrante simple et roulée) → clé unique ``R`` : le
    moteur n'a qu'une rhotique (uvulaire, cf. notation.py) ;
  * /x/ (j, g+e/i) → ``X`` (fricative uvulaire du moteur) ;
  * /ʝ/ (ll, y) → ``j`` (approximante palatale) — yeísmo ;
  * h TOUJOURS muet ; v → /b/ (clé ``b``) ;
  * voyelles : système à 5 phonèmes /a e i o u/ — les cibles ``E``/``O``
    de l'inventaire (language_vowel_sets) ne sont émises par aucune
    règle (elles servent de références de calibrage) ;
  * accents orthographiques = hiatus (tía, baúl) : les règles « à +
    voyelle atone » ne s'appliquent qu'aux voyelles non accentuées.

Limitations assumées (mots hors lexique) : pas de resyllabification,
pas de distinction /b/ occlusif vs /β/ spirant (Wikipron les transcrit
β mais l'inventaire moteur n'a pas d'approximante labiale).
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
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def _normalize_input(text: str) -> str:
    """NFC + ponctuationCurly apostrophes normalisés."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (mots fréquents irréguliers pour les règles)
# ===========================================================================

_ES_EXCEPTIONS: dict = {
    # conjonction / mots-outils
    'y': 'i',
    'más': 'm a s',
    'mí': 'm i',
    'sí': 's i',
    'sé': 's e',
    'en': 'e n',          # variante 'em' du Wiktionnaire écartée
    # x exotiques (x = /s/ ou /x/, pas /ks/)
    'méxico': 'X e k o s',
    'méjico': 'X e k o s',
    'mexicana': 'm e X i k a n a',
    'xavier': 'S a b j e R',
    # graphies rares
    'whisky': 'w i s k i',
}


# ===========================================================================
# Table de règles (motif le plus long d'abord)
# ===========================================================================

_ES_RULES: list = [
    # --- trigraphes et contextes longs ---
    ('güe', 'g w e'), ('güi', 'g w i'),
    ('gue', 'g e'), ('gui', 'g i'),
    ('que', 'k e'), ('qui', 'k i'),
    ('quie', 'k j e'), ('quio', 'k j o'),
    ('gia', 'X j a'), ('gio', 'X j o'), ('giu', 'X j u'),
    ('cia', 'T j a'), ('cio', 'T j o'), ('ciu', 'T j u'),
    ('gua', 'g w a'), ('guo', 'g w o'),
    ('hia', 'j a'), ('hie', 'j e'), ('hio', 'j o'),
    ('hua', 'w a'), ('hue', 'w e'), ('huo', 'w o'),
    ('cc',  'k T'),
    # --- digraphes ---
    ('ch', 'tS'),
    ('ll', 'j'),
    ('rr', 'R'),
    ('qu', 'k'),
    ('ge', 'X e'), ('gi', 'X i'),
    ('je', 'X e'), ('ji', 'X i'),
    ('ce', 'T e'), ('ci', 'T i'),
    ('ñ', 'J'),
    # --- hiatus accentués (la voyelle accentuée reste pleine) ---
    ('ía', 'i a'), ('úa', 'u a'), ('aí', 'a i'), ('eí', 'e i'),
    ('oí', 'o i'), ('aú', 'a u'), ('oú', 'o u'), ('úe', 'u e'),
    # --- diphtongues (i/u atones devant voyelle → glide) ---
    ('ia', 'j a'), ('ie', 'j e'), ('io', 'j o'), ('iu', 'j u'),
    ('ua', 'w a'), ('ue', 'w e'), ('uo', 'w o'), ('ui', 'w i'),
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'),
    ('ay', 'a j'), ('ey', 'e j'), ('oy', 'o j'), ('uy', 'w i'),
    # --- accents → voyelle de base ---
    ('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'),
    ('ü', 'u'),
    # --- lettres simples ---
    ('h', ''),            # h muet
    ('j', 'X'),           # jota /x/ (ja, jo, ju ; je/ji pris ci-dessus)
    ('v', 'b'),           # v → /b/ (pas d'approximante dans le moteur)
    ('x', 'k s'),
    ('z', 'T'),           # distinción castillane
    ('y', 'j'),
    ('r', 'R'),           # rhotique unique du moteur
    ('w', 'w'),           # loanwords (whisky…)
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('c', 'k'), ('d', 'd'), ('f', 'f'), ('g', 'g'),
    ('k', 'k'), ('l', 'l'), ('m', 'm'), ('n', 'n'), ('p', 'p'),
    ('s', 's'), ('t', 't'),
]

_ES_RULES_SORTED: list = sorted(_ES_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Conversion mot → clés
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Convertit un mot espagnol en liste de clés SAMPA moteur."""
    word_lc = word.lower().replace('’', "'")

    # (0) lexique externe — priorité absolue
    lex_keys = lexicon_for('es').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _ES_EXCEPTIONS:
        return _ES_EXCEPTIONS[word_lc].split()

    # (b) table de règles (motif le plus long d'abord)
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        for pat, repl in _ES_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:
                    keys.extend(repl.split())
                i += len(pat)
                break
        else:
            warnings.append(
                f"ES g2p: unknown character {word_lc[i]!r} in word {word!r}"
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


def text_to_sampa_es(text: str, warnings: list = None, **kwargs) -> str:
    """Convertit un texte espagnol en séquence SAMPA moteur.

    Même contrat que ``g2p.text_to_sampa`` (anglais) et
    ``text_to_sampa_fr`` : ponctuation de phrase → ``|``, virgule →
    pause courte, mots adjacents reliés par ``.`` (coarticulation).
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
        print(f'[g2p-es] {w}')
    return ' | '.join(out_phrases)


__all__ = ['text_to_sampa_es', '_ES_EXCEPTIONS', '_ES_RULES']
