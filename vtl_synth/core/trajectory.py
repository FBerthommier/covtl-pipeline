# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
trajectory.py -- Polar trajectory computation for the COVTL model.

Builds the global continuous polar trajectory (Pval) from gesture nodes
and anchors.  This is Step 3 of the synthesis pipeline.

All internal structures use the ``GestureNode``, ``GestureAnchor``,
and ``BlockInfo`` dataclasses from ``types.py`` rather than anonymous
dicts, ensuring type safety and explicit field documentation.

The original ``build_global_pval`` (>200 lines) has been split into
focused sub-functions handling each anchor-pair transition type.

Strict alignment with the COVTL reference.
"""

from __future__ import annotations

import numpy as np

from .constants import (
    N_VTL_PARAMS,
    COVTL_PARAMS,
)
from .phonology import (
    IPA_TO_SYNTSYL,
    _CC_ALIAS,
    _TABCONS_IDX,
    cluster_art_params,
    is_synthsyl_consonant,
    phoneme_base_token,
)
from .polar import arc_B, compute_P, build_background, inject_active_parameters
from .types import BlockInfo, GestureAnchor, GestureNode, PolarTarget


# =============================================================================
# Reco 1 -- Safe point extraction
# =============================================================================

def _safe_pt(anchor: GestureAnchor) -> list[float]:
    """Extract the polar point from *anchor*, defaulting to [0.0, 0.0].

    Every occurrence of ``X.pt if X.pt is not None else [0.0, 0.0]``
    in the module delegates to this helper.
    """
    pt = anchor.pt
    return pt if pt is not None else [0.0, 0.0]


# =============================================================================
# Reco 2 -- Plateau factory
# =============================================================================

def _append_plateau(blocks: list[np.ndarray], pt: list[float],
                     D: int) -> None:
    """Append a plateau block: ``compute_P(*pt)`` tiled for *D* steps."""
    P = compute_P(*pt)
    blocks.append(np.tile(P, (D, 1)))


# =============================================================================
# Reco 3 -- Full-parameter arc helper
# =============================================================================

def _append_arc(blocks: list[np.ndarray],
                pt_dep: list[float], pt_arr: list[float],
                D: int, nu: int, K: int, Pexp: int) -> None:
    """Append a full-N_VTL_PARAMS arc trajectory with default bounds.

    Centralises the common pattern ``arc_B(..., list(range(N_VTL_PARAMS)), D,
    [-np.pi, 0], 0, nu, K, Pexp)`` used by pause arcs and the
    initial-terminal handler.
    """
    blocks.append(arc_B(pt_dep, pt_arr, list(range(N_VTL_PARAMS)), D,
                        [-np.pi, 0], 0, nu, K, Pexp))


# =============================================================================
# Reco 4 -- Amplitude helpers
# =============================================================================

def _pre_amp_backward_scan(anchors: list[GestureAnchor], idx: int) -> float:
    """Compute pre_amp by scanning backward from *idx* for a non-vowel-onset V.

    Used in ``_handle_term_term`` and ``_handle_a_terminal`` where the
    pre-signal amplitude is determined by the nearest preceding vowel
    anchor, skipping pause/synth terminals.
    """
    _pre_a = 0.0
    for _look in range(idx - 1, -1, -1):
        _la = anchors[_look]
        if _la.kind in ("pause", "synth"):
            continue
        if _la.kind == "V" and not _la.is_vowel_onset:
            _pre_a = 1.0
        break
    return _pre_a


def _pre_amp_from_penultimate(anchors: list[GestureAnchor]) -> float:
    """Compute pre_amp from the penultimate anchor (flush section).

    Unlike :func:`_pre_amp_backward_scan`, this checks the second-to-last
    anchor directly and also excludes ``is_word_end`` anchors, matching
    the original flush logic.
    """
    if len(anchors) < 2:
        return 0.0
    a = anchors[-2]
    if (a.kind == "V"
            and not a.is_vowel_onset
            and not a.is_word_end):
        return 1.0
    return 0.0


def _amp(condition: bool) -> float:
    """Convert a boolean *condition* to a float amplitude (1.0 or 0.0)."""
    return 1.0 if condition else 0.0


# =============================================================================
# Reco 5 -- Composite helpers for repeated handler sequences
# =============================================================================

def _append_decay_block(blocks: list[np.ndarray],
                         block_info: list[BlockInfo],
                         pt: list[float], D: int,
                         pre_amp: float) -> None:
    """Append a decay plateau + block_info if *pre_amp* is significant."""
    if D > 0 and pre_amp > 0.01:
        _append_plateau(blocks, pt, D)
        block_info.append(BlockInfo(n_steps=D, kind="decay", pre_amp=pre_amp))


def _append_attack_block(blocks: list[np.ndarray],
                          block_info: list[BlockInfo],
                          pt: list[float], D: int,
                          post_amp: float) -> None:
    """Append an attack plateau + block_info if *post_amp* is significant."""
    if D > 0 and post_amp > 0.01:
        _append_plateau(blocks, pt, D)
        block_info.append(BlockInfo(n_steps=D, kind="attack", post_amp=post_amp))


# =============================================================================
# Cluster trajectory
# =============================================================================

def build_cluster_pval(anchor_dep: list[float], anchor_arr: list[float],
                        consonants: list[GestureNode], T: int,
                        nu: int, K: int, Kvoy: int,
                        Pexp: int) -> np.ndarray:
    """Build the Pval trajectory for a consonant cluster.

    Parameters
    ----------
    anchor_dep : [rho, theta] of the departure anchor
    anchor_arr : [rho, theta] of the arrival anchor
    consonants : list of GestureNode consonants
    T          : time steps per consonant segment
    nu, K, Kvoy, Pexp : coarticulation and arc parameters
    """
    m = len(consonants)
    Dtot = (m + 1) * T
    Pval = np.zeros((Dtot, N_VTL_PARAMS))
    Pval[:, :] = build_background(anchor_dep, anchor_arr, Dtot, nu, Kvoy, Pexp)

    use_art1 = False
    art1_params: list[int] | None = None
    if 2 <= m <= 3:
        keys = [c.seg_key for c in consonants]
        resolved_keys = [_CC_ALIAS.get(k, k) for k in keys]
        synt_keys = [IPA_TO_SYNTSYL.get(k, "") for k in resolved_keys]
        if all(is_synthsyl_consonant(k) for k in synt_keys):
            use_art1 = True
            art1_params = cluster_art_params(keys)

    if not use_art1 and m > 1:
        uniform_params = sorted(set().union(*(c.params for c in consonants)))
    else:
        uniform_params = None

    for k in range(m + 1):
        if k == 0:
            pt_d = [consonants[0].rho, consonants[0].theta]
            pt_a = anchor_dep
            tb, oi = [0, np.pi], 0
            act = art1_params if use_art1 else (uniform_params if uniform_params is not None else consonants[0].params)
        elif k < m:
            pt_d = [consonants[k - 1].rho, consonants[k - 1].theta]
            pt_a = [consonants[k].rho, consonants[k].theta]
            tb, oi = [-np.pi, 0], 0
            act = art1_params if use_art1 else (uniform_params if uniform_params is not None else sorted(set(consonants[k - 1].params) | set(consonants[k].params)))
        else:
            pt_d = [consonants[-1].rho, consonants[-1].theta]
            pt_a = anchor_arr
            tb, oi = [-np.pi, 0], 0
            act = art1_params if use_art1 else (uniform_params if uniform_params is not None else consonants[-1].params)

        inject_active_parameters(Pval, slice(k * T, (k + 1) * T),
                                 pt_d, pt_a, act, T, nu, K, Pexp, tb, oi)

    return Pval


# =============================================================================
# Helper: collect consonants between two anchors
# =============================================================================

def _collect_consonants(nodes: list[GestureNode], search_start: int,
                        search_end: int) -> list[GestureNode]:
    """Collect consonant nodes between two anchor indices."""
    consonants: list[GestureNode] = []
    n = len(nodes)
    for k in range(search_start, search_end):
        if 0 <= k < n and nodes[k].kind == "C":
            consonants.append(nodes[k])
    return consonants


# =============================================================================
# Helper: build cluster block_info
# =============================================================================

def _cluster_block_info(consonants: list[GestureNode], T_cons: int,
                         pre_token: str, post_token: str,
                         has_following_plateau: bool) -> BlockInfo:
    """Build a BlockInfo for a cluster block."""
    _ct = [phoneme_base_token(c.seg_key,
                               PolarTarget(rho=c.rho, theta=c.theta, is_vowel=False))
           for c in consonants]
    return BlockInfo(
        n_steps=(len(consonants) + 1) * T_cons,
        kind="cluster",
        n_cons=len(consonants),
        cons_tokens=_ct,
        pre_token=pre_token,
        post_token=post_token,
        has_following_plateau=has_following_plateau,
    )


def _has_following_plateau(anchors: list[GestureAnchor], idx: int) -> bool:
    """Check if there's a plateau (held V) after the current anchor pair."""
    for _fwd in range(idx + 1, len(anchors) - 1):
        _fA = anchors[_fwd]
        if (_fA.hold and _fA.kind == "V"
                and not _fA.is_vowel_onset
                and not _fA.is_word_end):
            return True
        elif _fA.kind in ("pause", "synth"):
            break
    return False


# =============================================================================
# Step 3: Global continuous polar trajectory
# =============================================================================

def build_global_pval(
    nodes: list[GestureNode],
    anchors: list[GestureAnchor],
    T_cons: int,
    T_voy: int,
    T_pause_short: int,
    T_pause_long: int,
    nu: int,
    K: int,
    Kvoy: int,
    Pexp: int,
    use_sigmoid_pause: bool = False,
    sigmoid_steepness: float = 4.0,
) -> tuple[np.ndarray, list[float], list[BlockInfo]]:
    """Build the global continuous polar trajectory (Pval).

    Returns
    -------
    Pval : np.ndarray
        Maeda parameter trajectory (n_steps x N_VTL_PARAMS).
    last_pt : list[float]
        [rho, theta] of the last anchor.
    block_info : list[BlockInfo]
        Per-block information for envelope construction.
    """
    blocks: list[np.ndarray] = []
    block_info: list[BlockInfo] = []
    n = len(nodes)

    pending_pause_pt: list[float] | None = None
    pending_pause_long: bool = False

    for idx in range(len(anchors) - 1):
        A, B = anchors[idx], anchors[idx + 1]

        a_is_term = A.kind in ("pause", "synth")
        b_is_term = B.kind in ("pause", "synth")
        a_is_vowel_onset = A.is_vowel_onset
        b_is_vowel_onset = B.is_vowel_onset
        a_is_V = A.kind == "V" and not a_is_vowel_onset
        b_is_V = B.kind == "V" and not b_is_vowel_onset

        b_long = B.long

        # -- Hold plateau --
        if A.hold and a_is_V:
            _append_plateau(blocks, _safe_pt(A), T_voy)
            block_info.append(BlockInfo(n_steps=T_voy, kind="plateau"))

        # Collect consonants between A and B
        search_start = A.i if a_is_vowel_onset else A.i + 1
        search_end = B.i
        consonants = _collect_consonants(nodes, search_start, search_end)
        m = len(consonants)

        # -- Case: both terminals --
        if a_is_term and b_is_term:
            blocks, block_info, pending_pause_pt, pending_pause_long = _handle_term_term(
                idx, anchors, A, B, nodes, blocks, block_info,
                pending_pause_pt, pending_pause_long, nu, K, Pexp,
                T_pause_long, T_pause_short)
            continue

        # -- Case: A is terminal --
        if a_is_term:
            blocks, block_info, pending_pause_pt, pending_pause_long = _handle_a_terminal(
                idx, anchors, A, B, nodes, consonants, m, blocks, block_info,
                pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                T_cons, T_voy, T_pause_short, T_pause_long,
                a_is_vowel_onset, b_is_V, b_is_vowel_onset)
            continue

        # -- Case: B is terminal --
        if b_is_term:
            blocks, block_info, pending_pause_pt, pending_pause_long = _handle_b_terminal(
                idx, anchors, A, B, nodes, consonants, m, blocks, block_info,
                pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                T_cons, T_voy, T_pause_short, T_pause_long,
                a_is_V, a_is_vowel_onset, b_is_term, b_long)
            continue

        # -- Case: pending pause --
        if pending_pause_pt is not None:
            blocks, block_info, pending_pause_pt, pending_pause_long = _handle_pending_pause(
                A, B, nodes, consonants, m, blocks, block_info,
                pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                T_cons, T_voy, T_pause_short, T_pause_long,
                a_is_V, b_is_V, a_is_vowel_onset, b_is_vowel_onset)

        # -- Case: V->V or V->C (no consonants) --
        if m == 0:
            # V_onset → nucleus V or V → V transition: continuous background arc.
            # The V_onset conditional jump was removed because it created
            # a discontinuity (V_onset rho ≠ nucleus V rho).
            # The background arc guarantees continuity between anchors.
            blocks.append(build_background(_safe_pt(A), _safe_pt(B), 2 * T_voy, nu, Kvoy, Pexp))
            block_info.append(BlockInfo(n_steps=2 * T_voy, kind="background"))
        else:
            # -- Cluster between two vowels --
            blocks.append(build_cluster_pval(_safe_pt(A), _safe_pt(B), consonants,
                                             T_cons, nu, K, Kvoy, Pexp))
            _pre = "V" if a_is_V else ("y" if A.is_syl_vowel_onset else ("O" if a_is_vowel_onset else "O"))
            _post = "V" if b_is_V else ("y" if B.is_syl_vowel_onset else ("O" if b_is_vowel_onset else "O"))
            _has_plat = _has_following_plateau(anchors, idx)
            block_info.append(_cluster_block_info(consonants, T_cons, _pre, _post, _has_plat))

    # -- Last anchor hold --
    if anchors:
        Blast = anchors[-1]
        if Blast.hold and Blast.kind == "V":
            _append_plateau(blocks, _safe_pt(Blast), T_voy)
            block_info.append(BlockInfo(n_steps=T_voy, kind="plateau"))

    # -- Flush remaining pending pause --
    if pending_pause_pt is not None and anchors:
        Blast = anchors[-1]
        pt_arr = _safe_pt(Blast)
        T_use = T_pause_long if pending_pause_long else T_pause_short
        _append_arc(blocks, pending_pause_pt, pt_arr, T_use, nu, K, Pexp)
        _pre_a = _pre_amp_from_penultimate(anchors)
        block_info.append(BlockInfo(n_steps=T_use, kind="terminal", pre_amp=_pre_a))
        pending_pause_pt = None

    Pval = np.vstack(blocks) if blocks else np.zeros((T_cons, N_VTL_PARAMS))
    last_pt = _safe_pt(anchors[-1]) if anchors else [0.0, 0.0]
    return Pval, last_pt, block_info


# =============================================================================
# Sub-handlers for build_global_pval
# =============================================================================

def _handle_term_term(idx, anchors, A, B, nodes, blocks, block_info,
                       pending_pause_pt, pending_pause_long, nu, K, Pexp,
                       T_pause_long, T_pause_short):
    """Handle the case where both A and B are terminals."""
    if pending_pause_pt is not None and B.kind == "synth":
        pt_arr = _safe_pt(B)
        T_use = T_pause_long if pending_pause_long else T_pause_short
        _append_arc(blocks, pending_pause_pt, pt_arr, T_use, nu, K, Pexp)
        _pre_a = _pre_amp_backward_scan(anchors, idx)
        block_info.append(BlockInfo(n_steps=T_use, kind="terminal", pre_amp=_pre_a))
        pending_pause_pt = None
        pending_pause_long = False
    elif B.kind == "pause":
        pending_pause_pt = _safe_pt(A)
        pending_pause_long = B.long
    else:
        pending_pause_pt = None
        pending_pause_long = False
    return blocks, block_info, pending_pause_pt, pending_pause_long


def _handle_a_terminal(idx, anchors, A, B, nodes, consonants, m,
                        blocks, block_info,
                        pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                        T_cons, T_voy, T_pause_short, T_pause_long,
                        a_is_vowel_onset, b_is_V, b_is_vowel_onset):
    """Handle the case where A is a terminal."""
    _was_pending = pending_pause_pt is not None
    if pending_pause_pt is not None:
        pt_A = pending_pause_pt
        T_use = T_pause_long if pending_pause_long else T_pause_short
        is_long = pending_pause_long
        pending_pause_pt = None
        pending_pause_long = False
    else:
        pt_A = _safe_pt(A)
        # Priming from neutral: use T_pause_long for the
        # phrase-start transition (synth_start → first phoneme).
        if A.kind == "synth":
            T_use = T_pause_long
            is_long = True
        else:
            T_use = T_pause_short
            is_long = False
    pt_B = _safe_pt(B)

    if m == 0:
        _append_arc(blocks, pt_A, pt_B, T_use, nu, K, Pexp)
        _post_amp = _amp(B.kind == "V")
        _pre_amp = _pre_amp_backward_scan(anchors, idx) if _was_pending else 0.0
        block_info.append(BlockInfo(
            n_steps=T_use, kind="initial" if not is_long else "pause",
            long=is_long, pre_amp=_pre_amp, post_amp=_post_amp))
        _b_is_vowel_onset = B.is_vowel_onset
        if _post_amp > 0.01 and T_use > 0 and not _b_is_vowel_onset:
            _append_attack_block(blocks, block_info, pt_B, T_cons, _post_amp)
    else:
        blocks.append(build_cluster_pval(pt_A, pt_B, consonants,
                                         T_cons, nu, K, Kvoy, Pexp))
        _pre = "O"
        _post = "y" if B.is_syl_vowel_onset else ("V" if B.kind == "V" else "O")
        _has_plat = _has_following_plateau(anchors, idx)
        block_info.append(_cluster_block_info(consonants, T_cons, _pre, _post, _has_plat))

    return blocks, block_info, pending_pause_pt, pending_pause_long


def _handle_b_terminal(idx, anchors, A, B, nodes, consonants, m,
                        blocks, block_info,
                        pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                        T_cons, T_voy, T_pause_short, T_pause_long,
                        a_is_V, a_is_vowel_onset, b_is_term, b_long):
    """Handle the case where B is a terminal."""
    if m > 0:
        pt_A = _safe_pt(A)
        pt_B = _safe_pt(B)
        blocks.append(build_cluster_pval(pt_A, pt_B, consonants,
                                         T_cons, nu, K, Kvoy, Pexp))
        _pre = "y" if A.is_syl_vowel_onset else ("O" if a_is_vowel_onset else ("V" if a_is_V else "O"))
        _post = "F" if B.kind == "synth" else "O"
        block_info.append(_cluster_block_info(consonants, T_cons, _pre, _post, False))
    elif A.kind == "V":
        if B.kind == "pause":
            pt_A = _safe_pt(A)
            _append_decay_block(blocks, block_info, pt_A, T_cons, pre_amp=1.0)
        elif B.kind == "synth":
            # Decay toward neutral: phrase-end arc
            # from the last vowel to the synth_end anchor (neutral).
            pt_A = _safe_pt(A)
            pt_B = _safe_pt(B)
            _append_arc(blocks, pt_A, pt_B, T_pause_long, nu, K, Pexp)
            block_info.append(BlockInfo(
                n_steps=T_pause_long, kind="terminal",
                long=True, pre_amp=1.0))

    if B.kind == "pause":
        pending_pause_pt = _safe_pt(A)
        pending_pause_long = b_long

    return blocks, block_info, pending_pause_pt, pending_pause_long


def _handle_pending_pause(A, B, nodes, consonants, m,
                           blocks, block_info,
                           pending_pause_pt, pending_pause_long, nu, K, Kvoy, Pexp,
                           T_cons, T_voy, T_pause_short, T_pause_long,
                           a_is_V, b_is_V, a_is_vowel_onset, b_is_vowel_onset):
    """Handle a pending pause before the current anchor pair."""
    pt_B_arr = _safe_pt(B)
    T_use = T_pause_long if pending_pause_long else T_pause_short
    _append_arc(blocks, pending_pause_pt, pt_B_arr, T_use, nu, K, Pexp)
    _pre_a = _amp(a_is_V)
    _post_a = _amp(b_is_V)
    block_info.append(BlockInfo(n_steps=T_use, kind="pause",
                                       long=pending_pause_long,
                                       pre_amp=_pre_a, post_amp=_post_a))
    _append_decay_block(blocks, block_info, _safe_pt(A), T_cons, pre_amp=_pre_a)
    _append_attack_block(blocks, block_info, _safe_pt(B), T_cons, post_amp=_post_a)
    pending_pause_pt = None
    pending_pause_long = False
    return blocks, block_info, pending_pause_pt, pending_pause_long
