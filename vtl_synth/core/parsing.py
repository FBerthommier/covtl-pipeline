# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
parsing.py - Text analysis and syllable structure for the Berthommier model.

This is Step 1 of the synthesis pipeline. The public entry point is
``parse_input()``, which returns a ``ParseResult`` dataclass.

This module is aligned on the COVTL reference architecture.
It handles ONLY text analysis and syllable structure -- no trajectory
construction (that lives in ``continuous.py``).

Pipeline:
    parse_input --> tokenize + build syllables --> accumulate --> build boundaries --> finalise

Notation:
  - '.' or '-': syllable separator (coarticulation INTRA-word)
    The dot is NOT a silence marker. It indicates a syllable boundary
    that may or may not be respected according to the phonotactic rule
    ``_should_split_at_dot()``:
      C.C -> respected (split), C.V / V.C / V.V -> ignored (merge)
  - Spaces: word separators (NOT IPA segments). They generate GAP markers.
  - '|': explicit pause marker.

Source: Berthommier 2023, SS3 (gestures, anchors, COEFCEN, concatenation)
       COVTL reference parsing architecture
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from vtl_synth.core.constants import VOWEL_TARGETS, ALL_PHONEME_KEYS
from vtl_synth.core.types import ParseResult, SyllableBoundary


# ======================================================================
# Business-rule helpers
# ======================================================================

def _is_vowel_seg(seg: str) -> bool:
    """Check if a segment is a vowel.

    Adapted from the COVTL reference: uses VOWEL_TARGETS instead of
    PanPhon's 'syl' feature.
    """
    return seg in VOWEL_TARGETS


def _is_pause_marker(token: str) -> bool:
    """Check if a token is a pause marker ('|')."""
    return token == '|'


def _is_syllable_separator(char: str) -> bool:
    """Check if a character is an explicit syllable separator ('.' or '-')."""
    return char in ('.', '-')


# ======================================================================
# Longest-match tokenisation (Directive 5)
# ======================================================================

def _match_longest_token(text: str, pos: int) -> Optional[Tuple[str, int]]:
    """Find the longest recognised phoneme key starting at *pos*.

    Searches ALL_PHONEME_KEYS by decreasing length (up to 3 characters).

    Returns (segment, length) if a match is found, or None.
    """
    for length in [3, 2, 1]:
        if pos + length > len(text):
            continue
        candidate = text[pos:pos + length]
        if candidate in ALL_PHONEME_KEYS:
            return candidate, length
    return None


def _tokenize_word(word: str) -> List[str]:
    """Tokenize a single word into phoneme keys and dot separators.

    Syllable separators ('.' and '-') are converted to '.' tokens.
    Unrecognised characters are silently consumed.
    """
    tokens: List[str] = []
    pos = 0
    while pos < len(word):
        if _is_syllable_separator(word[pos]):
            tokens.append('.')
            pos += 1
            continue
        result = _match_longest_token(word, pos)
        if result is not None:
            seg, length = result
            tokens.append(seg)
            pos += length
        else:
            pos += 1  # Skip unknown character
    return tokens


# ======================================================================
# Syllable construction from tokens
# ======================================================================

def _should_split_at_dot(
    prev_seg: Optional[str],
    next_seg: Optional[str],
) -> bool:
    """Determine whether to split at a dot separator.

    Returns True if the dot should be kept as a syllable boundary,
    False if the syllables should be merged.

    The phonological rule is:
      - C.C -> split (keep the boundary)
      - C.V, V.C, V.V -> merge (ignore the dot)

    If either surrounding segment is unknown, the default is to
    split (keep the boundary).
    """
    if prev_seg is None or next_seg is None:
        return True
    prev_v = _is_vowel_seg(prev_seg)
    next_v = _is_vowel_seg(next_seg)
    # C.C -> split; C.V, V.C, V.V -> merge
    return not prev_v and not next_v


def _build_syllables(tokens: List[str]) -> List[List[str]]:
    """Build syllables from a list of tokens (phonemes and dots).

    Dots are handled as explicit syllable separators.  The split/merge
    decision is delegated to ``_should_split_at_dot()``.
    """
    word_sylls: List[List[str]] = []
    current_syll: List[str] = []

    i_tok = 0
    while i_tok < len(tokens):
        tok = tokens[i_tok]
        if tok == '.':
            # Determine surrounding segments
            prev_seg: Optional[str] = None
            if current_syll:
                prev_seg = current_syll[-1]
            elif word_sylls:
                prev_seg = word_sylls[-1][-1]

            next_seg: Optional[str] = None
            for j in range(i_tok + 1, len(tokens)):
                if tokens[j] != '.':
                    next_seg = tokens[j]
                    break

            if _should_split_at_dot(prev_seg, next_seg):
                if current_syll:
                    word_sylls.append(current_syll)
                    current_syll = []
            # If not splitting, ignore the dot (continue in same syllable)

            i_tok += 1
            continue

        # Phoneme token: add to current syllable
        current_syll.append(tok)
        i_tok += 1

    if current_syll:
        word_sylls.append(current_syll)

    return word_sylls


# ======================================================================
# Pipeline helpers
# ======================================================================

def _parse_word(word: str) -> List[List[str]]:
    """Parse a single word into a list of syllables.

    Tokenizes the word, then builds syllables from the tokens
    using the dot-separator merge logic.
    """
    tokens = _tokenize_word(word)
    if not tokens:
        return []
    return _build_syllables(tokens)


def _flush_current_block(
    blocks: List[List[str]],
    syllables_per_word: List[List[List[str]]],
    current_block: List[str],
    current_word_sylls: List[List[str]],
) -> None:
    """Flush the current block and word syllables into the result lists.

    Called when a pause is encountered or at the end of parsing.
    Modifies *blocks* and *syllables_per_word* in place.
    """
    if current_block:
        blocks.append(current_block[:])
        syllables_per_word.append(current_word_sylls[:])


def _finalize_parse(
    flat: List[str],
    blocks: List[List[str]],
    syllables_per_word: List[List[List[str]]],
    word_starts: List[int],
    syl_boundaries: set,
    syl_boundary_info: List[SyllableBoundary],
) -> ParseResult:
    """Create the final ``ParseResult`` from accumulated parse data."""
    return ParseResult(
        flat=flat,
        blocks=blocks,
        syllables_per_word=syllables_per_word,
        word_starts=word_starts,
        syllable_boundaries=syl_boundaries,
        syllable_boundary_info=syl_boundary_info,
    )


# ======================================================================
# Public API
# ======================================================================

def parse_input(text: str) -> ParseResult:
    """Parse phonetic input text into a structured representation.

    The input text uses COVTL notation: IPA segments separated by
    spaces, ``|`` for pauses, and ``.`` or ``-`` for explicit syllable
    breaks.

    Convention (no space/IPA confusion):
      - Spaces are WORD separators. They do NOT generate phoneme
        segments. A word = everything between two spaces (or start/end).
      - '|' is an explicit pause marker.
      - '.' or '-' are intra-word syllable separators, handled by
        ``_should_split_at_dot()``: C.C -> split, C.V/V.C/V.V -> merge.

    Parameters
    ----------
    text : str
        Phonetic text. E.g. ``'dug bat aji big.bi'``

    Returns
    -------
    ParseResult
        flat, blocks, syllables_per_word, word_starts,
        syllable_boundaries, syllable_boundary_info.

    Examples
    --------
    >>> pr = parse_input('big.bi')
    >>> pr.flat        # ['b', 'i', 'g', 'b', 'i', 'GAP']
    >>> pr.syllables_per_word  # [[['b', 'i', 'g'], ['b', 'i']]]

    >>> pr = parse_input('ab.da abda')
    >>> pr.flat
    ['a', 'b', 'd', 'a', 'GAP', 'a', 'b', 'd', 'a', 'GAP']
    >>> pr.syllables_per_word
    [[['a', 'b'], ['d', 'a']], [['a', 'b', 'd', 'a']]]
    """
    words_raw = text.strip().split()

    flat: List[str] = []
    blocks: List[List[str]] = []
    syllables_per_word: List[List[List[str]]] = []
    current_block: List[str] = []
    current_word_sylls: List[List[str]] = []
    word_starts: List[int] = []
    syl_boundaries: set = set()
    syl_boundary_info: List[SyllableBoundary] = []

    for w in words_raw:
        if _is_pause_marker(w):
            flat.append('|')
            _flush_current_block(
                blocks, syllables_per_word,
                current_block, current_word_sylls,
            )
            current_block = []
            current_word_sylls = []
            continue

        # Insert GAP between words (before the current word)
        if flat and flat[-1] != '|':
            flat.append('GAP')

        word_starts.append(len(flat))

        # Parse the word into syllables
        word_sylls = _parse_word(w)

        # Insert segments into flat and record syllable boundaries
        word_syll_starts: List[Tuple[int, List[str]]] = []
        for segs in word_sylls:
            syl_start = len(flat)
            word_syll_starts.append((syl_start, segs))
            flat.extend(segs)
            current_block.extend(segs)

        # Mark syllable boundaries (all except the first in the word)
        for idx_syl, (start, segs) in enumerate(word_syll_starts):
            if idx_syl > 0:
                syl_boundaries.add(start)

        # Build syl_boundary_info (pairs of adjacent syllables)
        for sb_idx in range(len(word_syll_starts) - 1):
            prev_start, prev_segs = word_syll_starts[sb_idx]
            curr_start, curr_segs = word_syll_starts[sb_idx + 1]
            syl_boundary_info.append(SyllableBoundary(
                flat_idx=curr_start,
                prev_segments=prev_segs,
                curr_segments=curr_segs,
            ))

        # Accumulate syllables for the current word
        current_word_sylls.extend(word_sylls)

    # Flush remaining block
    _flush_current_block(
        blocks, syllables_per_word,
        current_block, current_word_sylls,
    )

    # Add trailing short pause if needed
    if flat and flat[-1] not in ('|', 'GAP'):
        flat.append('GAP')

    return _finalize_parse(
        flat, blocks, syllables_per_word,
        word_starts, syl_boundaries, syl_boundary_info,
    )
