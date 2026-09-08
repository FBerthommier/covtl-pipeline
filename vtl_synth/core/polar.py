# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
polar.py -- Polar coordinate projection primitives.

Contains the Maeda model projection functions (compute_P, arc_B,
sigmoid_transition) and the background trajectory builder.

Strict alignment with the COVTL reference.
All equations and numerical values identical to v15g.

Key fix vs. old projection.py arc_B:
  - np.unwrap on arrival theta to handle angular wrapping (pi -> -pi)
  - Per-parameter direct formula (not complex-z interpolation)
  - Correct opint=-1 handling (skip first point, not negate)
  - Correct nu/K sign convention (minus in cosine)
"""

from __future__ import annotations

import numpy as np
from typing import List, Optional, Tuple

from .constants import CO, N_VTL_PARAMS


def compute_P(rho: float, theta: float) -> np.ndarray:
    """Project polar target (rho, theta) into Maeda parameter space.

    P(p) = CO[p, 1] + rho * CO[p, 0] * cos(CO[p, 2] - theta)
    Applied to all N_VTL_PARAMS parameters.

    Parameters
    ----------
    rho : float
        Polar radius.
    theta : float
        Polar angle (rad).

    Returns
    -------
    np.ndarray, shape (N_VTL_PARAMS,)
    """
    return CO[:, 1] + rho * CO[:, 0] * np.cos(CO[:, 2] - theta)


def arc_B(pt_dep: List[float], pt_arr: List[float],
          params: List[int], D: int,
          thetabounds: List[float], opint: int,
          nu: int, K: int, Pexp: int = 2) -> np.ndarray:
    """Compute an arc trajectory in Maeda parameter space.

    v14: returns (D, len(params)) like v11, unwrap restored (FIX-7).

    Parameters:
        pt_dep: [rho, theta] departure polar point
        pt_arr: [rho, theta] arrival polar point
        params: list of active Maeda parameter indices
        D: number of trajectory steps
        thetabounds: [theta_start, theta_end] for the interpolation
        opint: interpolation mode (0=linspace, -1=skip first, else=linspace)
        nu, K, Pexp: arc model parameters

    Returns:
        array (D, len(params)) of Maeda parameter values
    """
    if D <= 0:
        return np.zeros((0, len(params)))

    if opint == 0:
        th = np.linspace(thetabounds[0], thetabounds[1], D)
    elif opint == -1:
        th1 = np.linspace(thetabounds[0], thetabounds[1], D + 1)
        th = th1[1:D + 1]
    else:
        th = np.linspace(thetabounds[0], thetabounds[1], D)

    # FIX-7: unwrap arrival theta to avoid angular wrapping jumps
    # (e.g. pi -> -pi causing ~6 rad discontinuity)
    pa_theta_uw = np.unwrap([pt_dep[1], pt_arr[1]])[1]
    if abs(pa_theta_uw - pt_dep[1]) < abs(pt_arr[1] - pt_dep[1]):
        pa_theta = pa_theta_uw
    else:
        pa_theta = pt_arr[1]

    pd = np.array(pt_dep, dtype=float)
    pa = np.array([pt_arr[0], pa_theta], dtype=float)
    params_list = list(params)
    Pt = np.zeros((D, len(params_list)))
    for k in range(D):
        rk = np.cos(th[k] / 2) ** Pexp
        for j, p in enumerate(params_list):
            Pt[k, j] = (CO[p, 1]
                        + rk * pa[0] * CO[p, 0] * np.cos(CO[p, 2] - pa[1] - (nu / K) * th[k])
                        + (1 - rk) * pd[0] * CO[p, 0] * np.cos(CO[p, 2] - pd[1]))
    return Pt


def build_background(pt_dep: List[float], pt_arr: List[float],
                     D: int, nu: int, Kvoy: int, Pexp: int) -> np.ndarray:
    """Build background trajectory (all N_VTL_PARAMS, full arc)."""
    return arc_B(pt_dep, pt_arr, list(range(N_VTL_PARAMS)), D,
                 [-np.pi, 0], 0, nu, Kvoy, Pexp)


def inject_active_parameters(Pval: np.ndarray, block_slice: slice,
                             pt_dep: List[float], pt_arr: List[float],
                             active_params: List[int], T: int,
                             nu: int, K: int, Pexp: int,
                             thetabounds: List[float], opint: int) -> None:
    """Inject active parameter trajectory into a Pval block.

    Modifies Pval in-place.
    """
    if not active_params:
        return
    seg = arc_B(pt_dep, pt_arr, active_params, T,
                thetabounds, opint, nu, K, Pexp)
    Pval[block_slice, active_params] = seg


# =============================================================================
# Legacy compatibility — symbols used by trajectory_legacy and parsing
# =============================================================================
from dataclasses import dataclass, field
from typing import List, Optional, Tuple as _Tuple, Dict


@dataclass
class ArcSpec:
    """Specification of a polar arc segment."""
    rho1: float
    theta1: float
    rho2: float
    theta2: float
    duration_ms: float
    K: float = 30.0
    nu: int = 1
    orientation: str = 'direct'
    selector: str = 'vocalic'
    consonant_key: Optional[str] = None


@dataclass
class SuperpositionSegment:
    """A pair of vocalic + consonantal arc lists for superposition."""
    consonant_arcs: List[ArcSpec] = field(default_factory=list)
    vocalic_arcs: List[ArcSpec] = field(default_factory=list)
    selector_v: List[str] = field(default_factory=list)
    selector_c: List[str] = field(default_factory=list)
    consonant_keys: List[str] = field(default_factory=list)
    vowel_key: str = ''
    _n_c_arcs_nominal: int = 1


# Legacy timing/model defaults
K_VOWEL_DEFAULT: float = 30.0
K_CONSONANT_DEFAULT: float = 10.0
NU_DIRECT: int = 1
DELTA_O_DEFAULT: float = 0.70
DELTA_E_DEFAULT: float = 0.70
T_BASE_DEFAULT: float = 80.0  # ms


def polar_arc(
    rho1: float, theta1: float,
    rho2: float, theta2: float,
    duration_ms: float, sr: float = 100.0,
    K: float = K_VOWEL_DEFAULT, nu: int = 1,
    orientation: str = 'direct',
) -> _Tuple[np.ndarray, np.ndarray]:
    """Generate a polar arc trajectory in the complex plane.

    Interpolates from the polar target (rho1, theta1) to (rho2, theta2)
    along a curved path in the z-plane: the blend factor follows
    cos²(th/2) over a half-turn sweep, and the end point carries an
    extra phase nu/K (COVTL reference model). Used by
    trajectory_legacy.py and parsing.py.

    Parameters
    ----------
    rho1, theta1 : float
        Polar coordinates of the arc start point (cm, rad).
    rho2, theta2 : float
        Polar coordinates of the arc end point (cm, rad); theta2 is
        unwrapped so that the arc takes the shortest angular path.
    duration_ms : float
        Total duration of the arc (ms).
    sr : float, optional
        Sampling rate of the output trajectory (Hz). Default: 100.
    K : float, optional
        Curvature constant (rad): the end-point phase offset is nu/K.
        Larger K = straighter path. Default: K_VOWEL_DEFAULT (30).
    nu : int, optional
        Number of turns of the end-point phase offset (offset = nu/K).
        Default: 1.
    orientation : str, optional
        Sweep direction of the half-turn parameter: 'direct' (0→pi)
        or 'inverse' (pi→0). Default: 'direct'.

    Returns
    -------
    z : np.ndarray of complex
        Complex trajectory z(t) = rho(t)·exp(i·theta(t)), of length
        round(duration_ms·sr/1000).
    rho_theta : np.ndarray (n, 2)
        The same trajectory as (rho, theta) columns.
    """
    n_samples = max(1, int(round(duration_ms * sr / 1000.0)))
    t = np.linspace(0, 1, n_samples, endpoint=True)

    # Angular sweep
    if orientation == 'inverse':
        th = np.linspace(np.pi, 0, n_samples, endpoint=True)
    else:
        th = np.linspace(0, np.pi, n_samples, endpoint=True)

    # Unwrap theta to handle wrapping
    th_uw = np.unwrap([theta1, theta2])
    theta2_uw = th_uw[1]
    if abs(theta2_uw - theta1) < abs(theta2 - theta1):
        theta2_eff = theta2_uw
    else:
        theta2_eff = theta2

    # Blend in complex plane
    rk = np.cos(th / 2) ** 2
    phase2 = theta2_eff + (nu / K) * th
    z1 = rho1 * np.exp(1j * theta1)
    z2 = rho2 * np.exp(1j * phase2)
    z = (1 - rk) * z1 + rk * z2

    rho_theta = np.column_stack([np.abs(z), np.angle(z)])
    return z, rho_theta


def stationary_point(
    rho: float, theta: float,
    duration_ms: float, sr: float = 100.0,
) -> _Tuple[np.ndarray, np.ndarray]:
    """Generate a stationary point trajectory (constant rho, theta)."""
    n_samples = max(1, int(round(duration_ms * sr / 1000.0)))
    z = np.full(n_samples, rho * np.exp(1j * theta), dtype=complex)
    rho_theta = np.tile([rho, theta], (n_samples, 1))
    return z, rho_theta
