# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_pt.py
=========
Graphème-phonème portugais (européen) : texte orthographique → SAMPA
moteur. Même architecture que ``g2p_fr.py`` (v2) :

  lexique externe (priorité absolue) → dictionnaire d'exceptions →
  prétraitement contextuel (nasalisation, s/z sonores, finales) →
  table de règles (motif le plus long d'abord).

Lexique : ``vtl_synth/data/pt_lexicon.tsv`` (Wikipron
``por_latn_po_broad_filtered.tsv`` — portugais EUROPÉEN ; variable :
``$COVTL_PT_LEXICON``), chargé par :mod:`vtl_synth.utils.lexicon_loader`.

Couverture graphémique : ã/õ, ão/ães/õe/ões, nasales en V+(m|n)+C,
ç /s/, nh /ɲ/, lh /ʎ/, ch /ʃ/, ss, s final /ʃ/, z final /ʃ/, g+e/i
/ʒ/, qu/gu, finales -o → /u/ et -e → /ɐ/, diphtongues en glides.

Convention nasale (moteur) : voyelle nasale = base + '~' (notation.py ;
syltraj retire le '~' avant lookup) — ex. cão → ``k @~ w``. En port.
européen, /ɐ̃/ (ã, am/an, em/en nasals) → ``@~``, base ``@`` (ɐ) qui
possède sa propre cible calibrée (language_vowel_sets 'pt').

Approximations documentées :
  * rhotiques (ɾ, r, ʁ) → clé unique ``R`` (seule rhotique du moteur) ;
  * l vélaire final (-al, -el, -ol : 'sol') → ``l`` simple ;
  * e/o atones NON finaux non réduits (européen : e → [ɨ], o → [u]
    selon le contexte ; le lexique porte les réductions exactes) ;
  * pas de distinction /b/ vs /β/ (moteur sans approximante).
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
_WORD_RE = re.compile(r"[A-Za-zÁÀÂÃÇÉÊÍÓÔÕÚáàâãçéêíóôõú]+")

_V = 'aeiouáàâãéêíóôõú'   # voyelles orthographiques


def _normalize_input(text: str) -> str:
    """NFC + apostrophes typographiques normalisés."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (mots fréquents irréguliers pour les règles)
# ===========================================================================

_PT_EXCEPTIONS: dict = {
    # mots-outils (voyelles pleines, nasales correctes)
    'e': 'e', 'é': 'e', 'ou': 'o w', 'não': 'n @~ w',
    'são': 's @~ w', 'nós': 'n O S', 'mais': 'm a j S',
    'mas': 'm a S', 'muito': 'm w i t u',
    'por': 'p u R', 'para': 'p a R a', 'com': 'k o~',
    'sem': 's e~ j', 'ser': 's e R', 'estar': 'S t a R',
    'ter': 't e R', 'ir': 'i R', 'ver': 'v e R', 'dar': 'd a R',
    'quando': 'k w @~ d u',
    'porque': 'p u R k e', 'também': 't @~ b e~ j',
    'agora': 'a g O R a', 'ainda': 'a j d a',
    # x = /ks/ (défaut /ʃ/)
    'táxi': 't a k s i', 'tóxico': 't O k s i k u',
    'axioma': 'a k s j o~ m @',
}


# ===========================================================================
# Prétraitement contextuel
# ===========================================================================

# Nasalisation V + (m|n) + C/final. Les digraphes nh/lh sont protégés
# (n devant h n'est pas un nasal ; l devant h non plus). Le m/n tombe,
# la voyelle porte le tilde : a/e → @~ (ɐ̃ européen), i → i~, o → o~,
# u → u~. Placeholders : AN→@~, IN→i~, ON→o~, UN→u~ (traduits par les
# règles 'AN' etc.).
_NASAL_MAP = {'a': 'AN', 'e': 'AN', 'i': 'IN', 'o': 'ON', 'u': 'UN'}


def _preprocess(word: str) -> str:
    """Normalisations contextuelles de l'orthographie portugaise.

    1. Nasales finales -am/-em/-ém/-êm/-im/-om/-um (diphtongues
       nasales : /ɐ̃w̃/, /ɐ̃j̃~ẽj̃/, /ĩ/, /õ/, /ũ/) → placeholders.
    2. Nasalisation interne V + m/n + C (le n de nh est protégé ;
       géminées nn/mm protégées).
    3. s sonore : intervocalique ou devant consonde sonore → /z/ ;
       s/z finaux → /ʃ/ (européen). Placeholders SZ / SF.
    4. Finales atones : -o → u, -e → @ — SAUF après ã/õ (ão, ãe, õe…)
       et après u (que, gue : le e de ces digraphes n'est pas atone).
    """
    # --- 1. nasales finales -------------------------------------------
    word = re.sub(r'am$', 'AMF', word)
    word = re.sub(r'(em|ém|êm)$', 'EMF', word)
    word = re.sub(r'im$', 'IMF', word)
    word = re.sub(r'om$', 'OMF', word)
    word = re.sub(r'um$', 'UMF', word)

    # --- 2. nasalisation interne V + m/n + (C ou fin) ------------------
    out = []
    i = 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ''
        if ch in 'mn':
            prev = out[-1] if out else ''
            if prev in _NASAL_MAP and (nxt == '' or nxt not in _V) \
                    and not (ch == 'n' and nxt == 'h') \
                    and not (ch == 'm' and nxt == 'm') \
                    and not (ch == 'n' and nxt == 'n'):
                out[-1] = _NASAL_MAP[prev]      # voyelle nasalisée
                i += 1
                continue
        # digraphes protégés : nh → NH, lh → LH
        if ch == 'n' and nxt == 'h':
            out.append('NHDIG'); i += 2; continue
        if ch == 'l' and nxt == 'h':
            out.append('LHDIG'); i += 2; continue
        out.append(ch)
        i += 1
    word = ''.join(out)

    # --- 3. s/z sonores et finaux ------------------------------------
    word = re.sub(r'(?<=[' + _V + r'])s(?=[' + _V + r'])', 'SZ', word)
    word = re.sub(r'(?<=[bfvdgzJ])s(?=[bfvdgJjwlmnR])', 'SZ', word)
    word = re.sub(r's$', 'SF', word)
    word = re.sub(r'z$', 'SF', word)

    # --- 4. finales atones -------------------------------------------
    word = re.sub(r'(?<![ãõ])o$', 'OFIN', word)
    word = re.sub(r'(?<![ãõu])e$', 'EFIN', word)
    return word


# ===========================================================================
# Table de règles (motif le plus long d'abord)
# ===========================================================================

_PT_RULES: list = [
    # --- placeholders du prétraitement ---
    ('NHDIG', 'J'), ('LHDIG', 'L'),
    ('AN', '@~'), ('IN', 'i~'), ('ON', 'o~'), ('UN', 'u~'),
    ('SZ', 'z'), ('SF', 'S'),
    ('OFIN', 'u'), ('EFIN', '@'),
    ('AMF', '@~ w'), ('EMF', 'e~ j'), ('IMF', 'i~'),
    ('OMF', 'o~'), ('UMF', 'u~'),
    # --- nasales orthographiques (tilde) ---
    ('ões', 'o~ j S'), ('ães', '@~ j S'), ('õe', 'o~ j'),
    ('ãe', '@~ j'),
    ('ão', '@~ w'), ('ã', '@~'), ('õ', 'o~'),
    # --- graphies contextuelles c/g + voyelle --------------------------
    ('gue', 'g e'), ('gui', 'g i'),
    ('que', 'k e'), ('qui', 'k i'),
    ('ge', 'Z e'), ('gi', 'Z i'),
    ('qua', 'k w a'), ('quo', 'k w o'),
    ('gua', 'g w a'), ('guo', 'g w o'),
    ('ç', 's'), ('ch', 'S'), ('ss', 's'),
    ('lh', 'L'), ('nh', 'J'),
    ('rr', 'R'),
    # --- hiatus accentués (voyelle accentuée pleine) --------------------
    ('ía', 'i a'), ('úa', 'u a'), ('aí', 'a i'), ('eí', 'e i'),
    ('oí', 'o i'), ('aú', 'a u'), ('oú', 'o u'),
    # --- diphtongues DESCENDANTES uniquement (les montantes de l'écrit
    #     portugais sont majoritairement des hiatus : família, dia,
    #     ruído — les vraies montantes passent par qua/gua/lexique) ----
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'), ('ou', 'o w'),
    # --- accents → voyelles ---------------------------------------------
    ('á', 'a'), ('à', 'a'), ('â', '@'), ('é', 'e'), ('ê', 'e'),
    ('í', 'i'), ('ó', 'o'), ('ô', 'o'),
    # --- lettres simples -------------------------------------------------
    ('g', 'g'), ('j', 'Z'), ('x', 'S'), ('r', 'R'),
    ('h', ''),             # h muet (hoje, hospital…)
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('c', 'k'), ('d', 'd'), ('f', 'f'), ('l', 'l'),
    ('m', 'm'), ('n', 'n'), ('p', 'p'), ('s', 's'), ('t', 't'),
    ('v', 'v'), ('z', 'z'),
]

_PT_RULES_SORTED: list = sorted(_PT_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Conversion mot → clés
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Convertit un mot portugais en liste de clés SAMPA moteur."""
    word_lc = word.lower().replace('’', "'")

    # (0) lexique externe — priorité absolue
    lex_keys = lexicon_for('pt').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _PT_EXCEPTIONS:
        return _PT_EXCEPTIONS[word_lc].split()

    # (b) prétraitement + table de règles
    word_lc = _preprocess(word_lc)
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        for pat, repl in _PT_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:
                    keys.extend(repl.split())
                i += len(pat)
                break
        else:
            warnings.append(
                f"PT g2p: unknown character {word_lc[i]!r} in word {word!r}"
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


def text_to_sampa_pt(text: str, warnings: list = None, **kwargs) -> str:
    """Convertit un texte portugais en séquence SAMPA moteur.

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
        print(f'[g2p-pt] {w}')
    return ' | '.join(out_phrases)


__all__ = ['text_to_sampa_pt', '_PT_EXCEPTIONS', '_PT_RULES']
