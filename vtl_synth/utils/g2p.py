# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p.py
======
English grapheme-to-phoneme gateway (text -> engine SAMPA).

Strategy (mirrors the vtl-pipeline reference repository):

  1. look each word up in CMUdict (ARPAbet, with stress digits);
  2. convert ARPAbet to the engine SAMPA inventory
     (``vtl_synth.core.phonemes.ARPA_TO_SAMPA``);
  3. words missing from the dictionary are passed through verbatim
     when they are already valid engine SAMPA (mixed
     orthographic/phonetic input is therefore tolerated), otherwise
     they are kept with a warning.

Sentence punctuation (``. ! ? ; :``) becomes the engine phrase
separator ``|`` (long pause); commas become a plain space (short
inter-word pause), exactly like hand-written input files.

``cmudict`` is an optional dependency: without it the input is assumed
to be SAMPA already and returned unchanged (with a warning), so the
package keeps working for phonetic input alone.
"""

from __future__ import annotations

import re

from vtl_synth.core.phonemes import (
    arpa_to_sampa,
    greedy_sampa_split,
    is_sampa_token,
    keys_to_connected,
    PAUSE_PUNCTUATION,
    SENTENCE_PUNCTUATION,
)

try:
    import cmudict
    _CMU = cmudict.dict()
except Exception:                                    # pragma: no cover
    _CMU = None

_WORD_RE = re.compile(r"[A-Za-z']+")
_TRAILING_PUNCT_RE = re.compile(r'^[' + re.escape(SENTENCE_PUNCTUATION)
                                + re.escape(PAUSE_PUNCTUATION) + r']+$')


def is_g2p_available() -> bool:
    """True when the CMUdict dictionary was loaded."""
    return _CMU is not None


def _word_to_sampa(word: str, warnings: list) -> str:
    """One orthographic word -> connected engine token (coarticulated).

    The returned token is a single connected chain with '.' between
    syllabic groups (e.g. ``Di.si.zi``) — never a space-separated
    phoneme list, which would insert an inter-word pause after every
    phoneme and break coarticulation.
    """
    variants = _CMU.get(word.lower())
    if variants:
        keys = []
        for sym in variants[0]:
            sym = sym.rstrip('012')
            keys.extend(arpa_to_sampa([sym]).split())
        return keys_to_connected(keys)
    if is_sampa_token(word):
        return word                     # already phonetic input
    warnings.append(
        f"word not in CMUdict (kept verbatim): {word!r}")
    return word


def text_to_sampa(text: str, warnings: list = None) -> str:
    """Convert English ``text`` to an engine SAMPA sequence.

    Parameters
    ----------
    text : str
        Either plain English ("this is easy for us") or already a
        SAMPA sequence ("Di s i z i z i f O r @ s").
    warnings : list, optional
        Collector for non-fatal messages (unknown words, missing
        dictionary).  When omitted, messages are printed.

    Returns
    -------
    str
        SAMPA sequence; phrases separated by ``|``.
    """
    own = warnings is None
    if own:
        warnings = []

    if _CMU is None:
        warnings.append('cmudict not installed: input is assumed '
                        'to be SAMPA already')
        return text.strip()

    phrases = re.split(r'[' + re.escape(SENTENCE_PUNCTUATION) + r']+\s*',
                       text)
    out_phrases = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        # commas inside the phrase keep an inter-word (short) pause:
        # words on both sides of a comma are separated by a space,
        # while plain adjacent words are connected with '.' so the
        # engine coarticulates across word boundaries
        parts = re.split(r'\s*[,–—]\s*', phrase)
        words_per_part = [_WORD_RE.findall(p) for p in parts]
        if not any(words_per_part):
            continue
        sampa_parts = []
        for words in words_per_part:
            tokens = [_word_to_sampa(w, warnings) for w in words]
            sampa_parts.append('.'.join(tokens))
        out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p] {w}')
    return ' | '.join(out_phrases)
