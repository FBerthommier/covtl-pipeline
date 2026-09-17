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

Homograph support (v1.0.3):
  CMUdict entries often carry several pronunciation variants for the
  same orthographic word (read = /riːd/ vs /rɛd/, lead = /liːd/ vs
  /lɛd/, wind = /wɪnd/ vs /waɪnd/, ...).  By default the engine
  keeps the pre-1.0.3 behaviour: variant 0 (CMUdict's most common
  form) is used for every word.  Pass ``homograph_resolver=...
  default_homograph_resolver`` to ``text_to_sampa`` to enable a
  coarse built-in heuristic based on the preceding word (determiner
  -> noun form, otherwise verb form).  Callers needing finer
  control can pass any callable with the same signature.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

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


# ===========================================================================
# Homograph resolution (CMUdict variants)
# ===========================================================================
# A homograph resolver receives:
#   word      (str)         - the orthographic word being looked up
#   variants  (list[list])   - the CMUdict ARPAbet variants for that word
#   context   (list[str])    - the words of the current sub-phrase
#                              (commas split a phrase into sub-phrases)
#   index     (int)          - position of `word` inside `context`
# and returns the index (0-based) of the variant to use.
HomographResolver = Callable[[str, list, list, int], int]

# Built-in table of common English homographs where the noun form and
# the verb form have distinct CMUdict variants. Each entry is
# (noun_variant_idx, verb_variant_idx). The ordering of CMUdict
# variants is not contractual; the indices below were verified
# against cmudict 0.4b (2014-12-10) but callers should re-verify
# if they ship a different dictionary build.
_DEFAULT_HOMOGRAPHS: dict = {
    'read':     (1, 0),   # /rɛd/ (past) at 0, /riːd/ (present) at 1
    'lead':     (1, 0),   # /lɛd/ (metal) at 0, /liːd/ (verb) at 1
    'wind':     (0, 1),   # /wɪnd/ (breeze) at 0, /waɪnd/ (turn) at 1
    'tear':     (1, 0),   # /tɛr/ (rip) at 0, /tɪr/ (eye) at 1
    'bow':      (1, 0),   # /baʊ/ (bend) at 0, /boʊ/ (weapon) at 1
    'bass':     (0, 1),   # /bæs/ (fish) at 0, /beɪs/ (low tone) at 1
    'minute':   (0, 1),   # /ˈmaɪnət/ (time) at 0, /mɪˈnjuːt/ (small) at 1
    'use':      (1, 0),   # /juːz/ (verb) at 0, /juːs/ (noun) at 1
    'house':    (1, 0),   # /haʊz/ (verb) at 0, /haʊs/ (noun) at 1
    'live':     (1, 0),   # /lɪv/ (verb) at 0, /laɪv/ (adj) at 1
    'close':    (1, 0),   # /kloʊz/ (verb) at 0, /kloʊs/ (adj/noun) at 1
    'content':  (1, 0),   # /kənˈtɛnt/ (verb) at 0, /ˈkɑntɛnt/ (noun) at 1
    'object':   (1, 0),   # /əbˈdʒɛkt/ (verb) at 0, /ˈɑbdʒɛkt/ (noun) at 1
    'project':  (1, 0),   # /prəˈdʒɛkt/ (verb) at 0, /ˈprɑdʒɛkt/ (noun) at 1
    'record':   (1, 0),   # /rəˈkɔrd/ (verb) at 0, /ˈrɛkərd/ (noun) at 1
    'present':  (1, 0),   # /prəˈzɛnt/ (verb) at 0, /ˈprɛzənt/ (noun/adj) at 1
    'conduct':  (1, 0),   # /kənˈdʌkt/ (verb) at 0, /ˈkɑndʌkt/ (noun) at 1
    'contract': (1, 0),   # /kənˈtrækt/ (verb) at 0, /ˈkɑntrækt/ (noun) at 1
    'conflict': (1, 0),   # /kənˈflɪkt/ (verb) at 0, /ˈkɑnflɪkt/ (noun) at 1
    'permit':   (1, 0),   # /pərˈmɪt/ (verb) at 0, /ˈpɜrmɪt/ (noun) at 1
}

# Words that, when immediately preceding the homograph, bias the
# resolver toward the noun form (determiners, possessives, numerals).
_DETERMINERS: frozenset = frozenset({
    'the', 'a', 'an', 'this', 'that', 'these', 'those',
    'my', 'your', 'his', 'her', 'its', 'our', 'their',
    'some', 'any', 'each', 'every', 'no', 'either', 'neither',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
    'nine', 'ten', 'all', 'both', 'several', 'many', 'few',
})


def default_homograph_resolver(
    word: str,
    variants: list,
    context: list,
    index: int,
) -> int:
    """Built-in homograph resolver using simple context heuristics.

    For known English homographs (read/lead/wind/tear/bow/bass/use/
    house/live/close/content/object/project/record/present/conduct/
    contract/conflict/permit/...), chooses the noun form when the
    preceding word is a determiner, and the verb form otherwise.
    For other words, returns 0 (CMUdict's most common variant).

    This is a coarse heuristic suitable for TTS pre-processing.
    For production use, consider plugging in a POS-tagging-based
    resolver (e.g. spaCy + a custom CMUdict lookup).
    """
    if not variants:
        return 0
    if len(variants) == 1:
        return 0
    word_lower = word.lower()
    if word_lower not in _DEFAULT_HOMOGRAPHS:
        return 0
    noun_idx, verb_idx = _DEFAULT_HOMOGRAPHS[word_lower]
    prev_word = ""
    if index > 0 and (index - 1) < len(context):
        prev_word = context[index - 1].lower()
    if prev_word in _DETERMINERS:
        if 0 <= noun_idx < len(variants):
            return noun_idx
    if 0 <= verb_idx < len(variants):
        return verb_idx
    return 0


def is_g2p_available() -> bool:
    """True when the CMUdict dictionary was loaded."""
    return _CMU is not None


def _word_to_sampa(
    word: str,
    warnings: list,
    context: Optional[list] = None,
    index: int = 0,
    resolver: Optional[HomographResolver] = None,
) -> str:
    """One orthographic word -> connected engine token (coarticulated).

    The returned token is a single connected chain with '.' between
    syllabic groups (e.g. ``Di.si.zi``) — never a space-separated
    phoneme list, which would insert an inter-word pause after every
    phoneme and break coarticulation.

    Parameters
    ----------
    word : str
        Orthographic word.
    warnings : list
        Collector for non-fatal messages (unknown words, etc.).
    context : list[str], optional
        Words of the current sub-phrase (comma-split part of a
        phrase). Used by the homograph resolver to look at the
        preceding word.
    index : int
        Position of `word` inside `context` (0-based).
    resolver : callable, optional
        Homograph resolver. When None, variant 0 (CMUdict's most
        common form) is always used (pre-1.0.3 behaviour).
    """
    variants = _CMU.get(word.lower())
    if variants:
        if resolver is not None and context is not None:
            try:
                idx = resolver(word, variants, context, index)
            except Exception as exc:  # pragma: no cover — defensive
                warnings.append(
                    f"homograph resolver raised on {word!r}: "
                    f"{exc!r}; falling back to variant 0")
                idx = 0
        else:
            idx = 0
        idx = max(0, min(int(idx), len(variants) - 1))
        keys = []
        for sym in variants[idx]:
            sym = sym.rstrip('012')
            keys.extend(arpa_to_sampa([sym]).split())
        return keys_to_connected(keys)
    if is_sampa_token(word):
        return word                     # already phonetic input
    warnings.append(
        f"word not in CMUdict (kept verbatim): {word!r}")
    return word


def text_to_sampa(
    text: str,
    warnings: list = None,
    homograph_resolver: Optional[HomographResolver] = None,
) -> str:
    """Convert English ``text`` to an engine SAMPA sequence.

    Parameters
    ----------
    text : str
        Either plain English ("this is easy for us") or already a
        SAMPA sequence ("Di s i z i z i f O r @ s").
    warnings : list, optional
        Collector for non-fatal messages (unknown words, missing
        dictionary).  When omitted, messages are printed.
    homograph_resolver : callable, optional
        Function ``(word, variants, context, index) -> int`` used
        to disambiguate CMUdict entries with multiple variants.
        When None (default), variant 0 (CMUdict's most common
        form) is used for every word (pre-1.0.3 behaviour). Pass
        ``default_homograph_resolver`` to enable basic English
        homograph disambiguation (read/lead/wind/use/...).

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
            tokens = [
                _word_to_sampa(
                    w, warnings,
                    context=words, index=wi,
                    resolver=homograph_resolver,
                )
                for wi, w in enumerate(words)
            ]
            sampa_parts.append('.'.join(tokens))
        out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p] {w}')
    return ' | '.join(out_phrases)
