# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
gesture.py — Gestural graph construction for the COVTL model.

Builds gesture nodes and gesture anchors from the flat segment list
and polar targets.  This is Step 2 of the synthesis pipeline.

All internal structures use the ``GestureNode`` and ``GestureAnchor``
dataclasses from ``types.py`` rather than anonymous dicts, ensuring
type safety and explicit field documentation.

Pipeline for build_gesture_nodes:
    parse_polar_targets → build_initial_nodes → detect_clusters → adjust_consonants

Pipeline for build_gesture_anchors:
    create_base_anchors → insert_word_end_anchors → insert_vowel_onset_anchors
    → insert_syllable_onset_anchors → ensure_terminal_anchors

Strict alignment with the COVTL reference.
"""

from __future__ import annotations

import numpy as np

from .constants import DELTA_E, NEUTRAL_RHO, NEUTRAL_THETA
from .phonology import (
    IPA_TO_SYNTSYL,
    _CC_ALIAS,
    _TABCONS_IDX,
    adjust_consonant_theta,
    is_vowel as is_vowel_seg,
    VOWELS_SYNTSYL,
    cluster_art_params,
)
from .types import GestureAnchor, GestureNode, PolarTarget, SyllableBoundary
from .timers import (
    LATERAL_KEYS,
    PLOSIVE_KEYS,
    get_lateral_virtual_target,
    get_plosive_virtual_target,
)


# ═══════════════════════════════════════════════════════════════════════════
# Pre-computed vowel lookup (O(1) instead of O(n) linear scan)
# ═══════════════════════════════════════════════════════════════════════════

def _precompute_vowel_indices(nodes: list[GestureNode]) -> tuple[list[int], list[int]]:
    """For each node, compute the index of the nearest vowel.

    Returns
    -------
    next_vowel : list[int]
        next_vowel[i] = index of the next vowel after node i,
        or -1 if none.
    prev_vowel : list[int]
        prev_vowel[i] = index of the previous vowel before node i,
        or -1 if none.
    """
    n = len(nodes)
    next_vowel = [-1] * n
    prev_vowel = [-1] * n

    # Forward pass
    last_v = -1
    for i in range(n):
        if nodes[i].kind == "V":
            last_v = i
        prev_vowel[i] = last_v

    # Backward pass
    last_v = -1
    for i in range(n - 1, -1, -1):
        if nodes[i].kind == "V":
            last_v = i
        next_vowel[i] = last_v

    return next_vowel, prev_vowel


def _nearest_vowel_theta(nodes: list[GestureNode], i: int,
                         next_vowel: list[int],
                         prev_vowel: list[int]) -> float:
    """Return the theta of the nearest vowel to node *i*.

    Uses pre-computed indices for O(1) lookup instead of O(n) scan.
    Falls back to π if no vowel is found.
    """
    # Search forward (skipping pauses)
    nv = next_vowel[i]
    if nv != -1:
        blocked = False
        for j in range(i + 1, nv):
            if nodes[j].kind == "pause":
                blocked = True
                break
        if not blocked:
            return nodes[nv].theta

    # Search backward (skipping pauses)
    pv = prev_vowel[i]
    if pv != -1:
        blocked = False
        for j in range(pv + 1, i):
            if nodes[j].kind == "pause":
                blocked = True
                break
        if not blocked:
            return nodes[pv].theta

    return np.pi


# ═══════════════════════════════════════════════════════════════════════════
# Node construction helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_vowel_node(rho: float, theta: float, seg_key: str,
                       i: int = 0) -> GestureNode:
    """Create a vowel gesture node."""
    return GestureNode(kind="V", rho=rho, theta=theta, seg_key=seg_key, i=i)


def _make_consonant_node(rho: float, theta: float, seg_key: str,
                           params: list[int] | None = None,
                           in_cluster: bool = False,
                           i: int = 0,
                           virtual_target: dict | None = None) -> GestureNode:
    """Create a consonant gesture node with selector params.

    If *params* is None, params are computed from seg_key via
    cluster_art_params (for ART1 single-selector model).

    For lateral consonants (/l/, /L/), a *virtual_target* dict
    from the Berthommier model can be provided. This ensures that
    the central occlusion contact/release occurs at high speed
    mid-transition, providing enhanced acoustic sharpness.

    The virtual target modifies rho slightly upward and applies
    a speed factor to the gesture execution in trajectory.py.
    """
    if params is None:
        params = cluster_art_params([seg_key])
    node = GestureNode(
        kind="C", rho=rho, theta=theta,
        params=params, seg_key=seg_key, in_cluster=in_cluster, i=i,
    )
    # Store virtual target metadata on the node for trajectory.py
    if virtual_target is not None:
        node.virtual_target = virtual_target
    return node


def _make_pause_node(seg_key: str = '|', i: int = 0) -> GestureNode:
    """Create a pause gesture node."""
    return GestureNode(kind="pause", seg_key=seg_key, i=i)


# ═══════════════════════════════════════════════════════════════════════════
# Anchor construction helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_vowel_anchor(i: int, pt: list[float] | None, hold: bool,
                       seg_key: str = '',
                       **extra) -> GestureAnchor:
    """Create a vowel anchor with label, seg_key and extra attributes.

    The label is auto-generated by GestureAnchor._auto_label() based
    on kind and flags (V_o, V, V_e).
    """
    return GestureAnchor(
        i=i, pt=pt, hold=hold, kind="V",
        seg_key=seg_key, **extra)


def _make_pause_anchor(i: int, long: bool, pause_role: str = '',
                          seg_key: str = '|') -> GestureAnchor:
    """Create a pause anchor with role and label."""
    return GestureAnchor(
        i=i, pt=None, hold=False, kind="pause",
        long=long, pause_role=pause_role, seg_key=seg_key)


def _make_synth_anchor(i: int, pt: list[float], label: str = '') -> GestureAnchor:
    """Create a synth (terminal) anchor with neutral position.

    Uses NEUTRAL_RHO / NEUTRAL_THETA as default pt.
    """
    return GestureAnchor(i=i, pt=pt, hold=False, kind="synth", label=label)


# ═══════════════════════════════════════════════════════════════════════════
# Search helpers
# ═══════════════════════════════════════════════════════════════════════════

def _find_prev_vowel(nodes: list[GestureNode],
                       start: int) -> tuple[float, float] | None:
    """Search backward from *start* for the nearest vowel, stopping at pauses.

    Returns (rho, theta) of the vowel found, or None if no vowel is
    found before a pause or the beginning of the list.
    """
    for j in range(start, -1, -1):
        if nodes[j].kind == "pause":
            break
        if nodes[j].kind == "V":
            return nodes[j].rho, nodes[j].theta
    return None


def _find_next_vowel(nodes: list[GestureNode],
                       start: int) -> tuple[float, float] | None:
    """Search forward from *start* for the nearest vowel, stopping at pauses.

    Returns (rho, theta) of the vowel found, or None.
    """
    n = len(nodes)
    for j in range(start, n):
        if nodes[j].kind == "pause":
            break
        if nodes[j].kind == "V":
            return nodes[j].rho, nodes[j].theta
    return None


def _find_next_vowel_theta(nodes: list[GestureNode],
                              start: int) -> float | None:
    """Search forward from *start* for the nearest vowel theta, stopping at pauses.

    Returns the theta of the vowel found, or None.
    """
    result = _find_next_vowel(nodes, start)
    return result[1] if result is not None else None


def _find_last_vowel_in_segs(segs: list[str]) -> tuple[float, float]:
    """Search backward through segment strings for the last vowel.

    Returns (rho, theta) found in VOWELS_SYNTSYL, or
    (NEUTRAL_RHO, NEUTRAL_THETA) as defaults.
    """
    for seg in reversed(segs):
        if is_vowel_seg(seg):
            vkey = IPA_TO_SYNTSYL.get(seg)
            if vkey and vkey in VOWELS_SYNTSYL:
                return VOWELS_SYNTSYL[vkey]["rho"], VOWELS_SYNTSYL[vkey]["theta"]
            return NEUTRAL_RHO, NEUTRAL_THETA
    return NEUTRAL_RHO, NEUTRAL_THETA


def _find_anchor_insert_pos(anchors: list[GestureAnchor],
                               node_idx: int) -> int:
    """Find the insertion position in *anchors* for a given node index.

    Returns the index at which a new anchor with node index *node_idx*
    should be inserted to maintain sorted order by ``i``.
    """
    pos = 0
    for ai, a in enumerate(anchors):
        if a.i >= node_idx:
            break
        pos = ai + 1
    return pos


# ═══════════════════════════════════════════════════════════════════════════
# Cluster detection helper
# ═══════════════════════════════════════════════════════════════════════════

# Pause markers accepted uniformly (requirement 5)
_PAUSE_MARKERS: frozenset = frozenset({'|', 'GAP'})


def _is_pause_seg(seg: str) -> bool:
    """Check if a segment is a pause marker ('|' or 'GAP')."""
    return seg in _PAUSE_MARKERS


def _cc_eligible(seg_key: str) -> bool:
    """Check if a segment is eligible for cluster detection."""
    resolved = _CC_ALIAS.get(seg_key, seg_key)
    synt = IPA_TO_SYNTSYL.get(resolved, "")
    return synt in _TABCONS_IDX


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline: build_gesture_nodes
# ═══════════════════════════════════════════════════════════════════════════

def _parse_polar_targets(flat_segments: list[str],
                         all_polars: list[PolarTarget]
                         ) -> list[PolarTarget | None]:
    """Phase 1: Read polar targets, aligning with flat segments.

    Returns a list indexed by segment position: ``None`` for pauses
    and gaps, the PolarTarget for all other segments.

    Uniform handling of '|' and 'GAP' (requirement 5).
    """
    pol_iter = iter(all_polars)
    polar_list: list[PolarTarget | None] = []
    for seg in flat_segments:
        if _is_pause_seg(seg):
            polar_list.append(None)
        else:
            polar_list.append(next(pol_iter))
    return polar_list


def _build_initial_nodes(flat_segments: list[str],
                         polar_list: list[PolarTarget | None]
                         ) -> list[GestureNode]:
    """Phase 2: Build initial gesture nodes from segments and polar data.

    Consonant nodes get selector params at construction (requirement 4).
    Pause nodes use seg_key to preserve '|' vs 'GAP' distinction.

    Lateral consonants (/l/, /L/) receive a virtual target from the
    Berthommier model for high-speed central occlusion.
    """
    nodes: list[GestureNode] = []
    for i, seg in enumerate(flat_segments):
        if _is_pause_seg(seg):
            nodes.append(_make_pause_node(seg_key=seg, i=i))
        else:
            p = polar_list[i]
            if p.is_vowel:
                nodes.append(_make_vowel_node(p.rho, p.theta, seg, i))
            else:
                # Check for lateral virtual target
                vt = None
                if seg in LATERAL_KEYS:
                    vt = get_lateral_virtual_target(seg)
                elif seg in PLOSIVE_KEYS:
                    vt = get_plosive_virtual_target(seg)
                nodes.append(_make_consonant_node(
                    p.rho, p.theta, seg, i=i,
                    virtual_target=vt,
                ))
    return nodes


def _detect_clusters(nodes: list[GestureNode],
                     syl_boundaries: set[int] | None) -> list[bool]:
    """Phase 3: Detect consonant clusters.

    Returns a cluster mask (list[bool]) aligned with *nodes*.
    """
    cluster_mask = [False] * len(nodes)
    syl_bounds = syl_boundaries or set()

    for i in range(1, len(nodes)):
        if (nodes[i].kind == "C" and nodes[i - 1].kind == "C"
                and i not in syl_bounds
                and _cc_eligible(nodes[i - 1].seg_key)
                and _cc_eligible(nodes[i].seg_key)):
            cluster_mask[i] = True
            cluster_mask[i - 1] = True

    return cluster_mask


def _adjust_consonants(nodes: list[GestureNode],
                       polar_list: list[PolarTarget | None],
                       cluster_mask: list[bool]) -> None:
    """Phase 4: Adjust consonant theta/rho using pre-computed vowel indices.

    Modifies *nodes* in place.
    """
    next_vowel, prev_vowel = _precompute_vowel_indices(nodes)
    for i, nd in enumerate(nodes):
        if nd.kind == "C":
            vr = _nearest_vowel_theta(nodes, i, next_vowel, prev_vowel)
            adj = adjust_consonant_theta(polar_list[i], vr, in_cluster=cluster_mask[i])
            nodes[i].rho = adj.rho
            nodes[i].theta = adj.theta
            nodes[i].in_cluster = cluster_mask[i]


def build_gesture_nodes(flat_segments: list[str],
                        all_polars: list[PolarTarget],
                        syl_boundaries: set[int] | None = None
                        ) -> list[GestureNode]:
    """Build the gesture node list from flat segments and polar targets.

    Pipeline: parse_polar_targets → build_initial_nodes → detect_clusters → adjust_consonants.
    """
    polar_list = _parse_polar_targets(flat_segments, all_polars)
    nodes = _build_initial_nodes(flat_segments, polar_list)
    cluster_mask = _detect_clusters(nodes, syl_boundaries)
    _adjust_consonants(nodes, polar_list, cluster_mask)
    return nodes


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline: build_gesture_anchors
# ═══════════════════════════════════════════════════════════════════════════

def _create_base_anchors(nodes: list[GestureNode]) -> list[GestureAnchor]:
    """Create the initial anchor list from V and pause nodes.

    Each anchor gets:
      - label (auto via GestureAnchor._auto_label)
      - seg_key (from node)
      - pause_role (for pauses: 'phrase_start', 'phrase_end', 'interword')
    """
    anchors: list[GestureAnchor] = []
    n = len(nodes)
    for i, nd in enumerate(nodes):
        if nd.kind == "V":
            prev_is_V = i > 0 and nodes[i - 1].kind == "V"
            next_is_V = i < n - 1 and nodes[i + 1].kind == "V"
            hold = not prev_is_V and not next_is_V
            anchors.append(_make_vowel_anchor(
                i, [nd.rho, nd.theta], hold, seg_key=nd.seg_key))
        elif nd.kind == "pause":
            # Distinguish pause roles (requirement 2)
            is_long = (nd.seg_key == '|')
            if i == 0:
                role = 'phrase_start'
            elif i == n - 1:
                role = 'phrase_end'
            else:
                role = 'interword'
            anchors.append(_make_pause_anchor(
                i, is_long, pause_role=role, seg_key=nd.seg_key))
    return anchors


def _insert_word_end_anchors(anchors: list[GestureAnchor],
                              nodes: list[GestureNode]) -> list[GestureAnchor]:
    """Insert word-end V_e anchors before pauses that follow consonants.

    Uses DELTA_E * last_vowel_rho for coherent V_e position (req. 2).
    """
    inserts: list[tuple[int, GestureAnchor]] = []
    for ai, a in enumerate(anchors):
        if a.kind == "pause" and ai > 0:
            pause_i = a.i
            if pause_i > 0 and nodes[pause_i - 1].kind == "C":
                result = _find_prev_vowel(nodes, pause_i - 1)
                if result is not None:
                    last_rho, last_theta = result
                else:
                    last_rho, last_theta = NEUTRAL_RHO, NEUTRAL_THETA
                we = _make_vowel_anchor(
                    pause_i, [DELTA_E * last_rho, last_theta], False,
                    seg_key='', is_word_end=True)
                inserts.append((ai, we))

    for pos, we in sorted(inserts, key=lambda x: x[0], reverse=True):
        anchors.insert(pos, we)
    return anchors


def _insert_vowel_onset_anchors(anchors: list[GestureAnchor],
                                nodes: list[GestureNode],
                                word_starts: list[int] | None
                                ) -> list[GestureAnchor]:
    """Insert vowel-onset anchors at word starts that begin with a consonant.

    These anchors represent the "initial vowel" concept
    from the COVTL model, inserted when a word starts with a consonant
    to provide a smooth articulatory transition.
    """
    if not word_starts:
        return anchors
    n = len(nodes)
    inserts: list[tuple[int, GestureAnchor]] = []
    for ws in word_starts:
        if ws < n and nodes[ws].kind == "C":
            theta_v = _find_next_vowel_theta(nodes, ws)
            if theta_v is None:
                theta_v = np.pi
            vd = _make_vowel_anchor(ws, [0.5, theta_v], False,
                                     seg_key='', is_vowel_onset=True)
            insert_pos = _find_anchor_insert_pos(anchors, ws)
            inserts.append((insert_pos, vd))

    for pos, vd in sorted(inserts, key=lambda x: x[0], reverse=True):
        anchors.insert(pos, vd)
    return anchors


def _insert_syllable_onset_anchors(anchors: list[GestureAnchor],
                                   syl_boundary_info: list[SyllableBoundary] | None
                                   ) -> list[GestureAnchor]:
    """Insert V_o anchors at inter-syllable boundaries.

    These anchors represent the "syllable-initial vowel" concept:
    when a syllable starts with a consonant, a vowel-onset anchor is
    inserted at the boundary to model the articulatory transition.

    Skips insertion if a vowel_onset anchor already exists at the
    same node index (e.g. from _insert_vowel_onset_anchors).

    syl_boundary_info must have real segments in curr_segments and
    prev_segments, with flat_idx pointing to the actual node index
    (requirement 5 — no more placeholder anchors).
    """
    if not syl_boundary_info:
        return anchors
    inserts: list[tuple[int, GestureAnchor]] = []
    for sb in syl_boundary_info:
        curr_segs = sb.curr_segments
        prev_segs = sb.prev_segments
        flat_idx = sb.flat_idx

        curr_booldeb = 1 if not is_vowel_seg(curr_segs[0]) else 0
        if curr_booldeb == 0:
            continue

        prev_boolast = 1 if not is_vowel_seg(prev_segs[-1]) else 0

        prev_last_rho, prev_last_theta = _find_last_vowel_in_segs(prev_segs)

        weight = (1 - prev_boolast) + DELTA_E * prev_boolast * curr_booldeb
        vd_rho = weight * prev_last_rho
        vd_theta = prev_last_theta

        vd = _make_vowel_anchor(
            flat_idx, [vd_rho, vd_theta], False,
            seg_key='', is_vowel_onset=True, is_syl_vowel_onset=True)
        insert_pos = _find_anchor_insert_pos(anchors, flat_idx)
        inserts.append((insert_pos, vd))

    for pos, vd in sorted(inserts, key=lambda x: x[0], reverse=True):
        anchors.insert(pos, vd)
    return anchors


def _ensure_terminal_anchors(anchors: list[GestureAnchor],
                                nodes: list[GestureNode]) -> list[GestureAnchor]:
    """Ensure the anchor list starts and ends with synth terminal anchors.

    The synth_start and synth_end anchors ALWAYS use
    NEUTRAL_RHO / NEUTRAL_THETA to guarantee a start from
    neutral and a decay toward neutral, in accordance with the
    reference model.

    The neighboring-vowel override was removed because it
    prevented the transition to neutral.
    """
    n = len(nodes)
    anchors.insert(0, _make_synth_anchor(-1, [NEUTRAL_RHO, NEUTRAL_THETA],
                                        label='synth_start'))
    anchors.append(_make_synth_anchor(n, [NEUTRAL_RHO, NEUTRAL_THETA],
                                      label='synth_end'))
    return anchors


def build_gesture_anchors(nodes: list[GestureNode],
                           word_starts: list[int] | None = None,
                           syl_boundary_info: list[SyllableBoundary] | None = None
                           ) -> list[GestureAnchor]:
    """Build the gesture anchor list from nodes.

    Pipeline:
        create_base_anchors
        → insert_word_end_anchors
        → insert_vowel_onset_anchors
        → insert_syllable_onset_anchors
        → ensure_terminal_anchors
    """
    anchors = _create_base_anchors(nodes)
    anchors = _insert_word_end_anchors(anchors, nodes)
    anchors = _insert_vowel_onset_anchors(anchors, nodes, word_starts)
    anchors = _insert_syllable_onset_anchors(anchors, syl_boundary_info)
    anchors = _ensure_terminal_anchors(anchors, nodes)
    return anchors
