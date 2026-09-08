# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
timers.py
=========
Three parsing timers for glottal source control
and tract extension parameters in the Berthommier pipeline.

This module implements the three timers specified by the user:
  1. Voicing timer (consonant pre-voicing)
  2. Nasality timer (velum opening VO)
  3. Laterality timer (TS3 parameter)

Architecture:

  The timers are built at the parsing level (parsing.py),
  from the ChainElements that contain the temporal positions
  of the segments. The timers produce time marks that
  are then used to build continuous curves
  (VO, TS3, voicing) injected into the COVTL parameter vector.

Flow:
    parsing.py (ChainElements + timings)
         │
         ▼
    timers.build_all_timers()  →  TimerData
         │
         ├──→  VoicingTimer  (pre-voicing marks)
         ├──→  NasalityTimer (nasality start/end)
         └──→  LateralTimer  (lateral occlusion marks)
         │
         ▼
    timers.build_extension_curves()  →  {VO, TS3_ortho, voicing_events}
         │
         ▼
    assemble_tract.py (injection into the 30-param vector)

Source: user specifications, sessions 4-7.
"""

from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from vtl_synth.core.constants import (
    FRICATIVE_KEYS,
    TAU_PEXP_MS,
    PEXP_FRICATIVE_PRESSURE,
    PEXP_BURST_PRESSURE,
    BURST_PEAK_DURATION_MS,
    BURST_RISE_MS,
    BURST_DECAY_MS,
    PLOSIVE_OCCLUSION_RHO,
    PLOSIVE_VIRTUAL_TARGETS,
)


# =============================================================================
# Timer constants
# =============================================================================

# Nasal consonants (IPA keys)
NASAL_KEYS: frozenset = frozenset({'m', 'n', 'N', 'J'})

# Lateral consonants (IPA keys)
LATERAL_KEYS: frozenset = frozenset({'l', 'L'})

# Nasalized vowels (IPA keys) — nasality carried by the vowel
NASALIZED_VOWEL_KEYS: frozenset = frozenset({'9', '6~'})  # 9=œ̃, 6~=œ̃

# Voiced consonants (canonical IPA keys — voiceless ones are resolved)
VOICED_CONSONANT_KEYS: frozenset = frozenset({
    'b', 'd', 'g', 'v', 'z', 'Z', 'D', 'R',
    'dZ', 'l', 'L', 'j', 'C',
    # Nasals (always voiced)
    'm', 'n', 'N', 'J',
})

# Voiceless consonants
VOICELESS_CONSONANT_KEYS: frozenset = frozenset({
    'p', 't', 'k', 'f', 's', 'S', 'T', 'tS', 'h',
})

# Plosive consonants (for pre-voicing)
PLOSIVE_KEYS: frozenset = frozenset({'b', 'p', 'd', 't', 'g', 'k'})

# Voiced fricatives (particularly concerned by continuous voicing)
VOICED_FRICATIVE_KEYS: frozenset = frozenset({'v', 'z', 'Z', 'D'})

# Time constants for exponential filtering (ms)
TAU_NASALITY_MS: float = 12.0   # Time constant for VO (nasality)
TAU_LATERALITY_MS: float = 5.0  # Fast time constant for TS3

# Time constant for voicing (ms)
TAU_VOICING_MS: float = 8.0

# TS3 target value for lateral consonants
TS3_LATERAL_TARGET: float = -1.0

# TS3 value at rest (non-lateral)
TS3_REST: float = 0.0

# VO target value for nasality (full velum opening)
VO_NASAL_TARGET: float = 1.0

# VO value at rest (oral)
VO_REST: float = 0.0

# Lateral occlusion area in the VTL model (mm²)
# When TS3 = -1, the model automatically adjusts the occlusion to 25 mm²
LATERAL_OCCLUSION_AREA: float = 25.0

# Affricate keys: treated as plosive + fricative
AFFRICATE_KEYS: frozenset = frozenset({'tS', 'dZ'})


# =============================================================================
# Time mark types
# =============================================================================

@dataclass
class VoicingMark:
    """Voicing time mark for a consonant.

    Attributes
    ----------
    seg_key : str
        IPA key of the consonant.
    t_target_ms : float
        Time (ms) at which the consonantal target is reached.
    is_voiced : bool
        True if the consonant is voiced (pre-voicing possible).
    t_start_ms : float
        Voicing start time (before t_target for pre-voicing,
        or at t_target for post-voicing).
    t_end_ms : float
        Voicing end time.
    glottal_shape : str
        Type of glottal shape: 'modal' for voiced, 'voiceless' otherwise.
    supraglottic_track : str
        Supraglottic occlusion track: 'lip', 'apex', 'body', or ''.
    position_in_syllable : str
        'onset' or 'coda'.
    flat_idx : int
        Index in the flat list of segments.
    """
    seg_key: str = ''
    t_target_ms: float = 0.0
    is_voiced: bool = False
    t_start_ms: float = 0.0
    t_end_ms: float = 0.0
    glottal_shape: str = 'voiceless'
    supraglottic_track: str = ''
    position_in_syllable: str = 'onset'
    flat_idx: int = -1


@dataclass
class NasalityMark:
    """Nasality time mark for a segment.

    Attributes
    ----------
    seg_key : str
        IPA key of the nasal segment or nasalized vowel.
    t_open_ms : float
        Time (ms) of velum opening start (start of the nasal segment).
    t_close_ms : float
        Time (ms) of velum closure end.
    vo_target : float
        VO target value (1.0 for fully nasal).
    flat_idx : int
        Index in the flat list of segments.
    """
    seg_key: str = ''
    t_open_ms: float = 0.0
    t_close_ms: float = 0.0
    vo_target: float = VO_NASAL_TARGET
    flat_idx: int = -1


@dataclass
class LateralMark:
    """Laterality time mark for a lateral consonant.

    Attributes
    ----------
    seg_key : str
        IPA key of the lateral consonant.
    t_occlusion_ms : float
        Time (ms) of the lateral occlusion (middle of the consonant).
    ts3_target : float
        TS3 target value (-1.0 for fully lateral).
    t_start_ms : float
        Start time of the TS3 transition toward the target.
    t_end_ms : float
        End time of the TS3 transition back to rest.
    flat_idx : int
        Index in the flat list of segments.
    has_virtual_target : bool
        True if /l/ uses a virtual target for the tongue tip.
    """
    seg_key: str = ''
    t_occlusion_ms: float = 0.0
    ts3_target: float = TS3_LATERAL_TARGET
    t_start_ms: float = 0.0
    t_end_ms: float = 0.0
    flat_idx: int = -1
    has_virtual_target: bool = False


@dataclass
class PexpMark:
    """Mark of the pulmonary Pexp timer (bursts and frications).

    WARNING: This Pexp is the VTL subglottal pressure
    (pulmonary), totally independent of the kinematic Pexp of
    Berthommier (exponent in arc_B).
    """
    seg_key: str = ''
    pexp_type: str = 'burst'
    t_start_ms: float = 0.0
    t_peak_ms: float = 0.0
    t_end_ms: float = 0.0
    amplitude: float = 0.0
    rho_target: float = 0.0
    theta_target: float = 0.0
    flat_idx: int = -1


@dataclass
class OcclusionTrace:
    """Trace of an occlusion for post-hoc adjustment of rho."""
    seg_key: str = ''
    frame_start: int = 0
    frame_end: int = 0
    frame_peak: int = 0
    rho_min: float = 0.0
    rho_measured: float = 0.0
    needs_correction: bool = False
    occlusion_type: str = 'plosive'


@dataclass
class OcclusionTraceResult:
    """Complete result of occlusion tracing."""
    traces: List[OcclusionTrace] = field(default_factory=list)
    rho_correction_curve: np.ndarray = field(default_factory=lambda: np.zeros(0))
    n_frames: int = 0


# =============================================================================
# Main container for timer data
# =============================================================================

@dataclass
class TimerData:
    """Container for all time marks of the timers.

    Built by build_all_timers() at the parsing level.
    Used by build_extension_curves() to generate the continuous
    VO and TS3 curves, and the voicing events.

    Attributes
    ----------
    voicing_marks : list[VoicingMark]
        Voicing marks for each consonant.
    nasality_marks : list[NasalityMark]
        Nasality marks for each nasal segment.
    lateral_marks : list[LateralMark]
        Laterality marks for each lateral consonant.
    pexp_marks : list[PexpMark]
        Pulmonary Pexp marks for plosive bursts and frication
        (VTL subglottal pressure — independent of the kinematic
        Pexp of the Berthommier arcs; see PexpMark).
    total_duration_ms : float
        Total duration of the utterance (ms).
    sr : float
        Target sampling rate (Hz) for the curves.
    """
    voicing_marks: List[VoicingMark] = field(default_factory=list)
    nasality_marks: List[NasalityMark] = field(default_factory=list)
    lateral_marks: List[LateralMark] = field(default_factory=list)
    pexp_marks: List[PexpMark] = field(default_factory=list)
    total_duration_ms: float = 0.0
    sr: float = 100.0  # TARGET_SR


# =============================================================================
# Time rescaling — align the timers with the trajectory clock
# =============================================================================

def rescale_timer_data(timer_data: TimerData, trajectory_duration_ms: float) -> TimerData:
    """Applies a time rescaling to the timer marks.

    The timers are built from ChainElement.duration_ms (which
    comes from CONSONANT_DURATIONS / DEFAULT_VOWEL_DURATION_MS),
    whereas the Berthommier trajectory is built from
    build_global_pval with T_cons / T_voy in frames.  The two
    clocks do not coincide.

    This function uniformly scales all mark times
    (t_target_ms, t_start_ms, t_end_ms, etc.) by the ratio:

        scale = trajectory_duration_ms / timer_data.total_duration_ms

    and updates total_duration_ms and sr to reflect the actual
    duration of the trajectory.

    Parameters
    ----------
    timer_data : TimerData
        Timer data (built from the ChainElements).
    trajectory_duration_ms : float
        Actual duration of the trajectory (n_frames * 1000 / sr).

    Returns
    -------
    TimerData
        Same object modified in place (the marks are mutable
        dataclasses).
    """
    if timer_data.total_duration_ms <= 0:
        timer_data.total_duration_ms = trajectory_duration_ms
        return timer_data

    scale = trajectory_duration_ms / timer_data.total_duration_ms

    if abs(scale - 1.0) < 1e-6:
        logger.debug('rescale_timer_data: scale=%.4f, no correction', scale)
        return timer_data

    logger.info(
        'rescale_timer_data: scale=%.4f '
        '(timer=%.1f ms → trajectory=%.1f ms)',
        scale, timer_data.total_duration_ms, trajectory_duration_ms)

    def _scale_ms(v: float) -> float:
        return v * scale

    for m in timer_data.voicing_marks:
        m.t_target_ms = _scale_ms(m.t_target_ms)
        m.t_start_ms = _scale_ms(m.t_start_ms)
        m.t_end_ms = _scale_ms(m.t_end_ms)

    for m in timer_data.nasality_marks:
        m.t_open_ms = _scale_ms(m.t_open_ms)
        m.t_close_ms = _scale_ms(m.t_close_ms)

    for m in timer_data.lateral_marks:
        m.t_occlusion_ms = _scale_ms(m.t_occlusion_ms)
        m.t_start_ms = _scale_ms(m.t_start_ms)
        m.t_end_ms = _scale_ms(m.t_end_ms)

    for m in timer_data.pexp_marks:
        m.t_start_ms = _scale_ms(m.t_start_ms)
        m.t_peak_ms = _scale_ms(m.t_peak_ms)
        m.t_end_ms = _scale_ms(m.t_end_ms)

    timer_data.total_duration_ms = trajectory_duration_ms
    return timer_data


# =============================================================================
# Determination of the supraglottic occlusion track
# =============================================================================

def _get_supraglottic_track(seg_key: str) -> str:
    """Determines the supraglottic occlusion track for a consonant.

    The tracks correspond to the articulators in the VTL model:
      - 'lip': lips (LP, LD) — bilabials / labiodentals
      - 'apex': tongue tip (TTX, TTY) — dentals / alveolars
      - 'body': tongue body (TCX, TCY, TBX, TBY) — velars / palatals
      - '': no supraglottic occlusion (nasals, glottal)

    Parameters
    ----------
    seg_key : str
        IPA key of the consonant.

    Returns
    -------
    str
        Occlusion track.
    """
    # Bilabials
    if seg_key in ('b', 'p', 'm', 'w'):
        return 'lip'
    # Labiodentals
    if seg_key in ('f', 'v'):
        return 'lip'
    # Dentals / alveolars
    if seg_key in ('d', 't', 'n', 'l', 'L', 's', 'z', 'S', 'Z',
                    'tS', 'dZ', 'T', 'D'):
        return 'apex'
    # Palatals
    if seg_key in ('C', 'j', 'J'):
        return 'body'
    # Velars
    if seg_key in ('g', 'k', 'N'):
        return 'body'
    # Uvulars
    if seg_key in ('R', 'X'):
        return 'body'
    # Glottal
    if seg_key == 'h':
        return ''
    return ''


# =============================================================================
# Determination of a priori voicing
# =============================================================================

def _is_consonant_voiced(seg_key: str) -> bool:
    """Checks whether a consonant is voiced (a priori information).

    Voiced/voiceless pairs share the same place of articulation.
    The distinction is handled by the glottal source, NOT by the tract.

    Parameters
    ----------
    seg_key : str
        IPA key of the consonant.

    Returns
    -------
    bool
        True if the consonant is voiced.
    """
    return seg_key in VOICED_CONSONANT_KEYS


def _is_consonant_voiceless(seg_key: str) -> bool:
    """Checks whether a consonant is voiceless."""
    return seg_key in VOICELESS_CONSONANT_KEYS


def _is_nasal(seg_key: str) -> bool:
    """Checks whether a segment is a nasal consonant."""
    return seg_key in NASAL_KEYS


def _is_lateral(seg_key: str) -> bool:
    """Checks whether a segment is a lateral consonant."""
    return seg_key in LATERAL_KEYS


def _is_plosive(seg_key: str) -> bool:
    """Checks whether a consonant is a plosive."""
    return seg_key in PLOSIVE_KEYS


def _is_fricative(seg_key: str) -> bool:
    """Checks whether a consonant is a fricative."""
    return seg_key in FRICATIVE_KEYS


def _is_affricate(seg_key: str) -> bool:
    """Checks whether a consonant is an affricate."""
    return seg_key in AFFRICATE_KEYS


def _is_nasalized_vowel(seg_key: str) -> bool:
    """Checks whether a vowel is nasalized."""
    return seg_key in NASALIZED_VOWEL_KEYS


# =============================================================================
# Timer 1: Voicing (consonant pre-voicing)
# =============================================================================

def build_voicing_timer(
    elements: list,
    sr: float = 100.0,
) -> List[VoicingMark]:
    """Builds the voicing timer for all consonants.

    For each consonant, computes the time at which the target is
    reached (t_target_ms). For voiced consonants, voicing (pre-voicing)
    starts BEFORE the target is reached — coordination between:
      - A supraglottic occlusion gesture (lips, tongue tip
        or tongue body track)
      - A 'modal' type glottal shape gesture

    For voiceless consonants, voicing only appears after
    the target is reached (post-voicing / late voicing).

    Parameters
    ----------
    elements : list[ChainElement]
        Chain of syllabic elements (from syllabify_continuous()).
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    list[VoicingMark]
        List of voicing marks per consonant.
    """
    from vtl_synth.core.polar import T_BASE_DEFAULT
    from vtl_synth.core.constants import TCONS_DEFAULT, TVOY_DEFAULT
    from vtl_synth.core.continuous import ChainElementType

    marks: List[VoicingMark] = []
    T = T_BASE_DEFAULT  # 100 ms
    t_cumul = 0.0

    for elem in elements:
        if elem.is_pause:
            t_cumul += elem.pause_duration_ms
            continue

        dur = elem.duration_ms
        onset_keys = elem.onset_keys
        coda_keys = elem.coda_keys

        # --- Onset consonants ---
        for ci, c_key in enumerate(onset_keys):
            voiced = _is_consonant_voiced(c_key)
            voiceless = _is_consonant_voiceless(c_key)
            track = _get_supraglottic_track(c_key)

            # Time at which the consonantal target is reached:
            # In the CV graph, the C target is reached at T * TCONS
            # after the start of the syllable (middle of the V_o → C → V arc).
            # For a simple onset (CV): t_target = T * TCONS
            # For a cluster (CCV): each successive C is shifted by T * TCONS
            t_target = t_cumul + T * TCONS_DEFAULT * (ci + 0.5)

            if voiced:
                # Pre-voicing: voicing starts ~20-30 ms before
                # the target is reached, for voiced stops.
                # For voiced fricatives, voicing is continuous.
                if _is_plosive(c_key):
                    pre_voicing_ms = 25.0  # ~25 ms of pre-voicing
                elif c_key in VOICED_FRICATIVE_KEYS:
                    pre_voicing_ms = 10.0  # Continuous voicing
                elif _is_nasal(c_key):
                    pre_voicing_ms = 15.0  # Nasals: voicing + nasality
                else:
                    pre_voicing_ms = 15.0  # Laterals, approximants

                t_start = max(0.0, t_target - pre_voicing_ms)
                # Voicing is maintained up to the vowel
                t_vowel_start = t_cumul + T * TCONS_DEFAULT * len(onset_keys)
                t_end = t_vowel_start
                glottal_shape = 'modal'
            else:
                # Voiceless consonant: no pre-voicing
                t_start = t_target
                t_end = t_target
                glottal_shape = 'voiceless'

            marks.append(VoicingMark(
                seg_key=c_key,
                t_target_ms=t_target,
                is_voiced=voiced,
                t_start_ms=t_start,
                t_end_ms=t_end,
                glottal_shape=glottal_shape,
                supraglottic_track=track,
                position_in_syllable='onset',
            ))

        # --- Coda consonants ---
        # Coda consonants start after the vocalic nucleus
        onset_dur = T * TCONS_DEFAULT * len(onset_keys) if onset_keys else 0.0
        nuc_dur = dur - onset_dur
        if nuc_dur < 0:
            nuc_dur = 0.0
        # The vocalic nucleus occupies the remaining duration
        coda_start_base = t_cumul + onset_dur + max(0, nuc_dur - T * TVOY_DEFAULT)

        for ci, c_key in enumerate(coda_keys):
            voiced = _is_consonant_voiced(c_key)
            voiceless = _is_consonant_voiceless(c_key)
            track = _get_supraglottic_track(c_key)

            # Time at which the coda target is reached
            t_target = coda_start_base + T * TCONS_DEFAULT * (ci + 0.5)

            if voiced:
                # In coda, voicing can extend past the target
                if _is_plosive(c_key):
                    # Voiced stop in coda: voicing during the occlusion
                    t_start = t_target
                    t_end = t_target + T * TCONS_DEFAULT * 0.5
                else:
                    t_start = t_target - 10.0
                    t_end = t_target + T * TCONS_DEFAULT * 0.5
                glottal_shape = 'modal'
            else:
                t_start = t_target
                t_end = t_target
                glottal_shape = 'voiceless'

            marks.append(VoicingMark(
                seg_key=c_key,
                t_target_ms=t_target,
                is_voiced=voiced,
                t_start_ms=t_start,
                t_end_ms=t_end,
                glottal_shape=glottal_shape,
                supraglottic_track=track,
                position_in_syllable='coda',
            ))

        t_cumul += dur

    return marks


# =============================================================================
# Timer 2: Nasality (velum opening VO)
# =============================================================================

def build_nasality_timer(
    elements: list,
    sr: float = 100.0,
) -> List[NasalityMark]:
    """Builds the nasality timer for all nasal segments.

    For each nasal segment (nasal consonant or nasalized vowel),
    records the opening and closing times of the velum.

    Timing homogeneous with the voicing timer:
      - Nasal consonants in onset use the same t_target
        as the other consonants: T * TCONS_DEFAULT * (ci + 0.5)
      - Nasal consonants in coda use the coda timing.
      - Nasalized vowels cover the vocalic nucleus range.

    Parameters
    ----------
    elements : list[ChainElement]
        Chain of syllabic elements.
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    list[NasalityMark]
        List of nasality marks.
    """
    from vtl_synth.core.polar import T_BASE_DEFAULT
    from vtl_synth.core.constants import TCONS_DEFAULT, TVOY_DEFAULT

    marks: List[NasalityMark] = []
    t_cumul = 0.0
    T = T_BASE_DEFAULT

    for elem in elements:
        if elem.is_pause:
            t_cumul += elem.pause_duration_ms
            continue

        dur = elem.duration_ms
        onset_keys = elem.onset_keys
        coda_keys = elem.coda_keys

        # --- Nasal onset consonants ---
        for ci, seg_key in enumerate(onset_keys):
            if _is_nasal(seg_key):
                # Timing aligned with the voicing timer:
                #   start  = T * TCONS_DEFAULT * ci
                #   end    = T * TCONS_DEFAULT * (ci + 1)
                t_open = t_cumul + T * TCONS_DEFAULT * ci
                t_close = t_cumul + T * TCONS_DEFAULT * (ci + 1)
                marks.append(NasalityMark(
                    seg_key=seg_key,
                    t_open_ms=t_open,
                    t_close_ms=t_close,
                    vo_target=VO_NASAL_TARGET,
                ))

        # --- Nasalized vowel (nucleus) ---
        if elem.nucleus_keys and _is_nasalized_vowel(elem.nucleus_keys[0]):
            # Nasality covers the vocalic nucleus
            onset_dur = T * TCONS_DEFAULT * len(onset_keys) if onset_keys else 0.0
            t_nuc_start = t_cumul + onset_dur
            # End of the nucleus: before the codas (if any)
            coda_dur = T * TCONS_DEFAULT * len(coda_keys) if coda_keys else 0.0
            t_nuc_end = t_cumul + dur - coda_dur if dur > onset_dur + coda_dur else t_cumul + dur
            marks.append(NasalityMark(
                seg_key=elem.nucleus_keys[0],
                t_open_ms=t_nuc_start,
                t_close_ms=t_nuc_end,
                vo_target=VO_NASAL_TARGET,
            ))

        # --- Nasal coda consonants ---
        onset_dur = T * TCONS_DEFAULT * len(onset_keys) if onset_keys else 0.0
        nuc_dur = dur - onset_dur
        if nuc_dur < 0:
            nuc_dur = 0.0
        coda_start_base = t_cumul + onset_dur + max(0, nuc_dur - T * TVOY_DEFAULT)

        for ci, seg_key in enumerate(coda_keys):
            if _is_nasal(seg_key):
                t_open = coda_start_base + T * TCONS_DEFAULT * ci
                t_close = coda_start_base + T * TCONS_DEFAULT * (ci + 1)
                marks.append(NasalityMark(
                    seg_key=seg_key,
                    t_open_ms=t_open,
                    t_close_ms=t_close,
                    vo_target=VO_NASAL_TARGET,
                ))

        t_cumul += dur

    return marks


# =============================================================================
# Timer 3: Laterality (TS3 parameter)
# =============================================================================

def build_lateral_timer(
    elements: list,
    sr: float = 100.0,
) -> List[LateralMark]:
    """Builds the laterality timer for lateral consonants.

    For each lateral consonant (/l/, /L/), records:
      - The occlusion time mark (t_occlusion_ms)
      - The TS3 transition times toward -1 and back to 0
      - The virtual target information for /l/

    Timing homogeneous with the voicing timer:
      - Lateral consonants in onset use the same t_target
        as the other consonants: T * TCONS_DEFAULT * (ci + 0.5)
      - Lateral consonants in coda use the coda timing.

    Parameters
    ----------
    elements : list[ChainElement]
        Chain of syllabic elements.
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    list[LateralMark]
        List of laterality marks.
    """
    from vtl_synth.core.polar import T_BASE_DEFAULT
    from vtl_synth.core.constants import TCONS_DEFAULT, TVOY_DEFAULT

    marks: List[LateralMark] = []
    t_cumul = 0.0
    T = T_BASE_DEFAULT

    for elem in elements:
        if elem.is_pause:
            t_cumul += elem.pause_duration_ms
            continue

        dur = elem.duration_ms
        onset_keys = elem.onset_keys
        coda_keys = elem.coda_keys

        # --- Lateral onset consonants ---
        for ci, seg_key in enumerate(onset_keys):
            if _is_lateral(seg_key):
                # Timing aligned with the voicing timer:
                #   start  = T * TCONS_DEFAULT * ci
                #   peak   = T * TCONS_DEFAULT * (ci + 0.5)
                #   end    = T * TCONS_DEFAULT * (ci + 1)
                t_start = t_cumul + T * TCONS_DEFAULT * ci
                t_occlusion = t_cumul + T * TCONS_DEFAULT * (ci + 0.5)
                t_end = t_cumul + T * TCONS_DEFAULT * (ci + 1)

                has_virtual = (seg_key == 'l')

                marks.append(LateralMark(
                    seg_key=seg_key,
                    t_occlusion_ms=t_occlusion,
                    ts3_target=TS3_LATERAL_TARGET,
                    t_start_ms=t_start,
                    t_end_ms=t_end,
                    has_virtual_target=has_virtual,
                ))

        # --- Lateral coda consonants ---
        onset_dur = T * TCONS_DEFAULT * len(onset_keys) if onset_keys else 0.0
        nuc_dur = dur - onset_dur
        if nuc_dur < 0:
            nuc_dur = 0.0
        coda_start_base = t_cumul + onset_dur + max(0, nuc_dur - T * TVOY_DEFAULT)

        for ci, seg_key in enumerate(coda_keys):
            if _is_lateral(seg_key):
                t_start = coda_start_base + T * TCONS_DEFAULT * ci
                t_occlusion = coda_start_base + T * TCONS_DEFAULT * (ci + 0.5)
                t_end = coda_start_base + T * TCONS_DEFAULT * (ci + 1)

                has_virtual = (seg_key == 'l')

                marks.append(LateralMark(
                    seg_key=seg_key,
                    t_occlusion_ms=t_occlusion,
                    ts3_target=TS3_LATERAL_TARGET,
                    t_start_ms=t_start,
                    t_end_ms=t_end,
                    has_virtual_target=has_virtual,
                ))

        t_cumul += dur

    return marks


# =============================================================================
# Building all timers
# =============================================================================

def build_all_timers(
    elements: list,
    sr: float = 100.0,
) -> TimerData:
    """Builds the three timers from the syllabic elements.

    This function is called at the parsing level, after
    syllabify_continuous(), to install the voicing, nasality
    and laterality time marks.

    Parameters
    ----------
    elements : list[ChainElement]
        Chain of syllabic elements (from syllabify_continuous()).
    sr : float
        Target sampling rate (Hz).

    Returns
    -------
    TimerData
        Container with all the time marks.
    """
    voicing_marks = build_voicing_timer(elements, sr)
    nasality_marks = build_nasality_timer(elements, sr)
    lateral_marks = build_lateral_timer(elements, sr)
    pexp_marks = build_pexp_timer(elements, sr)

    # Compute the total duration
    total_ms = 0.0
    for elem in elements:
        if elem.is_pause:
            total_ms += elem.pause_duration_ms
        else:
            total_ms += elem.duration_ms

    return TimerData(
        voicing_marks=voicing_marks,
        nasality_marks=nasality_marks,
        lateral_marks=lateral_marks,
        pexp_marks=pexp_marks,
        total_duration_ms=total_ms,
        sr=sr,
    )


# =============================================================================
# Building the extension curves (VO, TS3, voicing)
# =============================================================================

def _exponential_filter(
    impulse: np.ndarray,
    tau_ms: float,
    dt_ms: float,
) -> np.ndarray:
    """Applies exponential filtering to an impulse.

    Converts a series of impulses (or steps) into a smooth curve
    with a time constant tau.

    The first-order exponential filter is:
      dy/dt = -y/tau + x/tau

    In discrete form: y[n+1] = alpha * x[n] + (1 - alpha) * y[n]
    where alpha = dt / (tau + dt)

    Parameters
    ----------
    impulse : np.ndarray, shape (N,)
        Input signal (impulses or steps).
    tau_ms : float
        Time constant (ms).
    dt_ms : float
        Time step (ms).

    Returns
    -------
    np.ndarray, shape (N,)
        Filtered signal.
    """
    if tau_ms <= 0:
        return impulse.copy()
    alpha = dt_ms / (tau_ms + dt_ms)
    alpha = np.clip(alpha, 0.0, 1.0)
    out = np.zeros_like(impulse)
    y = 0.0
    for n in range(len(impulse)):
        y = alpha * impulse[n] + (1.0 - alpha) * y
        out[n] = y
    return out


def build_voicing_curve(
    timer_data: TimerData,
    n_frames: int,
) -> np.ndarray:
    """Builds the voicing curve V(t) from the timer marks.

    The voicing curve is binary (0 or 1) with exponential
    filtering (time constant TAU_VOICING_MS) for smooth
    transitions.

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    np.ndarray, shape (n_frames,)
        Voicing curve V(t) in [0, 1].
    """
    if timer_data.total_duration_ms <= 0:
        return np.zeros(n_frames)

    dt_ms = timer_data.total_duration_ms / n_frames
    t = np.linspace(0, timer_data.total_duration_ms, n_frames, endpoint=False)

    # Build the voicing impulse
    impulse = np.zeros(n_frames)
    for mark in timer_data.voicing_marks:
        if mark.glottal_shape == 'modal':
            # Voicing regions
            mask = (t >= mark.t_start_ms) & (t <= mark.t_end_ms)
            impulse[mask] = 1.0

    # Exponential filtering
    curve = _exponential_filter(impulse, TAU_VOICING_MS, dt_ms)
    return np.clip(curve, 0.0, 1.0)


def build_vo_curve(
    timer_data: TimerData,
    n_frames: int,
) -> np.ndarray:
    """Builds the nasality curve VO(t) from the timer marks.

    The VO curve is built from the velum opening and closing
    data, with a 12 ms time constant for the exponential
    filtering.

    The curve is then inserted into the parameter vector
    at index IDX_VO (position 7 in the full tract vector).

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    np.ndarray, shape (n_frames,)
        VO(t) curve in [0, 1]. 0 = oral, 1 = fully nasal.
    """
    if timer_data.total_duration_ms <= 0:
        return np.zeros(n_frames)

    dt_ms = timer_data.total_duration_ms / n_frames
    t = np.linspace(0, timer_data.total_duration_ms, n_frames, endpoint=False)

    # Build the nasality impulse
    impulse = np.zeros(n_frames)
    for mark in timer_data.nasality_marks:
        mask = (t >= mark.t_open_ms) & (t <= mark.t_close_ms)
        impulse[mask] = mark.vo_target

    # Exponential filtering with a 12 ms time constant
    curve = _exponential_filter(impulse, TAU_NASALITY_MS, dt_ms)
    return np.clip(curve, 0.0, 1.0)


def build_ts3_curve(
    timer_data: TimerData,
    n_frames: int,
) -> np.ndarray:
    """Builds the laterality curve TS3(t) from the timer marks.

    The TS3 curve is built like the VO curve:
      - From the opening/closing data (timer marks)
      - With a fast time constant
    
    For lateral consonants, TS3 reaches -1 at the moment of
    occlusion. The model automatically adjusts the occlusion to
    25 mm² when TS3 = -1.

    For /l/, the virtual target for the tongue tip guarantees
    that contact and release of the central occlusion occur
    with high velocity in the middle of the transition.

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    np.ndarray, shape (n_frames,)
        TS3(t) curve in [-1, 1]. 0 = rest, -1 = fully lateral.
    """
    if timer_data.total_duration_ms <= 0:
        return np.zeros(n_frames)

    dt_ms = timer_data.total_duration_ms / n_frames
    t = np.linspace(0, timer_data.total_duration_ms, n_frames, endpoint=False)

    # Build the laterality impulse
    impulse = np.zeros(n_frames)
    for mark in timer_data.lateral_marks:
        mask = (t >= mark.t_start_ms) & (t <= mark.t_end_ms)
        impulse[mask] = mark.ts3_target

    # Exponential filtering with a fast time constant
    curve = _exponential_filter(impulse, TAU_LATERALITY_MS, dt_ms)
    return np.clip(curve, -1.0, 1.0)


def build_ts3_ortho_curve(
    timer_data: TimerData,
    n_frames: int,
) -> np.ndarray:
    """Builds the orthogonal TS3 curve for the additive overload.

    In the architecture VTL(t) = B(t) + E(t) + E_ortho(t):
      - The COVTL core TS3 (B(t)) remains unchanged
      - TS3_ortho is the lateral overload added in E_ortho(t)

    This curve is used by assemble_tract.py as the
    ts3_ortho parameter for addition to the COVTL core TS3.

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    np.ndarray, shape (n_frames,)
        TS3_ortho(t) curve. Non-zero values only for
        lateral consonants.
    """
    ts3_full = build_ts3_curve(timer_data, n_frames)
    # The orthogonal curve is the pure lateral part
    # (the COVTL TS3 is ~0 for laterals at rest)
    return ts3_full


def build_glottal_shape_events(
    timer_data: TimerData,
    n_frames: int,
) -> List[dict]:
    """Builds the glottal shape events for pre-voicing.

    For each voiced consonant, generates a coordination event:
      - A supraglottic occlusion gesture (lips, tongue tip
        or tongue body track)
      - A 'modal' type glottal shape gesture

    These events are used by glottal_source.py to
    build the glottal trajectory with pre-voicing.

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    list[dict]
        List of glottal events with keys:
        't_start', 't_end', 'shape', 'seg_key', 'track'.
    """
    events = []
    for mark in timer_data.voicing_marks:
        if mark.glottal_shape == 'modal':
            events.append({
                't_start_ms': mark.t_start_ms,
                't_end_ms': mark.t_end_ms,
                't_target_ms': mark.t_target_ms,
                'shape': mark.glottal_shape,
                'seg_key': mark.seg_key,
                'track': mark.supraglottic_track,
                'position': mark.position_in_syllable,
                'is_prevoicing': mark.t_start_ms < mark.t_target_ms,
            })
    return events


def build_extension_curves(
    timer_data: TimerData,
    n_frames: int,
) -> dict:
    """Builds all the extension curves from the timers.

    Generates the VO, TS3 and voicing curves and the glottal events.
    The result is a dictionary compatible with the
    extension_data parameter of AssembleTract.assemble().

    Parameters
    ----------
    timer_data : TimerData
        Timer data.
    n_frames : int
        Number of frames of the trajectory.

    Returns
    -------
    dict
        Dictionary with keys:
          - 'VO': np.ndarray (n_frames,) — nasality curve
          - 'TS3_ortho': np.ndarray (n_frames,) — lateral overload
          - 'V': np.ndarray (n_frames,) — voicing curve
          - 'glottal_events': list[dict] — glottal shape events
    """
    vo_curve = build_vo_curve(timer_data, n_frames)
    ts3_ortho = build_ts3_ortho_curve(timer_data, n_frames)
    v_curve = build_voicing_curve(timer_data, n_frames)
    glottal_events = build_glottal_shape_events(timer_data, n_frames)
    pexp_curve = build_pexp_curve(timer_data, n_frames)

    return {
        'VO': vo_curve,
        'TS3_ortho': ts3_ortho,
        'V': v_curve,
        'glottal_events': glottal_events,
        'Pexp_pulmonary': pexp_curve,
    }


# =============================================================================
# Virtual target for /l/ (Berthommier model)
# =============================================================================

def get_lateral_virtual_target(seg_key: str) -> Optional[dict]:
    """Returns the virtual target for the tongue tip of a lateral.

    /l/ uses a virtual target for the tongue tip given by the
    Berthommier model. This target guarantees that contact and
    release of the central occlusion (while the sides lower
    via TS3) occur with high velocity in the middle of the
    transition, ensuring increased acoustic sharpness.

    The virtual target is an overload of the polar target (rho, theta)
    of the tongue tip (TTX, TTY) specifically for the central
    occlusion phase of the lateral consonant.

    Parameters
    ----------
    seg_key : str
        IPA key ('l' or 'L').

    Returns
    -------
    dict or None
        Information about the virtual target, or None if not applicable.
        Keys: 'rho_virtual', 'theta_virtual', 'speed_factor',
        'occlusion_duration_factor'.
    """
    if seg_key == 'l':
        # Virtual target for clear /l/ (alveolar)
        # The virtual rho is slightly above the canonical target
        # to force firmer contact at the center.
        # The theta stays the same (alveolar direction).
        return {
            'rho_virtual': 1.20,          # vs 1.15 canonical
            'theta_virtual': np.radians(7),  # same alveolar direction
            'speed_factor': 1.5,         # Increased contact/release velocity
            'occlusion_duration_factor': 0.3,  # Short occlusion at the center
        }
    elif seg_key == 'L':
        # Virtual target for /L/ (dark-l, velar)
        return {
            'rho_virtual': 1.30,          # vs 1.25 canonical
            'theta_virtual': np.radians(7),
            'speed_factor': 1.3,
            'occlusion_duration_factor': 0.35,
        }
    return None


# =============================================================================

def get_plosive_virtual_target(seg_key):
    """Returns the virtual target parameters for a plosive."""
    return PLOSIVE_VIRTUAL_TARGETS.get(seg_key, None)


# =============================================================================
# Pulmonary Pexp timer (bursts and frications)
# =============================================================================

def build_pexp_timer(elements, sr=100.0):
    """Builds the pulmonary Pexp timer marks.

    WARNING: This timer produces an additive modulation of the
    VTL subglottal pressure. It is INDEPENDENT of the kinematic
    Pexp of Berthommier (cos(theta/2)^Pexp in polar.py).

    Timing homogeneous with the voicing timer:
      - The temporal positions are computed with the same
        T * TCONS_DEFAULT logic as build_voicing_timer(), guaranteeing that
        the pressure peak (burst) and the occlusion trace are aligned
        with the actual consonantal target in the trajectory.

    For plosives (onset):
      t_target  = t_cumul + T * TCONS_DEFAULT * (ci + 0.5)
      t_start   = t_cumul + T * TCONS_DEFAULT * ci       (closure start)
      t_release = t_cumul + T * TCONS_DEFAULT * (ci + 1)   (end of C arc)

    For plosives (coda):
      coda_start = t_cumul + onset_dur + max(0, nuc_dur - T*TVOY_DEFAULT)
      t_target   = coda_start + T * TCONS_DEFAULT * (ci + 0.5)
      t_start    = coda_start + T * TCONS_DEFAULT * ci
      t_release  = coda_start + T * TCONS_DEFAULT * (ci + 1)
    """
    from vtl_synth.core.polar import T_BASE_DEFAULT
    from vtl_synth.core.constants import TCONS_DEFAULT, TVOY_DEFAULT

    marks = []
    t_cumul = 0.0
    T = T_BASE_DEFAULT  # 80 ms — same base as the voicing timer

    for elem in elements:
        if elem.is_pause:
            t_cumul += elem.pause_duration_ms
            continue

        dur = elem.duration_ms
        onset_keys = elem.onset_keys
        coda_keys = elem.coda_keys

        # --- Onset consonants ---
        for ci, c_key in enumerate(onset_keys):
            is_plos = _is_plosive(c_key)
            is_fric = _is_fricative(c_key)
            is_affr = _is_affricate(c_key)

            if not (is_plos or is_fric or is_affr):
                continue

            # Timing aligned with the voicing timer
            arc_c_start = t_cumul + T * TCONS_DEFAULT * ci
            t_target    = t_cumul + T * TCONS_DEFAULT * (ci + 0.5)
            arc_c_end   = t_cumul + T * TCONS_DEFAULT * (ci + 1)

            if is_plos:
                # Plosive burst:
                #   t_start  = start of the closure
                #   t_peak   = C target (occlusion peak, aligned with the trace)
                #   t_end    = end of the C arc + pressure decay
                burst_end = arc_c_end + BURST_DECAY_MS
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='burst',
                    t_start_ms=arc_c_start, t_peak_ms=t_target,
                    t_end_ms=min(burst_end,
                                 t_cumul + dur + BURST_DECAY_MS),
                    amplitude=PEXP_BURST_PRESSURE,
                    rho_target=PLOSIVE_OCCLUSION_RHO.get(c_key, 1.15),
                    theta_target=0.0, flat_idx=-1,
                ))
            elif is_fric:
                # Fricative: constriction maintained over the whole C arc
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='frication',
                    t_start_ms=arc_c_start,
                    t_peak_ms=t_target,
                    t_end_ms=arc_c_end,
                    amplitude=PEXP_FRICATIVE_PRESSURE,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))
            elif is_affr:
                # Affricate: plosive phase then fricative phase
                affr_mid = (t_target + arc_c_end) / 2.0
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='burst',
                    t_start_ms=arc_c_start, t_peak_ms=t_target,
                    t_end_ms=affr_mid,
                    amplitude=PEXP_BURST_PRESSURE * 0.8,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='frication',
                    t_start_ms=affr_mid, t_peak_ms=affr_mid + TAU_PEXP_MS,
                    t_end_ms=arc_c_end,
                    amplitude=PEXP_FRICATIVE_PRESSURE * 0.7,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))

        # --- Coda consonants ---
        onset_dur = T * TCONS_DEFAULT * len(onset_keys) if onset_keys else 0.0
        nuc_dur = dur - onset_dur
        if nuc_dur < 0:
            nuc_dur = 0.0
        coda_start_base = t_cumul + onset_dur + max(0, nuc_dur - T * TVOY_DEFAULT)

        for ci, c_key in enumerate(coda_keys):
            is_plos = _is_plosive(c_key)
            is_fric = _is_fricative(c_key)
            is_affr = _is_affricate(c_key)

            if not (is_plos or is_fric or is_affr):
                continue

            # Coda timing: same logic as the voicing timer (l.505)
            arc_c_start = coda_start_base + T * TCONS_DEFAULT * ci
            t_target    = coda_start_base + T * TCONS_DEFAULT * (ci + 0.5)
            arc_c_end   = coda_start_base + T * TCONS_DEFAULT * (ci + 1)

            if is_plos:
                # Plosive in coda: burst without audible release
                # (final occlusion, sometimes unreleased)
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='burst',
                    t_start_ms=arc_c_start, t_peak_ms=t_target,
                    t_end_ms=min(arc_c_end + BURST_DECAY_MS,
                                 t_cumul + dur + BURST_DECAY_MS),
                    amplitude=PEXP_BURST_PRESSURE * 0.5,
                    rho_target=PLOSIVE_OCCLUSION_RHO.get(c_key, 1.15),
                    theta_target=0.0, flat_idx=-1,
                ))
            elif is_fric:
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='frication',
                    t_start_ms=arc_c_start, t_peak_ms=t_target,
                    t_end_ms=arc_c_end,
                    amplitude=PEXP_FRICATIVE_PRESSURE * 0.7,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))
            elif is_affr:
                affr_mid = (t_target + arc_c_end) / 2.0
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='burst',
                    t_start_ms=arc_c_start, t_peak_ms=t_target,
                    t_end_ms=affr_mid,
                    amplitude=PEXP_BURST_PRESSURE * 0.4,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))
                marks.append(PexpMark(
                    seg_key=c_key, pexp_type='frication',
                    t_start_ms=affr_mid, t_peak_ms=affr_mid + TAU_PEXP_MS,
                    t_end_ms=arc_c_end,
                    amplitude=PEXP_FRICATIVE_PRESSURE * 0.5,
                    rho_target=1.15, theta_target=0.0, flat_idx=-1,
                ))

        t_cumul += dur

    return marks


def build_occlusion_traces(elements, pexp_marks, sr=100.0, n_frames=None):
    """Builds the occlusion traces for post-hoc adjustment of rho.

    Parameters
    ----------
    elements : list[ChainElement]
        Syllabic elements (used only if n_frames is None).
    pexp_marks : list[PexpMark]
        Rescaled Pexp marks (times aligned with the trajectory).
    sr : float
        Sampling rate (Hz).
    n_frames : int, optional
        Number of frames of the actual trajectory.
        If provided, the value computed from the elements is ignored.
    """
    if n_frames is None:
        total_ms = 0.0
        for elem in elements:
            if elem.is_pause:
                total_ms += elem.pause_duration_ms
            else:
                total_ms += elem.duration_ms
        n_frames = max(1, int(total_ms * sr / 1000.0))

    traces = []

    for mark in pexp_marks:
        i_start = max(0, min(int(mark.t_start_ms * sr / 1000.0), n_frames - 1))
        i_end = max(0, min(int(mark.t_end_ms * sr / 1000.0), n_frames - 1))
        i_peak = int(mark.t_peak_ms * sr / 1000.0)
        # Do not clamp i_peak here — the guard in
        # update_occlusion_traces will handle it.
        occl_type = 'plosive' if mark.pexp_type == 'burst' else 'fricative'
        traces.append(OcclusionTrace(
            seg_key=mark.seg_key, frame_start=i_start, frame_end=i_end,
            frame_peak=i_peak, rho_min=mark.rho_target, rho_measured=0.0,
            needs_correction=False, occlusion_type=occl_type,
        ))

    return OcclusionTraceResult(
        traces=traces, rho_correction_curve=np.zeros(n_frames), n_frames=n_frames,
    )


def update_occlusion_traces(trace_result, pval_trajectory):
    """Updates the traces with the values measured from Pval.

    For each plosive occlusion trace, measures the relevant
    VTL parameter at the occlusion peak frame and computes a
    **per-parameter** correction (2D: n_frames x N_VTL_PARAMS) that will
    be applied directly to the trajectory by apply_occlusion_corrections().

    If frame_peak >= n_frames (peak in the final pause), the trace
    is marked needs_correction=False and a log is emitted — no
    silent clamping onto the final pause.

    COVTL indices (15 params, without VS/VO/TRX/TRY):
      0:HX 1:HY 2:JX 3:JA 4:LP 5:LD
      6:TCX 7:TCY 8:TTX 9:TTY
      10:TBX 11:TBY 12:TS1 13:TS2 14:TS3
    """
    from vtl_synth.core.constants import N_VTL_PARAMS
    n_frames = len(pval_trajectory)
    if n_frames == 0:
        return trace_result

    # Correct COVTL indices
    LD_IDX = 5   # Lip distance
    TTY_IDX = 9  # Tongue tip Y (alveolar contact)
    TCX_IDX = 6  # Tongue body X (velar region)
    TCY_IDX = 7  # Tongue body Y (velar height)
    TBX_IDX = 10 # Tongue base X
    TBY_IDX = 11 # Tongue base Y

    # (param_idx, threshold, direction, correction_sign)
    # correction_sign: -1 = subtract the deficit (below), +1 = add (above)
    _OCCL = {
        # Bilabials: LD (lip distance) must be close to 0
        'b': (LD_IDX, 0.10, 'below'),
        'p': (LD_IDX, 0.10, 'below'),
        # Alveolars: TTY (tongue tip Y) must be high (> threshold)
        'd': (TTY_IDX, 0.50, 'above'),
        't': (TTY_IDX, 0.50, 'above'),
        # Velars: TCY (tongue body Y, height) must be high
        # + TBX retraction for velar contact
        'g': (TCY_IDX, 1.50, 'above'),
        'k': (TCY_IDX, 1.50, 'above'),
    }

    # 2D correction: (n_frames, N_VTL_PARAMS)
    nvp = min(N_VTL_PARAMS, pval_trajectory.shape[1])
    correction = np.zeros((n_frames, nvp))

    for trace in trace_result.traces:
        if trace.frame_end <= trace.frame_start:
            continue

        # --- Guard: peak in the final pause ---
        # If the occlusion peak falls outside the trajectory
        # (frame_peak >= n_frames), it means the timer is
        # locked onto the final pause.  We do not correct and we log.
        if trace.frame_peak >= n_frames:
            logger.warning(
                'update_occlusion_traces: %s frame_peak=%d >= n_frames=%d '
                '→ needs_correction=False (peak in the final pause)',
                trace.seg_key, trace.frame_peak, n_frames)
            trace.needs_correction = False
            trace.rho_measured = 0.0
            continue

        if trace.frame_peak < 0:
            logger.warning(
                'update_occlusion_traces: %s frame_peak=%d < 0 '
                '→ needs_correction=False',
                trace.seg_key, trace.frame_peak)
            trace.needs_correction = False
            trace.rho_measured = 0.0
            continue

        fs = max(0, min(trace.frame_start, n_frames - 1))
        fe = max(0, min(trace.frame_end, n_frames - 1))
        pk = trace.frame_peak  # no more silent clamping

        if fe <= fs:
            continue

        if trace.occlusion_type == 'plosive' and trace.seg_key in _OCCL:
            param_idx, threshold, direction = _OCCL[trace.seg_key]

            pk_val = pval_trajectory[pk, :nvp]
            measured = pk_val[param_idx] if param_idx < nvp else 0.0
            trace.rho_measured = measured
            trace.needs_correction = (
                (measured > threshold) if direction == 'below'
                else (measured < threshold)
            )

            if trace.needs_correction:
                zone_len = fe - fs
                if zone_len > 0:
                    if direction == 'below':
                        deficit = measured - threshold
                    else:
                        deficit = threshold - measured

                    sign = -1.0 if direction == 'below' else +1.0

                    for fi in range(fs, min(fe + 1, n_frames)):
                        dist = abs(fi - pk) / max(zone_len / 2, 1)
                        w = max(0.0, 1.0 - dist ** 2)
                        correction[fi, param_idx] += sign * deficit * w

                    # For velars, also correct TBX
                    if trace.seg_key in ('g', 'k') and TBX_IDX < nvp:
                        tbx_measured = pk_val[TBX_IDX]
                        tbx_threshold = 3.50
                        if tbx_measured < tbx_threshold:
                            tbx_deficit = tbx_threshold - tbx_measured
                            for fi in range(fs, min(fe + 1, n_frames)):
                                dist = abs(fi - pk) / max(zone_len / 2, 1)
                                w = max(0.0, 1.0 - dist ** 2)
                                correction[fi, TBX_IDX] += tbx_deficit * w * 0.5
        else:
            # Fricatives: no parameter correction
            if pk < n_frames:
                trace.rho_measured = float(np.linalg.norm(pval_trajectory[pk, :nvp]))
            else:
                trace.rho_measured = 0.0
            trace.needs_correction = False

    trace_result.rho_correction_curve = correction
    return trace_result


def build_pexp_curve(timer_data, n_frames):
    """Builds the additive pulmonary Pexp curve."""
    if timer_data.total_duration_ms <= 0 or not timer_data.pexp_marks:
        return np.zeros(n_frames)

    dt_ms = timer_data.total_duration_ms / n_frames
    t = np.linspace(0, timer_data.total_duration_ms, n_frames, endpoint=False)
    curve = np.zeros(n_frames)

    for mark in timer_data.pexp_marks:
        if mark.pexp_type == 'burst':
            rise_end = mark.t_peak_ms
            peak_end = mark.t_peak_ms + BURST_PEAK_DURATION_MS
            decay_end = mark.t_end_ms
            for i, ti in enumerate(t):
                if ti < mark.t_start_ms or ti > decay_end:
                    continue
                elif ti < rise_end:
                    progress = (ti - mark.t_start_ms) / max(rise_end - mark.t_start_ms, 0.1)
                    curve[i] = max(curve[i], mark.amplitude * progress * 0.5)
                elif ti < peak_end:
                    curve[i] = max(curve[i], mark.amplitude)
                else:
                    dt_sp = ti - peak_end
                    curve[i] = max(curve[i], mark.amplitude * np.exp(-dt_sp / BURST_DECAY_MS))
        elif mark.pexp_type == 'frication':
            for i, ti in enumerate(t):
                if ti < mark.t_start_ms or ti > mark.t_end_ms:
                    continue
                elif ti < mark.t_peak_ms:
                    progress = (ti - mark.t_start_ms) / max(mark.t_peak_ms - mark.t_start_ms, 0.1)
                    curve[i] = max(curve[i], mark.amplitude * (1 - np.exp(-3 * progress)))
                else:
                    curve[i] = max(curve[i], mark.amplitude)

    if timer_data.total_duration_ms > 0:
        curve = _exponential_filter(curve, TAU_PEXP_MS, dt_ms)
    return np.clip(curve, 0.0, 1.5)



# =============================================================================
# Display functions (debug)
# =============================================================================

def print_voicing_timer(marks: list) -> None:
    """Displays the voicing timer marks."""
    if not marks:
        print('  [voicing_timer] No marks')
        return
    print(f'  [voicing_timer] {len(marks)} marks:')
    for m in marks:
        pre = 'PRE-VOICING' if m.t_start_ms < m.t_target_ms else 'POST'
        print(f'    {m.seg_key:5s} t_target={m.t_target_ms:7.1f}ms '
              f'[{pre:14s}] t=[{m.t_start_ms:6.1f},{m.t_end_ms:6.1f}]ms '
              f'track={m.supraglottic_track:8s} shape={m.glottal_shape}')


def print_nasality_timer(marks: list) -> None:
    """Displays the nasality timer marks."""
    if not marks:
        print('  [nasality_timer] No marks')
        return
    print(f'  [nasality_timer] {len(marks)} marks:')
    for m in marks:
        print(f'    {m.seg_key:5s} t=[{m.t_open_ms:6.1f},{m.t_close_ms:6.1f}]ms '
              f'VO_target={m.vo_target:.2f}')

def print_lateral_timer(marks: list) -> None:
    """Displays the laterality timer marks."""
    if not marks:
        print('  [lateral_timer] No marks')
        return
    print(f'  [lateral_timer] {len(marks)} marks:')
    for m in marks:
        vt = 'VIRTUAL' if m.has_virtual_target else ''
        print(f'    {m.seg_key:5s} t_occl={m.t_occlusion_ms:7.1f}ms '
              f't=[{m.t_start_ms:6.1f},{m.t_end_ms:6.1f}]ms '
              f'TS3={m.ts3_target:.1f} {vt}')


# =============================================================================
# Reference pipeline timers (flat, nodes, block_info)
# =============================================================================
# These functions build the TimerData from the reference pipeline
# (parse_input → gesture → trajectory) instead of from the ChainElements.
# They are used when build_global_pval() is called directly.
# =============================================================================

def _frame_to_ms(frame: int, sr: float) -> float:
    """Convert a frame index to time (ms)."""
    return frame * 1000.0 / sr


def _map_nodes_to_blocks(flat: List[str], nodes: List,
                           block_info: list) -> List[dict]:
    """Maps each non-pause node to its block and frame range.

    Returns a list of dicts:
      { 'node': GestureNode, 'flat_idx': int,
        'block_idx': int, 'frame_start': int, 'frame_end': int }
    Only non-pause nodes are included.
    """
    # Build the flat_idx → node mapping
    flat_idx = 0
    node_map: dict = {}  # flat_idx → node
    for nd in nodes:
        if nd.kind == 'pause':
            continue
        # Skip pause segments in flat
        while flat_idx < len(flat) and flat[flat_idx] in ('GAP', '|'):
            flat_idx += 1
        if flat_idx < len(flat):
            node_map[flat_idx] = nd
            flat_idx += 1

    # Build the cumulative frame count per block
    block_starts: List[int] = []
    cumul = 0
    for bi in block_info:
        block_starts.append(cumul)
        cumul += bi.n_steps
    total_frames = cumul

    # Assign each node to its block
    result: List[dict] = []
    # The non-pause nodes in flat are aligned sequentially
    # with the non-pause blocks.
    # The flat_idx is used as the relative position.
    for flat_i, nd in sorted(node_map.items()):
        # Find the block that contains this node.
        # The nodes are distributed uniformly across the non-pause blocks.
        # The 'pause' and 'terminal' blocks have no nodes.
        pass

    # Simplified approach: distribute the non-pause nodes
    # over the block sequence, proportionally to n_steps.
    non_pause_blocks = [(i, bi) for i, bi in enumerate(block_info)
                       if bi.kind not in ('pause', 'terminal', 'initial')]
    non_pause_nodes = [nd for nd in nodes if nd.kind != 'pause']

    # Cumulative frames available in the non-pause blocks
    cumul_frames = 0
    for _, bi in non_pause_blocks:
        cumul_frames += bi.n_steps

    if cumul_frames == 0 or not non_pause_nodes:
        return result

    # Distribute the times uniformly
    dt_per_node = cumul_frames / max(len(non_pause_nodes), 1)
    for ni, nd in enumerate(non_pause_nodes):
        frame_start = int(ni * dt_per_node)
        frame_end = int((ni + 1) * dt_per_node)
        frame_start = min(frame_start, total_frames)
        frame_end = min(frame_end, total_frames)
        result.append({
            'node': nd,
            'flat_idx': ni,
            'frame_start': frame_start,
            'frame_end': frame_end,
        })

    return result


def build_reference_timers(
    flat: List[str],
    nodes: list,
    block_info: list,
    sr: float = 100.0,
) -> 'TimerData':
    """Builds the timers from the reference pipeline.

    Adaptation of build_all_timers() to the structures of the
    reference pipeline (parse_input → gesture → trajectory).

    Parameters
    ----------
    flat : list[str]
        Flat list of segments (output of parse_input).
    nodes : list[GestureNode]
        Gesture nodes (output of build_gesture_nodes).
    block_info : list[BlockInfo]
        Per-block information (output of build_global_pval).
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    TimerData
        Data of the three timers, compatible with
        build_voicing_curve(), build_vo_curve(), build_ts3_curve().
    """
    # Compute the total duration
    total_frames = sum(bi.n_steps for bi in block_info)
    total_ms = _frame_to_ms(total_frames, sr)

    # Map the nodes to frames
    node_frames = _map_nodes_to_blocks(flat, nodes, block_info)

    # --- Voicing marks ---
    voicing_marks: List[VoicingMark] = []
    for nf in node_frames:
        nd = nf['node']
        if nd.kind != 'C':
            continue
        seg_key = nd.seg_key
        f_start = nf['frame_start']
        f_end = nf['frame_end']
        f_mid = (f_start + f_end) // 2

        t_target = _frame_to_ms(f_mid, sr)
        voiced = seg_key in VOICED_CONSONANT_KEYS
        track = _get_supraglottic_track(seg_key)

        if voiced:
            if seg_key in PLOSIVE_KEYS:
                pre_voicing_ms = 25.0
            elif seg_key in VOICED_FRICATIVE_KEYS:
                pre_voicing_ms = 10.0
            elif seg_key in NASAL_KEYS:
                pre_voicing_ms = 15.0
            else:
                pre_voicing_ms = 15.0

            t_start = max(0.0, t_target - pre_voicing_ms)
            t_end = _frame_to_ms(f_end, sr)
            glottal_shape = 'modal'
        else:
            t_start = t_target
            t_end = t_target
            glottal_shape = 'voiceless'

        voicing_marks.append(VoicingMark(
            seg_key=seg_key,
            t_target_ms=t_target,
            is_voiced=voiced,
            t_start_ms=t_start,
            t_end_ms=t_end,
            glottal_shape=glottal_shape,
            supraglottic_track=track,
            position_in_syllable='onset',
            flat_idx=nf['flat_idx'],
        ))

    # --- Nasality marks ---
    nasality_marks: List[NasalityMark] = []
    for nf in node_frames:
        nd = nf['node']
        if nd.kind == 'C' and nd.seg_key in NASAL_KEYS:
            f_start = nf['frame_start']
            f_end = nf['frame_end']
            nasality_marks.append(NasalityMark(
                seg_key=nd.seg_key,
                t_open_ms=_frame_to_ms(f_start, sr),
                t_close_ms=_frame_to_ms(f_end, sr),
                vo_target=VO_NASAL_TARGET,
                flat_idx=nf['flat_idx'],
            ))

    # --- Lateral marks ---
    lateral_marks: List[LateralMark] = []
    for nf in node_frames:
        nd = nf['node']
        if nd.kind == 'C' and nd.seg_key in LATERAL_KEYS:
            f_start = nf['frame_start']
            f_end = nf['frame_end']
            f_mid = (f_start + f_end) // 2
            lateral_marks.append(LateralMark(
                seg_key=nd.seg_key,
                t_occlusion_ms=_frame_to_ms(f_mid, sr),
                ts3_target=TS3_LATERAL_TARGET,
                t_start_ms=_frame_to_ms(f_start, sr),
                t_end_ms=_frame_to_ms(f_end, sr),
                flat_idx=nf['flat_idx'],
                has_virtual_target=(nd.virtual_target is not None),
            ))

    return TimerData(
        voicing_marks=voicing_marks,
        nasality_marks=nasality_marks,
        lateral_marks=lateral_marks,
        total_duration_ms=total_ms,
        sr=sr,
    )
