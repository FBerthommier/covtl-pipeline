# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_de.py
=========
German grapheme-to-phoneme: orthographic text → engine SAMPA.
Same architecture as ``g2p_fr.py`` (v2):

  external lexicon (absolute priority) → exceptions dictionary →
  contextual preprocessing (final devoicing, ach/ich-laut,
  voiced s, unstressed final reductions) → rule table.

Lexicon: ``vtl_synth/data/de_lexicon.tsv`` (Wikipron
``deu_latn_broad_filtered.tsv``; variable: ``$COVTL_DE_LEXICON``),
loaded by :mod:`vtl_synth.utils.lexicon_loader`.

Graphemic coverage (cf. specification): ä ö ü ß, sch, ch
(ach/ich depending on the vocalic context), ei, eu/äu, ie, au, mute
h (lengthening after a vowel), plus final devoicing
(Auslautverhärtung), initial st-/sp- /ʃt ʃp/, intervocalic s /z/,
-z- /ts/ and the -er/-en/-el/-e finals reduced to @.

Documented approximations:
  * ö/ü always tense (2/y): the rule has no length test
    (the lexicon provides the correct short realizations 9/Y);
  * ʁ → ``R`` (the engine's only rhotic); ɐ → ``@``;
  * no glottal stop (ʔ absent from the inventory);
  * no e → ə reduction outside the -e/-er/-en/-el finals;
  * double consonants are emitted twice (geminated);
  * ɪ/ʊ/ʏ (lax) from the lexicon and exceptions -> i/u/y (tense):
    the I/U/Y keys are not in the engine inventory
    (CORRECTIONS v2.1, g2p-de leak — before: vowels silently
    dropped by the parsers).

The preprocessing uses UPPERCASE PLACEHOLDERS (ACH, ICH, TSCH,
SCH, SDT, SDP, SZ, SCHWA, ERFIN, ENFIN, ELFIN, IQ): the word is
lowercased first, so they cannot collide with the orthography,
and the rule table translates them to the keys.
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
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

_V = 'aeiouäöü'          # orthographic vowels


def _normalize_input(text: str) -> str:
    """NFC + typographic apostrophes normalized."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (frequent words irregular for the rules)
# ===========================================================================

_DE_EXCEPTIONS: dict = {
    # function words (full vowels, no final reduction)
    'der': 'd e R', 'die': 'd i', 'das': 'd a s', 'den': 'd e n',
    'dem': 'd e m', 'des': 'd e s', 'ein': 'a j n', 'eine': 'a j n @',
    'einen': 'a j n @ n', 'und': 'u n t', 'ist': 'i s t',
    'sind': 'z i n t', 'war': 'v a R', 'waren': 'v a R @ n',
    'von': 'f O n', 'mit': 'm i t', 'auf': 'a w f', 'aus': 'a w s',
    'bei': 'b a j', 'für': 'f y R', 'wie': 'v i', 'wo': 'v o',
    'was': 'v a s', 'wer': 'v e R', 'sehr': 'z e R',
    'ja': 'j a', 'nein': 'n a j n', 'nicht': 'n i C t',
    'noch': 'n O X', 'schon': 'S o n', 'auch': 'a w X',
    'wieder': 'v i d e R', 'über': 'y b e R', 'unter': 'u n t e R',
}


# ===========================================================================
# Contextual preprocessing
# ===========================================================================

def _preprocess(word: str) -> str:
    """Contextual normalizations of the German orthography.

    Order: final -ig /ɪç/ → final devoicing → complex affricates/
    fricatives to placeholders → ach/ich-laut according to the
    preceding vowel → initial st/sp → voiced s → reduced finals.
    """
    # 1. final -ig → /ɪç/ (König, zufrieden…) — BEFORE the devoicing
    #    (else ig becomes ik and the ich-laut is lost)
    word = re.sub(r'ig$', 'IQ', word)
    # 2. Auslautverhärtung: word-final b/d/g → p/t/k
    if len(word) > 2 and word[-1] in 'bdg':
        word = word[:-1] + {'b': 'p', 'd': 't', 'g': 'k'}[word[-1]]
    # 3. affricates / complex clusters to placeholders (tsch BEFORE
    #    sch, chs BEFORE ch)
    word = word.replace('tsch', 'TSCH').replace('sch', 'SCH')
    word = word.replace('chs', 'CHS')
    # 4. ach-laut (/x/) after a/o/u, else ich-laut (/ç/)
    word = re.sub(r'(?<=[aou])ch', 'ACH', word)
    word = word.replace('ch', 'ICH')
    # 5. INITIAL st-/sp- only → /ʃt ʃp/
    word = re.sub(r'^st', 'SDT', word)
    word = re.sub(r'^sp', 'SDP', word)
    # 6. voiced s: initial before a vowel, or intervocalic
    word = re.sub(r'^s(?=[' + _V + r'])', 'SZ', word)
    word = re.sub(r'(?<=[' + _V + r'])s(?=[' + _V + r'])', 'SZ', word)
    # 7. unstressed finals reduced (er > en > el > e, longest
    #    first)
    word = re.sub(r'er$', 'ERFIN', word)
    word = re.sub(r'en$', 'ENFIN', word)
    word = re.sub(r'el$', 'ELFIN', word)
    word = re.sub(r'e$', 'SCHWA', word)
    return word


# ===========================================================================
# Rule table (longest pattern first)
# ===========================================================================

_DE_RULES: list = [
    # --- preprocessing placeholders ---
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
    # --- written long vowels (mute lengthening h) ---
    ('ah', 'a'), ('eh', 'e'), ('ih', 'i'), ('oh', 'o'), ('uh', 'u'),
    ('äh', 'E'), ('öh', '2'), ('üh', 'y'),
    ('ee', 'e'), ('oo', 'o'),
    # --- umlauts et lettres simples ---
    ('ä', 'E'), ('ö', '2'), ('ü', 'y'), ('ß', 's'), ('ss', 's'),
    ('h', 'h'),           # initial h / after a consonant
    ('v', 'f'), ('w', 'v'), ('j', 'j'), ('z', 't s'), ('c', 'k'),
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('d', 'd'), ('f', 'f'), ('g', 'g'), ('k', 'k'),
    ('l', 'l'), ('m', 'm'), ('n', 'n'), ('p', 'p'), ('r', 'R'),
    ('s', 's'), ('t', 't'),
]

_DE_RULES_SORTED: list = sorted(_DE_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Word → keys conversion
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Converts a German word to a list of engine SAMPA keys."""
    word_lc = word.lower().replace('’', "'")

    # (0) external lexicon — absolute priority
    lex_keys = lexicon_for('de').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _DE_EXCEPTIONS:
        return _DE_EXCEPTIONS[word_lc].split()

    # (b) preprocessing + rule table
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


def text_to_sampa_de(text: str, warnings: list = None, **kwargs) -> str:
    """Converts a German text to an engine SAMPA sequence.

    Same contract as ``g2p.text_to_sampa`` (English): sentence
    punctuation → ``|``, comma → short pause, adjacent words
    linked with ``.`` (coarticulation).
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
