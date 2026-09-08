# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
trajectory.py
==============
Graph construction, execution, and the full tract trajectory.

Orchestrates the three levels of the model:

  1. **Planning** (polar.py): z(t) trajectories in the complex plane
  2. **Coordination** (projection.py): COVTL projection
  3. **Selection / Superposition** (projection.py): V and C branches

This module contains:
  - Graph construction (CV, CVC, CCV, vocalic-only)
  - Execution of superposition segments → per-frame parameters
  - Computation of the full trajectory (compute_tract_trajectory)
  - Scaling, hold, and extraction utilities

Reference: Frédéric Berthommier, "Why can big.bi be changed to bi.gbi?
A mathematical model of syllabification and articulatory synthesis",
Interspeech 2023, arXiv:2307.02299.

Architecture:

    SEGMENTS / TTS
         │
         ▼
    GRAPH   (CV, CVC, CCV)
         │
    ┌────┴────┐
    ▼         ▼
  z_v(t)   z_c(t)       ← planning (polar.py)
    │         │
    └────┬────┘
         ▼
    SELECTION Sv / Sc    ← selection (projection.py)
         │
         ▼
    SUPERPOSITION         ← coordination + selection
         │
         ▼
      COVTL               ← projection (projection.py)
         │
         ▼
    VTL tract parameters

Variables managed by this module (COVTL, 15 parameters):
    HX, HY, JX, JA, LP, LD, TCX, TCY, TTX, TTY,
    TBX, TBY, TS1, TS2, TS3

Variables OUTSIDE this module (extension engine):
    VS, VO (nasality), TRX, TRY (auto VTL),
    f0, pressure, glottis (source)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from vtl_synth.core.constants import (
    CO_VTL,
    CONSONANT_TARGETS,
    VOWEL_TARGETS,
    TRACT_PARAM_NAMES,
    AUTO_PARAMS,
    COVTL_PARAMS,
    TCONS_DEFAULT,
    TVOY_DEFAULT,
    C_BEFORE_PAUSE_HOLD_MS,
)
from vtl_synth.core.polar import (
    polar_arc,
    stationary_point,
    ArcSpec,
    SuperpositionSegment,
    K_VOWEL_DEFAULT,
    K_CONSONANT_DEFAULT,
    NU_DIRECT,
    DELTA_O_DEFAULT,
    DELTA_E_DEFAULT,
    T_BASE_DEFAULT,
)
from vtl_synth.core.projection import (
    project_covtl,
    superimpose,
    normalize_consonant_key,
    get_selector_list,
    get_consonant_target,
)


# ==========================================================================
# Graph construction (CV, CVC, CCV)
# ==========================================================================

def build_cv_graph(
    vowel_key: str,
    consonant_key: str,
    T: float = T_BASE_DEFAULT,
    delta_o: float = DELTA_O_DEFAULT,
    sustain_ms: float = 0.0,
    K_v: float = K_VOWEL_DEFAULT,
    K_c: float = K_CONSONANT_DEFAULT,
    nu_c: int = 1,
    c_branch_start: Optional[Tuple[float, float]] = None,
    v_start: Optional[Tuple[float, float]] = None,
) -> SuperpositionSegment:
    """Builds the superposition graph for a CV syllable.

    Two construction modes depending on the syllabic context
    (COVTL reference):

    **Isolated mode** (c_branch_start=None, V_o == V):
        C branch: C → V   (1 arc, starting at the C target)
        V branch: V → V   (stationary, V_o == V)

    **Concatenated mode** (c_branch_start=None, V_o != V):
        C branch: V_o → C → V  (2 arcs, duration = 2T)
        V branch: V_o → V      (1 arc, duration = 2T)

    **Mode with explicit c_branch_start**:
        C branch: c_branch_start → V  (1 arc, starting at the specified point)
        V branch: v_start → V (if v_start != V) or V → V

    The ``c_branch_start`` parameter specifies the starting point of
    the consonantal branch. If None and V_o != V, the
    graph uses V_o → C → V (2 arcs). If None and V_o == V, the
    graph reduces to C → V (1 arc).

    Parameters
    ----------
    vowel_key : str
        IPA key of the vowel.
    consonant_key : str
        IPA key of the consonant.
    T : float
        Base period (ms). Default: 100.
    delta_o : float
        Anticipation factor (ρ reduction at V_o). Default: 0.7.
    sustain_ms : float
        Duration of the vocalic sustain (ms). 0 = no sustain.
    K_v, K_c : float
        Vowel/consonant curvature.
    nu_c : int
        Consonantal curvature orientation.
    c_branch_start : tuple[float, float] or None
        Explicit starting point (ρ, θ) for the C branch.
        If provided, the C branch is a single arc: c_branch_start → V.
        If None, the default graph V_o → C → V is used,
        except when V_o == V (isolation), where it reduces to C → V.
    v_start : tuple[float, float] or None
        Explicit starting point (ρ, θ) for the V branch.
        If provided, replaces V_o. If None, uses delta_o * rho_v.

    Returns
    -------
    SuperpositionSegment
    """
    rho_v, theta_v = VOWEL_TARGETS[vowel_key]

    # Consonant target (with special g/k handling)
    ct = get_consonant_target(consonant_key, theta_v)
    if ct is None:
        return build_vocalic_only(vowel_key, T=T)
    rho_c, theta_c = ct

    # Selectors (theta_v to choose g_vel vs g_pal)
    sel_c = get_selector_list(consonant_key, theta_v)
    if sel_c is None:
        return build_vocalic_only(vowel_key, T=T)

    # All COVTL parameters except AUTO_PARAMS, minus the selector
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v = [p for p in all_covtl if p not in sel_c]

    # Nodes
    V = (rho_v, theta_v)             # full vowel
    C = (rho_c, theta_c)             # consonant

    # V_o: either explicit via v_start, or computed via delta_o
    if v_start is not None:
        V_o = v_start
    else:
        V_o = (delta_o * rho_v, theta_v)

    # --- Determine the construction mode ---
    # Explicit c_branch_start: 1 arc C → V from this point
    if c_branch_start is not None:
        arc_c = ArcSpec(
            rho1=c_branch_start[0], theta1=c_branch_start[1],
            rho2=V[0], theta2=V[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal',
            consonant_key=consonant_key,
        )
        consonant_arcs = [arc_c]
        n_c_arcs_nominal = 1
    # V_o == V (isolation): reduced graph C → V
    elif abs(V_o[0] - V[0]) < 1e-6 and abs(V_o[1] - V[1]) < 1e-6:
        arc_c = ArcSpec(
            rho1=C[0], theta1=C[1],
            rho2=V[0], theta2=V[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal',
            consonant_key=consonant_key,
        )
        consonant_arcs = [arc_c]
        n_c_arcs_nominal = 1
    # V_o != V (concatenated): full graph V_o → C → V
    else:
        arc_c1 = ArcSpec(
            rho1=V_o[0], theta1=V_o[1],
            rho2=C[0], theta2=C[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal',
            consonant_key=consonant_key,
        )
        arc_c2 = ArcSpec(
            rho1=C[0], theta1=C[1],
            rho2=V[0], theta2=V[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal',
            consonant_key=consonant_key,
        )
        consonant_arcs = [arc_c1, arc_c2]
        n_c_arcs_nominal = 2

    # --- Vocalic branch ---
    vocalic_arcs_list = []
    if abs(V_o[0] - V[0]) < 1e-6 and abs(V_o[1] - V[1]) < 1e-6:
        # V_o == V: stationary
        arc_v = ArcSpec(
            rho1=V[0], theta1=V[1],
            rho2=V[0], theta2=V[1],
            duration_ms=T, K=K_v, nu=NU_DIRECT,
            orientation='inverse',
            selector='vocalic',
        )
    else:
        arc_v = ArcSpec(
            rho1=V_o[0], theta1=V_o[1],
            rho2=V[0], theta2=V[1],
            duration_ms=2.0 * T, K=K_v, nu=NU_DIRECT,
            orientation='inverse',
            selector='vocalic',
        )
    vocalic_arcs_list.append(arc_v)

    # --- Vocalic sustain ---
    if sustain_ms > 0:
        arc_sustain = ArcSpec(
            rho1=V[0], theta1=V[1],
            rho2=V[0], theta2=V[1],
            duration_ms=sustain_ms, K=K_v, nu=NU_DIRECT,
            orientation='inverse',
            selector='vocalic',
        )
        vocalic_arcs_list.append(arc_sustain)

    seg = SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=vocalic_arcs_list,
        selector_v=sel_v,
        selector_c=sel_c,
        consonant_keys=[consonant_key],
        vowel_key=vowel_key,
    )
    seg._n_c_arcs_nominal = n_c_arcs_nominal
    return seg


def build_cvc_graph(
    vowel_key: str,
    onset_key: str,
    coda_key: str,
    T: float = T_BASE_DEFAULT,
    delta_o: float = DELTA_O_DEFAULT,
    delta_e: float = DELTA_E_DEFAULT,
    K_v: float = K_VOWEL_DEFAULT,
    K_c: float = K_CONSONANT_DEFAULT,
    nu_c: int = 1,
) -> List[SuperpositionSegment]:
    """Builds the graph for a CVC syllable.

    Two symmetric superposition segments:
        Segment 1 (onset): V_o → C1 → V    (dur = 2T)
        Segment 2 (coda):  V → C2 → V_e    (dur = 2T)

    The V sustain between onset and coda is handled by the caller
    (compute_tract_trajectory) via the sustain_ms parameter
    of the parsing layer.

    Parameters
    ----------
    vowel_key : str
        IPA key of the vowel.
    onset_key : str
        IPA key of the onset consonant.
    coda_key : str
        IPA key of the coda consonant.
    T : float
        Base period (ms).
    delta_o, delta_e : float
        Anticipation/completion factors.
    K_v, K_c : float
        Vowel/consonant curvature.
    nu_c : int
        Consonantal curvature orientation.

    Returns
    -------
    list[SuperpositionSegment]
        Two superposition segments.
    """
    rho_v, theta_v = VOWEL_TARGETS[vowel_key]

    # Segment 1: CV (onset)
    seg1 = build_cv_graph(
        vowel_key, onset_key, T=T,
        delta_o=delta_o, K_v=K_v, K_c=K_c, nu_c=nu_c,
    )

    # Segment 2: VC (coda)
    ct2 = get_consonant_target(coda_key, theta_v)
    if ct2 is None:
        return [seg1]
    rho_c2, theta_c2 = ct2
    sel_c2 = get_selector_list(coda_key, theta_v)
    if sel_c2 is None:
        return [seg1]

    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_v2 = [p for p in all_covtl if p not in sel_c2]

    V_e = (delta_e * rho_v, theta_v)
    V = (rho_v, theta_v)
    C2 = (rho_c2, theta_c2)

    # Consonantal branch (coda): V → C2 → V_e
    arc_c1 = ArcSpec(
        rho1=V[0], theta1=V[1],
        rho2=C2[0], theta2=C2[1],
        duration_ms=T, K=K_c, nu=nu_c,
        orientation='inverse',
        selector='consonantal',
        consonant_key=coda_key,
    )
    arc_c2 = ArcSpec(
        rho1=C2[0], theta1=C2[1],
        rho2=V_e[0], theta2=V_e[1],
        duration_ms=T, K=K_c, nu=nu_c,
        orientation='inverse',
        selector='consonantal',
        consonant_key=coda_key,
    )

    # Vocalic branch (coda): V → V_e (dur = 2T)
    arc_v = ArcSpec(
        rho1=V[0], theta1=V[1],
        rho2=V_e[0], theta2=V_e[1],
        duration_ms=2.0 * T, K=K_v, nu=NU_DIRECT,
        orientation='inverse',
        selector='vocalic',
    )

    seg2 = SuperpositionSegment(
        consonant_arcs=[arc_c1, arc_c2],
        vocalic_arcs=[arc_v],
        selector_v=sel_v2,
        selector_c=sel_c2,
        consonant_keys=[coda_key],
        vowel_key=vowel_key,
    )

    return [seg1, seg2]


def build_ccv_graph(
    vowel_key: str,
    c1_key: str,
    c2_key: str,
    T: float = T_BASE_DEFAULT,
    delta_o: float = DELTA_O_DEFAULT,
    K_v: float = K_VOWEL_DEFAULT,
    K_c: float = K_CONSONANT_DEFAULT,
    nu_c: int = 1,
) -> SuperpositionSegment:
    """Builds the graph for a CCV syllable.

    Graph: V_o → C1 → C2 → V

    Branches (same duration = 3T):
        Consonantal: V_o → C1 (T) → C2 (T) → V (T)
        Vocalic:     V_e → V (3T)

    C1 and C2 belong to the SAME consonantal branch
    (cluster structure), not treated as two independent CVs.

    Parameters
    ----------
    vowel_key, c1_key, c2_key : str
        IPA keys.
    T, delta_o, K_v, K_c, nu_c :
        Model parameters.

    Returns
    -------
    SuperpositionSegment
    """
    rho_v, theta_v = VOWEL_TARGETS[vowel_key]

    ct1 = get_consonant_target(c1_key, theta_v)
    ct2 = get_consonant_target(c2_key, theta_v)

    if ct1 is None and ct2 is None:
        return build_vocalic_only(vowel_key, T=T)

    # Selectors — merged for the cluster
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    sel_set = set()
    if ct1 is not None:
        s1 = get_selector_list(c1_key, theta_v)
        if s1 is not None:
            sel_set.update(s1)
    if ct2 is not None:
        s2 = get_selector_list(c2_key, theta_v)
        if s2 is not None:
            sel_set.update(s2)
    sel_c = list(sel_set) if sel_set else None

    if sel_c is None:
        return build_vocalic_only(vowel_key, T=T)

    sel_v = [p for p in all_covtl if p not in sel_c]

    V_o = (delta_o * rho_v, theta_v)
    V = (rho_v, theta_v)

    # --- Consonantal branch: 3 arcs ---
    consonant_arcs = []
    consonant_keys = []

    if ct1 is not None:
        consonant_arcs.append(ArcSpec(
            rho1=V_o[0], theta1=V_o[1],
            rho2=ct1[0], theta2=ct1[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal', consonant_key=c1_key,
        ))
        consonant_keys.append(c1_key)

    if ct1 is not None and ct2 is not None:
        consonant_arcs.append(ArcSpec(
            rho1=ct1[0], theta1=ct1[1],
            rho2=ct2[0], theta2=ct2[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal', consonant_key=c2_key,
        ))
        consonant_keys.append(c2_key)
    elif ct2 is not None:
        consonant_arcs.append(ArcSpec(
            rho1=V_o[0], theta1=V_o[1],
            rho2=ct2[0], theta2=ct2[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal', consonant_key=c2_key,
        ))
        consonant_keys.append(c2_key)

    last_c = ct2 if ct2 is not None else ct1
    last_c_key = consonant_keys[-1] if consonant_keys else ''
    if last_c is not None:
        consonant_arcs.append(ArcSpec(
            rho1=last_c[0], theta1=last_c[1],
            rho2=V[0], theta2=V[1],
            duration_ms=T, K=K_c, nu=nu_c,
            orientation='inverse',
            selector='consonantal',
            consonant_key=last_c_key,
        ))

    # --- Vocalic branch: V_e → V (dur = 3T) ---
    arc_v = ArcSpec(
        rho1=V_o[0], theta1=V_o[1],
        rho2=V[0], theta2=V[1],
        duration_ms=3.0 * T, K=K_v, nu=NU_DIRECT,
        orientation='inverse',
        selector='vocalic',
    )

    return SuperpositionSegment(
        consonant_arcs=consonant_arcs,
        vocalic_arcs=[arc_v],
        selector_v=sel_v,
        selector_c=sel_c,
        consonant_keys=consonant_keys,
        vowel_key=vowel_key,
    )


def build_vocalic_only(
    vowel_key: str,
    T: float = T_BASE_DEFAULT,
) -> SuperpositionSegment:
    """Builds a purely vocalic segment (no superposition).

    Sv = 1, Sc = empty.
    """
    all_covtl = [p for p in CO_VTL.keys() if p not in AUTO_PARAMS]
    rho_v, theta_v = VOWEL_TARGETS[vowel_key]

    arc_v = ArcSpec(
        rho1=rho_v, theta1=theta_v,
        rho2=rho_v, theta2=theta_v,
        duration_ms=T, K=K_VOWEL_DEFAULT, nu=NU_DIRECT,
        orientation='inverse',
        selector='vocalic',
    )

    return SuperpositionSegment(
        vocalic_arcs=[arc_v],
        selector_v=all_covtl,
        selector_c=[],
        consonant_keys=[],
        vowel_key=vowel_key,
    )


# ==========================================================================
# Graph execution → time trajectories
# ==========================================================================

def execute_arc(arc: ArcSpec, sr: float) -> np.ndarray:
    """Executes an arc and returns the complex trajectory z(t).

    Parameters
    ----------
    arc : ArcSpec
        Arc specification.
    sr : float
        Sampling frequency (Hz).

    Returns
    -------
    np.ndarray, shape (n_samples,)
        Complex trajectory.
    """
    # Stationary point (same start/end)
    if (abs(arc.rho1 - arc.rho2) < 1e-10 and
            abs(arc.theta1 - arc.theta2) < 1e-10):
        z, _ = stationary_point(arc.rho1, arc.theta1,
                                arc.duration_ms, sr)
        return z

    z, _ = polar_arc(
        arc.rho1, arc.theta1,
        arc.rho2, arc.theta2,
        arc.duration_ms, sr,
        K=arc.K, nu=arc.nu,
        orientation=arc.orientation,
    )
    return z


def execute_superposition_segment(
    seg: SuperpositionSegment,
    sr: float = 100.0,
) -> Tuple[Dict[str, np.ndarray], int, np.ndarray]:
    """Executes a superposition segment → per-frame VTL parameters.

    Parameters
    ----------
    seg : SuperpositionSegment
        Superposition segment (from the graph).
    sr : float
        Sampling frequency (Hz).

    Returns
    -------
    tuple[dict[str, np.ndarray], int, np.ndarray]
        - Per-frame COVTL parameters (each value is an ndarray)
        - Number of frames generated
        - z_v: complex vocalic trajectory (n_frames,)
          Lets you extract rho/theta without selection bias.
    """
    duration_c = sum(a.duration_ms for a in seg.consonant_arcs)
    duration_v = sum(a.duration_ms for a in seg.vocalic_arcs)

    if not seg.consonant_arcs or duration_c == 0:
        duration_c = duration_v

    n_frames_c = max(1, int(duration_c * sr / 1000.0))
    n_frames_v = max(1, int(duration_v * sr / 1000.0))
    n_frames = max(n_frames_c, n_frames_v)

    # --- Consonantal branch ---
    if seg.consonant_arcs and seg.selector_c:
        z_c_parts = []
        for idx, arc in enumerate(seg.consonant_arcs):
            z_part = execute_arc(arc, sr)
            if idx > 0 and len(z_part) > 1:
                z_part = z_part[1:]
            z_c_parts.append(z_part)
        z_c = np.concatenate(z_c_parts)
        if len(z_c) < n_frames:
            z_c = np.concatenate([z_c, np.full(n_frames - len(z_c), z_c[-1])])
        elif len(z_c) > n_frames:
            z_c = z_c[:n_frames]
    else:
        rho_v, theta_v = VOWEL_TARGETS[seg.vowel_key]
        z_c = np.full(n_frames, rho_v * np.exp(1j * theta_v),
                       dtype=np.complex128)

    # --- Vocalic branch ---
    z_v_parts = []
    for idx, arc in enumerate(seg.vocalic_arcs):
        z_part = execute_arc(arc, sr)
        if idx > 0 and len(z_part) > 1:
            z_part = z_part[1:]
        z_v_parts.append(z_part)
    z_v = np.concatenate(z_v_parts)
    if len(z_v) < n_frames:
        z_v = np.concatenate([z_v, np.full(n_frames - len(z_v), z_v[-1])])
    elif len(z_v) > n_frames:
        z_v = z_v[:n_frames]

    # --- Superposition ---
    if seg.selector_c:
        params = superimpose(
            z_v, z_c, seg.selector_v, seg.selector_c,
        )
    else:
        params = {}
        for p in seg.selector_v:
            c1, c0, c2 = CO_VTL[p]
            psi = c0 * np.exp(1j * c2)
            params[p] = c1 + np.real(psi * np.conj(z_v))

    return params, n_frames, z_v


# ==========================================================================
# Building the full trajectory from segments
# ==========================================================================



# ==========================================================================
# Scaling, hold, and extraction utilities
# ==========================================================================

def scale_durations_tcons_tvoy(
    seg: SuperpositionSegment,
    target_ms: float,
    tcons: float,
    tvoy: float,
    sustain_ms: float = 0.0,
    T: float = T_BASE_DEFAULT,
    n_c_arcs_nominal: Optional[int] = None,
) -> None:
    """Adjusts arc durations with the Tcons/Tvoy factors.

    Nominal timing (Berthommier 2023 model, cf. constants.py):

      For isolated CV (n_c_arcs = 1, C → V mode):
        C branch: 1 arc  x T = T   ->  with tcons: T*tcons
        V branch: stationary (duration not relevant)
        Target duration = T*tcons

      For concatenated CV (n_c_arcs = 2):
        C branch: 2 arcs x T = 2T  ->  with tcons: 2T*tcons
        V branch: 1 arc  x 2T = 2T ->  with tvoy: 2T*tvoy

      For CCV (n_c_arcs = 3):
        C branch: 3 arcs x T = 3T  ->  with tcons: 3T*tcons
        V branch: 1 arc  x 3T = 3T ->  with tvoy: 3T*tvoy

      For a CVC segment (n_c_arcs = 2 per sub-segment):
        Each sub-segment follows the CV logic above.

    The vocalic sustain (stationary V->V arc) is NOT
    re-scaled: it keeps its absolute duration.

    If the sum of transitions + sustain exceeds target_ms,
    a global compression factor is applied to the
    transitions only (not to the sustain). The compression
    preserves the tcons:tvoy ratio.

    If the sum is below target_ms (a frequent case when
    the vowel is long), the V branch (transitions + sustain)
    is longer than the C branch. execute_superposition_segment
    pads z_c with its last value (V) to equalize the
    lengths — this pad is the expected behavior: the consonant
    has finished its transition and holds at V during the
    vocalic surplus.

    Parameters
    ----------
    seg : SuperpositionSegment
        Superposition segment.
    target_ms : float
        Target total duration for the segment (ms).
    tcons, tvoy : float
        Multiplicative factors for the transitions.
        tcons modifies the consonantal arcs,
        tvoy modifies the vocalic transition arcs.
    sustain_ms : float
        Duration of the vocalic sustain (already in the V branch).
        This argument serves as documentation; the sustain is
        detected automatically (stationary arcs rho1~=rho2).
        It is also used for the global compression
        computation (step 4) to reserve the sustain space.
    T : float
        Base period (ms).
    n_c_arcs_nominal : int or None
        Number of nominal consonantal arcs. If None,
        uses seg._n_c_arcs_nominal if available,
        otherwise len(seg.consonant_arcs).
    """
    if not seg.consonant_arcs and not seg.vocalic_arcs:
        return

    # Nominal number of C arcs
    if n_c_arcs_nominal is None:
        n_c_arcs_nominal = getattr(seg, '_n_c_arcs_nominal', None)
        if n_c_arcs_nominal is None:
            n_c_arcs_nominal = len(seg.consonant_arcs)

    # --- 1. Nominal target durations ---
    c_transition_target = n_c_arcs_nominal * T * tcons
    v_transition_target = 2.0 * T * tvoy

    # --- 2. Scale the C branch to its nominal Tcons duration ---
    dur_c_current = sum(a.duration_ms for a in seg.consonant_arcs)
    if dur_c_current > 1e-6:
        scale_c = c_transition_target / dur_c_current
        for a in seg.consonant_arcs:
            a.duration_ms *= scale_c

    # --- 3. Scale the V branch (transitions only, not sustain) ---
    v_transition_arcs = []
    v_sustain_arcs = []
    for a in seg.vocalic_arcs:
        if abs(a.rho1 - a.rho2) < 1e-6 and abs(a.theta1 - a.theta2) < 1e-6:
            v_sustain_arcs.append(a)
        else:
            v_transition_arcs.append(a)

    dur_v_trans = sum(a.duration_ms for a in v_transition_arcs)
    if dur_v_trans > 1e-6:
        scale_v = v_transition_target / dur_v_trans
        for a in v_transition_arcs:
            a.duration_ms *= scale_v

    # --- 4. Global compression if target_ms is exceeded ---
    total_transition = c_transition_target + v_transition_target
    total_with_sustain = total_transition + sustain_ms
    if total_with_sustain > target_ms and total_transition > 1e-6:
        available_for_transitions = max(0.0, target_ms - sustain_ms)
        global_scale = available_for_transitions / total_transition
        if global_scale < 1.0:
            for a in seg.consonant_arcs:
                a.duration_ms *= global_scale
            for a in v_transition_arcs:
                a.duration_ms *= global_scale


def scale_durations(seg: SuperpositionSegment, target_ms: float) -> None:
    """Adjusts arc durations proportionally to the target.

    Parameters
    ----------
    seg : SuperpositionSegment
        Superposition segment.
    target_ms : float
        Target total duration (ms).
    """
    if not seg.consonant_arcs and not seg.vocalic_arcs:
        return

    dur_c = sum(a.duration_ms for a in seg.consonant_arcs)
    dur_v = sum(a.duration_ms for a in seg.vocalic_arcs)

    if dur_c > 0:
        scale_c = target_ms / dur_c
        for a in seg.consonant_arcs:
            a.duration_ms *= scale_c

    if dur_v > 0:
        scale_v = target_ms / dur_v
        for a in seg.vocalic_arcs:
            a.duration_ms *= scale_v


def append_c_hold(
    all_frames: list,
    all_rho_theta: list,
    c_node: 'GestureNode',
    nucleus_node: Optional['GestureNode'],
    c_hold_ms: float,
    sr: float,
    param_names: List[str],
) -> None:
    """Appends a stationary point (hold) at the consonant target.

    Used when a syllable ends with a coda consonant
    followed by a pause. The consonant is held for
    c_hold_ms before the transition to silence.

    **Selective Sc/Sv projection**:

    The consonantal selector (Sc) parameters are projected
    via z_c (C target). The vocalic parameters (Sv) are projected
    via z_v (V target). This corresponds to the model:
    P(t) = Sv . Re[Psi.conj(z_v)] + Sc . Re[Psi.conj(z_c)]
    with z_c constant = C target during the hold.

    Modifies all_frames and all_rho_theta in place.
    """
    theta_v = 0.0
    if nucleus_node is not None and nucleus_node.target is not None:
        theta_v = nucleus_node.target.theta

    ct = get_consonant_target(c_node.key, theta_v)
    if ct is None:
        return

    rho_h, theta_h = ct
    n_hold = max(1, int(c_hold_ms * sr / 1000.0))
    z_hold_c = rho_h * np.exp(1j * theta_h)
    z_hold_c_arr = np.full(n_hold, z_hold_c, dtype=np.complex128)

    sel_hold = get_selector_list(c_node.key, theta_v)
    hold_params = {}

    if nucleus_node is not None and nucleus_node.key in VOWEL_TARGETS:
        rho_v_h, theta_v_h = VOWEL_TARGETS[nucleus_node.key]
    else:
        rho_v_h, theta_v_h = 0.7, 0.0
    z_hold_v = rho_v_h * np.exp(1j * theta_v_h)
    z_hold_v_arr = np.full(n_hold, z_hold_v, dtype=np.complex128)

    sel_hold_set = set(sel_hold) if sel_hold else set()
    for p in param_names:
        if p not in CO_VTL:
            continue
        c1, c0, c2 = CO_VTL[p]
        psi = c0 * np.exp(1j * c2)
        if p in sel_hold_set:
            hold_params[p] = c1 + np.real(psi * np.conj(z_hold_c_arr))
        else:
            hold_params[p] = c1 + np.real(psi * np.conj(z_hold_v_arr))

    frames_hold = params_to_array(hold_params, param_names, n_hold)
    rt_hold = np.column_stack([
        np.full(n_hold, rho_h),
        np.full(n_hold, theta_h),
    ])
    all_frames.append(frames_hold)
    all_rho_theta.append(rt_hold)


def patch_arc_start(
    seg: SuperpositionSegment,
    v_start: Tuple[float, float],
) -> None:
    """Replaces the V_o starting point of all arcs
    (vocalic and consonantal) with v_start = (rho, theta).

    This operation ensures the continuity of z_v and z_c at the
    inter-syllabic junction point.

    Parameters
    ----------
    seg : SuperpositionSegment
        Segment whose arcs must be patched.
    v_start : tuple[float, float]
        (rho, theta) of the common starting point.
    """
    rho_s, theta_s = v_start
    if seg.vocalic_arcs:
        seg.vocalic_arcs[0].rho1 = rho_s
        seg.vocalic_arcs[0].theta1 = theta_s
    if seg.consonant_arcs:
        seg.consonant_arcs[0].rho1 = rho_s
        seg.consonant_arcs[0].theta1 = theta_s


def params_to_array(
    params: Dict[str, np.ndarray],
    param_names: List[str],
    n_frames: int,
) -> np.ndarray:
    """Converts a dict of parameters into an (n_frames, n_params) matrix.
    """
    arr = np.zeros((n_frames, len(param_names)), dtype=np.float64)
    for j, p in enumerate(param_names):
        if p in params:
            arr[:, j] = params[p][:n_frames]
    return arr


def extract_rho_theta_from_zv(
    z_v: np.ndarray,
) -> np.ndarray:
    """Extracts (rho, theta) directly from the z_v trajectory.

    Unlike the old version, which inverted TCX/TCY
    (biased if these parameters belong to Sc), this
    version uses z_v directly: no selection bias.

    Parameters
    ----------
    z_v : np.ndarray, shape (n_frames,)
        Complex vocalic trajectory.

    Returns
    -------
    np.ndarray, shape (n_frames, 2)
        Columns: [rho, theta].
    """
    rt = np.zeros((len(z_v), 2), dtype=np.float64)
    rt[:, 0] = np.abs(z_v)
    rt[:, 1] = np.angle(z_v)
    return rt


def extract_rho_theta(
    params: Dict[str, np.ndarray],
    n_frames: int,
    rho_v: float,
    theta_v: float,
) -> np.ndarray:
    """Extracts approximate (rho, theta) from the projected parameters.

    **Deprecated**: kept for backward compatibility.
    Prefer extract_rho_theta_from_zv(z_v), which has no
    selection bias (TCX/TCY may belong to Sc).

    Returns
    -------
    np.ndarray, shape (n_frames, 2)
    """
    rt = np.zeros((n_frames, 2), dtype=np.float64)
    c1_tcx, c0_tcx, c2_tcx = CO_VTL['TCX']
    c1_tcy, c0_tcy, c2_tcy = CO_VTL['TCY']
    tcx = np.asarray(params.get('TCX', np.full(n_frames, c1_tcx)), dtype=np.float64)
    tcy = np.asarray(params.get('TCY', np.full(n_frames, c1_tcy)), dtype=np.float64)
    dx = tcx - c1_tcx
    dy = tcy - c1_tcy
    A = np.array([
        [np.cos(c2_tcx), np.sin(c2_tcx)],
        [np.cos(c2_tcy), np.sin(c2_tcy)],
    ])
    b = np.stack([dx / c0_tcx, dy / c0_tcy], axis=0)
    det = A[0,0]*A[1,1] - A[0,1]*A[1,0]
    if abs(det) > 1e-10:
        Ainv = np.array([[A[1,1], -A[0,1]], [-A[1,0], A[0,0]]]) / det
        xy = Ainv @ b
        rt[:, 0] = np.sqrt(xy[0]**2 + xy[1]**2)
        rt[:, 1] = np.arctan2(xy[1], xy[0])
    else:
        rt[:, 0] = rho_v
        rt[:, 1] = theta_v
    return rt


def segment_into_syllable_groups(segments):
    """Groups segments into sub-lists by syllable.

    Each group corresponds to one syllable (up to the next
    pause segment or the end of the list).

    Parameters
    ----------
    segments : list
        List of segments (objects with a `kind` attribute).

    Returns
    -------
    list[list]
        List of groups of segments.
    """
    groups = []
    current = []
    for seg in segments:
        current.append(seg)
        # A pause or end segment terminates the group
        if getattr(seg, 'is_pause', False):
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups if groups else [segments] if segments else []


# ==========================================================================
# Backward-compatible aliases
# ==========================================================================

# Old names kept as aliases
covtl_arc = polar_arc
superimpose_covtl = superimpose
_scale_durations = scale_durations

_execute_arc = execute_arc
_segment_into_syllable_groups = segment_into_syllable_groups
_scale_durations_tcons_tvoy = scale_durations_tcons_tvoy
_build_vocalic_only = build_vocalic_only
_patch_arc_start = patch_arc_start
_append_c_hold = append_c_hold
_params_to_array = params_to_array
_extract_rho_theta_from_zv = extract_rho_theta_from_zv
_extract_rho_theta = extract_rho_theta
