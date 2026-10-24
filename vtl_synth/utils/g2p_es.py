# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_es.py
=========
Spanish (Castilian) grapheme-to-phoneme: orthographic text → engine
SAMPA. Same architecture as ``g2p_fr.py`` (v2):

  external lexicon (absolute priority) → exceptions dictionary →
  contextual preprocessing → rule table (longest pattern first).

Lexicon: ``vtl_synth/data/es_lexicon.tsv`` (Wikipron
``spa_latn_ca_broad_filtered.tsv`` — Castilian WITH distinción: c/z
before e,i → /θ/; variable: ``$COVTL_ES_LEXICON``), loaded by the
shared module :mod:`vtl_synth.utils.lexicon_loader`.

Phonetic conventions (documented approximations):
  * /ɾ/ and /r/ (tap and trill) → single key ``R``: the engine
    has only one rhotic (uvular, cf. notation.py);
  * /x/ (j, g+e/i) → ``X`` (the engine's uvular fricative);
  * /ʝ/ (ll, y) → ``j`` (palatal approximant) — yeísmo;
  * h ALWAYS mute; v → /b/ (key ``b``);
  * vowels: 5-phoneme system /a e i o u/ — the ``E``/``O`` targets
    of the inventory (language_vowel_sets) are emitted by no rule
    (they serve as calibration references);
  * orthographic accents = hiatus (tía, baúl): the "unstressed
    vowel + vowel" rules only apply to unaccented vowels.

Known limitations (words outside the lexicon): no resyllabification,
no stop /b/ vs spirant /β/ distinction (Wikipron transcribes them
β but the engine inventory has no labial approximant).
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

from vtl_synth.core.phonemes import keys_to_connected
from vtl_synth.utils.lexicon_loader import lexicon_for


# ===========================================================================
# Tokenization (mirror of g2p_fr.py)
# ===========================================================================

_SENT_PUNCT_RE = re.compile(r'[.!?;:]+\s*')
_COMMA_RE = re.compile(r'\s*[,–—]\s*')
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def _normalize_input(text: str) -> str:
    """NFC + ponctuationCurly apostrophes normalisés."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (frequent words irregular for the rules)
# ===========================================================================

_ES_EXCEPTIONS: dict = {
    # conjunction / function words
    'y': 'i',
    'más': 'm a s',
    'mí': 'm i',
    'sí': 's i',
    'sé': 's e',
    'en': 'e n',          # 'em' Wiktionary variant rejected
    # exotic x (x = /s/ or /x/, not /ks/)
    'méxico': 'X e k o s',
    'méjico': 'X e k o s',
    'mexicana': 'm e X i k a n a',
    'xavier': 'S a b j e R',
    # graphies rares
    'whisky': 'w i s k i',
}


# ===========================================================================
# Rule table (longest pattern first)
# ===========================================================================

_ES_RULES: list = [
    # --- trigraphs and long contexts ---
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
    # --- accented hiatus (the accented vowel stays full) ---
    ('ía', 'i a'), ('úa', 'u a'), ('aí', 'a i'), ('eí', 'e i'),
    ('oí', 'o i'), ('aú', 'a u'), ('oú', 'o u'), ('úe', 'u e'),
    # --- diphthongs (atonic i/u before a vowel → glide) ---
    ('ia', 'j a'), ('ie', 'j e'), ('io', 'j o'), ('iu', 'j u'),
    ('ua', 'w a'), ('ue', 'w e'), ('uo', 'w o'), ('ui', 'w i'),
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'),
    ('ay', 'a j'), ('ey', 'e j'), ('oy', 'o j'), ('uy', 'w i'),
    # --- accents → base vowel ---
    ('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'),
    ('ü', 'u'),
    # --- single letters ---
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
# Word → keys conversion
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Converts a Spanish word to a list of engine SAMPA keys."""
    word_lc = word.lower().replace('’', "'")

    # (0) external lexicon — absolute priority
    lex_keys = lexicon_for('es').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _ES_EXCEPTIONS:
        return _ES_EXCEPTIONS[word_lc].split()

    # (b) rule table (longest pattern first)
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
    """Converts a phrase (single words) to SAMPA."""
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
    """Converts a Spanish text to an engine SAMPA sequence.

    Same contract as ``g2p.text_to_sampa`` (English) and
    ``text_to_sampa_fr``: sentence punctuation → ``|``, comma →
    short pause, adjacent words linked with ``.`` (coarticulation).
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
