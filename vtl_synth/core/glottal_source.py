# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
glottal_source.py
==================
Rule engine for glottal source parameter generation.

Replaces the ad hoc glottis writes in AssembleTract.assemble() with a
proper shape-classification → smoothing → F0/pressure pipeline that
reproduces VTL's own gesture dynamics.

Architecture (5 steps):
  0. Data extraction from JD3.speaker  (in constants.py → JD3_GLOTTIS_PRESETS)
  1. Shape classification per segment  (glottal_shape_for_segment)
  2. Shape trajectory smoothing          (smooth_glottal_trajectory)
  3. F0(t) computation                   (compute_f0_contour)
  4. Subglottal pressure(t)             (compute_pressure — kept from assemble)

Time constant: VTL's default gesture dynamics = 12 ms critically-damped
low-pass filter (2nd-order Butterworth, cutoff = 1/(2π·τ)).

Source: VTL 2.4 documentation, Birkholz (via JD3.speaker geometric model)
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple

from .constants import (
    JD3_GLOTTIS_PRESETS,
    GLOTTIS_PARAM_NAMES,
    N_GLOTTIS_PARAMS,
    TARGET_SR,
    EFFORT_DEFAULTS,
)


# ==============================================================================
# STEP 1 — Shape classification per segment
# ==============================================================================

# IPA keys for each manner class
_PLOSIVES: frozenset = frozenset({'p', 'b', 't', 'd', 'k', 'g'})
_FRICATIVES: frozenset = frozenset({'f', 'v', 's', 'z', 'S', 'Z', 'T', 'D'})
_NASALS: frozenset = frozenset({'m', 'n', 'N', 'J'})
_APPROXIMANTS: frozenset = frozenset({'l', 'L', 'w', 'j', 'R'})
_GLOTTAL: frozenset = frozenset({'?'})  # glottal stop

# Voiced counterparts (for devoicing detection)
_VOICELESS: frozenset = frozenset({'p', 't', 'k', 'f', 's', 'S', 'T'})


# Valid shape labels — the rule engine's output vocabulary
VALID_SHAPES = frozenset({
    'modal',
    'voiced-fricative',
    'voiceless-fricative',
    'voiceless-plosive',  # BUG-ACTIVE-002: distinct JD3 preset (≈ fricative
                          # but kept separate to track identity)
    'stop',           # covers voiced-plosive & voiceless-plosive
    'breathy',
    'voiceless',      # generic voiceless (fallback)
})


def glottal_shape_for_segment(ipa_key: str, voicing: float) -> str:
    """Classify a segment's glottal shape from IPA key and voicing value.

    Parameters
    ----------
    ipa_key : str
        IPA key for the segment (e.g. 'b', 'a', 's', 'm').
    voicing : float
        Voicing value in [0, 1].  >0.5 = voiced, <=0.5 = voiceless.

    Returns
    -------
    str
        One of VALID_SHAPES.

    Raises
    ------
    ValueError
        If the segment doesn't fit any known category.
    """
    voiced = voicing > 0.5

    # Vowels and approximants → modal
    if ipa_key in _APPROXIMANTS or _is_vowel_key(ipa_key):
        return 'modal'

    # Nasals → modal (always voiced in French)
    if ipa_key in _NASALS:
        return 'modal'

    # Plosives
    if ipa_key in _PLOSIVES:
        if voiced:
            # Pre-voicing (C1-C3): the glottis stays in a phonation
            # configuration ('modal') during the occlusion — the
            # voicing bar amplitude is controlled downstream by pressure
            # (PREVOICING_PRESSURE) and rel_amp (pre-voicing bounds).
            # The former 'stop' (pressed glottis, x_bottom/x_top ≈ −0.01)
            # smothered all phonation during the occlusion.
            return 'modal'
        else:
            # BUG-ACTIVE-002: use the JD3 'voiceless-plosive' preset
            # (distinct from 'voiceless-fricative' in JD3_GLOTTIS_PRESETS)
            return 'voiceless-plosive'

    # Fricatives
    if ipa_key in _FRICATIVES:
        if voiced:
            return 'voiced-fricative'
        else:
            return 'voiceless-fricative'

    # Glottal stop / h
    if ipa_key in _GLOTTAL or ipa_key == 'h':
        return 'voiceless-fricative'

    # Unknown — raise rather than guess
    raise ValueError(
        f"Cannot classify glottal shape for IPA key '{ipa_key}' "
        f"(voicing={voicing:.2f}). Not in plosives, fricatives, nasals, "
        f"approximants, or vowels."
    )


def _is_vowel_key(key: str) -> bool:
    """Check if an IPA key is a vowel."""
    from .constants import VOWEL_TARGETS
    return key in VOWEL_TARGETS


# ==============================================================================
# STEP 2 — Shape trajectory smoothing (critically-damped low-pass)
# ==============================================================================
# VTL's gesture dynamics use a time constant of ~12 ms.
# At TARGET_SR=100 Hz, one frame = 10 ms.
# Critically-damped 2nd-order filter:  ω₀ = 1/τ, ζ = 1
# Equivalent to 2nd-order Butterworth with cutoff fc = 1/(2πτ)
#
# τ = 12 ms  →  fc = 1/(2π·0.012) ≈ 13.26 Hz
# At 100 Hz:  fn = 50 Hz,  fc/fn = 0.265

VTL_GESTURE_TAU_MS: float = 12.0  # VTL default gesture time constant (ms)


def _butterworth2_coeffs(
    sr: float, tau: float = VTL_GESTURE_TAU_MS,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (b, a) coefficients for a 2nd-order critically-damped filter.

    Critically-damped:  ζ = 1  →  Q = 0.5  →  Butterworth order 2.
    Cutoff:  fc = 1 / (2π · τ)

    Parameters
    ----------
    sr : float
        Sampling rate (Hz).
    tau : float
        Time constant (seconds).

    Returns
    -------
    (b, a) : tuple of ndarray
        Filter coefficients (numerator, denominator).
    """
    from scipy.signal import butter
    tau_s = tau / 1000.0
    fc = 1.0 / (2.0 * np.pi * tau_s)
    fn = sr / 2.0
    # Clamp fc to valid range
    fc = min(fc, fn * 0.99)
    return butter(N=2, Wn=fc / fn, btype='low')


def smooth_glottal_trajectory(
    shape_events: List[Tuple[str, int]],
    n_frames: int,
    sr: float = TARGET_SR,
    tau: float = VTL_GESTURE_TAU_MS,
) -> np.ndarray:
    """Produce a smoothed per-frame glottis control vector at sr.

    Given a sequence of (shape_label, start_frame) events, construct
    a piecewise-constant glottis vector from JD3_GLOTTIS_PRESETS, then
    apply VTL-matching critically-damped low-pass filtering.

    Parameters
    ----------
    shape_events : list of (str, int)
        Ordered list of (shape_label, start_frame).  The last event's
        shape extends to n_frames.
    n_frames : int
        Total number of output frames.
    sr : float
        Sampling rate (Hz).  Default: TARGET_SR (100).
    tau : float
        Time constant (ms).  Default: 12 ms (VTL gesture dynamics).

    Returns
    -------
    np.ndarray, shape (n_frames, 11)
        Smoothed glottis control vector.  Columns follow GLOTTIS_PARAM_NAMES.
        Only columns 2-10 (XB..AS) are filled; columns 0 (F0) and 1 (PR)
        are left at 0 — they are overridden by Step 3 and Step 4.
    """
    if not shape_events:
        return np.zeros((n_frames, N_GLOTTIS_PARAMS), dtype=np.float64)

    # Build piecewise-constant vector from JD3 presets
    raw = np.zeros((n_frames, N_GLOTTIS_PARAMS), dtype=np.float64)
    for i, (label, start) in enumerate(shape_events):
        # Determine end frame
        if i + 1 < len(shape_events):
            end = shape_events[i + 1][1]
        else:
            end = n_frames
        start = min(start, n_frames)
        end = min(end, n_frames)

        if start >= end:
            continue

        # Look up preset vector
        preset = _lookup_preset_vector(label)
        raw[start:end, :] = preset

    # Apply critically-damped low-pass filter to each param column
    # Filter columns 2-10 only (skip F0=0, PR=0 — filled later)
    try:
        b, a = _butterworth2_coeffs(sr, tau)
        from scipy.signal import filtfilt
        for col in range(2, N_GLOTTIS_PARAMS):
            raw[:, col] = filtfilt(b, a, raw[:, col])
    except ImportError:
        # Fallback: simple exponential smoothing if scipy not available
        alpha = 1.0 - np.exp(-1.0 / (tau / 1000.0 * sr))
        for col in range(2, N_GLOTTIS_PARAMS):
            for i in range(1, n_frames):
                raw[i, col] = alpha * raw[i, col] + (1 - alpha) * raw[i - 1, col]

    return raw


def _lookup_preset_vector(label: str) -> np.ndarray:
    """Get the 11-element control vector for a glottal shape label.

    Uses JD3_GLOTTIS_PRESETS when available, falls back to generic.
    """
    # Normalize label names
    normalized = label
    if label == 'voiceless':
        normalized = 'voiceless-fricative'

    if normalized in JD3_GLOTTIS_PRESETS:
        return JD3_GLOTTIS_PRESETS[normalized].to_vector()

    # Fallback: return modal
    if 'modal' in JD3_GLOTTIS_PRESETS:
        return JD3_GLOTTIS_PRESETS['modal'].to_vector()

    # Absolute fallback (should not happen)
    v = np.zeros(N_GLOTTIS_PARAMS, dtype=np.float64)
    v[0] = 120.0   # f0
    v[1] = 8000.0  # pressure
    v[6] = 1.0     # rel_amp
    return v


# ==============================================================================
# STEP 3 — F0(t)
# ==============================================================================

# Micro-prosody coupling constant.
# k_micro controls how much effort deviation modulates F0.
# Typical range: 5–20 Hz per unit E.  Start conservative.
F0_MICRO_K: float = 10.0  # Hz per unit E deviation


def compute_f0_contour(
    n_frames: int,
    f0_base: float,
    E: np.ndarray,
    V: np.ndarray,
    sr: float = TARGET_SR,
    k_micro: float = F0_MICRO_K,
) -> np.ndarray:
    """Compute F0(t) with micro-prosody and no zeroing during unvoiced.

    F0(t) = F0_base + k_micro · (E(t) - mean(E))

    During unvoiced stretches (V < 0.5), the LAST voiced F0 value is
    held for numeric continuity — f0 is NOT zeroed.  The glottis shape
    vector's rel_amp controls actual voicing; f0 must remain defined
    for smooth transitions.

    Parameters
    ----------
    n_frames : int
        Number of frames.
    f0_base : float
        Speaker's baseline F0 (Hz).  e.g. 102.2 for JD3 default.
    E : np.ndarray, shape (n_frames,)
        Effort envelope.
    V : np.ndarray, shape (n_frames,)
        Voicing signal (0=voiceless, 1=voiced).
    sr : float
        Sampling rate (Hz).
    k_micro : float
        Micro-prosody gain (Hz per unit E deviation).

    Returns
    -------
    np.ndarray, shape (n_frames,)
        F0 contour.  Always > 0.
    """
    E_mean = np.mean(E) if len(E) > 0 else 0.0
    f0 = np.full(n_frames, f0_base + k_micro * (E - E_mean), dtype=np.float64)

    # Clamp to physiological range
    f0 = np.clip(f0, 40.0, 600.0)

    # During voiceless stretches, hold the last voiced value.
    # This preserves numeric continuity and avoids zero-F0 artifacts.
    voiced_mask = V > 0.5
    last_voiced_f0 = f0_base
    for i in range(n_frames):
        if voiced_mask[i]:
            last_voiced_f0 = f0[i]
        else:
            f0[i] = last_voiced_f0

    return f0


# ==============================================================================
# STEP 4 — Subglottal pressure (quadratic E mapping)
# ==============================================================================

P_MIN: float = 0.0      # dPa — true silence (boundary frames only)
P_MIN_PHONATION: float = 3000.0   # dPa — floor for voiced frames outside true silence
P_MAX: float = EFFORT_DEFAULTS.P_max   # dPa — full phonation (single source: EffortBounds, HARD-001)


def compute_pressure(
    E: np.ndarray,
    V: np.ndarray | None = None,
    p_min: float = P_MIN,
    p_max: float = P_MAX,
    p_min_phonation: float = P_MIN_PHONATION,
) -> np.ndarray:
    """Compute subglottic pressure from effort envelope.

    P(t) = P_MIN + E_clamp^1.2 * (P_MAX - P_MIN)

    Pure E² was abandoned: it crushed the amplitude when E dropped
    to 0.5 -> P = 0.25 * deltaP. The E^1.2 mapping is more linear.

    When V(t) is provided, P is floored at P_MIN_PHONATION during
    voiced frames (V > 0.5), guaranteeing P >= 3000 dPa
    during phonation. This prevents the inter-syllabic
    collapse.

    Parameters
    ----------
    E : np.ndarray, shape (n_frames,)
        Effort envelope.
    V : np.ndarray, shape (n_frames,), optional
        Voicing signal (0/1). If provided, enables phonation floor.
    p_min, p_max : float
        Pressure range (dPa).
    p_min_phonation : float
        Minimum pressure during voiced frames (dPa).

    Returns
    -------
    np.ndarray, shape (n_frames,)
        Pressure contour (dPa).
    """
    E_clamp = np.clip(E, 0.0, 1.5)

    # E^1.2 mapping instead of E² — less dynamic compression
    P = p_min + (E_clamp ** 1.2) * (p_max - p_min)

    # Apply a phonation floor if V(t) is available
    if V is not None and p_min_phonation > p_min:
        voiced_mask = V > 0.5
        P[voiced_mask] = np.maximum(P[voiced_mask], p_min_phonation)

    return P


# ==============================================================================
# STEP 5 — Pulmonary effort synthesis (E + pre-voicing + nasality)
# ==============================================================================

E_FLOOR_THRESHOLD: float = 0.05
E_PREVOICING_FLOOR: float = 0.30
E_NASAL_FLOOR: float = 0.25
E_PULMONARY_TAU_MS: float = 12.0
V_VOICING_THRESHOLD: float = 0.3
VO_NASAL_THRESHOLD: float = 0.2



def _asymmetric_smoothing(
    signal: np.ndarray,
    sr: float,
    tau_rise_ms: float = 6.0,
    tau_fall_ms: float = 20.0,
) -> np.ndarray:
    """Asymmetric exponential smoothing (fast rise, slow fall).

    When the signal rises (x[n] > y[n-1]), uses tau_rise (small →
    responsiveness). When it falls (x[n] < y[n-1]), uses tau_fall
    (large → energy retention).

    Directional filter:
      y[n] = alpha_rise * x[n] + (1 - alpha_rise) * y[n-1]   if x > y
      y[n] = alpha_fall * x[n] + (1 - alpha_fall) * y[n-1]   if x <= y

    Parameters
    ----------
    signal : np.ndarray
        Input signal (E_gated).
    sr : float
        Sampling frequency (Hz).
    tau_rise_ms : float
        Rise time constant (ms). Default: 6 ms.
    tau_fall_ms : float
        Fall time constant (ms). Default: 20 ms.

    Returns
    -------
    np.ndarray
        Signal smoothed with asymmetric dynamics.
    """
    if len(signal) == 0:
        return signal.copy()
    dt_ms = 1000.0 / sr
    alpha_rise = dt_ms / (tau_rise_ms + dt_ms)
    alpha_fall = dt_ms / (tau_fall_ms + dt_ms)
    alpha_rise = np.clip(alpha_rise, 0.0, 1.0)
    alpha_fall = np.clip(alpha_fall, 0.0, 1.0)

    out = np.zeros_like(signal, dtype=np.float64)
    y = signal[0]
    for i in range(len(signal)):
        if signal[i] > y:
            # Rise: use tau_rise (fast)
            y = alpha_rise * signal[i] + (1.0 - alpha_rise) * y
        else:
            # Fall: use tau_fall (slow)
            y = alpha_fall * signal[i] + (1.0 - alpha_fall) * y
        out[i] = y
    return out


def _exponential_smoothing_1st_order(
    signal: np.ndarray,
    tau_ms: float,
    sr: float,
) -> np.ndarray:
    """First-order exponential smoothing of a signal.

    Filter: y[n+1] = alpha * x[n] + (1 - alpha) * y[n]
    where alpha = dt / (tau + dt)
    """
    if tau_ms <= 0 or len(signal) == 0:
        return signal.copy()
    dt_ms = 1000.0 / sr
    alpha = dt_ms / (tau_ms + dt_ms)
    alpha = np.clip(alpha, 0.0, 1.0)
    out = np.zeros_like(signal, dtype=np.float64)
    y = signal[0] if len(signal) > 0 else 0.0
    for i in range(len(signal)):
        y = alpha * signal[i] + (1.0 - alpha) * y
        out[i] = y
    return out





def compute_pulmonary_effort(
    E: np.ndarray,
    V: np.ndarray,
    VO: np.ndarray,
    sr: float = TARGET_SR,
    tau_ms: float = E_PULMONARY_TAU_MS,
    prevoicing_floor: float = E_PREVOICING_FLOOR,
    nasal_floor: float = E_NASAL_FLOOR,
    voicing_threshold: float = V_VOICING_THRESHOLD,
    nasal_threshold: float = VO_NASAL_THRESHOLD,
) -> np.ndarray:
    """Synthesize pulmonary effort from E(t), V(t), and VO(t).

    The pulmonary effort E_pulm(t) is the synthesis of three components:

      1. E(t) — COVTL amplitude envelope (from block_info)
         This is the main effort signal. For vowels it
         is close to 1.0; for consonants it can drop
         toward 0 (especially for stops).

      2. V(t) — voicing curve (from the voicing timer)
         During pre-voicing, V(t) > 0 but E(t) can be
         close to 0 (the envelope is zeroed before the occlusion).
         Effort must be sustained to maintain the vibration.

      3. VO(t) — nasality curve (from the nasality timer)
         During nasal segments, VO(t) > 0 but E(t) can
         be low. Effort must maintain a nasal airflow.

    Synthesis formula:

      E_demands(t) = max(
          E(t),
          V(t) > threshold ? E_prevoicing : 0,
          VO(t) > threshold ? E_nasal     : 0
      )

      E_pulm(t) = smooth(E_demands(t), tau=12ms)

    The exponential smoothing (12 ms, identical to the VTL gesture
    dynamics) ensures smooth effort transitions, avoiding
    acoustic artifacts when entering/exiting
    pre-voicing or nasality.

    Parameters
    ----------
    E : np.ndarray, shape (n_frames,)
        Amplitude envelope at 100 Hz.
    V : np.ndarray, shape (n_frames,)
        Voicing curve (0-1) from the timers.
    VO : np.ndarray, shape (n_frames,)
        Nasality curve (0-1) from the timers.
    sr : float
        Sampling frequency (Hz). Default: 100.
    tau_ms : float
        Smoothing time constant (ms). Default: 12.
    prevoicing_floor : float
        Minimum effort during pre-voicing. Default: 0.30.
    nasal_floor : float
        Minimum effort during nasality. Default: 0.25.
    voicing_threshold : float
        V(t) threshold above which voicing is active. Default: 0.3.
    nasal_threshold : float
        VO(t) threshold above which nasality is active. Default: 0.2.

    Returns
    -------
    np.ndarray, shape (n_frames,)
        E_pulm(t) — synthesized pulmonary effort, always ≥ 0.
        This signal replaces E(t) in the computation of the
        subglottal pressure P(t) and of rel_amp(t).

    Examples
    --------
    >>> E = np.array([0.0, 0.0, 0.5, 1.0, 1.0, 0.5, 0.0, 0.0])
    >>> V = np.array([0.8, 0.9, 0.5, 1.0, 1.0, 0.5, 0.1, 0.0])
    >>> VO = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.5])
    >>> E_pulm = compute_pulmonary_effort(E, V, VO)
    >>> # Frames 0-1 have E ≈ 0 but V > threshold → E_pulm ≈ 0.30 (pre-voicing)
    >>> # Frames 6-7 have E ≈ 0 but VO > threshold → E_pulm ≈ 0.25 (nasality)
    """
    n = len(E)
    if n == 0:
        return np.array([], dtype=np.float64)

    # Ensure the same length for all signals
    V_aligned = np.zeros(n, dtype=np.float64)
    VO_aligned = np.zeros(n, dtype=np.float64)
    if len(V) > 0:
        V_aligned[:min(len(V), n)] = V[:min(len(V), n)]
    if len(VO) > 0:
        VO_aligned[:min(len(VO), n)] = VO[:min(len(VO), n)]

    # --- Component 1: E(t) — envelope (already provided) ---
    E_base = np.clip(E.copy(), 0.0, 1.5)

    # --- Component 2: voicing demand (pre-voicing) ---
    # During pre-voicing of voiced stops, V(t) > 0
    # but E(t) can be close to 0. Effort must be
    # sustained to maintain vocal fold vibration.
    voicing_demand = np.where(
        V_aligned > voicing_threshold,
        prevoicing_floor,
        0.0,
    )

    # --- Component 3: nasality demand ---
    # During nasal segments, VO(t) > 0 but E(t) can
    # be low. Effort must maintain a nasal airflow.
    nasal_demand = np.where(
        VO_aligned > nasal_threshold,
        nasal_floor,
        0.0,
    )

    # --- Synthesis: maximum of the three components ---
    # Taking the maximum guarantees that each demand
    # (envelope, voicing, nasality) is satisfied.
    # If the envelope is already sufficient (E > floor), it
    # naturally dominates.
    E_demands = np.maximum(E_base, np.maximum(voicing_demand, nasal_demand))

    # --- Exponential smoothing ---
    # The 12 ms smoothing (identical to the VTL gesture time
    # constant) ensures smooth transitions consistent
    # with the articulatory model dynamics.
    # Without smoothing, a brutal effort transition would create
    # an audible subglottal pressure artifact.
    E_pulm = _exponential_smoothing_1st_order(E_demands, tau_ms, sr)

    return E_pulm


def compute_pulmonary_effort_from_timers(
    E: np.ndarray,
    timer_data,
    sr: float = TARGET_SR,
) -> np.ndarray:
    """Simplified version using a TimerData directly.

    Builds V(t) and VO(t) from the timers, then calls
    compute_pulmonary_effort() for the synthesis.

    Parameters
    ----------
    E : np.ndarray, shape (n_frames,)
        Amplitude envelope.
    timer_data : TimerData
        Data of the three timers (voicing, nasality, laterality).
    sr : float
        Sampling frequency (Hz).

    Returns
    -------
    np.ndarray, shape (n_frames,)
        E_pulm(t) — synthesized pulmonary effort.
    """
    from vtl_synth.core.timers import build_voicing_curve, build_vo_curve

    n = len(E)
    V = build_voicing_curve(timer_data, n)
    VO = build_vo_curve(timer_data, n)

    return compute_pulmonary_effort(E, V, VO, sr=sr)


# ==============================================================================
# Full pipeline: shape events → complete glottis matrix
# ==============================================================================

def build_glottis_trajectory(
    shape_events: List[Tuple[str, int]],
    n_frames: int,
    E: np.ndarray,
    V: np.ndarray,
    f0_base: float = 102.216,
    sr: float = TARGET_SR,
    tau: float = VTL_GESTURE_TAU_MS,
    k_micro: float = F0_MICRO_K,
) -> np.ndarray:
    """Build the complete glottis control trajectory (Steps 2–4).

    Parameters
    ----------
    shape_events : list of (str, int)
        (shape_label, start_frame) events.
    n_frames : int
        Total frames.
    E : np.ndarray, shape (n_frames,)
        Effort envelope.
    V : np.ndarray, shape (n_frames,)
        Voicing signal.
    f0_base : float
        Speaker baseline F0 (Hz).
    sr : float
        Sampling rate.
    tau : float
        Gesture smoothing time constant (ms).
    k_micro : float
        Micro-prosody gain.

    Returns
    -------
    np.ndarray, shape (n_frames, 11)
        Complete glottis trajectory ready for VTL.
    """
    # Step 2: smoothed shape trajectory (fills cols 2-10)
    glottis = smooth_glottal_trajectory(shape_events, n_frames, sr, tau)

    # Step 3: F0(t)
    glottis[:, 0] = compute_f0_contour(n_frames, f0_base, E, V, sr, k_micro)

    # Step 4: Pressure(t) — E^1.2 mapping with phonation floor
    glottis[:, 1] = compute_pressure(E, V=V)

    # Step 4b: rel_amp(t) — E_gate with floor AND asymmetric smoothing
    #
    # Asymmetric smoothing is the key to avoiding the inter-syllabic
    # collapse:
    #   - τ_rise  = 6 ms  (fast rise, crisp attack)
    #   - τ_fall  = 20 ms (slow fall, energy retention)
    #
    # This guarantees the glottal source does not die out between
    # two consecutive voiced syllables.
    E_GATE_FLOOR = 0.35
    # C3: rel_amp bounds during voiced closures (low-amplitude
    # voicing bar, closed oral cavity).
    PREVOICING_REL_AMP_MIN = 0.10
    PREVOICING_REL_AMP_MAX = 0.18
    # C2: target pressure during voiced closure (replaces the
    # P_MIN_PHONATION=3000 floor on those frames: more discreet pre-voicing).
    PREVOICING_PRESSURE = 1800.0  # dPa
    E_clamp = np.clip(E, 0.0, 1.5)

    # Apply the E_GATE_FLOOR floor to E_clamp
    E_gated = np.maximum(E_clamp, E_GATE_FLOOR)

    # Asymmetric smoothing: fast rise, slow fall
    E_gate_smooth = _asymmetric_smoothing(E_gated, sr=sr,
                                          tau_rise_ms=6.0, tau_fall_ms=20.0)

    # rel_amp = E_gate_smooth, puis gated by V
    voiced = V > 0.5
    glottis[voiced, 6] = E_gate_smooth[voiced]
    glottis[~voiced, 6] = 0.0

    # Step 4c: Gate rel_amp by V(t)
    V_clamp = np.clip(V, 0.0, 1.0)
    glottis[:, 6] *= V_clamp

    # Step 4d: Suppress TRUE silence ONLY
    # True silence = E < 0.05 AND V < 0.5 (both must be low)
    # This avoids killing the pressure in transitions where E is low
    # but V is still active.
    silent_frames = (E < 0.05) & (V < 0.5)
    glottis[silent_frames, 1] = P_MIN  # pressure
    glottis[silent_frames, 6] = 0.0  # rel_amp

    # Step 4e (C3): voiced closures (pre-voicing /b,d,g/...).
    # When E has dropped (closure) but V keeps the voicing, the
    # voicing bar must remain at LOW amplitude: rel_amp bounded
    # to [PREVOICING_REL_AMP_MIN, PREVOICING_REL_AMP_MAX] and pressure
    # brought back to PREVOICING_PRESSURE (the P_MIN_PHONATION floor of
    # compute_pressure suited vowels but gave too strong
    # a pre-voicing).
    closure_voiced = (E < 0.05) & (V >= 0.5)
    if closure_voiced.any():
        glottis[closure_voiced, 6] = np.clip(
            glottis[closure_voiced, 6],
            PREVOICING_REL_AMP_MIN, PREVOICING_REL_AMP_MAX)
        glottis[closure_voiced, 1] = PREVOICING_PRESSURE

    return glottis


def classify_segment_events(
    segments: list,
    sr: float = TARGET_SR,
) -> List[Tuple[str, int]]:
    """Convert a list of segment objects to shape events for the glottal engine.

    Parameters
    ----------
    segments : list
        Segment objects (each with .key, .kind, .t_start, .t_end, .glottal_tag).
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    list of (str, int)
        (shape_label, start_frame) events, sorted by start_frame.
    """
    events = []
    for seg in segments:
        if seg.kind == 'V':
            shape = 'modal'
        else:
            # BUG-ACTIVE-001: Segment exposes .voice (bool), not .voicing —
            # the former getattr(seg, 'voicing', 1.0) made all
            # consonants voiced by default.
            voicing = 1.0 if getattr(seg, 'voice', True) else 0.0
            shape = glottal_shape_for_segment(seg.key, voicing)

        start_frame = max(0, int(round(seg.t_start * sr / 1000.0)))
        events.append((shape, start_frame))

    # Sort by start frame
    events.sort(key=lambda x: x[1])
    return events


def classify_block_events(
    block_info: list,
    cons_keys: list,
    sr: float = TARGET_SR,
) -> List[Tuple[str, int]]:
    """Shape events aligned with block_info (the trajectory's REAL timing).

    Fixes the oscillations of the glottis parameters (x_top, chink...)
    at the start of a sequence: ``classify_segment_events`` uses the PARSER's
    t_start values (segment durations ~50-60 ms), which run ~2.3× faster
    than the real trajectory — stop/modal events compress into
    the first frames (x_top zigzags −0.01↔+0.02, chink −0.001↔0.05)
    then the shape freezes on the last event for everything else.

    Here, each trajectory block emits its events at the right time:
      - cluster → one shape per consonant (frames spread out),
      - plateau / background → 'modal',
      - pause / terminal / initial / decay / attack → no event
        (previous shape held).
    An initial 'modal' is emitted at frame 0; consecutive identical
    labels are deduplicated.

    Parameters
    ----------
    block_info : list
        Blocks of parse_to_tract_trajectory (kind, n_steps, cons_tokens...).
    cons_keys : list[str]
        IPA keys of the consonants in chronological order.
    sr : float
        Sampling frequency of the block frames (Hz).

    Returns
    -------
    list of (str, int)
        (shape_label, start_frame) events, sorted.
    """
    from .constants import VOICED_CONSONANT_KEYS

    events: List[Tuple[str, int]] = [('modal', 0)]
    ki = 0
    off = 0
    for b in block_info:
        n_steps = b.n_steps
        if b.kind == 'cluster':
            n_cons = b.n_cons if b.n_cons > 0 else len(b.cons_tokens)
            keys = cons_keys[ki:ki + n_cons]
            ki += n_cons
            for k, key in enumerate(keys):
                s0 = off + int(round(k * n_steps / max(len(keys), 1)))
                voicing = 1.0 if key in VOICED_CONSONANT_KEYS else 0.0
                try:
                    shape = glottal_shape_for_segment(key, voicing)
                except ValueError:
                    shape = 'modal'
                events.append((shape, s0))
        elif b.kind in ('plateau', 'background'):
            events.append(('modal', off))
        # pause/terminal/initial/decay/attack: hold the previous shape
        off += n_steps

    dedup = [events[0]]
    for label, f in events[1:]:
        if label != dedup[-1][0] or f == 0:
            dedup.append((label, f))
    return dedup


# ==============================================================================
# Reference pipeline integration (flat, nodes, block_info)
# ==============================================================================
# Build glottal trajectory from the reference pipeline outputs
# (parse_input → gesture → trajectory) instead of ChainElements.
# ==============================================================================

def classify_nodes_to_shape_events(
    nodes: list,
    block_info: list,
    sr: float = TARGET_SR,
) -> List[Tuple[str, int]]:
    """Convert gesture nodes + block_info to shape events.

    For each block in block_info, determines the glottal shape from
    the nodes it contains, and produces (shape_label, start_frame)
    events compatible with smooth_glottal_trajectory().

    Parameters
    ----------
    nodes : list[GestureNode]
        Gesture nodes from build_gesture_nodes.
    block_info : list[BlockInfo]
        Block info from build_global_pval.
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    list of (str, int)
        (shape_label, start_frame) events.
    """
    # Build a shape event for each block
    events: List[Tuple[str, int]] = []
    cumul_frames = 0

    # Get non-pause nodes in order
    non_pause_nodes = [nd for nd in nodes if nd.kind != 'pause']
    n_np = len(non_pause_nodes)

    # Count non-pause block frames for proportional distribution
    non_pause_total = sum(
        bi.n_steps for bi in block_info
        if bi.kind not in ('pause', 'terminal', 'initial')
    )

    for bi in block_info:
        start = cumul_frames
        cumul_frames += bi.n_steps

        if bi.kind in ('pause', 'terminal', 'initial'):
            # Silence → voiceless
            events.append(('voiceless', start))
            continue

        if bi.kind == 'plateau':
            events.append(('modal', start))
            continue

        if bi.kind == 'background':
            events.append(('modal', start))
            continue

        if bi.kind in ('cluster', 'attack', 'decay'):
            # Determine shape from pre/post tokens
            # Cluster/attack: use voiceless if no vowel context
            if bi.pre_token in ('V', 'y') and bi.post_token in ('V', 'y'):
                events.append(('modal', start))
            elif bi.pre_token in ('V', 'y'):
                # V → C: transition
                events.append(('stop', start))
            elif bi.post_token in ('V', 'y'):
                # C → V: transition
                # Check if consonant is voiced
                if non_pause_nodes:
                    events.append(('stop', start))
                else:
                    events.append(('voiceless', start))
            else:
                events.append(('voiceless', start))
            continue

        # Default
        events.append(('modal', start))

    return events
