# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
pulmonary_effort.py
====================
Pulmonary effort variable — final synthesis step.

This module implements the synthesis of pulmonary effort from:
  - The envelope E(t) (amplitude from block_info)
  - Pre-voicing V_pre(t) (voicing curve from the timer)
  - Nasality VO(t) (velum opening curve from the timer)

For some stops, the envelope E(t) is zeroed before the occlusion
(plosive consonant: complete tract closure). Pre-voicing and
nasality must then independently drive the pulmonary effort
to maintain phonation during the occlusion phase.

Architecture:

  E(t)           : amplitude envelope (block_info)
  V_pre(t)       : voicing curve (voicing timer)
  VO(t)          : nasality curve (nasality timer)
       │
       ▼
  compute_pulmonary_effort()  →  P_effort(t)
       │
       ├──→  subglottal pressure P(t)
       └──→  relative amplitude R(t)

Synthesis rules:
  1. During voiced stops (E(t) ≈ 0, V_pre(t) > 0):
     The effort is driven by pre-voicing: P_effort = V_pre(t)
     → pressure maintained for phonation during the occlusion.
  2. During nasals (VO(t) > 0):
     Nasal effort is added: P_effort += 0.5 * VO(t)
     → nasal murmur requires continuous air flow.
  3. During vowels and non-stop consonants:
     The effort is driven by E(t) normally.
  4. Final combination: P_effort(t) = max(E(t), V_pre(t), 0.3*VO(t))
     with a smooth transition (10 ms time constant).

Source: user specification, session 9.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


# Time constants
TAU_EFFORT_MS: float = 10.0  # Time constant for the final smoothing

# Pressure bounds (dPa) and relative amplitude
P_MIN: float = 400.0    # Minimum pressure (whisper)
P_MAX: float = 8000.0   # Maximum pressure (loud voice)
R_MIN: float = 0.0      # Minimum relative amplitude (silence)
R_MAX: float = 1.2      # Maximum relative amplitude


@dataclass
class PulmonaryEffortResult:
    """Result of pulmonary effort synthesis.

    Attributes
    ----------
    effort : np.ndarray, shape (N,)
        Combined pulmonary effort variable in [0, 1+].
    pressure : np.ndarray, shape (N,)
        Derived subglottal pressure (dPa).
    rel_amp : np.ndarray, shape (N,)
        Derived relative amplitude.
    e_contribution : np.ndarray, shape (N,)
        Contribution of E(t) to the effort.
    prevoicing_contribution : np.ndarray, shape (N,)
        Contribution of pre-voicing to the effort.
    nasality_contribution : np.ndarray, shape (N,)
        Contribution of nasality to the effort.
    """
    effort: np.ndarray
    pressure: np.ndarray
    rel_amp: np.ndarray
    e_contribution: np.ndarray
    prevoicing_contribution: np.ndarray
    nasality_contribution: np.ndarray
    pexp_pulmonary_contribution: np.ndarray


def _exponential_smooth(
    signal: np.ndarray,
    tau_ms: float,
    dt_ms: float,
) -> np.ndarray:
    """First-order exponential smoothing.

    y[n+1] = alpha * x[n] + (1 - alpha) * y[n]
    where alpha = dt / (tau + dt)
    """
    if tau_ms <= 0:
        return signal.copy()
    alpha = np.clip(dt_ms / (tau_ms + dt_ms), 0.0, 1.0)
    out = np.zeros_like(signal)
    y = 0.0
    for n in range(len(signal)):
        y = alpha * signal[n] + (1.0 - alpha) * y
        out[n] = y
    return out


def compute_pulmonary_effort(
    E: np.ndarray,
    V_pre: np.ndarray,
    VO: np.ndarray,
    sr: float = 100.0,
    plosive_mask: Optional[np.ndarray] = None,
    pexp_pulmonary: Optional[np.ndarray] = None,
) -> PulmonaryEffortResult:
    """Synthesize the pulmonary effort variable.

    Combines the envelope E(t), pre-voicing, and nasality
    into a single effort variable that drives the subglottal
    pressure and the relative amplitude.

    For stops, E(t) is zeroed during the occlusion phase.
    Pre-voicing and nasality then take over to maintain
    the phonatory effort.

    Parameters
    ----------
    E : np.ndarray, shape (N,)
        Amplitude envelope in [0, 1+].
    V_pre : np.ndarray, shape (N,)
        Voicing curve in [0, 1].
    VO : np.ndarray, shape (N,)
        Nasality curve (velum opening) in [0, 1].
    sr : float
        Sampling rate (Hz).
    plosive_mask : np.ndarray, shape (N,), optional
        Binary mask indicating plosive occlusion frames.
        If provided, E(t) is zeroed on these frames.

    Returns
    -------
    PulmonaryEffortResult
        Result containing the effort, pressure, and amplitude.
    """
    n = len(E)
    dt_ms = 1000.0 / sr  # time step in ms

    # --- Step 1: Zeroing of E(t) during stops ---
    E_eff = E.copy()
    if plosive_mask is not None:
        # During the plosive occlusion, the envelope is zeroed
        # (the tract is fully closed, no acoustic output)
        E_eff[plosive_mask > 0.5] = 0.0
        # Smooth transition entering and leaving the occlusion
        E_eff = _exponential_smooth(E_eff, 5.0, dt_ms)

    # --- Step 2: Pre-voicing contribution ---
    # Pre-voicing provides an independent effort during
    # voiced stops. The effort is proportional to
    # the voicing intensity (V_pre).
    #
    # For voiced stops (/b/, /d/, /g/):
    #   - V_pre > 0 during the occlusion → effort maintained
    #   - Pressure is reduced (no acoustic output)
    #     but sufficient to sustain vocal-fold vibration
    prevoicing_effort = V_pre * 0.6  # 60% of maximal effort for pre-voicing

    # --- Step 3: Nasality contribution ---
    # During nasal segments, air passes through the nasal cavity.
    # Nasal murmur requires continuous air flow,
    # hence pulmonary effort even when E(t) is low.
    #
    # For nasals (/m/, /n/, /N/):
    #   - VO > 0 → active nasal effort
    #   - Effort is proportional to the velum opening
    nasality_effort = VO * 0.5  # 50% of effort for nasal murmur

    # --- Step 4: Combining the contributions ---
    # The final effort is the maximum of the three contributions.
    # This guarantees that:
    #   - During vowels: E(t) dominates (normal effort)
    #   - During voiced stops: pre-voicing dominates
    #   - During nasals: nasality dominates
    #   - During transitions: the max ensures continuity
    # --- Step 4b: Pulmonary Pexp contribution (ADDITIVE) ---
    # WARNING: This Pexp is the VTL subglottal pressure,
    # totally independent of Berthommier's kinematic Pexp.
    # It is added to the base effort to produce bursts
    # (plosives) and frication (continuous constrictions).
    #
    # Addition guarantees that the burst/frication adds to the
    # existing voicing/devoicing without interacting with the
    # Berthommier model.
    pexp_contribution = np.zeros(n)
    if pexp_pulmonary is not None and len(pexp_pulmonary) == n:
        pexp_contribution = pexp_pulmonary

    effort_raw = np.maximum(
        np.maximum(E_eff, prevoicing_effort),
        np.maximum(nasality_effort, pexp_contribution),
    )

    # --- Step 5: Final smoothing ---
    # The effort variable is smoothed with a 10 ms time
    # constant to avoid overly abrupt transitions.
    effort = _exponential_smooth(effort_raw, TAU_EFFORT_MS, dt_ms)

    # --- Step 6: Deriving pressure and amplitude ---
    # Subglottal pressure and relative amplitude are
    # derived from the effort by nonlinear functions.
    #
    # P(t) = P_min + effort² × (P_max - P_min)
    # R(t) = R_min + effort × (R_max - R_min)
    #
    # Squaring the effort for pressure reflects the fact
    # that pressure grows faster than perceived effort.
    effort_sq = effort ** 2
    pressure = P_MIN + effort_sq * (P_MAX - P_MIN)
    rel_amp = R_MIN + effort * (R_MAX - R_MIN)

    # During silence (effort ≈ 0), force rel_amp to 0
    silence_mask = effort < 0.02
    rel_amp[silence_mask] = 0.0
    pressure[silence_mask] = P_MIN  # minimal residual pressure

    return PulmonaryEffortResult(
        effort=effort,
        pressure=pressure,
        rel_amp=rel_amp,
        e_contribution=E_eff,
        prevoicing_contribution=prevoicing_effort,
        nasality_contribution=nasality_effort,
        pexp_pulmonary_contribution=pexp_contribution,
    )


def build_plosive_mask(
    voicing_marks: list,
    total_duration_ms: float,
    n_frames: int,
    sr: float = 100.0,
) -> np.ndarray:
    """Build the plosive occlusion mask.

    For each VOICED plosive consonant, the mask is active
    between the start of pre-voicing and target attainment.
    This corresponds to the occlusion phase where E(t) must
    be zeroed.

    Parameters
    ----------
    voicing_marks : list[VoicingMark]
        Voicing timer marks.
    total_duration_ms : float
        Total duration (ms).
    n_frames : int
        Number of frames.
    sr : float
        Sampling rate (Hz).

    Returns
    -------
    np.ndarray, shape (n_frames,)
        Binary mask (1 = active plosive occlusion).
    """
    from vtl_synth.core.timers import PLOSIVE_KEYS

    mask = np.zeros(n_frames)
    if total_duration_ms <= 0:
        return mask

    t = np.linspace(0, total_duration_ms, n_frames, endpoint=False)

    for mark in voicing_marks:
        # Only voiced plosives
        if mark.seg_key not in PLOSIVE_KEYS:
            continue
        if not mark.is_voiced:
            continue
        # Check that this is pre-voicing (active occlusion)
        if hasattr(mark, 'is_prevoicing'):
            if not mark.is_prevoicing:
                continue
        elif mark.t_start_ms >= mark.t_target_ms:
            continue

        # The plosive occlusion runs from the start of pre-voicing
        # until the target is reached
        occ_start = mark.t_start_ms
        occ_end = mark.t_target_ms

        plosive_zone = (t >= occ_start) & (t <= occ_end)
        mask[plosive_zone] = 1.0

    return mask
