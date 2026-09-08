# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
types.py
=========
Data types for the Berthommier gesture system.

This module defines the intermediate structures between
syllabification (phonology.py) and trajectory construction
(trajectory.py — build_global_pval).

Main structures:
  - PolarTarget     : (rho, theta) target in the complex plane
  - GestureNode     : gesture node with target and active params
  - GestureAnchor   : time anchor (build_global_pval format)
  - BlockInfo       : per-block metadata for the envelope
  - GestureSyllable : syllable described as gestures and anchors (legacy)

NOTE: GestureAnchor and GestureNode have two sets of fields:
  - The "legacy" fields (rho, theta, label, node) used by
    gesture.py and the old trajectory.py.
  - The "ref" fields (kind, pt, i, hold, long, etc.) used
    by the new trajectory.py (build_global_pval).
  Both coexist for progressive migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union

import numpy as np


# ==========================================================================
# Polar target
# ==========================================================================

@dataclass
class PolarTarget:
    """(rho, theta) target in the Berthommier complex plane.

    Attributes
    ----------
    rho : float
        Polar radius (0 to ~1.3).
    theta : float
        Polar angle (rad), in [0, 2pi).
    label : str
        Descriptive label (e.g. 'V_a', 'C_b', 'V_o').
    is_vowel : bool
        True if this target is vocalic.
    """
    rho: float
    theta: float
    label: str = ''
    is_vowel: bool = True

    def to_complex(self) -> complex:
        return self.rho * np.exp(1j * self.theta)

    def copy(self) -> 'PolarTarget':
        return PolarTarget(self.rho, self.theta, self.label, self.is_vowel)


# ==========================================================================
# Gesture type
# ==========================================================================

class GestureKind(Enum):
    """Articulatory gesture type."""
    VOCALIC = 'vocalic'
    CONSONANTAL = 'consonantal'
    BOUNDARY = 'boundary'
    STEADY_STATE = 'steady'


# ==========================================================================
# BlockInfo — metadata for build_global_pval
# ==========================================================================

@dataclass
class BlockInfo:
    """Metadata for a block of the Pval trajectory.

    Used by build_global_pval() to inform the construction
    of the glottal envelope.

    Attributes
    ----------
    n_steps : int
        Number of time steps.
    kind : str
        Block type: 'plateau', 'background', 'cluster',
        'pause', 'initial', 'terminal', 'decay', 'attack'.
    n_cons : int, optional
        Number of consonants in a cluster.
    cons_tokens : list, optional
        Consonantal tokens.
    pre_token : str, optional
        Preceding token ('V', 'O', 'y').
    post_token : str, optional
        Following token ('V', 'O', 'y', 'F').
    pre_amp : float, optional
        Signal amplitude before the block.
    post_amp : float, optional
        Signal amplitude after the block.
    long : bool, optional
        Long pause.
    has_following_plateau : bool, optional
        A plateau follows this block.
    """
    n_steps: int = 0
    kind: str = ''
    n_cons: int = 0
    cons_tokens: list = field(default_factory=list)
    pre_token: str = ''
    post_token: str = ''
    pre_amp: float = 0.0
    post_amp: float = 0.0
    long: bool = False
    has_following_plateau: bool = False


# ==========================================================================
# Gesture node
# ==========================================================================

@dataclass
class GestureNode:
    """Gesture node: a phoneme with its target and role.

    This dataclass serves both the legacy pipeline (gesture.py)
    and the new pipeline (build_global_pval).

    Attributes
    ----------
    kind : str
        'V' for vowel, 'C' for consonant, 'pause', 'synth'.
    key / seg_key : str
        IPA key of the phoneme. Canonical field: ``seg_key`` (RISK-005,
        2026-09-04); ``key`` is now only a read alias.
    rho, theta : float
        Polar coordinates (used by build_global_pval).
    params : list[int]
        Indices of active COVTL parameters (used by arc_B).
    target : PolarTarget or None
        Polar target (legacy).
    gesture_kind : GestureKind
        Gesture type (legacy).
    duration_ms : float
        Phoneme duration (ms).
    t_start, t_end : float
        Absolute time (ms).
    syllable_idx : int
        Syllable index.
    position_in_syllable : str
        'onset', 'nucleus', 'coda'.
    selector : list[str] or None
        List of selected COVTL parameters (legacy).
    i : int
        Index in the global sequence (build_global_pval).
    """
    # --- Common fields ---
    # RISK-005: seg_key is the canonical field; `key` is a read alias
    # (property below) for trajectory_legacy compatibility.
    seg_key: str = ''
    kind: str = 'V'

    # --- build_global_pval fields ---
    rho: float = 0.0
    theta: float = 0.0
    params: List[int] = field(default_factory=list)
    i: int = 0
    in_cluster: bool = False

    # --- Legacy fields ---
    target: Optional[PolarTarget] = None
    gesture_kind: GestureKind = GestureKind.VOCALIC
    duration_ms: float = 100.0
    t_start: float = 0.0
    t_end: float = 0.0
    syllable_idx: int = 0
    position_in_syllable: str = 'nucleus'
    selector: Optional[List[str]] = None
    virtual_target: Optional[dict] = None

    @property
    def key(self) -> str:
        """Read alias of the canonical field ``seg_key``."""
        return self.seg_key

    @property
    def is_vowel(self) -> bool:
        return self.kind == 'V'

    @property
    def has_selector(self) -> bool:
        return self.selector is not None and len(self.selector) > 0


# ==========================================================================
# Gesture anchor (build_global_pval format)
# ==========================================================================

@dataclass
class GestureAnchor:
    """Time anchor for build_global_pval.

    In the new pipeline, anchors mark the departure/arrival
    points of arcs. The ``pt`` field contains
    [rho, theta]. The flags control processing
    in build_global_pval.

    Attributes
    ----------
    kind : str
        'V' (vowel), 'C' (consonant), 'pause', 'synth'.
    pt : list[float] or None
        [rho, theta]. None for synth terminals.
    i : int
        Index in the node sequence.
    label : str
        Semantic label of the anchor:
        'V_o' (initial/anticipation vowel),
        'V'   (vocalic nucleus),
        'V_e' (final vowel),
        'C_k' (consonant, k = IPA key),
        'pause_start' / 'pause_end' / 'pause_inter',
        'synth_start' / 'synth_end'.
    is_vowel_onset : bool
        True if this is a V_o (anticipation vowel).
    is_syl_vowel_onset : bool
        True if this is the V_o of a syllable.
    is_word_end : bool
        True if this is the end of a word.
    hold : bool
        True if a (sustain) plateau follows this anchor.
    long : bool
        True if this is a long pause.
    pause_role : str
        Role of the pause: 'phrase_start', 'phrase_end',
        'interword', '' (not a pause).
    seg_key : str
        IPA key of the associated segment (empty if no segment).

    --- Legacy fields (gesture.py compatibility) ---
    rho, theta : float
    t_ms : float or None
        Absolute time in ms (assignable by assign_anchor_times).
    node : GestureNode or None
    """
    # --- build_global_pval fields ---
    kind: str = 'V'
    pt: Optional[List[float]] = None
    i: int = 0
    is_vowel_onset: bool = False
    is_syl_vowel_onset: bool = False
    is_word_end: bool = False
    hold: bool = False
    long: bool = False
    label: str = ''  # Auto-generated by _auto_label() if empty
    pause_role: str = ''
    seg_key: str = ''

    # --- Legacy fields ---
    rho: float = 0.0
    theta: float = 0.0
    t_ms: Optional[float] = None
    node: Optional[GestureNode] = None

    def __post_init__(self):
        if self.pt is None:
            self.pt = [self.rho, self.theta]
        else:
            self.rho = self.pt[0]
            self.theta = self.pt[1]
        # Auto-label if not set
        if not self.label:
            self.label = self._auto_label()

    def _auto_label(self) -> str:
        """Generate a default label from kind and flags."""
        if self.kind == 'synth':
            return 'synth_start' if self.i < 0 else 'synth_end'
        if self.kind == 'pause':
            if self.pause_role:
                return f'pause_{self.pause_role}'
            return 'pause_inter'
        if self.kind == 'V':
            if self.is_vowel_onset:
                return 'V_o'
            if self.is_word_end:
                return 'V_e'
            return 'V'
        if self.kind == 'C' and self.seg_key:
            return f'C_{self.seg_key}'
        return self.kind

    def to_polar_target(self) -> PolarTarget:
        return PolarTarget(self.rho, self.theta, self.label)

    def to_complex(self) -> complex:
        return self.rho * np.exp(1j * self.theta)


def _arc_duration_ms(a: GestureAnchor, b: GestureAnchor,
                      T_cons: float, T_voy: float,
                      T_pause_short: float, T_pause_long: float) -> float:
    """Estimate the arc duration between two anchors."""
    # Pause or terminal
    if a.kind in ('synth', 'pause'):
        return T_pause_long if (a.long or b.long) else T_pause_short
    # Vocalic plateau (hold)
    if a.kind == 'V' and a.hold:
        return T_voy
    # V_o → cluster: cluster duration
    if a.is_vowel_onset:
        return T_cons
    # V_e
    if a.is_word_end:
        return T_cons
    # V → V: vocalic transition
    if a.kind == 'V' and b.kind == 'V':
        return T_voy
    # Default: consonantal transition
    return T_cons


# ==========================================================================
# Syllabic boundary (legacy)
# ==========================================================================

class BoundaryDirection(Enum):
    ONSET_TO_NUCLEUS = 'o2n'
    NUCLEUS_TO_CODA = 'n2c'
    SYLLABLE_JUNCTION = 's2s'


@dataclass
class SyllableBoundary:
    direction: BoundaryDirection = BoundaryDirection.SYLLABLE_JUNCTION
    anchor_from: Optional['GestureAnchor'] = None
    anchor_to: Optional['GestureAnchor'] = None
    duration_ms: float = 0.0
    syllable_idx: int = 0
    # Fields for build_gesture_anchors (reference pipeline)
    curr_segments: list = field(default_factory=list)
    prev_segments: list = field(default_factory=list)
    flat_idx: int = 0


# ==========================================================================
# ParseResult — result of parse_input() (reference pipeline)
# ==========================================================================

@dataclass
class ParseResult:
    """Result of parse_input() for the gesture/reference pipeline.

    Attributes
    ----------
    flat : list[str]
        Flat list of IPA segments and markers (GAP, |).
    blocks : list[list[str]]
        Segments grouped by word (without markers).
    syllables_per_word : list[list[list[str]]]
        Syllables grouped by word, each syllable = list of segments.
    word_starts : list[int]
        Indices in flat where each word starts.
    syllable_boundaries : set[int]
        Indices in flat of syllable boundaries.
    syllable_boundary_info : list[SyllableBoundary]
        Detailed information about each intersyllabic boundary.
    """
    flat: List[str] = field(default_factory=list)
    blocks: List[List[str]] = field(default_factory=list)
    syllables_per_word: List[List[List[str]]] = field(default_factory=list)
    word_starts: List[int] = field(default_factory=list)
    syllable_boundaries: set = field(default_factory=set)
    syllable_boundary_info: List['SyllableBoundary'] = field(default_factory=list)


# ==========================================================================
# Syllable structure (legacy)
# ==========================================================================

@dataclass
class GestureSyllable:
    index: int = 0
    onset_nodes: List[GestureNode] = field(default_factory=list)
    nucleus_node: Optional[GestureNode] = None
    coda_nodes: List[GestureNode] = field(default_factory=list)
    anchors: List[GestureAnchor] = field(default_factory=list)
    boundaries: List[SyllableBoundary] = field(default_factory=list)
    t_start: float = 0.0
    t_end: float = 0.0

    @property
    def duration_ms(self) -> float:
        return self.t_end - self.t_start

    @property
    def all_nodes(self) -> List[GestureNode]:
        nodes = list(self.onset_nodes)
        if self.nucleus_node is not None:
            nodes.append(self.nucleus_node)
        nodes.extend(self.coda_nodes)
        return nodes

    @property
    def structure_type(self) -> str:
        n_onset = len(self.onset_nodes)
        has_coda = len(self.coda_nodes) > 0
        has_nucleus = self.nucleus_node is not None
        if not has_nucleus:
            return 'C'
        if n_onset == 0 and not has_coda:
            return 'V'
        if n_onset == 1 and not has_coda:
            return 'CV'
        if n_onset == 2 and not has_coda:
            return 'CCV'
        if n_onset >= 1 and has_coda:
            return 'CVC'
        if n_onset == 0 and has_coda:
            return 'VC'
        return 'V'
