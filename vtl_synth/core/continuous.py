# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""continuous.py - Continuous syllabification and trajectory pipeline.

This module implements the continuous synthesis pipeline that
takes IPA strings with markers and produces articulatory trajectories.
It is the runtime engine used by text_to_tract.py.

The structural text analysis (tokenisation, syllable boundaries)
lives in parsing.py (aligned on the COVTL reference).
This module handles the continuous execution layer:

    parse_ipa_with_markers()  ->  ParseToken[]
           |   ("." -> COARTICULATION, "|" -> PAUSE)
           v
    syllabify_continuous()    ->  ChainElement[]
           |   (syllable or pause, with transition info)
           v
    _chain_elements_to_pval() ->  (tract_frames, rho_theta, block_info)

Notation:
  - "." or "-": syllable separator (coarticulation INTRA-word)
  - Space: inter-word pause marker (silence)
  - "|": phrase anchor (longer pause)

Source: Berthommier 2023, SS3 (gestures, anchors, COEFCEN, concatenation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from vtl_synth.core.constants import (
    COEFCEN,
    DELTA_O,
    DELTA_E,
    CO_VTL,
    VOWEL_TARGETS,
    CONSONANT_TARGETS,
    ALL_PHONEME_KEYS,
    AUTO_PARAMS,
    TRACT_PARAM_NAMES,
    COVTL_PARAMS,
    NEUTRAL_RHO,
    NEUTRAL_THETA,
)
from vtl_synth.core.types import SyllableBoundary, BoundaryDirection, ParseResult

# Re-export parse_input from parsing.py for backward compatibility
from vtl_synth.core.parsing import parse_input  # noqa: F401

# ======================================================================
# Markers and parsing constants (continuous API)
# ======================================================================

# The '|' character is the phrase start/end anchor.
# It is added automatically by parse_ipa_with_markers().
PHRASE_ANCHOR: str = '|'
COARTICULATION_MARKER: str = '.'
DEFAULT_PAUSE_DURATION_MS: float = 300.0
DEFAULT_VOWEL_DURATION_MS: float = 60.0
DEFAULT_CONSONANT_DURATION_MS: float = 50.0

# ==========================================================================
# Case normalization — SAMPA phonemic uppercase letters
# ==========================================================================
# In SAMPA, some uppercase letters have a phonemic meaning
# that is DISTINCT from their lowercase counterpart:
#   Consonants: S(/ʃ/), Z(/ʒ/), T(/θ/), D(/ð/), R(/ʁ/), N(/ŋ/),
#               J(/ɲ/), C(/ç/), L(dark-l), X(/χ/)
#   Vowels    : E(/ɛ/), O(/ɔ/)
#   Diphthongs: I, U, Y (2nd uppercase vowel = diphthong marker)
#
# The other uppercase letters (A, B, F, G, H, K, M, P, V, W)
# have NO phonemic counterpart and are normalized to lowercase.
# This lets us accept "Halt" as "halt", "Haus" as "haus".
_PHONEMIC_UPPER: frozenset = frozenset('SETDZLRNCJXOEIUY')

# Translation table for NON-phonemic letters
_CASE_NORM_TABLE = str.maketrans({
    c: c.lower()
    for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if c not in _PHONEMIC_UPPER
})


# ==========================================================================
# Diphthongs (VV decomposition with rapid transition)
# ==========================================================================
# Diphthongs are recognized in the IPA string and decomposed
# into two vowels forming a single syllabic nucleus (VV).
#
# Notation convention:
#   - The 2nd vowel is UPPERCASE to distinguish the diphthong
#     from a heterosyllabic sequence of two vowels.
#     E.g.: 'aI' = diphthong /aɪ/, 'ai' = two syllables /a.i/
#   - The orientation (direct/inverse) determines the direction of curvature.
#
# Structure: IPA key → (vowel_1, vowel_2, transition_duration_ms)
# The transition duration is the share of V1→V2 relative to the total.
DIPHTHONG_DECOMPOSITIONS: Dict[str, Tuple[str, str, float]] = {
    # Standard German
    'aI': ('a', 'i', 0.35),   # /aɪ̯/ (Ei, mein) — 35% for the transition
    'aU': ('a', 'u', 0.35),   # /aʊ̯/ (Haus, aus)
    'OY': ('O', 'y', 0.35),   # /ɔʏ̯/ (Euro, heute)
    'OI': ('O', 'i', 0.35),   # /ɔɪ/ variant
    # Additional variants
    'EY': ('E', 'y', 0.35),   # /ɛʏ/ (Bavarian)
    'AY': ('a', 'y', 0.35),   # /aʏ/ (Swiss German)
    'aY': ('a', 'y', 0.35),   # lowercase variant (after case normalization)
}

# Unicode IPA to diphthong keys (preprocessing)
DIPHTHONG_UNICODE: Dict[str, str] = {
    # /aɪ/  (a + ɪ)
    'a\u026a': 'aI',
    # /aʊ/  (a + ʊ)
    'a\u028a': 'aU',
    # /ɔʏ/  (ɔ + ʏ)
    '\u0254\u028f': 'OY',
    # /ɔɪ/  (ɔ + ɪ)
    '\u0254\u026a': 'OI',
}

# Default duration of a diphthong (ms)
DEFAULT_DIPHTHONG_DURATION_MS: float = 120.0

# Per-consonant specific durations (ms)
#
# WARNING — Limited role in the pipeline:
#   These durations do NOT control the timing of the articulatory
#   trajectory.  They are used only to:
#     1) Compute ChainElement.duration_ms (indicative value)
#     2) Size the segments for TimedEnvelope/FeatureTimer
#
#   The EFFECTIVE articulation timing is controlled by:
#     - T_cons = 160 ms and T_voy = 160 ms (parsing.py:l.2865-2866)
#     - build_global_pval() in trajectory.py
#   The E(t) envelope and V(t) are computed from block_info
#   (which shares this T_cons/T_voy timing), NOT from these durations.
#
#   In short: these values interfere with neither the articulation
#   nor E(t).  They only serve the source extensions
#   (TimedEnvelope), which are in any case overridden by
#   V(t) from block_info in text_to_tract.py and
#   build_phrase_tract.py.
CONSONANT_DURATIONS: Dict[str, float] = {
    'b': 60, 'p': 70, 'd': 45, 't': 55, 'g': 50, 'k': 60,
    'f': 100, 'v': 90, 's': 90, 'z': 80, 'S': 110, 'Z': 100,
    'T': 90, 'D': 80, 'X': 100, 'R': 70,
    'tS': 120, 'dZ': 110,
    'm': 70, 'n': 60, 'J': 70, 'N': 80,
    'l': 60, 'L': 70, 'j': 50, 'C': 90, 'w': 50,
    # Diphthongs (treated as units, total duration)
    'aI': 120, 'aU': 120, 'OY': 120, 'OI': 120, 'EY': 120, 'AY': 120, 'aY': 120,
}

# Neutral tract position (for transitions to/from pauses)
# Defined in constants.py — re-exported here for internal compatibility.
# from pipeline.constants import NEUTRAL_RHO, NEUTRAL_THETA  # via the global import

# Duration of the inter-syllabic transition arc (ms)
TRANSITION_ARC_DURATION_MS: float = 40.0

# Valid consonant clusters in syllable onset (French)
# Used by the onset maximization algorithm
VALID_ONSETS_2: frozenset = frozenset({
    'pR', 'tR', 'kR', 'bR', 'dR', 'gR',
    'fR', 'vR', 'sR', 'ZR', 'SR', 'tSR', 'dZR',
    'pS', 'tS', 'dZ', 'bJ', 'dj',
    'pl', 'pL', 'bl', 'bL', 'kl', 'kL', 'gl', 'gL',
    'tR', 'dR', 'fR', 'vR', 'sR', 'ZR', 'SR',
    'pw', 'tw', 'kw', 'bw', 'dw', 'gw',
})

VALID_ONSETS_3: frozenset = frozenset({
    'stR', 'spR', 'skR', 'ztR', 'zdR', 'zgR',
    'str', 'spr', 'skr',
})


# ==========================================================================
# Parsed token types
# ==========================================================================

class TokenType(Enum):
    PHONEME = 'phoneme'
    PAUSE = 'pause'
    COARTICULATION = 'coarticulation'


@dataclass
class ParseToken:
    """Token produced by IPA parsing.

    Attributes
    ----------
    token_type : TokenType
        PHONEME or PAUSE.
    key : str
        IPA key of the phoneme, or 'PAUSE'.
    kind : str
        'V', 'C', 'VV' (diphthong), or 'PAUSE'.
    duration_ms : float
        Duration (ms).
    diphthong_info : tuple or None
        For kind='VV': (vowel1_key, vowel2_key, transition_ratio).
        transition_ratio is the fraction of the total duration devoted
        to the V1→V2 transition (e.g. 0.35 = 35%).
    """
    token_type: TokenType
    key: str
    kind: str = 'C'
    duration_ms: float = DEFAULT_CONSONANT_DURATION_MS
    diphthong_info: Optional[Tuple[str, str, float]] = None


# ==========================================================================
# Types for the continuous chain
# ==========================================================================

class ChainElementType(Enum):
    SYLLABLE = 'syllable'
    PAUSE = 'pause'


@dataclass
class ChainElement:
    """Element of the continuous chain.

    Attributes
    ----------
    element_type : ChainElementType
        SYLLABLE or PAUSE.
    onset_keys : list[str]
        IPA keys of the onset consonants.
    nucleus_key : str
        IPA key of the nucleus vowel (first component
        of a diphthong, or simple vowel).
    nucleus_keys : list[str]
        IPA keys of the vocalic nucleus components.
        Length 1 for a simple vowel, 2 for a diphthong.
    diphthong_ratio : float
        For a diphthong: fraction of the total duration
        devoted to the V1→V2 transition (0.0-1.0).
        0.0 = no diphthong.
    coda_keys : list[str]
        IPA keys of the coda consonants.
    structure_type : str
        Structure type: V, CV, CVC, VV, CVV, VVC, CVVC,
        CCV, CCCV, VC, VCC, etc.
    duration_ms : float
        Total duration of the element (ms).
    pause_duration_ms : float
        Duration of the pause (ms), if element_type == PAUSE.
    transition_from_prev : str
        Type of transition from the previous element:
        'none' (phrase start), 'concatenated' (continuous arc),
        'paused' (after a pause).
    rho_v : float
        Polar radius of the nucleus vowel (V1 for a diphthong).
    theta_v : float
        Polar angle of the nucleus vowel (V1 for a diphthong).
    rho_v2 : float
        Polar radius of the 2nd vowel (diphthong only).
    theta_v2 : float
        Polar angle of the 2nd vowel (diphthong only).
    rho_vo : float
        Radius of the V_o anchor (COEFCEN * rho_v or rho_v at phrase start).
    theta_vo : float
        Angle of the V_o anchor.
    rho_ve : float
        Radius of the V_e anchor (COEFCEN * rho_v2 or rho_v at phrase end).
    theta_ve : float
        Angle of the V_e anchor.
    """
    element_type: ChainElementType = ChainElementType.SYLLABLE
    onset_keys: List[str] = field(default_factory=list)
    nucleus_key: str = ''
    nucleus_keys: List[str] = field(default_factory=list)
    diphthong_ratio: float = 0.0
    coda_keys: List[str] = field(default_factory=list)
    structure_type: str = 'V'
    duration_ms: float = 0.0
    pause_duration_ms: float = 0.0
    pause_role: str = ''
    pause_key: str = ''  # 'PHRASE_ANCHOR' or 'PAUSE' (interword)
    transition_from_prev: str = 'none'
    rho_v: float = 0.5
    theta_v: float = np.pi
    rho_v2: float = 0.5
    theta_v2: float = np.pi
    rho_vo: float = 0.35
    theta_vo: float = np.pi
    rho_ve: float = 0.35
    theta_ve: float = np.pi

    @property
    def n_onset(self) -> int:
        return len(self.onset_keys)

    @property
    def n_coda(self) -> int:
        return len(self.coda_keys)

    @property
    def has_nucleus(self) -> bool:
        return self.nucleus_key != ''

    @property
    def is_diphthong(self) -> bool:
        return len(self.nucleus_keys) == 2

    @property
    def is_pause(self) -> bool:
        return self.element_type == ChainElementType.PAUSE


# ==========================================================================
# Part 1 — IPA parsing with pause markers
# ==========================================================================

def _normalize_ipa(ipa_str: str) -> str:
    """Normalizes Unicode IPA symbols to internal keys.

    Handles three steps:
      0. Case normalization: non-phonemic uppercase letters (A, B, F,
         G, H, K, M, P, V, W) are converted to lowercase. Phonemic
         uppercase letters (S, E, T, D, Z, L, R, N, C, J, X, O, I, U, Y)
         are preserved intact.
      1. Common multi-character symbols (ʃ→S, ŋ→N, etc.)
      2. Unicode diphthongs (aɪ→aI, aʊ→aU, etc.)

    Diphthongs are normalized AFTER simple symbols
    to avoid conflicts (e.g. ɛ + ʏ → OY).
    """
    # 0. Case normalization (before any other transformation)
    ipa_str = ipa_str.translate(_CASE_NORM_TABLE)

    # 1. Simple and multi-character symbols
    multi_char = {
        '\u0283': 'S', '\u0292': 'Z', '\u0074\u0283': 'tS',
        '\u0064\u0292': 'dZ', '\u014b': 'N', '\u0272': 'J',
        '\u0281': 'R', '\u0153': '6', '\u025b': 'E',
        '\u0254': 'O', '\u00f8': '2', '\u0259': '@',
        '\u025b\u0303': '9', '\u0153\u0303': '6',
        '\u0251\u0303': '6', '\u0254\u0303': '9',
        '\u03b2': 'v', '\u00f0': 'D', '\u03b8': 'T',
        '\u03c7': 'X', '\u00e7': 'C', '\u029d': 'j',
        '\u028d': 'w', '\u0265': 'w',
        '\u026a': 'I',  # ɪ → I (diphthong component)
        '\u028f': 'Y',  # ʏ → Y (diphthong component)
        '\u028a': 'U',  # ʊ → U (diphthong component)
    }
    result = ipa_str
    for uni, key in sorted(multi_char.items(), key=lambda x: -len(x[0])):
        result = result.replace(uni, key)

    # 2. Unicode diphthongs (after component normalization)
    for uni, key in sorted(DIPHTHONG_UNICODE.items(), key=lambda x: -len(x[0])):
        result = result.replace(uni, key)

    return result


def parse_ipa_with_markers(
    ipa_str: str,
    coarticulation_marker: str = COARTICULATION_MARKER,
    pause_duration_ms: float = DEFAULT_PAUSE_DURATION_MS,
    vowel_duration_ms: float = DEFAULT_VOWEL_DURATION_MS,
    consonant_durations: Optional[Dict[str, float]] = None,
    phrase_pause_duration_ms: Optional[float] = None,
    add_phrase_anchors: bool = True,
) -> List[ParseToken]:
    """Parse an IPA string with markers.

    Convention:
      - Space / whitespace: inter-word pause marker (silence).
        Spaces in the input string are treated as
        pauses of duration pause_duration_ms.
      - '.' or '-': coarticulation marker (intra-word syllable boundary)
        The dot is NOT a silence marker. It indicates a
        syllable boundary that will be handled by syllabify_continuous()
        with the phonotactic rule C.C → split, C.V → merge.
      - '|': phrase start/end anchor (longer pause).
        Added automatically at start and end if add_phrase_anchors=True.
        There is NO double bar '||'.

    Parameters
    ----------
    ipa_str : str
        IPA string that may contain markers.
        Examples: 'ba.bi.bu' (intra-word coarticulation),
                  'ba bi' (pause between words, the space = pause),
                  'ba.bi ku.pi' (mixed)
    coarticulation_marker : str
        Character used as the coarticulation marker.
    pause_duration_ms : float
        Default duration of an inter-word pause (ms).
    vowel_duration_ms : float
        Default duration of vowels (ms).
    consonant_durations : dict, optional
        Specific durations per consonant.
    phrase_pause_duration_ms : float, optional
        Duration of the phrase start/end anchor pause (ms).
        If None, uses pause_duration_ms.
    add_phrase_anchors : bool
        If True (default), adds '|' at phrase start and end.

    Returns
    -------
    list[ParseToken]
        Parsed tokens in order.
    """
    ipa_str = _normalize_ipa(ipa_str)

    if phrase_pause_duration_ms is None:
        phrase_pause_duration_ms = pause_duration_ms

    # Spaces (whitespace) = inter-word pauses.
    # They are replaced with a temporary marker that will be treated as a pause.
    _SPACE_PAUSE = '\x00'  # internal marker for space pauses
    ipa_str = ipa_str.replace(' ', _SPACE_PAUSE)

    # Add phrase start and end anchors ('|')
    # Idempotent: if '|' is already at the start/end, do not double it.
    # '||' is normalized to a single '|' (no double bar).
    # Model-compliant: '|' = phrase anchor ONLY.
    if add_phrase_anchors:
        ipa_str = ipa_str.replace('||', PHRASE_ANCHOR)
        if not ipa_str.startswith(PHRASE_ANCHOR):
            ipa_str = PHRASE_ANCHOR + ipa_str
        if not ipa_str.endswith(PHRASE_ANCHOR):
            ipa_str = ipa_str + PHRASE_ANCHOR

    # Remove commas
    ipa_str = ipa_str.replace(',', '')

    if consonant_durations is None:
        consonant_durations = CONSONANT_DURATIONS

    # Known keys, sorted by decreasing length
    sorted_keys = sorted(ALL_PHONEME_KEYS, key=len, reverse=True)

    # Diphthong keys, sorted by decreasing length
    sorted_diphthongs = sorted(DIPHTHONG_DECOMPOSITIONS.keys(),
                                key=len, reverse=True)

    tokens: List[ParseToken] = []
    i = 0
    while i < len(ipa_str):
        ch = ipa_str[i]

        # Phrase start/end anchor ('|')
        # key='PHRASE_ANCHOR' (not 'PAUSE') to distinguish
        # from inter-word pauses (space).
        if ch == PHRASE_ANCHOR:
            tokens.append(ParseToken(
                token_type=TokenType.PAUSE,
                key='PHRASE_ANCHOR',
                kind='PAUSE',
                duration_ms=phrase_pause_duration_ms,
            ))
            i += 1
            continue

        # Space = inter-word pause (internal marker _SPACE_PAUSE)
        if ch == _SPACE_PAUSE:
            tokens.append(ParseToken(
                token_type=TokenType.PAUSE,
                key='PAUSE',
                kind='PAUSE',
                duration_ms=pause_duration_ms,
            ))
            i += 1
            continue

        # Coarticulation marker ('.' or '-')
        # The dot is NOT a silence: it is an indication of an
        # intra-word syllable boundary. The token is kept
        # so that syllabify_continuous() can apply the
        # phonotactic rule C.C → split, C.V → merge.
        if ch in (coarticulation_marker, '-'):
            tokens.append(ParseToken(
                token_type=TokenType.COARTICULATION,
                key='COART',
                kind='COART',
                duration_ms=0.0,
            ))
            i += 1
            continue

        # Try to match a diphthong (BEFORE simple phonemes)
        matched = False
        for diph_key in sorted_diphthongs:
            if ipa_str[i:i+len(diph_key)] == diph_key:
                v1, v2, ratio = DIPHTHONG_DECOMPOSITIONS[diph_key]
                dur = consonant_durations.get(
                    diph_key, DEFAULT_DIPHTHONG_DURATION_MS)
                tokens.append(ParseToken(
                    token_type=TokenType.PHONEME,
                    key=diph_key,
                    kind='VV',
                    duration_ms=dur,
                    diphthong_info=(v1, v2, ratio),
                ))
                i += len(diph_key)
                matched = True
                break

        if matched:
            continue

        # Try to match a known phoneme
        for key in sorted_keys:
            if ipa_str[i:i+len(key)] == key:
                is_vowel = key in VOWEL_TARGETS
                kind = 'V' if is_vowel else 'C'
                if is_vowel:
                    dur = vowel_duration_ms
                else:
                    dur = consonant_durations.get(key, DEFAULT_CONSONANT_DURATION_MS)
                tokens.append(ParseToken(
                    token_type=TokenType.PHONEME,
                    key=key,
                    kind=kind,
                    duration_ms=dur,
                ))
                i += len(key)
                matched = True
                break

        if not matched:
            # Unknown character: ignore it
            i += 1

    return tokens


# ==========================================================================
# Part 2 — Continuous syllabification (aligned with the COVTL reference)
# ==========================================================================

def _is_vowel_key(key: str) -> bool:
    """Check whether an IPA key is a vowel."""
    return key in VOWEL_TARGETS


def _is_valid_onset(consonant_keys: List[str]) -> bool:
    """Check whether a group of consonants forms a valid onset."""
    n = len(consonant_keys)
    if n == 0:
        return True
    if n == 1:
        return True
    if n == 2:
        return ''.join(consonant_keys) in VALID_ONSETS_2
    if n == 3:
        return ''.join(consonant_keys) in VALID_ONSETS_3
    return False


def _should_split_at_coart(prev_seg: str | None, next_seg: str | None) -> bool:
    """Determine whether a coarticulation marker forces a split.

    Phonotactic rule (per the COVTL reference):
      C.C → split (honored) — e.g. 'p.t' in 'hap.tas'
      C.V → merge (ignored) — e.g. 'b.a' keeps the coarticulation
      V.C → merge (ignored)
      V.V → merge (ignored)

    If either segment is unknown, split by default.
    """
    if prev_seg is None or next_seg is None:
        return True
    prev_v = _is_vowel_key(prev_seg)
    next_v = _is_vowel_key(next_seg)
    # C.C → split; C.V, V.C, V.V → merge
    return not prev_v and not next_v


def syllabify_continuous(
    tokens: List[ParseToken],
    coefcen: float = COEFCEN,
) -> List[ChainElement]:
    """Syllabify a sequence of tokens into a continuous chain.

    Algorithm:
      1. Pauses (spaces → 'PAUSE') force GROUP boundaries (silence)
      2. Phrase anchors ('PHRASE_ANCHOR') also force boundaries
      3. Coarticulation markers ('.') guide intra-word
         syllabification with the rule C.C → split, C.V → merge
      4. Vowels are the syllable nuclei
      5. Pre-nucleus consonants are the onset (maximized onset, max 3)
      6. Post-nucleus consonants up to the next vowel or
         pause are the coda

    Parameters
    ----------
    tokens : list[ParseToken]
        Tokens parsed by parse_ipa_with_markers().
    coefcen : float
        rho reduction coefficient at boundaries.

    Returns
    -------
    list[ChainElement]
        Continuous chain of elements (syllables and pauses),
        each with its V_o/V_e anchors and its transition
        information.
    """
    elements: List[ChainElement] = []
    n_tokens = len(tokens)
    i = 0

    while i < n_tokens:
        tok = tokens[i]

        # --- Pause (space or '|') ---
        if tok.token_type == TokenType.PAUSE:
            role = 'interword' if tok.key != 'PHRASE_ANCHOR' else ''
            elements.append(ChainElement(
                element_type=ChainElementType.PAUSE,
                pause_duration_ms=tok.duration_ms,
                structure_type='PAUSE',
                duration_ms=tok.duration_ms,
                pause_role=role,
                pause_key=tok.key,
            ))
            i += 1
            continue

        # --- Coarticulation ('.' or '-') ---
        # The coarticulation marker is NOT a silence.
        # It indicates a potential syllable boundary.
        # The decision to split or merge is made by
        # _should_split_at_coart() based on the adjacent segments.
        #
        # We collect the phonemes up to the next nucleus,
        # then decide whether the boundary is honored.
        if tok.token_type == TokenType.COARTICULATION:
            # Find the adjacent segments
            prev_seg: str | None = None
            if elements and elements[-1].element_type == ChainElementType.SYLLABLE:
                if elements[-1].coda_keys:
                    prev_seg = elements[-1].coda_keys[-1]
                elif elements[-1].nucleus_key:
                    prev_seg = elements[-1].nucleus_key

            next_seg: str | None = None
            for j in range(i + 1, n_tokens):
                if tokens[j].token_type == TokenType.PHONEME:
                    next_seg = tokens[j].key
                    break

            if _should_split_at_coart(prev_seg, next_seg):
                # C.C → force a syllable boundary
                # The effect is to ensure that the consonants
                # on the left go to the coda of the current syllable,
                # and the consonants on the right will go to the onset of the next.
                # We do NOT create a pause element — just a logical
                # marker that will be handled by the onset maximization algorithm.
                pass  # The boundary is implicit
            # If merge (C.V, V.C, V.V), ignore the marker
            i += 1
            continue

        # --- Search for the next vocalic nucleus ---
        pending_consonants: List[ParseToken] = []
        found_nucleus = False
        force_split = False  # Forced by a preceding C.C marker

        while i < n_tokens:
            tok = tokens[i]

            if tok.token_type == TokenType.PAUSE:
                # Pause = group boundary
                break

            if tok.token_type == TokenType.COARTICULATION:
                # Coarticulation: check whether C.C → split
                prev_seg_c: str | None = None
                if pending_consonants:
                    prev_seg_c = pending_consonants[-1].key
                elif elements and elements[-1].element_type == ChainElementType.SYLLABLE:
                    if elements[-1].coda_keys:
                        prev_seg_c = elements[-1].coda_keys[-1]
                    elif elements[-1].nucleus_key:
                        prev_seg_c = elements[-1].nucleus_key

                next_seg_c: str | None = None
                for j in range(i + 1, n_tokens):
                    if tokens[j].token_type == TokenType.PHONEME:
                        next_seg_c = tokens[j].key
                        break

                if _should_split_at_coart(prev_seg_c, next_seg_c):
                    # C.C: force the end of the current syllable.
                    # The pending consonants go to the coda.
                    # The marker is consumed.
                    force_split = True
                    i += 1
                    break
                else:
                    # C.V, V.C, V.V: ignore, continue
                    i += 1
                    continue

            if tok.kind == 'V' or tok.kind == 'VV':
                found_nucleus = True
                break
            else:
                pending_consonants.append(tok)
                i += 1

        if not found_nucleus:
            # Consonants with no following vowel:
            # attach them to the last syllable as coda.
            if pending_consonants and elements:
                last = elements[-1]
                if last.element_type == ChainElementType.SYLLABLE:
                    for c in pending_consonants:
                        last.coda_keys.append(c.key)
                        last.duration_ms += c.duration_ms
                    _update_structure_type(last)
                    _update_anchors(last, coefcen)
            continue

        # tok is now the vocalic nucleus
        nucleus_tok = tok
        i += 1  # advance past the nucleus

        # --- Collect the coda with onset maximization ---
        coda_consonants: List[ParseToken] = []
        lookahead: List[ParseToken] = []
        dot_split_at_coda = False  # marker: dot forced within the coda
        coart_count_in_coda = 0  # number of COARTs consumed during the coda
        j = i
        while j < n_tokens and tokens[j].token_type != TokenType.PAUSE:
            if tokens[j].token_type == TokenType.COARTICULATION:
                coart_count_in_coda += 1
                # Check whether to split here.
                # Use the last consonant in lookahead (if any)
                # as the previous segment, otherwise the nucleus.
                if lookahead:
                    prev_seg_l: str | None = lookahead[-1].key
                else:
                    prev_seg_l: str | None = nucleus_tok.key
                next_seg_l: str | None = None
                for k in range(j + 1, n_tokens):
                    if tokens[k].token_type == TokenType.PHONEME:
                        next_seg_l = tokens[k].key
                        break
                if _should_split_at_coart(prev_seg_l, next_seg_l):
                    # C.C → force the end of the coda here.
                    # The collected consonants do NOT go to the coda:
                    # they will be left in the stream for the next
                    # syllable (which will treat them as pre-nucleus onset).
                    dot_split_at_coda = True
                    j += 1  # consume the marker
                    break
                else:
                    # C.V / V.C / V.V → merge: ignore the dot
                    j += 1
                    continue
            if tokens[j].kind in ('V', 'VV'):
                break
            lookahead.append(tokens[j])
            j += 1

        if not dot_split_at_coda and lookahead:
            n_coda = len(lookahead)
            n_to_next_onset = 0

            # Onset maximization: maximize the onset of the next syllable
            for n_try in range(min(3, len(lookahead)), 0, -1):
                candidate_onset = [c.key for c in lookahead[:n_try]]
                if _is_valid_onset(candidate_onset):
                    n_to_next_onset = n_try
                    n_coda = len(lookahead) - n_try
                    break

            coda_consonants = lookahead[:n_coda]

        # --- Syllable construction ---
        onset_keys = [c.key for c in pending_consonants]
        coda_keys = [c.key for c in coda_consonants]

        # Total duration
        dur = sum(c.duration_ms for c in pending_consonants)
        dur += nucleus_tok.duration_ms
        dur += sum(c.duration_ms for c in coda_consonants)

        # Handle diphthong vs simple vowel
        is_diphthong = nucleus_tok.kind == 'VV' and nucleus_tok.diphthong_info is not None
        if is_diphthong:
            v1_key, v2_key, diph_ratio = nucleus_tok.diphthong_info
            nucleus_key = v1_key
            nucleus_keys = [v1_key, v2_key]
            rho_v, theta_v = VOWEL_TARGETS.get(v1_key, (0.5, np.pi))
            rho_v2, theta_v2 = VOWEL_TARGETS.get(v2_key, (0.5, np.pi))
        else:
            nucleus_key = nucleus_tok.key
            nucleus_keys = [nucleus_key]
            rho_v, theta_v = VOWEL_TARGETS.get(nucleus_key, (0.5, np.pi))
            rho_v2, theta_v2 = rho_v, theta_v
            diph_ratio = 0.0

        elem = ChainElement(
            element_type=ChainElementType.SYLLABLE,
            onset_keys=onset_keys,
            nucleus_key=nucleus_key,
            nucleus_keys=nucleus_keys,
            diphthong_ratio=diph_ratio,
            coda_keys=coda_keys,
            duration_ms=dur,
            rho_v=rho_v,
            theta_v=theta_v,
            rho_v2=rho_v2,
            theta_v2=theta_v2,
        )
        _update_structure_type(elem)
        elements.append(elem)

        # Advance i beyond the nucleus AND the coda consonants.
        # If a dot forced a split, do not consume the consonants.
        # BUGFIX: when COARTs are consumed during coda collection
        # (coart_count_in_coda > 0), i must also advance past those COARTs
        # to avoid the outer loop re-processing them and duplicating
        # segments.  However if dot_split_at_coda, the consonants in
        # lookahead are not consumed: i must advance only by
        # len(coda_consonants) (which is 0 in that case).
        if coart_count_in_coda > 0 and coda_consonants:
            i += coart_count_in_coda + len(coda_consonants)
        else:
            i += len(coda_consonants)

    # NOTE: _fix_vc_to_cv_at_dot_boundaries is DISABLED.
    # This post-processing converted VC syllables to CV at boundaries
    # forced by '.'.  It corrupted the segment order in the flat:
    #   "abda" (without a dot) produced VC(a,b) → CV(b,a) and the flat
    #   became [b,a,d,a] instead of [a,b,d,a] (the initial 'a' was lost).
    #   "ab.da" (with a C.C dot) produced the same problem.
    # The VC→CV correction is syllabic-structure metadata that
    # must NOT modify the segment order in the flat stream.
    # The function is kept for reference but is no longer called.

    # --- Post-processing: update anchors and transitions ---
    _assign_transitions(elements, coefcen)

    # --- Post-processing 2: assign pause_role ---
    _assign_pause_roles(elements)

    return elements


def _assign_pause_roles(elements: List[ChainElement]) -> None:
    """Assign pause_role to PHRASE_ANCHOR pauses.

    Walks the list and labels:
      - First element (if a pause) → 'phrase_start'
      - Last element (if a pause) → 'phrase_end'
      - Other PHRASE_ANCHOR pauses (theoretically impossible)
        → 'interword' (fallback)

    Inter-word pauses (key='PAUSE') keep the
    pause_role='interword' already assigned in syllabify_continuous().
    """
    n = len(elements)
    for idx, elem in enumerate(elements):
        if elem.is_pause and elem.pause_role == '' and elem.pause_key == 'PHRASE_ANCHOR':
            if idx == 0:
                elem.pause_role = 'phrase_start'
            elif idx == n - 1:
                elem.pause_role = 'phrase_end'
            else:
                elem.pause_role = 'interword'


def _onset_prefix(n_on: int) -> str:
    """Return the canonical prefix for n onset consonants.

    0→'', 1→'C', 2→'CC', 3+→'CCC'.
    """
    if n_on <= 0:
        return ''
    elif n_on == 1:
        return 'C'
    elif n_on == 2:
        return 'CC'
    else:
        return 'CCC'


def _update_structure_type(elem: ChainElement) -> None:
    """Update the structure type of an element.

    Handles diphthong structures (VV, CVV, VVC, CVVC)
    in addition to the classic consonantal structures.
    """
    n_on = elem.n_onset
    n_co = elem.n_coda
    has_nuc = elem.has_nucleus
    is_diph = elem.is_diphthong

    if not has_nuc:
        elem.structure_type = 'C'
        return

    # Diphthong prefix
    diph = 'V' if is_diph else ''

    # Onset prefix
    on_p = _onset_prefix(n_on)

    if n_on == 0 and n_co == 0:
        elem.structure_type = 'VV' if is_diph else 'V'
    elif n_co == 0:
        # CV, CCV, CCCV (+ diphthongs: CVV, CCVV, CCCVV)
        elem.structure_type = f'{on_p}{diph}V'
    elif n_on == 0 and n_co >= 1:
        # VC, VCC, VCCC (+ diphthongs: VVC, VVCC, etc.)
        if n_co == 1:
            elem.structure_type = f'{diph}VC'
        elif n_co == 2:
            elem.structure_type = f'{diph}VCC'
        else:
            elem.structure_type = f'{diph}VCC+' 
    else:
        # CVC, CCVC, CCCVC (+ diphthongs: CVVC, CCVVC, etc.)
        if n_co == 1:
            elem.structure_type = f'{on_p}{diph}VC'
        else:
            elem.structure_type = f'{on_p}{diph}VC{n_co - 1}'


def _update_anchors(elem: ChainElement, delta_o: float = DELTA_O,
                       delta_e: float = DELTA_E) -> None:
    """Update the V_o and V_e anchors of an element.

    Parameters
    ----------
    elem : ChainElement
        Syllabic element.
    delta_o : float
        Reduction coefficient for V_o.
    delta_e : float
        Reduction coefficient for V_e.
    """
    elem.rho_vo = delta_o * elem.rho_v
    elem.theta_vo = elem.theta_v
    elem.rho_ve = delta_e * elem.rho_v
    elem.theta_ve = elem.theta_v


def _assign_transitions(
    elements: List[ChainElement],
    coefcen: float,
    delta_o: float = DELTA_O,
    delta_e: float = DELTA_E,
) -> None:
    """Assign inter-element transitions and anchors.

    For each syllabic element:
      - V_o: DELTA_O * rho_v (except at phrase start or after a pause → rho_v)
      - V_e: DELTA_E * rho_v (except at phrase end or before a pause → rho_v)

    Pauses force a reset of the anchors.

    Parameters
    ----------
    elements : list[ChainElement]
        Chain of elements.
    coefcen : float
        rho reduction coefficient (legacy).
    delta_o : float
        Reduction coefficient for V_o.
    delta_e : float
        Reduction coefficient for V_e.
    """
    prev_was_pause = False
    is_first_syllable = True

    for idx, elem in enumerate(elements):
        if elem.is_pause:
            prev_was_pause = True
            continue

        # --- V_o ---
        # In the Berthommier model, V_o is ALWAYS reduced
        # by a coefficient < 1 (DELTA_O), including at phrase
        # start and after a pause. V_o represents an articulatory
        # anticipation that never reaches the full target.
        elem.rho_vo = delta_o * elem.rho_v
        elem.theta_vo = elem.theta_v

        # --- V_e ---
        # Look for the next non-pause element
        next_is_pause_or_end = True
        for j in range(idx + 1, len(elements)):
            if not elements[j].is_pause:
                next_is_pause_or_end = False
                break

        if next_is_pause_or_end:
            # Phrase end or pause after:
            # V_e reduced by DELTA_E for the transition toward
            # the neutral position or the end.
            # For a diphthong, V_e is based on V2.
            rho_end = elem.rho_v2 if elem.is_diphthong else elem.rho_v
            theta_end = elem.theta_v2 if elem.is_diphthong else elem.theta_v
            elem.rho_ve = delta_e * rho_end
            elem.theta_ve = theta_end
        else:
            # Continuous concatenation: V_e reduced by DELTA_E
            # For a diphthong, V_e is based on V2
            # (it is V2 that connects to the V_o of the next syllable).
            rho_end = elem.rho_v2 if elem.is_diphthong else elem.rho_v
            theta_end = elem.theta_v2 if elem.is_diphthong else elem.theta_v
            elem.rho_ve = delta_e * rho_end
            elem.theta_ve = theta_end

        # --- Transition from the previous element ---
        if is_first_syllable:
            elem.transition_from_prev = 'none'
        elif prev_was_pause:
            elem.transition_from_prev = 'paused'
        else:
            elem.transition_from_prev = 'concatenated'

        is_first_syllable = False
        prev_was_pause = False


# ==========================================================================
# Part 3 — Continuous trajectory construction
# ==========================================================================



def _execute_syllable_element(
    elem: ChainElement,
    sr: float,
    K_v: float,
    K_c: float,
    nu_c: int,
    coefcen: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Execute a syllabic element with Tvoy/Tcons.

    Per the Berthommier COVTL model:
    - The C and V branches have durations modulated independently
      by Tcons and Tvoy
    - The vocalic sustain is computed automatically:
      if nucleus_duration > 2T*Tvoy, the excess is allocated to a
      stationary point on the target vowel
    - The rho/theta extraction uses z_v (vocalic branch),
      with no selection bias

    Parameters
    ----------
    elem : ChainElement
        Syllabic element.
    sr, K_v, K_c, nu_c, coefcen :
        Model parameters.
    param_names : list[str]
        Names of the output parameters.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (tract_frames, rho_theta)
    """
    from vtl_synth.core.trajectory_legacy import (
        build_cv_graph, build_cvc_graph, build_ccv_graph,
        execute_superposition_segment,
        build_vocalic_only as _build_vocalic_only,
        scale_durations_tcons_tvoy as _scale_tcons_tvoy,
        params_to_array as _params_to_array,
        extract_rho_theta_from_zv,
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        SuperpositionSegment, ArcSpec,
    )
    from vtl_synth.core.constants import (
        TCONS_DEFAULT, TVOY_DEFAULT,
        VOWEL_TARGETS,
    )
    from vtl_synth.core.polar import T_BASE_DEFAULT

    def _make_rt(zv, n, rho_fallback, theta_fallback):
        """Extract rho/theta from z_v (unbiased)."""
        if zv is not None and len(zv) == n:
            return np.column_stack([np.abs(zv), np.angle(zv)])
        return np.tile([rho_fallback, theta_fallback], (n, 1))

    st = elem.structure_type
    rho_v = elem.rho_v
    theta_v = elem.theta_v
    T = T_BASE_DEFAULT

    if st == 'V':
        seg = _build_vocalic_only(elem.nucleus_key)
        seg.vocalic_arcs[0].duration_ms = elem.duration_ms
        params, n, zv = execute_superposition_segment(seg, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CV':
        c_key = elem.onset_keys[0]

        # COVTL reference: V_o depends on the syllabic context
        # - Isolated syllable / after pause: V_o = V (no reduction)
        #   → reduced graph: C → V (1 arc), V → V (stationary)
        #   → target duration = T * (n_c * tcons + tvoy * 0.2)
        # - Concatenated syllable: V_o = COEFCEN * V
        #   → full graph: V_o → C → V (2 arcs), V_o → V
        #   → target duration = T * (n_c * tcons + 2 * tvoy)
        is_isolated = elem.transition_from_prev in ('none', 'paused')
        delta_o_eff = 1.0 if is_isolated else coefcen
        v_start_pt = (elem.rho_vo, elem.theta_vo)

        if is_isolated:
            # Duration for isolated CV: T * (n_c * tcons + tvoy * 0.2)
            # = 100 * (1.0 + 0.2) = 120ms for T=100, tcons=tvoy=1.0
            n_c_nom = 1
            target_dur = T * (n_c_nom * TCONS_DEFAULT + TVOY_DEFAULT * 0.2)
        else:
            n_c_nom = 2
            # Duration for concatenated CV: T * (n_c * tcons + 2 * tvoy)
            # = 100 * (2.0 + 2.0) = 400ms nominal, compressed to elem.duration_ms
            target_dur = elem.duration_ms

        sup = build_cv_graph(
            elem.nucleus_key, c_key,
            delta_o=delta_o_eff, K_v=K_v, K_c=K_c, nu_c=nu_c,
            sustain_ms=0.0,
            v_start=v_start_pt,
        )
        _scale_tcons_tvoy(
            sup, target_dur,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=0.0, T=T,
            n_c_arcs_nominal=n_c_nom,
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CCV':
        c1_key = elem.onset_keys[0]
        c2_key = elem.onset_keys[1]
        dur_c = sum(DEFAULT_CONSONANT_DURATION_MS
                       for k in elem.onset_keys)
        dur_nuc = elem.duration_ms - dur_c
        tvoy_trans = 2.0 * T * TVOY_DEFAULT
        sustain_ms = max(0.0, dur_nuc - tvoy_trans)

        # COVTL reference: same isolation/concatenation logic as CV
        is_isolated = elem.transition_from_prev in ('none', 'paused')
        delta_o_eff = 1.0 if is_isolated else coefcen
        v_start_pt = (elem.rho_vo, elem.theta_vo)
        sup = build_ccv_graph(
            elem.nucleus_key, c1_key, c2_key,
            delta_o=delta_o_eff, K_v=K_v, K_c=K_c, nu_c=nu_c,
        )
        if sustain_ms > 0:
            arc_sustain = ArcSpec(
                rho1=rho_v, theta1=theta_v,
                rho2=rho_v, theta2=theta_v,
                duration_ms=sustain_ms, K=K_v, nu=1,
                orientation='inverse', selector='vocalic',
            )
            sup.vocalic_arcs.append(arc_sustain)

        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=sustain_ms, T=T, n_c_arcs_nominal=3,
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CCCV':
        dur_c = sum(DEFAULT_CONSONANT_DURATION_MS
                       for k in elem.onset_keys)
        dur_nuc = elem.duration_ms - dur_c
        tvoy_trans = 2.0 * T * TVOY_DEFAULT
        sustain_ms = max(0.0, dur_nuc - tvoy_trans)

        sup = _build_cccv_graph(
            elem.onset_keys, elem.nucleus_key,
            elem.duration_ms, coefcen, K_v, K_c, nu_c,
        )
        if sustain_ms > 0:
            arc_sustain = ArcSpec(
                rho1=rho_v, theta1=theta_v,
                rho2=rho_v, theta2=theta_v,
                duration_ms=sustain_ms, K=K_v, nu=1,
                orientation='inverse', selector='vocalic',
            )
            sup.vocalic_arcs.append(arc_sustain)

        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=sustain_ms, T=T, n_c_arcs_nominal=len(elem.onset_keys),
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CVC':
        c1_key = elem.onset_keys[0]
        c2_key = elem.coda_keys[0]
        dur_onset_c = DEFAULT_CONSONANT_DURATION_MS
        dur_coda_c = DEFAULT_CONSONANT_DURATION_MS
        dur_nuc = elem.duration_ms - dur_onset_c - dur_coda_c
        tvoy_trans = 2.0 * T * TVOY_DEFAULT
        sustain_onset = max(0.0, dur_nuc * 0.5 - tvoy_trans)
        sustain_coda = max(0.0, dur_nuc * 0.5 - tvoy_trans)

        onset_weight = dur_onset_c + 0.5 * TVOY_DEFAULT * T
        coda_weight = dur_coda_c + 0.5 * TVOY_DEFAULT * T
        total_weight = onset_weight + coda_weight
        if total_weight <= 0:
            total_weight = 1.0

        sups = build_cvc_graph(
            elem.nucleus_key, c1_key, c2_key,
            delta_o=coefcen, delta_e=coefcen,
            K_v=K_v, K_c=K_c, nu_c=nu_c,
        )
        parts_tract = []
        parts_rt = []
        for si, sup in enumerate(sups):
            if si == 0:
                seg_dur = elem.duration_ms * onset_weight / total_weight
                seg_sustain = sustain_onset
            else:
                seg_dur = elem.duration_ms * coda_weight / total_weight
                seg_sustain = sustain_coda
            if seg_sustain > 0:
                arc_s = ArcSpec(
                    rho1=rho_v, theta1=theta_v,
                    rho2=rho_v, theta2=theta_v,
                    duration_ms=seg_sustain, K=K_v, nu=1,
                    orientation='inverse', selector='vocalic',
                )
                sup.vocalic_arcs.append(arc_s)

            _scale_tcons_tvoy(
                sup, seg_dur,
                tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
                sustain_ms=seg_sustain, T=T, n_c_arcs_nominal=2,
            )
            params, n, zv = execute_superposition_segment(sup, sr)
            frames = _params_to_array(params, param_names, n)
            rt = _make_rt(zv, n, rho_v, theta_v)
            parts_tract.append(frames)
            parts_rt.append(rt)
        return np.concatenate(parts_tract, axis=0), np.concatenate(parts_rt, axis=0)

    elif st == 'VC':
        c_key = elem.coda_keys[0]
        sup = _build_vc_graph(
            elem.nucleus_key, [c_key],
            elem.duration_ms, coefcen, K_v, K_c, nu_c,
        )
        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=0.0, T=T, n_c_arcs_nominal=2,
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st.startswith('VC') and st != 'VC':
        # VCC, VCCV, VCCC: extended coda
        sup = _build_vc_graph(
            elem.nucleus_key, elem.coda_keys,
            elem.duration_ms, coefcen, K_v, K_c, nu_c,
        )
        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=0.0, T=T,
            n_c_arcs_nominal=len(elem.coda_keys),
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CCVC':
        sup = _build_ccvc_graph(
            elem.onset_keys, elem.nucleus_key, elem.coda_keys,
            elem.duration_ms, coefcen, K_v, K_c, nu_c,
        )
        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=0.0, T=T,
            n_c_arcs_nominal=len(elem.onset_keys) + len(elem.coda_keys),
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    elif st == 'CVCC':
        sup = _build_cvc_extended_graph(
            elem.onset_keys, elem.nucleus_key, elem.coda_keys,
            elem.duration_ms, coefcen, K_v, K_c, nu_c,
        )
        _scale_tcons_tvoy(
            sup, elem.duration_ms,
            tcons=TCONS_DEFAULT, tvoy=TVOY_DEFAULT,
            sustain_ms=0.0, T=T,
            n_c_arcs_nominal=1 + len(elem.coda_keys),
        )
        params, n, zv = execute_superposition_segment(sup, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

    # --- Diphthong structures ---
    elif st == 'VV':
        frames, rt = _execute_diphthong(
            elem, sr, K_v, param_names)
        return frames, rt

    elif st in ('CVV', 'CCVV', 'CCCVV'):
        frames, rt = _execute_onset_diphthong(
            elem, sr, K_v, K_c, nu_c, coefcen, param_names)
        return frames, rt

    elif st in ('VVC', 'VVCC'):
        frames, rt = _execute_diphthong_coda(
            elem, sr, K_v, K_c, nu_c, coefcen, param_names)
        return frames, rt

    elif 'VV' in st and 'C' in st:
        # CVVC, CCVVC, etc. — generic fallback
        frames, rt = _execute_onset_diphthong_coda(
            elem, sr, K_v, K_c, nu_c, coefcen, param_names)
        return frames, rt

    else:
        # Fallback: treat as vocalic only
        seg = _build_vocalic_only(elem.nucleus_key or 'a')
        seg.vocalic_arcs[0].duration_ms = elem.duration_ms
        params, n, zv = execute_superposition_segment(seg, sr)
        frames = _params_to_array(params, param_names, n)
        rt = _make_rt(zv, n, rho_v, theta_v)
        return frames, rt

# ==========================================================================
# Diphthong graphs (VV, CVV, VVC, CVVC)
# ==========================================================================

def _build_diphthong_vocalic_arcs(
    v1_key: str, v2_key: str,
    rho_vo: float, theta_vo: float,
    rho_v1: float, theta_v1: float,
    rho_v2: float, theta_v2: float,
    rho_ve: float, theta_ve: float,
    diph_ratio: float,
    total_duration_ms: float,
    K_v: float = 30.0,
) -> Tuple[List['ArcSpec'], float]:
    """Build the vocalic arcs for a diphthong syllable.

    The vocalic graph of a diphthong is:

        V_o → V1 → V2 → V_e
        |---sustain---|trans|---sustain---|

    The V1→V2 transition takes up diph_ratio of the total duration.
    The rest is shared between V_o→V1 and V2→V_e.

    Parameters
    ----------
    v1_key, v2_key : str
        Keys of the two vowels.
    rho_vo, theta_vo : float
        V_o anchor (syllable start).
    rho_v1, theta_v1 : float
        V1 target (first component).
    rho_v2, theta_v2 : float
        V2 target (second component).
    rho_ve, theta_ve : float
        V_e anchor (syllable end).
    diph_ratio : float
        Fraction of the duration for the V1→V2 transition.
    total_duration_ms : float
        Total duration of the diphthong.
    K_v : float
        Vocalic curvature.

    Returns
    -------
    tuple[list[ArcSpec], float]
        (vocalic_arcs, consonant_branch_duration)
    """
    from vtl_synth.core.polar import ArcSpec, NU_DIRECT

    # Duration split
    trans_dur = total_duration_ms * diph_ratio  # V1→V2
    remain_dur = total_duration_ms - trans_dur      # V_o→V1 + V2→V_e
    dur_vo_v1 = remain_dur * 0.5                    # half for the onset
    dur_v2_ve = remain_dur * 0.5                    # half for the end

    arc_1 = ArcSpec(
        rho1=rho_vo, theta1=theta_vo,
        rho2=rho_v1, theta2=theta_v1,
        duration_ms=dur_vo_v1, K=K_v, nu=NU_DIRECT,
        orientation='inverse', selector='vocalic',
    )
    arc_2 = ArcSpec(
        rho1=rho_v1, theta1=theta_v1,
        rho2=rho_v2, theta2=theta_v2,
        duration_ms=trans_dur, K=K_v, nu=NU_DIRECT,
        orientation='inverse', selector='vocalic',
    )
    arc_3 = ArcSpec(
        rho1=rho_v2, theta1=theta_v2,
        rho2=rho_ve, theta2=theta_ve,
        duration_ms=dur_v2_ve, K=K_v, nu=NU_DIRECT,
        orientation='inverse', selector='vocalic',
    )

    return [arc_1, arc_2, arc_3], total_duration_ms


def _execute_diphthong(
    elem: ChainElement,
    sr: float,
    K_v: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Execute a pure diphthong (VV).

    Vocalic graph: V_o → V1 → V2 → V_e
    No consonantal branch.
    """
    from vtl_synth.core.trajectory_legacy import (
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment,
        execute_superposition_segment,
        params_to_array as _params_to_array,
    )
    from vtl_synth.core.polar import polar_arc as covtl_arc
    from vtl_synth.core.constants import CO_VTL

    v1_key = elem.nucleus_keys[0]
    v2_key = elem.nucleus_keys[1]

    vocalic_arcs, _ = _build_diphthong_vocalic_arcs(
        v1_key, v2_key,
        elem.rho_vo, elem.theta_vo,
        elem.rho_v, elem.theta_v,
        elem.rho_v2, elem.theta_v2,
        elem.rho_ve, elem.theta_ve,
        elem.diphthong_ratio,
        elem.duration_ms,
        K_v=K_v,
    )

    # Build the superposition segment (vocalic only)
    sup = SuperpositionSegment(
        consonant_arcs=[],
        vocalic_arcs=vocalic_arcs,
        selector_v=list(CO_VTL.keys()),
        selector_c=[],
        consonant_keys=[],
        vowel_key=v1_key,
    )

    params, n, zv = execute_superposition_segment(sup, sr)
    frames = _params_to_array(params, param_names, n)
    # rho_theta: use the real z_v trajectory
    if zv is not None and len(zv) == n:
        rt = np.column_stack([np.abs(zv), np.angle(zv)])
    else:
        rt = np.tile([elem.rho_v, elem.theta_v], (n, 1))
    return frames, rt


def _execute_onset_diphthong(
    elem: ChainElement,
    sr: float, K_v: float, K_c: float, nu_c: int,
    coefcen: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Execute a CVV syllable (onset + diphthong).

    Combines a standard CV graph (V_o → C → V1) with
    the diphthong transition (V1 → V2 → V_e).

    Consonantal branch: V_o → C → V2
    Vocalic branch     : V_o → V1 → V2 → V_e
    """
    from vtl_synth.core.trajectory_legacy import (
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment, ArcSpec,
        execute_superposition_segment,
        params_to_array as _params_to_array,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    v1_key = elem.nucleus_keys[0]
    v2_key = elem.nucleus_keys[1]
    onset_keys = elem.onset_keys

    # Check whether the consonants have COVTL selectors
    sel_set = set()
    consonant_arcs = []
    prev_rho, prev_theta = elem.rho_vo, elem.theta_vo

    for c_key in onset_keys:
        ct = _get_consonant_target(c_key, elem.theta_v)
        if ct is None:
            continue
        rho_c, theta_c = ct
        sel = _get_selector_list(c_key, elem.theta_v)
        if sel is not None:
            sel_set.update(sel)
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=rho_c, theta2=theta_c,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=c_key,
        ))
        prev_rho, prev_theta = rho_c, theta_c

    # Final arc C → V2 (the C branch targets V2, not V1)
    if consonant_arcs:
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=elem.rho_v2, theta2=elem.theta_v2,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=v2_key,
        ))

    if not sel_set or not consonant_arcs:
        # No selector (nasals, etc.) → vocalic only with diphthong
        return _execute_diphthong(elem, sr, K_v, param_names)

    sel_c = list(sel_set)
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    # Vocalic branch: V_o → V1 → V2 → V_e
    vocalic_arcs, v_total = _build_diphthong_vocalic_arcs(
        v1_key, v2_key,
        elem.rho_vo, elem.theta_vo,
        elem.rho_v, elem.theta_v,
        elem.rho_v2, elem.theta_v2,
        elem.rho_ve, elem.theta_ve,
        elem.diphthong_ratio,
        elem.duration_ms,
        K_v=K_v,
    )

    # Scale the consonantal arcs
    n_c_arcs = len(consonant_arcs)
    c_unit = elem.duration_ms / (n_c_arcs + 0)  # proportional
    # The C branch covers V_o→C→V2, same duration as the V branch
    for arc in consonant_arcs:
        arc.duration_ms = v_total / n_c_arcs

    sup = SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=vocalic_arcs,
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=onset_keys,
        vowel_key=v1_key,
    )

    params, n, zv = execute_superposition_segment(sup, sr)
    frames = _params_to_array(params, param_names, n)
    if zv is not None and len(zv) == n:
        rt = np.column_stack([np.abs(zv), np.angle(zv)])
    else:
        rt = np.tile([elem.rho_v, elem.theta_v], (n, 1))
    return frames, rt


def _execute_diphthong_coda(
    elem: ChainElement,
    sr: float, K_v: float, K_c: float, nu_c: int,
    coefcen: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Execute a VVC syllable (diphthong + coda).

    Graph:
        Consonantal: V1 → V2 → C1 → V_e
        Vocalic    : V_o → V1 → V2 → V_e
    """
    from vtl_synth.core.trajectory_legacy import (
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment, ArcSpec,
        execute_superposition_segment,
        params_to_array as _params_to_array,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    v1_key = elem.nucleus_keys[0]
    v2_key = elem.nucleus_keys[1]
    coda_keys = elem.coda_keys

    # Consonantal branch of the coda (from V2)
    sel_set = set()
    consonant_arcs = []
    prev_rho, prev_theta = elem.rho_v2, elem.theta_v2

    for c_key in coda_keys:
        ct = _get_consonant_target(c_key, elem.theta_v2)
        if ct is None:
            continue
        rho_c, theta_c = ct
        sel = _get_selector_list(c_key, elem.theta_v2)
        if sel is not None:
            sel_set.update(sel)
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=rho_c, theta2=theta_c,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=c_key,
        ))
        prev_rho, prev_theta = rho_c, theta_c

    # Final arc C → V_e
    if consonant_arcs:
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=elem.rho_ve, theta2=elem.theta_ve,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=coda_keys[-1],
        ))

    if not sel_set or not consonant_arcs:
        return _execute_diphthong(elem, sr, K_v, param_names)

    sel_c = list(sel_set)
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    # Vocalic branch
    vocalic_arcs, v_total = _build_diphthong_vocalic_arcs(
        v1_key, v2_key,
        elem.rho_vo, elem.theta_vo,
        elem.rho_v, elem.theta_v,
        elem.rho_v2, elem.theta_v2,
        elem.rho_ve, elem.theta_ve,
        elem.diphthong_ratio,
        elem.duration_ms,
        K_v=K_v,
    )

    # Scale consonantal arcs
    n_c_arcs = len(consonant_arcs)
    for arc in consonant_arcs:
        arc.duration_ms = v_total / n_c_arcs

    sup = SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=vocalic_arcs,
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=coda_keys,
        vowel_key=v1_key,
    )

    params, n, zv = execute_superposition_segment(sup, sr)
    frames = _params_to_array(params, param_names, n)
    if zv is not None and len(zv) == n:
        rt = np.column_stack([np.abs(zv), np.angle(zv)])
    else:
        rt = np.tile([elem.rho_v, elem.theta_v], (n, 1))
    return frames, rt


def _execute_onset_diphthong_coda(
    elem: ChainElement,
    sr: float, K_v: float, K_c: float, nu_c: int,
    coefcen: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Execute a CVVC syllable (onset + diphthong + coda).

    Combines CVV and VVC: the C branch covers V_o→C→V2,
    the coda adds C1→V_e.
    The V branch covers V_o→V1→V2→V_e.
    """
    # Approximation: execute as CVV + VC merged.
    # Split the duration: 60% for CVV, 40% for VVC
    from vtl_synth.core.trajectory_legacy import (
        execute_superposition_segment,
        params_to_array as _params_to_array,
        SuperpositionSegment, ArcSpec,
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import CO_VTL, AUTO_PARAMS

    v1_key = elem.nucleus_keys[0]
    v2_key = elem.nucleus_keys[1]
    dur_cv = elem.duration_ms * 0.6
    dur_vc = elem.duration_ms * 0.4

    # Part 1: CVV (onset + diphthong)
    elem_cv = ChainElement(
        onset_keys=elem.onset_keys,
        nucleus_key=v1_key,
        nucleus_keys=[v1_key, v2_key],
        diphthong_ratio=elem.diphthong_ratio,
        duration_ms=dur_cv,
        rho_v=elem.rho_v, theta_v=elem.theta_v,
        rho_v2=elem.rho_v2, theta_v2=elem.theta_v2,
        rho_vo=elem.rho_vo, theta_vo=elem.theta_vo,
        rho_ve=elem.rho_v2 * 0.7, theta_ve=elem.theta_v2,
    )
    frames_cv, rt_cv = _execute_onset_diphthong(
        elem_cv, sr, K_v, K_c, nu_c, coefcen, param_names)

    # Part 2: VC (from V2 to coda)
    if elem.coda_keys:
        sup_vc = _build_vc_graph(
            v2_key, elem.coda_keys,
            dur_vc, coefcen, K_v, K_c, nu_c,
        )
        params_vc, n_vc, zv_vc = execute_superposition_segment(sup_vc, sr)
        frames_vc = _params_to_array(params_vc, param_names, n_vc)
        if zv_vc is not None and len(zv_vc) == n_vc:
            rt_vc = np.column_stack([np.abs(zv_vc), np.angle(zv_vc)])
        else:
            rt_vc = np.tile([elem.rho_v2, elem.theta_v2], (n_vc, 1))
    else:
        frames_vc = np.zeros((0, len(param_names)))
        rt_vc = np.zeros((0, 2))

    return np.concatenate([frames_cv, frames_vc], axis=0), np.concatenate([rt_cv, rt_vc], axis=0)


# ==========================================================================
# Extended graphs (CCCV, VCC, CCVC, CVCC)
# ==========================================================================

def _build_cccv_graph(
    onset_keys: List[str],
    vowel_key: str,
    total_duration_ms: float,
    coefcen: float,
    K_v: float,
    K_c: float,
    nu_c: int,
) -> 'SuperpositionSegment':
    """Build the graph for a CCCV syllable (3 onset).

    Extension of the CCV scheme with a third consonantal arc.

    Branches (same duration = 4T):
        Consonantal: V_o → C1 → C2 → C3 → V (4 arcs)
        Vocalic     : V_o → V (1 arc, dur = 4T)
    """
    from vtl_synth.core.trajectory_legacy import (
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment, ArcSpec,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    rho_v, theta_v = VOWEL_TARGETS[vowel_key]

    # Resolve the consonantal targets and collect the selectors
    consonant_arcs = []
    consonant_keys = []
    sel_set = set()
    prev_rho, prev_theta = coefcen * rho_v, theta_v  # V_o

    for c_key in onset_keys:
        ct = _get_consonant_target(c_key, theta_v)
        if ct is None:
            continue
        rho_c, theta_c = ct
        sel = _get_selector_list(c_key, theta_v)
        if sel is not None:
            sel_set.update(sel)

        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=rho_c, theta2=theta_c,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=c_key,
        ))
        prev_rho, prev_theta = rho_c, theta_c
        consonant_keys.append(c_key)

    # Final arc: last C → V
    if consonant_arcs:
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=rho_v, theta2=theta_v,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=vowel_key,
        ))

    if not consonant_arcs or not sel_set:
        return _build_vocalic_only(vowel_key)

    sel_c = list(sel_set)
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    # Vocalic branch: V_o → V
    n_c_arcs = len(consonant_arcs)
    arc_v = ArcSpec(
        rho1=coefcen * rho_v, theta1=theta_v,
        rho2=rho_v, theta2=theta_v,
        duration_ms=float(n_c_arcs), K=K_v, nu=NU_DIRECT,
        orientation='inverse', selector='vocalic',
    )

    # Scale the durations so that total = total_duration_ms
    n_arcs_total = n_c_arcs + 1  # +1 for the vocalic
    unit_dur = total_duration_ms / n_arcs_total
    for arc in consonant_arcs:
        arc.duration_ms = unit_dur
    arc_v.duration_ms = unit_dur * n_c_arcs

    return SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=[arc_v],
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=consonant_keys,
        vowel_key=vowel_key,
    )


def _build_vc_graph(
    vowel_key: str,
    coda_keys: List[str],
    total_duration_ms: float,
    coefcen: float,
    K_v: float,
    K_c: float,
    nu_c: int,
) -> 'SuperpositionSegment':
    """Build the graph for a VC, VCC, VCCC, etc. syllable.

    Extension of the VC scheme with a variable number of
    coda consonants.

    Branches:
        Consonantal: V → C1 → [C2 → ...] → V_e (n_coda+1 arcs)
        Vocalic    : V → V_e (1 arc)
    """
    from vtl_synth.core.trajectory_legacy import (
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment, ArcSpec,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    rho_v, theta_v = VOWEL_TARGETS[vowel_key]
    V = (rho_v, theta_v)
    V_e = (coefcen * rho_v, theta_v)

    # Build the consonantal arcs of the coda
    consonant_arcs = []
    consonant_keys_list = []
    sel_set = set()
    prev_rho, prev_theta = V

    for c_key in coda_keys:
        ct = _get_consonant_target(c_key, theta_v)
        if ct is None:
            continue
        rho_c, theta_c = ct
        sel = _get_selector_list(c_key, theta_v)
        if sel is not None:
            sel_set.update(sel)

        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=rho_c, theta2=theta_c,
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=c_key,
        ))
        prev_rho, prev_theta = rho_c, theta_c
        consonant_keys_list.append(c_key)

    # Final arc: last C → V_e
    if consonant_arcs:
        consonant_arcs.append(ArcSpec(
            rho1=prev_rho, theta1=prev_theta,
            rho2=V_e[0], theta2=V_e[1],
            duration_ms=1.0, K=K_c, nu=nu_c,
            orientation='inverse', selector='consonantal',
            consonant_key=coda_keys[-1],
        ))

    if not consonant_arcs or not sel_set:
        seg = _build_vocalic_only(vowel_key)
        seg.vocalic_arcs[0].duration_ms = total_duration_ms
        return seg

    sel_c = list(sel_set)
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    # Vocalic branch: V → V_e
    n_c_arcs = len(consonant_arcs)
    arc_v = ArcSpec(
        rho1=V[0], theta1=V[1],
        rho2=V_e[0], theta2=V_e[1],
        duration_ms=float(n_c_arcs), K=K_v, nu=NU_DIRECT,
        orientation='inverse', selector='vocalic',
    )

    # Scale the durations
    n_arcs_total = n_c_arcs + 1
    unit_dur = total_duration_ms / n_arcs_total
    for arc in consonant_arcs:
        arc.duration_ms = unit_dur
    arc_v.duration_ms = unit_dur * n_c_arcs

    return SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=[arc_v],
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=consonant_keys_list,
        vowel_key=vowel_key,
    )


def _build_ccvc_graph(
    onset_keys: List[str],
    vowel_key: str,
    coda_keys: List[str],
    total_duration_ms: float,
    coefcen: float,
    K_v: float,
    K_c: float,
    nu_c: int,
) -> 'SuperpositionSegment':
    """Build the graph for a CCVC syllable.

    Combines the CCV onset with the VC coda in two consecutive
    superposition segments.

    Segment 1 (onset CCV)  : V_o → C1 → C2 → V
    Segment 2 (coda VC)   : V → C3 → V_e
    """
    from vtl_synth.core.trajectory_legacy import (
        build_ccv_graph, scale_durations as _scale_durations,
        get_consonant_target as _get_consonant_target,
        get_selector_list as _get_selector_list,
        build_vocalic_only as _build_vocalic_only,
        SuperpositionSegment, ArcSpec,
        execute_superposition_segment,
        params_to_array as _params_to_array,
        extract_rho_theta as _extract_rho_theta,
    )
    from vtl_synth.core.polar import NU_DIRECT
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    # Segment 1 is a standard CCV
    n_onset = len(onset_keys)
    if n_onset >= 3:
        sup1 = _build_cccv_graph(
            onset_keys, vowel_key,
            total_duration_ms * 0.6, coefcen, K_v, K_c, nu_c,
        )
    elif n_onset == 2:
        sup1 = build_ccv_graph(
            vowel_key, onset_keys[0], onset_keys[1],
            delta_o=coefcen, K_v=K_v, K_c=K_c, nu_c=nu_c,
        )
        from vtl_synth.core.trajectory_legacy import scale_durations as _sd
        _sd(sup1, total_duration_ms * 0.6)
    else:
        from vtl_synth.core.trajectory_legacy import build_cv_graph, scale_durations as _sd
        sup1 = build_cv_graph(
            vowel_key, onset_keys[0],
            delta_o=coefcen, K_v=K_v, K_c=K_c, nu_c=nu_c,
        )
        _sd(sup1, total_duration_ms * 0.6)

    # Segment 2 is a VC
    sup2 = _build_vc_graph(
        vowel_key, coda_keys,
        total_duration_ms * 0.4, coefcen, K_v, K_c, nu_c,
    )

    # Merge the two segments into a single SuperpositionSegment
    # by concatenating the arcs
    merged_consonant_arcs = sup1.consonant_arcs + sup2.consonant_arcs
    merged_vocalic_arcs = sup1.vocalic_arcs + sup2.vocalic_arcs

    # Merged selectors
    sel_c = list(set(sup1.selector_c) | set(sup2.selector_c))
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    return SuperpositionSegment(
        consonant_arcs=merged_consonant_arcs,
        vocalic_arcs=merged_vocalic_arcs,
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=sup1.consonant_keys + sup2.consonant_keys,
        vowel_key=vowel_key,
    )


def _build_cvc_extended_graph(
    onset_keys: List[str],
    vowel_key: str,
    coda_keys: List[str],
    total_duration_ms: float,
    coefcen: float,
    K_v: float,
    K_c: float,
    nu_c: int,
) -> 'SuperpositionSegment':
    """Build the graph for CVCC (simple onset + extended coda).

    Segment 1 (onset CV)   : V_o → C1 → V
    Segment 2 (coda VCC)  : V → C2 → C3 → V_e
    """
    from vtl_synth.core.trajectory_legacy import (
        build_cv_graph, scale_durations as _scale_durations,
        SuperpositionSegment,
    )
    from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL, AUTO_PARAMS

    sup1 = build_cv_graph(
        vowel_key, onset_keys[0],
        delta_o=coefcen, K_v=K_v, K_c=K_c, nu_c=nu_c,
    )
    _scale_durations(sup1, total_duration_ms * 0.55)

    sup2 = _build_vc_graph(
        vowel_key, coda_keys,
        total_duration_ms * 0.45, coefcen, K_v, K_c, nu_c,
    )

    merged_consonant_arcs = sup1.consonant_arcs + sup2.consonant_arcs
    merged_vocalic_arcs = sup1.vocalic_arcs + sup2.vocalic_arcs

    sel_c = list(set(sup1.selector_c) | set(sup2.selector_c))
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    return SuperpositionSegment(
        consonant_arcs=merged_consonant_arcs,
        vocalic_arcs=merged_vocalic_arcs,
        selector_v=sel_v, selector_c=sel_c,
        consonant_keys=sup1.consonant_keys + sup2.consonant_keys,
        vowel_key=vowel_key,
    )


# ==========================================================================
# Transition arcs and pauses
# ==========================================================================

def _build_transition_arc(
    rho_from: float,
    theta_from: float,
    rho_to: float,
    theta_to: float,
    duration_ms: float,
    sr: float,
    K_v: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a vocalic transition arc between two anchors.

    This arc ensures flow continuity between two concatenated
    syllables. It is a vocalic arc (V branch only)
    in the complex plane.

    Parameters
    ----------
    rho_from, theta_from : float
        Polar coordinates of the start anchor (V_e).
    rho_to, theta_to : float
        Polar coordinates of the arrival anchor (V_o).
    duration_ms : float
        Duration of the transition arc (ms).
    sr : float
        Sampling rate.
    K_v : float
        Vocalic curvature.
    param_names : list[str]
        Names of the output parameters.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (tract_frames, rho_theta)
    """
    from vtl_synth.core.polar import polar_arc as covtl_arc
    from vtl_synth.core.projection import project_covtl
    from vtl_synth.core.constants import CO_VTL

    # Simple vocalic arc
    z, rho_t = covtl_arc(
        rho_from, theta_from,
        rho_to, theta_to,
        duration_ms, sr,
        K=K_v, nu=1, orientation='inverse',
    )

    # Project via COVTL (full vocalic branch)
    n = len(z)
    frames = np.zeros((n, len(param_names)), dtype=np.float64)
    for j, p in enumerate(param_names):
        if p in CO_VTL:
            c1, c0, c2 = CO_VTL[p]
            psi = c0 * np.exp(1j * c2)
            frames[:, j] = c1 + np.real(psi * np.conj(z))

    # rho_theta from the complex trajectory
    rt = np.zeros((n, 2), dtype=np.float64)
    rt[:, 0] = np.abs(z)      # rho
    rt[:, 1] = np.angle(z)     # theta

    return frames, rt


def _generate_pause(
    duration_ms: float,
    sr: float,
    prev_rho: Optional[float],
    prev_theta: Optional[float],
    K_v: float,
    param_names: List[str],
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate pause frames as a continuous vocalic arc.

    In the Berthommier COVTL model, a pause is NOT
    a transition to a neutral position. It is a hold of the
    V_e vocalic position of the previous syllable, forming a
    continuous vocalic arc. The z(t) trajectory stays on the
    vocalic branch for the whole duration of the pause.

    Parameters
    ----------
    duration_ms : float
        Duration of the pause (ms).
    sr : float
        Sampling rate.
    prev_rho, prev_theta : float or None
        V_e polar position before the pause. If None, uses
        the schwa (rho=0.42, theta=pi).
    K_v : float
        Vocalic curvature (unused for the stationary point).
    param_names : list[str]
        Names of the output parameters.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (tract_frames, rho_theta)
    """
    from vtl_synth.core.polar import stationary_point
    from vtl_synth.core.constants import CO_VTL

    # If no previous position, use the schwa as the resting point
    if prev_rho is None or prev_theta is None:
        prev_rho = 0.42
        prev_theta = np.pi

    # Continuous vocalic arc: hold of V_e (stationary point)
    n_frames = max(1, int(duration_ms * sr / 1000.0))
    z_pause = prev_rho * np.exp(1j * prev_theta)
    z_arr = np.full(n_frames, z_pause, dtype=np.complex128)

    # COVTL projection via the vocalic branch
    frames = np.zeros((n_frames, len(param_names)), dtype=np.float64)
    for j, p in enumerate(param_names):
        if p in CO_VTL:
            c1, c0, c2 = CO_VTL[p]
            psi = c0 * np.exp(1j * c2)
            frames[:, j] = c1 + np.real(psi * np.conj(z_arr))

    # rho/theta from z_v (vocalic branch)
    rt = np.zeros((n_frames, 2), dtype=np.float64)
    rt[:, 0] = np.abs(z_arr)
    rt[:, 1] = np.angle(z_arr)

    return frames, rt


# ==========================================================================
# Part 4 — Main entry point
# ==========================================================================

def parse_to_tract_trajectory(
    ipa_str: str,
    sr: float = 100.0,
    K_v: float = 30.0,
    K_c: float = 10.0,
    nu_c: int = 1,
    coefcen: float = COEFCEN,
    pause_duration_ms: float = DEFAULT_PAUSE_DURATION_MS,
    phrase_pause_duration_ms: Optional[float] = None,
    vowel_duration_ms: float = DEFAULT_VOWEL_DURATION_MS,
    consonant_durations: Optional[Dict[str, float]] = None,
    add_phrase_anchors: bool = True,
    verbose: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Main entry point: IPA with markers → continuous trajectory.

    Full parsing pipeline:

      1. parse_ipa_with_markers()   →  ParseToken[]
      2. syllabify_continuous()      →  ChainElement[]
      3. _chain_elements_to_pval()   → (tract, rho_theta, block_info)

    Parameters
    ----------
    ipa_str : str
        IPA string with markers.
        Space = inter-word pause, '.' = intra-word coarticulation.
        Start/end '|' anchors are added automatically.
        Examples: 'ba.bi.bu' (coarticulation), 'ba bi' (inter-word pause),
                  'ba.bi ku.pi' (mixed)
    sr : float
        Sampling rate (Hz). Default: 100.
    K_v, K_c : float
        Vocalic/consonantal curvature.
    nu_c : int
        Consonantal curvature orientation.
    coefcen : float
        rho reduction coefficient at syllable boundaries.
    pause_duration_ms : float
        Default duration of an inter-word pause (ms).
    phrase_pause_duration_ms : float, optional
        Duration of the phrase start/end anchor pause (ms).
        If None, uses pause_duration_ms.
    vowel_duration_ms : float
        Default duration of vowels (ms).
    consonant_durations : dict, optional
        Specific durations per consonant.
    add_phrase_anchors : bool
        If True (default), adds '|' anchors at start and end.
    verbose : bool
        Display parsing information.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, list]
        (tract_frames, rho_theta_frames, block_info)
        - tract_frames : (T, N_tract_params)
        - rho_theta_frames : (T, 2)
        - block_info : list[BlockInfo]

    Examples
    --------
    >>> tract, rt, bi = parse_to_tract_trajectory('ba.bi.bu')
    >>> tract, rt, bi = parse_to_tract_trajectory('ba bi')  # inter-word pause
    >>> tract, rt, bi = parse_to_tract_trajectory('badiba')  # auto
    """
    # Step 1: Parsing
    tokens = parse_ipa_with_markers(
        ipa_str,
        pause_duration_ms=pause_duration_ms,
        phrase_pause_duration_ms=phrase_pause_duration_ms,
        vowel_duration_ms=vowel_duration_ms,
        consonant_durations=consonant_durations,
        add_phrase_anchors=add_phrase_anchors,
    )

    if verbose:
        print(f'[parsing] Tokens ({len(tokens)}): '
              f'{[(t.key, t.kind, t.duration_ms) for t in tokens]}')

    # Step 2: Continuous syllabification
    elements = syllabify_continuous(tokens, coefcen=coefcen)

    if verbose:
        for elem in elements:
            if elem.is_pause:
                print(f'  PAUSE  dur={elem.pause_duration_ms:.0f}ms')
            else:
                print(f'  {elem.structure_type:6s} '
                      f'onset={elem.onset_keys} '
                      f'nuc={elem.nucleus_key} '
                      f'coda={elem.coda_keys} '
                      f'dur={elem.duration_ms:.0f}ms '
                      f'trans={elem.transition_from_prev} '
                      f'V_o=({elem.rho_vo:.3f},{elem.theta_vo:.2f}) '
                      f'V_e=({elem.rho_ve:.3f},{elem.theta_ve:.2f})')

    # Step 3: Trajectory construction (new gestures+anchors pipeline)
    tract, rho_theta, block_info = _chain_elements_to_pval(
        elements, sr=sr, nu_c=nu_c, K_v=K_v, K_c=K_c, coefcen=coefcen,
    )

    if verbose:
        print(f'[parsing] Trajectory: {tract.shape} at {sr} Hz, '
              f'{len(tract)/sr*1000:.1f} ms')
        print(f'[parsing] block_info: {len(block_info)} blocks')

    # Store block_info and timer_data for later access by callers
    parse_to_tract_trajectory.last_block_info = block_info

    # Retrieve the TimerData containing the three timers (central state)
    timer_data = get_last_timer_data()
    parse_to_tract_trajectory.last_timer_data = timer_data

    if verbose and timer_data is not None:
        from vtl_synth.core.timers import (
            print_voicing_timer, print_nasality_timer, print_lateral_timer,
        )
        print_voicing_timer(timer_data.voicing_marks)
        print_nasality_timer(timer_data.nasality_marks)
        print_lateral_timer(timer_data.lateral_marks)
    elif verbose:
        print('[parsing] TimerData not available')

    return tract, rho_theta, block_info


def parse_to_segments(
    ipa_str: str,
    pause_duration_ms: float = DEFAULT_PAUSE_DURATION_MS,
    phrase_pause_duration_ms: Optional[float] = None,
    vowel_duration_ms: float = DEFAULT_VOWEL_DURATION_MS,
    consonant_durations: Optional[Dict[str, float]] = None,
    add_phrase_anchors: bool = True,
) -> Tuple[List, List[ChainElement]]:
    """Parse IPA and return the segments AND the chain elements.

    Version compatible with the existing API: returns both
    the Segment objects (for ProsodySource) and the ChainElement objects
    (for continuous flow tracking).

    Parameters
    ----------
    ipa_str : str
        IPA string with markers.
        Space = inter-word pause. '|' anchors are added
        automatically at phrase start and end.
    pause_duration_ms : float
        Default duration of an inter-word pause.
    phrase_pause_duration_ms : float, optional
        Duration of the phrase start/end anchor pause.
    vowel_duration_ms : float
        Default duration of vowels.
    consonant_durations : dict, optional
        Specific durations per consonant.
    add_phrase_anchors : bool
        If True (default), adds '|' anchors at start and end.

    Returns
    -------
    tuple[list[Segment], list[ChainElement]]
        (segments, chain_elements)
        - segments : Segment objects (for ProsodySource, without pauses)
        - chain_elements : ChainElement objects (for the trajectory)
    """
    from vtl_synth.core.prosody_source import Segment

    tokens = parse_ipa_with_markers(
        ipa_str,
        pause_duration_ms=pause_duration_ms,
        phrase_pause_duration_ms=phrase_pause_duration_ms,
        vowel_duration_ms=vowel_duration_ms,
        consonant_durations=consonant_durations,
        add_phrase_anchors=add_phrase_anchors,
    )

    elements = syllabify_continuous(tokens)

    # Create the segments (without pauses NOR coarticulations)
    segments = []
    t = 0.0
    for tok in tokens:
        if tok.token_type in (TokenType.PAUSE, TokenType.COARTICULATION):
            continue
        seg = Segment(
            key=tok.key,
            kind=tok.kind,
            duration_ms=tok.duration_ms,
            t_start=t,
            t_end=t + tok.duration_ms,
        )
        segments.append(seg)
        t += tok.duration_ms

    return segments, elements


# ==========================================================================
# State of the last parsing (RISK-001: centralized and read via accessors)
# ==========================================================================
# Populated by _chain_elements_to_pval(); callers (text_to_tract,
# build_phrase_tract) read via get_last_pval_state()/get_last_timer_data()
# instead of fetching private attributes on the function.
_LAST_PVAL_STATE: Dict[str, object] = {}


def get_last_pval_state() -> Tuple[list, list]:
    """Return the (nodes, anchors) produced by the last call to
    _chain_elements_to_pval (empty lists if no parsing was done)."""
    return _LAST_PVAL_STATE.get('nodes', []), _LAST_PVAL_STATE.get('anchors', [])


def get_last_timer_data():
    """Return the TimerData of the last parsing (None if unavailable)."""
    return _LAST_PVAL_STATE.get('timer_data')


def _chain_elements_to_pval(
    elements: list,
    sr: float = 100.0,
    nu_c: int = 1,
    K_v: float = 30.0,
    K_c: float = 10.0,
    coefcen: float = COEFCEN,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build the trajectory via build_global_pval (COVTL reference).

    Uses gesture.build_gesture_nodes and gesture.build_gesture_anchors
    for proper anchor encoding, following the COVTL reference
    pipeline.  This ensures correct V_o computation (context-dependent
    rho reduction) and syllable-respecting anchor placement.

    Parameters
    ----------
    elements : list[ChainElement]
        Chain produced by syllabify_continuous().
    sr : float
        Sampling rate (Hz).
    nu_c, K_v, K_c : curvature.
    coefcen : COEFCEN coefficient.

    Returns
    -------
    (tract_frames, rho_theta_frames, block_info)
    """
    from vtl_synth.core.constants import COVTL_PARAMS, VOWEL_TARGETS
    from vtl_synth.core.projection import get_selector_list, get_consonant_target
    from vtl_synth.core.trajectory import build_global_pval
    from vtl_synth.core.gesture import build_gesture_nodes, build_gesture_anchors
    from vtl_synth.core.types import GestureNode, GestureAnchor, PolarTarget, SyllableBoundary, BoundaryDirection
    from vtl_synth.core.constants import TCONS_DEFAULT, TVOY_DEFAULT

    _covtl_name_to_idx = {n: i for i, n in enumerate(COVTL_PARAMS)}

    # Timing (in frames at sr)
    # NOTE — These are the MASTER values of articulatory timing.
    # T_cons and T_voy control the duration of each block in
    # build_global_pval(), and hence the total number of frames.
    # The CONSONANT_DURATIONS (above) have no effect here.
    from vtl_synth.core.polar import T_BASE_DEFAULT
    T_cons = max(1, int(round(0.160 * sr)))       # 16 frames at 100Hz (160ms)
    T_voy = max(1, int(round(0.160 * sr)))       # 16 frames at 100Hz (160ms)
    T_pause_short = max(1, int(round(0.100 * sr)))    # 10 frames at 100Hz (100ms) — inter-syllabic
    T_pause_long = max(1, int(round(0.200 * sr)))     # 20 frames at 100Hz (200ms) — phrase boundaries
    Pexp = 2

    # ==================================================================
    # Step 1: Build flat_segments and all_polars from ChainElements
    # ==================================================================
    flat_segments: list[str] = []
    all_polars: list[PolarTarget] = []
    flat_theta_v: list[float] = []  # theta_vowel for each flat segment
    word_starts: list[int] = []   # flat indices where words start
    syl_boundaries: set[int] = set()  # flat indices of syllable starts

    # Track per-syllable segment lists for SyllableBoundary construction
    syl_segments_list: list[list[str]] = []
    current_syl_segs: list[str] = []
    in_word = False
    word_start_idx = 0

    elem_idx = 0
    for elem in elements:
        if elem.is_pause:
            # Pause marker in flat segments
            flat_segments.append('|')
            in_word = False
            # Finalize current syllable segments
            if current_syl_segs:
                syl_segments_list.append(list(current_syl_segs))
                current_syl_segs = []
            elem_idx += 1
            continue

        # Start of a new word
        if not in_word:
            word_start_idx = len(flat_segments)
            word_starts.append(word_start_idx)
            in_word = True

        # Mark syllable boundary
        syl_boundaries.add(len(flat_segments))

        # Onset consonants
        for ck in elem.onset_keys:
            ct = get_consonant_target(ck, elem.theta_v)
            if ct is None:
                continue
            rho_c, theta_c = ct
            flat_segments.append(ck)
            flat_theta_v.append(elem.theta_v)
            all_polars.append(PolarTarget(rho_c, theta_c, f'C_{ck}', is_vowel=False))
            current_syl_segs.append(ck)

        # Nucleus vowel
        if elem.nucleus_key in VOWEL_TARGETS:
            rv, tv = VOWEL_TARGETS[elem.nucleus_key]
            flat_segments.append(elem.nucleus_key)
            flat_theta_v.append(elem.theta_v)
            all_polars.append(PolarTarget(rv, tv, f'V_{elem.nucleus_key}', is_vowel=True))
            current_syl_segs.append(elem.nucleus_key)

        # Coda consonants
        for ck in elem.coda_keys:
            ct = get_consonant_target(ck, elem.theta_v)
            if ct is None:
                continue
            rho_c, theta_c = ct
            flat_segments.append(ck)
            flat_theta_v.append(elem.theta_v)
            all_polars.append(PolarTarget(rho_c, theta_c, f'C_{ck}', is_vowel=False))
            current_syl_segs.append(ck)

        # End of syllable — save segments
        syl_segments_list.append(list(current_syl_segs))
        current_syl_segs = []
        elem_idx += 1

    # ==================================================================
    # Step 2: Build SyllableBoundary info for gesture anchors
    # ==================================================================
    syl_boundary_info: list[SyllableBoundary] = []
    syl_bound_list = sorted(syl_boundaries)
    for si in range(1, len(syl_segments_list)):
        prev_segs = syl_segments_list[si - 1]
        curr_segs = syl_segments_list[si]
        flat_idx = syl_bound_list[si] if si < len(syl_bound_list) else len(flat_segments)

        sb = SyllableBoundary(
            direction=BoundaryDirection.SYLLABLE_JUNCTION,
            anchor_from=GestureAnchor(i=0, kind='V'),  # placeholder
            anchor_to=GestureAnchor(i=flat_idx, kind='V'),  # placeholder
            curr_segments=curr_segs,
            prev_segments=prev_segs,
            flat_idx=flat_idx,
        )
        syl_boundary_info.append(sb)

    # ==================================================================
    # Step 3: Build gesture nodes and anchors via reference gesture.py
    # ==================================================================
    nodes = build_gesture_nodes(flat_segments, all_polars, syl_boundaries)
    anchors = build_gesture_anchors(
        nodes,
        word_starts=word_starts,
        syl_boundary_info=syl_boundary_info if syl_boundary_info else None,
    )

    # ==================================================================
    # Step 4: Add COVTL selector params to consonant nodes
    # ==================================================================
    for nd in nodes:
        if nd.kind == 'C':
            tv = flat_theta_v[nd.i] if nd.i < len(flat_theta_v) else 0.0
            sel = get_selector_list(nd.seg_key, tv)
            if sel:
                nd.params = sorted([_covtl_name_to_idx[p] for p in sel])

    # ==================================================================
    # Step 5: Ensure hold=True for vowel nuclei that follow consonants
    # ==================================================================
    # In the reference pipeline, _create_base_anchors sets hold=True
    # when the vowel is not adjacent to another vowel.
    # For CV syllables, the nucleus vowel should always hold.
    # Skip word_end and vowel_onset anchors.
    for ai, a in enumerate(anchors):
        if (a.kind == 'V' and not a.is_vowel_onset and not a.is_word_end
                and not a.hold):
            # Check if there's a consonant before this vowel
            if a.i > 0 and a.i - 1 < len(nodes) and nodes[a.i - 1].kind == 'C':
                anchors[ai] = GestureAnchor(
                    i=a.i, pt=a.pt, hold=True, kind='V',
                    is_vowel_onset=a.is_vowel_onset,
                    is_syl_vowel_onset=a.is_syl_vowel_onset,
                    is_word_end=a.is_word_end,
                    long=a.long,
                )

    # ==================================================================
    # Step 5.5: Build the timers (voicing, nasality, laterality)
    # ==================================================================
    # The three timers are built at the parsing level, before
    # build_global_pval(). For each consonant, the voicing timer
    # computes the time at which the target is reached. For each
    # nasal, the nasality timer gives the start and end times.
    # For each lateral, the lateral timer gives the occlusion mark.
    #
    # The timers are stored as TimerData (containing the three
    # lists of marks) for later use by
    # glottal_source.compute_pulmonary_effort() and
    # assemble_tract.py.
    from vtl_synth.core.timers import build_all_timers
    timer_data = build_all_timers(elements, sr=sr)
    _LAST_PVAL_STATE['timer_data'] = timer_data

    # ==================================================================
    # Step 6: Call build_global_pval
    # ==================================================================
    Pval, last_pt, block_info = build_global_pval(
        nodes, anchors,
        T_cons=T_cons,
        T_voy=T_voy,
        T_pause_short=T_pause_short,
        T_pause_long=T_pause_long,
        nu=nu_c,
        K=int(K_c),
        Kvoy=int(K_v),
        Pexp=Pexp,
    )

    # Store block_info, nodes, anchors for access (RISK-001: central state
    # read via get_last_pval_state(), no more scattered private attributes)
    _chain_elements_to_pval.last_block_info = block_info
    _LAST_PVAL_STATE.clear()
    _LAST_PVAL_STATE.update(nodes=nodes, anchors=anchors, timer_data=timer_data)

    # ==================================================================
    # Step 7: Extract rho_theta from Pval via TCX/TCY (inverse COVTL)
    # ==================================================================
    n_frames = Pval.shape[0]
    rho_theta = np.zeros((n_frames, 2), dtype=np.float64)
    idx_tcx = _covtl_name_to_idx.get('TCX')
    idx_tcy = _covtl_name_to_idx.get('TCY')
    if idx_tcx is not None and idx_tcy is not None:
        from vtl_synth.core.constants import CO_VTL
        c1_tcx, c0_tcx, c2_tcx = CO_VTL['TCX']
        c1_tcy, c0_tcy, c2_tcy = CO_VTL['TCY']
        tcx = Pval[:, idx_tcx]
        tcy = Pval[:, idx_tcy]
        dx = tcx - c1_tcx
        dy = tcy - c1_tcy
        A_mat = np.array([
            [np.cos(c2_tcx), np.sin(c2_tcx)],
            [np.cos(c2_tcy), np.sin(c2_tcy)],
        ])
        det = A_mat[0, 0] * A_mat[1, 1] - A_mat[0, 1] * A_mat[1, 0]
        if abs(det) > 1e-10:
            Ainv = np.array([[A_mat[1, 1], -A_mat[0, 1]],
                             [-A_mat[1, 0], A_mat[0, 0]]]) / det
            xy = Ainv @ np.stack([dx, dy], axis=0)
            rho_theta[:, 0] = np.sqrt(xy[0] ** 2 + xy[1] ** 2)
            rho_theta[:, 1] = np.arctan2(xy[1], xy[0])
        else:
            rho_theta = _extract_rho_from_anchors(anchors, n_frames)
    else:
        rho_theta = _extract_rho_from_anchors(anchors, n_frames)

    return Pval, rho_theta, block_info


def _extract_rho_from_anchors(anchors: list, n_frames: int) -> np.ndarray:
    """Extract rho_theta by interpolation between the anchors."""
    if not anchors:
        return np.zeros((max(n_frames, 1), 2))
    valid = [(a, a.pt) for a in anchors
             if a.pt is not None and a.kind not in ('pause', 'synth')]
    if not valid:
        return np.zeros((n_frames, 2))
    rt = np.zeros((n_frames, 2))
    n_ancres = len(valid)
    for i, (a, pt) in enumerate(valid):
        start_f = int(i / n_ancres * n_frames)
        end_f = int((i + 1) / n_ancres * n_frames)
        start_f = min(start_f, n_frames)
        end_f = min(end_f, n_frames)
        if end_f > start_f:
            rt[start_f:end_f, 0] = pt[0]
            rt[start_f:end_f, 1] = pt[1]
    return rt
