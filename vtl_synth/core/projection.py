# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
projection.py
==============
Coordination (COVTL projection) and Selection/Superposition.

Level 2 — Coordination (eq. 1):
    P_i = c1_i + c0_i · rho · cos(c2_i - theta)

Level 3 — Selection / Superposition (eq. 4):
    P(t) = Sv ⊙ Re[ Ψ·z̄_v(t) ] + Sc ⊙ Re[ Ψ·z̄_c(t) ]

Reference: Frédéric Berthommier, "Why can big.bi be changed to bi.gbi?
A mathematical model of syllabification and articulatory synthesis",
Interspeech 2023, arXiv:2307.02299.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from vtl_synth.core.constants import (
    CO_VTL,
    CONSONANT_TARGETS,
    VOWEL_TARGETS,
    AUTO_PARAMS,
)

# Palatal criterion for /g/,/k/:
#   Front vowel → theta > π → palatal context (g_pal)
#   /a/ (theta = π) or back vowel → velar context (g_vel)
_IS_PALATAL_THRESHOLD = np.pi


# ==========================================================================
# Level 2 — Coordination: COVTL projection
# ==========================================================================

def project_covtl(z: Union[complex, np.ndarray]) -> Dict[str, float]:
    """COVTL projection: complex z → articulatory parameters.

    Implements equation (1) of Berthommier 2023:

        P_i - Omega_i = Re[ Psi_i · conj(z) ]

    In our VTL parametrization:
        P_i = c1_i + Re[ c0_i · exp(i·c2_i) · conj(z) ]
              = c1_i + c0_i · |z| · cos(c2_i - arg(z))

    If z = rho · exp(i·theta), this gives:
        P_i = c1_i + c0_i · rho · cos(c2_i - theta)

    Parameters
    ----------
    z : complex or np.ndarray
        Point or trajectory in the complex plane.
        If scalar: returns a dict.
        If vector: returns a dict of np.ndarray.

    Returns
    -------
    dict[str, float | np.ndarray]
        Projected COVTL parameters.
    """
    result = {}
    for param_name, (c1, c0, c2) in CO_VTL.items():
        # Re[ c0 * exp(i*c2) * conj(z) ] = c0 * |z| * cos(c2 - arg(z))
        result[param_name] = c1 + c0 * np.real(np.exp(1j * c2) * np.conj(z))
    return result


def project_covtl_polar(rho: float, theta: float) -> Dict[str, float]:
    """COVTL projection from polar (rho, theta).

    Parameters
    ----------
    rho : float
        Polar radius.
    theta : float
        Polar angle (rad).

    Returns
    -------
    dict[str, float]
        COVTL parameter values.
    """
    z = rho * np.exp(1j * theta)
    return project_covtl(z)


# ==========================================================================
# Level 3 — Selection / Superposition
# ==========================================================================

def superimpose(
    z_v: np.ndarray,
    z_c: np.ndarray,
    selector_v: List[str],
    selector_c: List[str],
    covtl_params: Optional[Dict[str, Tuple[float, float, float]]] = None,
) -> Dict[str, np.ndarray]:
    """Superposition of the two branches according to equation (4).

    P(t) = Sv ⊙ Re[ Psi · conj(z_v(t)) ] + Sc ⊙ Re[ Psi · conj(z_c(t)) ]

    Each articulatory parameter belongs exclusively to one branch:
        Sv + Sc = 1  (vector of 1s, component by component)

    Parameters
    ----------
    z_v : np.ndarray, shape (T,)
        Vocalic trajectory in the complex plane.
    z_c : np.ndarray, shape (T,)
        Consonantal trajectory in the complex plane.
    selector_v : list[str]
        Names of the parameters following the vocalic branch.
    selector_c : list[str]
        Names of the parameters following the consonantal branch.
    covtl_params : dict, optional
        COVTL coefficients. If None, uses the global CO_VTL.

    Returns
    -------
    dict[str, np.ndarray]
        Per-frame articulatory parameters, shape (T,).
    """
    if covtl_params is None:
        covtl_params = CO_VTL

    T = len(z_v)
    # z_c may be shorter (consonantal arc) → pad with the
    # last value if necessary
    if len(z_c) < T:
        z_c = np.concatenate([z_c, np.full(T - len(z_c), z_c[-1])])

    result = {}
    all_params = set(covtl_params.keys())

    for p in all_params:
        if p in AUTO_PARAMS:
            continue

        c1, c0, c2 = covtl_params[p]
        psi = c0 * np.exp(1j * c2)

        if p in selector_v:
            result[p] = c1 + np.real(psi * np.conj(z_v[:T]))
        elif p in selector_c:
            result[p] = c1 + np.real(psi * np.conj(z_c[:T]))
        else:
            result[p] = c1 + np.real(psi * np.conj(z_v[:T]))

    return result


# Backward-compatible alias
superimpose_covtl = superimpose


# ==========================================================================
# Consonant normalization — voiced/voiceless pairs
# ==========================================================================
# In SAMPA, voiced/voiceless pairs share the same place
# of articulation and therefore the same (rho, theta) target and the
# same COVTL selector. The voicing/voiceless distinction is handled
# by the glottal source (V(t), glottal preset), not by the tract.
#
# This mapping centralizes normalization: every voiceless consonant
# is first resolved to its voiced counterpart before lookup
# in CONSONANT_TARGETS. The g/k entries are a further special
# case because /g/ has no direct entry (only
# g_vel and g_pal, chosen dynamically by g_target()).
_VOICELESS_TO_VOICED: Dict[str, str] = {
    'p': 'b',   # bilabial
    't': 'd',   # alveolar
    'f': 'v',   # labiodental
    's': 'z',   # alveolar fricative
    'S': 'Z',   # post-alveolar
    'T': 'D',   # dental
    'tS': 'dZ', # post-alveolar affricate
    'k': 'g',   # velar/palatal (resolved dynamically)
}


def normalize_consonant_key(key: str) -> str:
    """Normalizes a consonant key to its canonical form.

    Voiceless consonants are resolved to their voiced
    counterpart (same place of articulation, same tract target).
    Already-voiced consonants or special entries (g_vel,
    g_pal, nasals, etc.) are returned unchanged.

    Parameters
    ----------
    key : str
        Consonant key (e.g. 'p', 'k', 'b', 'S', 'tS').

    Returns
    -------
    str
        Normalized key (e.g. 'b', 'g', 'b', 'Z', 'dZ').
    """
    return _VOICELESS_TO_VOICED.get(key, key)


# Backward-compatible alias
_normalize_consonant_key = normalize_consonant_key


# ==========================================================================
# Consonantal selectors — conversion to parameter lists
# ==========================================================================

def get_selector_list(
    consonant_key: str,
    theta_vowel: float = 0.0,
) -> Optional[List[str]]:
    """Returns the parameter list of the consonantal selector.

    Voiced/voiceless pairs share the same selector
    (normalized via normalize_consonant_key).
    For /g/ and /k/, the selector depends on the vocalic context:
      - front vowel → g_pal (selector without TCX)
      - otherwise → g_vel (selector with TCX)

    Parameters
    ----------
    consonant_key : str
        Consonant key (e.g. 'b', 's', 'tS', 'g', 'k').
    theta_vowel : float
        Polar angle of the contextual vowel (rad).
        Used to choose g_vel vs g_pal (theta > pi → palatal).
        Default 0 → g_vel.

    Returns
    -------
    list[str] or None
        List of selected COVTL parameters, or None if there is no
        selector (nasals, approximants).
    """
    key = normalize_consonant_key(consonant_key)
    _is_pal = theta_vowel > _IS_PALATAL_THRESHOLD

    # The g_vel/g_pal conditional entries contain the selector.
    # For g/k, choose the right suffix based on the vocalic context.
    for suffix in ('_vel', '_pal'):
        candidate = f'{key}{suffix}'
        if candidate not in CONSONANT_TARGETS:
            continue
        # If the candidate is g_vel or g_pal, check the context
        if suffix == '_vel' and _is_pal:
            continue  # skip g_vel, use g_pal
        if suffix == '_pal' and not _is_pal:
            continue  # skip g_pal, use g_vel
        return list(CONSONANT_TARGETS[candidate][2])

    # Simple entry
    entry = CONSONANT_TARGETS.get(key)
    if entry is not None:
        sel = list(entry[2])
        # Nasals have an empty selector []: no COVTL effect,
        # the processing is vocalic only (nasality handled by VO/VS).
        # Return None to trigger the vocalic-only fallback.
        return sel if sel else None

    return None


# Backward-compatible alias
_get_selector_list = get_selector_list


def get_consonant_target(
    consonant_key: str,
    theta_vowel: float,
) -> Optional[Tuple[float, float]]:
    """Returns (rho_c, theta_c) for a consonant.

    Voiced/voiceless pairs share the same target
    (normalized via normalize_consonant_key).
    For /g/ and /k/, the target depends on the vocalic context
    (palatal if the vowel is front, velar otherwise).

    Parameters
    ----------
    consonant_key : str
        Consonant key.
    theta_vowel : float
        Polar angle of the current vowel (rad).

    Returns
    -------
    tuple[float, float] or None
        (rho, theta) or None.
    """
    key = normalize_consonant_key(consonant_key)

    if key == 'g':
        # Conditional vel/pal target depending on the vocalic context
        _is_pal = theta_vowel > _IS_PALATAL_THRESHOLD
        suffix = 'pal' if _is_pal else 'vel'
        entry = CONSONANT_TARGETS.get(f'{key}_{suffix}')
        if entry is not None:
            return entry[0], entry[1]
        return None

    if key == 'z':
        # Conditional z/z_front target (2026-09-02, round 14): in front of a
        # high front vowel (θ<90° or θ>290° — /u/, /i/), the high tongue
        # tip of the context closes the alveolar groove at ρ1.00 → variant
        # z_front (ρ0.90). θ=0 (call without context) → production. The
        # window (0°,90°)∪(290°,360°) isolates exactly {u, i} in
        # VOWEL_TARGETS.
        th_deg = float(np.degrees(theta_vowel))
        if 0.0 < th_deg < 90.0 or th_deg > 290.0:
            entry = CONSONANT_TARGETS.get('z_front')
            if entry is not None:
                return entry[0], entry[1]

    entry = CONSONANT_TARGETS.get(key)
    if entry is not None:
        return entry[0], entry[1]
    return None


# Backward-compatible alias
_get_consonant_target = get_consonant_target


# ==========================================================================
# Public API
# ==========================================================================



def get_consonant_info(
    ipa: str,
) -> Optional[Tuple[float, float, List[str]]]:
    """Returns (rho, theta, selector) for an IPA consonant.

    Convention: voiced/voiceless pairs share the same target
    and the same COVTL selector (same place of articulation).
    Normalization is centralized in normalize_consonant_key:
      p→b, t→d, f→v, s→z, S→Z, T→D, tS→dZ, k→g
    For g/k, the target is resolved dynamically (vel/pal)
    based on the vocalic context.

    Parameters
    ----------
    ipa : str
        Consonant key.

    Returns
    -------
    tuple[float, float, list[str]] or None
    """
    key = normalize_consonant_key(ipa)

    # Conditional entries
    for suffix in ('_vel', '_pal'):
        entry = CONSONANT_TARGETS.get(f'{key}{suffix}')
        if entry is not None:
            return (entry[0], entry[1], list(entry[2]))

    # Simple entry
    entry = CONSONANT_TARGETS.get(key)
    if entry is not None:
        return (entry[0], entry[1], list(entry[2]))
    return None


def g_target(theta_vowel: float, ipa: str = 'g') -> Tuple[float, float]:
    """Conditional target for /g/ and /k/.

    The locus of /g,k/ depends on the contextual vowel:
      - Front vowel → palatal target (g_pal)
      - Otherwise → velar target (g_vel)

    Parameters
    ----------
    theta_vowel : float
        Polar angle of the current vowel (rad).
    ipa : str
        Phoneme ('g' or 'k').

    Returns
    -------
    tuple[float, float]
        (rho_c, theta_c).
    """
    key = normalize_consonant_key(ipa)
    _is_pal = theta_vowel > _IS_PALATAL_THRESHOLD
    suffix = 'pal' if _is_pal else 'vel'
    entry = CONSONANT_TARGETS.get(f'{key}_{suffix}')
    if entry is None:
        raise KeyError(
            f"Conditional target '{key}_{suffix}' not found "
            f"in CONSONANT_TARGETS for ipa='{ipa}'"
        )
    return entry[0], entry[1]


def project_vtl_frame(
    rho_v: float,
    theta_v: float,
    active_segment: Optional[object] = None,
) -> Dict[str, float]:
    """Projects a full VTL frame (tract) from (rho, theta).

    **DEPRECATED** (RISK-002, 2026-09-04): STATIC projection path
    (consonantal selector as override, no trajectory, no
    superposition) — no live callers outside the re-export in
    ``pipeline.__init__``. The active path is projection by polar
    arcs (polar.arc_B via syltraj/trajectory). Kept only
    for API compatibility; do not use in new code.

    Parameters
    ----------
    rho_v : float
        Polar radius of the current vowel.
    theta_v : float
        Polar angle of the current vowel (rad).
    active_segment : object, optional
        Segment object with key, kind attributes.

    Returns
    -------
    dict[str, float]
        COVTL tract parameter values.
    """
    z = rho_v * np.exp(1j * theta_v)
    out = project_covtl(z)

    # If a consonantal segment is active, apply the selector
    # as a static override (backward compatibility).
    # NOTE: this is NOT superposition.
    # Superposition is in compute_tract_trajectory().
    if active_segment is not None and getattr(active_segment, 'kind', None) == 'C':
        key = active_segment.key
        info = get_consonant_info(key)
        if info is not None:
            if key in ('g', 'k'):
                rho_c, theta_c = g_target(theta_v, ipa=key)
                sel = info[2]
            else:
                rho_c, theta_c, sel = info
            z_c = rho_c * np.exp(1j * theta_c)
            for p in sel:
                if p in CO_VTL:
                    c1, c0, c2 = CO_VTL[p]
                    out[p] = c1 + c0 * np.real(
                        np.exp(1j * c2) * np.conj(z_c)
                    )

    # Remove AUTO_PARAMS
    for p in AUTO_PARAMS:
        out.pop(p, None)

    return out


# Backward-compatible aliases
_project_covtl_scalar = project_covtl_polar


# ==========================================================================
# Level 2b — arc_B and compute_P (build_global_pval architecture)
# ==========================================================================
# These functions are used by trajectory.build_global_pval() to
# build trajectories in the COVTL parameter space.
#
# arc_B: generates an arc between two (rho, theta) points for the
#          specified parameters, using the Berthommier formula.
# compute_P: generates a stationary point (all COVTL params).
#
# Unlike the z_v/z_c + superimpose() approach, these functions
# work directly in parameter space, which
# guarantees frame-by-frame synchronization (no padding).
# =============================================================================

from vtl_synth.core.constants import COVTL_PARAMS, N_VTL_PARAMS


# Mapping name → index in the COVTL vector (fixed order)
_COVTL_NAME_TO_IDX: Dict[str, int] = {
    name: idx for idx, name in enumerate(COVTL_PARAMS)
}
