# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_pt.py
=========
European Portuguese grapheme-to-phoneme: orthographic text → engine
SAMPA. Same architecture as ``g2p_fr.py`` (v2):

  external lexicon (absolute priority) → exceptions dictionary →
  contextual preprocessing (nasalization, voiced s/z, finals) →
  rule table (longest pattern first).

Lexicon: ``vtl_synth/data/pt_lexicon.tsv`` (Wikipron
``por_latn_po_broad_filtered.tsv`` — EUROPEAN Portuguese;
variable: ``$COVTL_PT_LEXICON``), loaded by
:mod:`vtl_synth.utils.lexicon_loader`.

Graphemic coverage: ã/õ, ão/ães/õe/ões, nasals in V+(m|n)+C,
ç /s/, nh /ɲ/, lh /ʎ/, ch /ʃ/, ss, final s /ʃ/, final z /ʃ/, g+e/i
/ʒ/, qu/gu, finals -o → /u/ and -e → /ɐ/, diphthongs as glides.

Nasal convention (engine): nasal vowel = base + '~' (notation.py;
syltraj strips the '~' before lookup) — e.g. cão → ``k @~ w``. In
European Portuguese, /ɐ̃/ (ã, nasal am/an, em/en) → ``@~``, base
``@`` (ɐ) which has its own calibrated target (language_vowel_sets
'pt').

Documented approximations:
  * rhotics (ɾ, r, ʁ) → single key ``R`` (the engine's only rhotic);
  * final velar l (-al, -el, -ol: 'sol') → plain ``l``;
  * NON-final atonic e/o not reduced (European: e → [ɨ], o → [u]
    depending on context; the lexicon carries the exact reductions);
  * no /b/ vs /β/ distinction (engine without an approximant);
  * residual "qu" (not covered by que/qui/qua/quo, e.g.
    "quente") -> /k/ (CORRECTIONS v2.1, g2p-pt leak — before:
    a raw 'q' leaked into the SAMPA output).
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

_V = 'aeiouáàâãéêíóôõú'   # orthographic vowels


def _normalize_input(text: str) -> str:
    """NFC + typographic apostrophes normalized."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (frequent words irregular for the rules)
# ===========================================================================

_PT_EXCEPTIONS: dict = {
    # function words (full vowels, correct nasals)
    'e': 'e', 'é': 'e', 'ou': 'o w', 'não': 'n @~ w',
    'são': 's @~ w', 'nós': 'n O S', 'mais': 'm a j S',
    'mas': 'm a S', 'muito': 'm w i t u',
    'por': 'p u R', 'para': 'p a R a', 'com': 'k o~',
    'sem': 's e~ j', 'ser': 's e R', 'estar': 'S t a R',
    'ter': 't e R', 'ir': 'i R', 'ver': 'v e R', 'dar': 'd a R',
    'quando': 'k w @~ d u',
    'porque': 'p u R k e', 'também': 't @~ b e~ j',
    'agora': 'a g O R a', 'ainda': 'a j d a',
    # x = /ks/ (default /ʃ/)
    'táxi': 't a k s i', 'tóxico': 't O k s i k u',
    'axioma': 'a k s j o~ m @',
}


# ===========================================================================
# Prétraitement contextuel
# ===========================================================================

# Nasalization V + (m|n) + C/final. The nh/lh digraphs are protected
# (n before h is not a nasal; neither is l before h). The m/n drops,
# the vowel carries the tilde: a/e → @~ (European ɐ̃), i → i~, o → o~,
# u → u~. Placeholders: AN→@~, IN→i~, ON→o~, UN→u~ (translated by
# the 'AN' etc. rules).
_NASAL_MAP = {'a': 'AN', 'e': 'AN', 'i': 'IN', 'o': 'ON', 'u': 'UN'}


def _preprocess(word: str) -> str:
    """Contextual normalizations of the Portuguese orthography.

    1. Final nasals -am/-em/-ém/-êm/-im/-om/-um (nasal diphthongs:
       /ɐ̃w̃/, /ɐ̃j̃~ẽj̃/, /ĩ/, /õ/, /ũ/) → placeholders.
    2. Internal nasalization V + m/n + C (the n of nh is protected;
       nn/mm geminates protected).
    3. Voiced s: intervocalic or before a voiced consonant → /z/;
       final s/z → /ʃ/ (European). Placeholders SZ / SF.
    4. Atonic finals: -o → u, -e → @ — EXCEPT after ã/õ (ão, ãe, õe…)
       and after u (que, gue: the e of these digraphs is not atonic).
    """
    # --- 1. final nasals -------------------------------------------
    word = re.sub(r'am$', 'AMF', word)
    word = re.sub(r'(em|ém|êm)$', 'EMF', word)
    word = re.sub(r'im$', 'IMF', word)
    word = re.sub(r'om$', 'OMF', word)
    word = re.sub(r'um$', 'UMF', word)

    # --- 2. internal nasalization V + m/n + (C or end) ------------------
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
                out[-1] = _NASAL_MAP[prev]      # nasalized vowel
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
# Rule table (longest pattern first)
# ===========================================================================

_PT_RULES: list = [
    # --- preprocessing placeholders ---
    ('NHDIG', 'J'), ('LHDIG', 'L'),
    ('AN', '@~'), ('IN', 'i~'), ('ON', 'o~'), ('UN', 'u~'),
    ('SZ', 'z'), ('SF', 'S'),
    ('OFIN', 'u'), ('EFIN', '@'),
    ('AMF', '@~ w'), ('EMF', 'e~ j'), ('IMF', 'i~'),
    ('OMF', 'o~'), ('UMF', 'u~'),
    # --- orthographic nasals (tilde) ---
    ('ões', 'o~ j S'), ('ães', '@~ j S'), ('õe', 'o~ j'),
    ('ãe', '@~ j'),
    ('ão', '@~ w'), ('ã', '@~'), ('õ', 'o~'),
    # --- contextual spellings c/g + vowel --------------------------
    ('gue', 'g e'), ('gui', 'g i'),
    ('que', 'k e'), ('qui', 'k i'),
    ('ge', 'Z e'), ('gi', 'Z i'),
    ('qua', 'k w a'), ('quo', 'k w o'),
    # CORRECTIONS v2.1 (g2p-pt leak, 2026-10-23): "qu" fallback
    # for spellings not covered by que/qui/qua/quo (qu + nasalized
    # vowel: "quente" -> placeholder AN, hence a bare "qu";
    # quê, quá…) — a raw 'q' leaked into the SAMPA output (key
    # absent from the engine inventory, silently dropped).
    ('qu', 'k'),
    ('gua', 'g w a'), ('guo', 'g w o'),
    ('ç', 's'), ('ch', 'S'), ('ss', 's'),
    ('lh', 'L'), ('nh', 'J'),
    ('rr', 'R'),
    # --- accented hiatus (full accented vowel) --------------------
    ('ía', 'i a'), ('úa', 'u a'), ('aí', 'a i'), ('eí', 'e i'),
    ('oí', 'o i'), ('aú', 'a u'), ('oú', 'o u'),
    # --- FALLING diphthongs only (the rising sequences of Portuguese
    #     orthography are mostly hiatus: família, dia, ruído — the
    #     true rising ones go through qua/gua/lexicon) ----
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'), ('ou', 'o w'),
    # --- accents → vowels ---------------------------------------------
    ('á', 'a'), ('à', 'a'), ('â', '@'), ('é', 'e'), ('ê', 'e'),
    ('í', 'i'), ('ó', 'o'), ('ô', 'o'),
    # --- lettres simples -------------------------------------------------
    ('g', 'g'), ('j', 'Z'), ('x', 'S'), ('r', 'R'),
    ('h', ''),             # mute h (hoje, hospital…)
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('c', 'k'), ('d', 'd'), ('f', 'f'), ('l', 'l'),
    ('m', 'm'), ('n', 'n'), ('p', 'p'), ('s', 's'), ('t', 't'),
    ('v', 'v'), ('z', 'z'),
]

_PT_RULES_SORTED: list = sorted(_PT_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Word → keys conversion
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Converts a Portuguese word to a list of engine SAMPA keys."""
    word_lc = word.lower().replace('’', "'")

    # (0) external lexicon — absolute priority
    lex_keys = lexicon_for('pt').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _PT_EXCEPTIONS:
        return _PT_EXCEPTIONS[word_lc].split()

    # (b) preprocessing + rule table
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
