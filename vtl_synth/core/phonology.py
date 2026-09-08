# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
phonology.py
=============
Syllabification and syllable boundaries.

This module takes a sequence of phonemic segments and
produces a list of GestureSyllable (syllabic structure).

Syllabification algorithm:
  1. Vowels form the syllable nuclei.
  2. Pre-nucleus consonants form the onset.
  3. Post-nucleus consonants up to the next vowel form the coda.
  4. At most 2 onset consonants (CCV).

This algorithm is deterministic and follows the conventions of the
Berthommier model (2023): the graphs are CV, CVC, CCV.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from vtl_synth.core.types import (
    GestureNode,
    GestureSyllable,
    GestureKind,
    PolarTarget,
)
from vtl_synth.core.constants import (
    VOWEL_TARGETS,
    CONSONANT_TARGETS,
)

# Weight of the consonant in the cluster coarticulation blend:
# theta_final = CLUSTER_CONS_BLEND * theta_C + (1 - w) * theta_V
CLUSTER_CONS_BLEND: float = 0.7


# ==========================================================================
# Syllabification
# ==========================================================================



def _assign_timing(
    syllables: List[GestureSyllable],
    segments: list,
) -> None:
    """Assign t_start and t_end to each syllable and node.

    Modifies the objects in place.
    """
    t = 0.0
    seg_idx = 0

    for syl in syllables:
        syl.t_start = t

        for node in syl.all_nodes:
            node.t_start = t
            t += node.duration_ms
            node.t_end = t
            seg_idx += 1

        syl.t_end = t


# ==========================================================================
# Resolution of consonant targets (vowel context)
# ==========================================================================



# ==========================================================================
# Utility functions
# ==========================================================================



# ==========================================================================
# COVTL mapping and cluster helpers (for build_global_pval)
# ==========================================================================

# Mapping IPA (SAMPA) keys to COVTL-compatible names.
# Used by trajectory.build_global_pval for cluster lookups.
IPA_TO_SYNTSYL: dict = {
    # --- Plosives ---
    'b': 'b', 'p': 'b',
    'd': 'd', 't': 'd',
    'g': 'g', 'k': 'g',
    # --- Fricatives ---
    'f': 'f', 'v': 'v',
    's': 's', 'z': 'z',
    'S': 'sh', 'Z': 'zh',
    'T': 'th', 'D': 'dh',
    'X': 'x',
    # --- Affricates ---
    'tS': 'tch', 'dZ': 'j',
    # --- Nasals ---
    'm': 'm', 'n': 'n', 'N': 'ng', 'J': 'ny',
    # --- Laterals ---
    'l': 'l', 'L': 'L',
    # --- Palatals ---
    'C': 'ch', 'j': 'y',
    # --- Approximants ---
    'w': 'w',
    'R': 'r',
    # --- Glottal ---
    'h': 'h',
    # --- Vowels ---
    'a': 'a', 'i': 'i', 'u': 'u',
    'e': 'e', 'E': 'eh',
    'o': 'o', 'O': 'oh',
    '6': 'oe', '9': 'oen',
    '@': 'schwa', 'y': 'y', '2': 'oe2',
}

# Consonant cluster aliases.
# Some IPA cluster representations have alternative canonical forms
# used in the COVTL table lookups.
_CC_ALIAS: dict = {
    'StS': 'STS',
    'StR': 'STR',
    'SpR': 'SPR',
    'SkR': 'SKR',
    'ptS': 'pTCH',
    'ktS': 'kTCH',
}

# Table mapping consonant COVTL names to COVTL parameter indices.
# Used by cluster_art_params() for the ART1 (single-selector) cluster model.
# Values are sorted lists of parameter indices into COVTL_PARAMS.
# COVTL_PARAMS = ('HX','HY','JX','JA','LP','LD',
#                   'TCX','TCY','TTX','TTY','TBX','TBY','TS1','TS2','TS3')
#   indices:        0     1     2    3    4    5    6    7    8    9    10   11   12   13   14
_TABCONS_IDX: dict = {
    'b': [3, 5, 6, 7],           # JA, LD, TCX, TCY
    'd': [3, 6, 7, 8, 9, 10, 11],  # JA, TCX, TCY, TTX, TTY, TBX, TBY
    'g': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'f': [3, 6, 7],               # JA, TCX, TCY
    'v': [2, 3, 4, 5, 6, 7],       # JX, JA, LP, LD, TCX, TCY
    's': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'z': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'sh': [3, 6, 7, 10, 11],      # JA, TCX, TCY, TBX, TBY
    'zh': [3, 6, 7, 10, 11],      # JA, TCX, TCY, TBX, TBY
    'th': [3, 6, 7, 10, 11],      # JA, TCX, TCY, TBX, TBY
    'dh': [3, 6, 7, 10, 11],      # JA, TCX, TCY, TBX, TBY
    'r': [3, 6, 7, 10, 11, 13],    # JA, TCX, TCY, TBX, TBY, TS2
    'tch': [3, 6, 7, 10, 11, 4],   # JA, TCX, TCY, TBX, TBY, LP
    'j': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'l': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'L': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'ch': [3, 6, 7, 10, 11],      # JA, TCX, TCY, TBX, TBY
    'y': [3, 6, 7, 10, 11],       # JA, TCX, TCY, TBX, TBY
    'x': [3, 6, 7, 10, 11, 13],    # JA, TCX, TCY, TBX, TBY, TS2
    'w': [3, 6, 7],               # JA, TCX, TCY
    'h': [],                       # no COVTL selector
}

# Set of COVTL vowel names (for is_synthsyl_consonant)
_SYNTSYL_VOWELS: frozenset = frozenset({
    'a', 'i', 'u', 'e', 'eh', 'o', 'oh', 'oe', 'oen', 'schwa', 'y', 'oe2',
})


def is_synthsyl_consonant(s: str) -> bool:
    """Check if a COVTL name represents a consonant.

    Returns True if *s* is a non-empty string in the COVTL consonant
    set (i.e. it is an IPA_TO_SYNTSYL value but NOT a vowel).
    """
    return bool(s) and s not in _SYNTSYL_VOWELS


def cluster_art_params(keys: list) -> list:
    """Return COVTL parameter indices for a consonant cluster (ART1 model).

    For each IPA key in *keys*, resolve through IPA_TO_SYNTSYL, then look
    up _TABCONS_IDX.  Return the sorted union of all parameter indices.
    If a key is not found, its selector is looked up via
    pipeline.projection.get_selector_list and mapped to indices.
    """
    from vtl_synth.core.constants import COVTL_PARAMS
    _covtl_name_to_idx = {n: i for i, n in enumerate(COVTL_PARAMS)}
    indices: set = set()
    for k in keys:
        synt = IPA_TO_SYNTSYL.get(k, '')
        tab = _TABCONS_IDX.get(synt)
        if tab is not None:
            indices.update(tab)
        else:
            # Fallback: use projection.get_selector_list
            try:
                from vtl_synth.core.projection import get_selector_list
                sel = get_selector_list(k)
                if sel:
                    for sn in sel:
                        idx = _covtl_name_to_idx.get(sn)
                        if idx is not None:
                            indices.add(idx)
            except Exception:
                pass
    return sorted(indices)


# ==========================================================================
# Vowel/consonant classification helpers (for gesture.py reference pipeline)
# ==========================================================================

# Vowel targets keyed by COVTL name (values of IPA_TO_SYNTSYL for vowels).
# Used by gesture._find_last_vowel_in_segs.
# Built from VOWEL_TARGETS by reversing through IPA_TO_SYNTSYL.
def _build_vowels_synthsyl() -> dict:
    """Build VOWELS_SYNTSYL from VOWEL_TARGETS + IPA_TO_SYNTSYL."""
    result = {}
    # Invert: for each IPA key in VOWEL_TARGETS, find its COVTL name
    ipa_to_synt = {k: v for k, v in IPA_TO_SYNTSYL.items()}
    for ipa_key, (rho, theta) in VOWEL_TARGETS.items():
        synt_name = ipa_to_synt.get(ipa_key)
        if synt_name and synt_name in _SYNTSYL_VOWELS:
            result[synt_name] = {"rho": rho, "theta": theta}
    return result


VOWELS_SYNTSYL: dict = _build_vowels_synthsyl()


# Rho override table for consonant clusters.
# Maps resolved cluster alias keys to a rho multiplier or absolute rho.
# Currently empty — reserved for future cluster-specific adjustments.
_CC_RHO_OVERRIDE: dict = {}


def is_vowel(seg_key: str) -> bool:
    """Check if a segment key represents a vowel.

    Used by gesture.py to classify nodes.
    Checks against VOWEL_TARGETS (the authoritative vowel registry).
    """
    return seg_key in VOWEL_TARGETS


def adjust_consonant_theta(polar_target, vowel_theta: float,
                           in_cluster: bool = False) -> 'PolarTarget':
    """Adjust a consonant's polar target based on the nearest vowel context.

    For consonants in a cluster, the theta is pulled toward the vowel
    theta to model coarticulation.  For non-cluster consonants, the
    original theta is preserved.

    Parameters
    ----------
    polar_target : PolarTarget or None
        The consonant's polar target.
    vowel_theta : float
        Theta of the nearest contextual vowel.
    in_cluster : bool
        True if this consonant is part of a cluster.

    Returns
    -------
    PolarTarget
        Adjusted polar target (or copy of original if None).
    """
    if polar_target is None:
        return PolarTarget(0.5, vowel_theta, '', is_vowel=False)

    rho = polar_target.rho
    theta = polar_target.theta

    if in_cluster:
        # In clusters, pull theta toward the vowel theta
        # to model coarticulatory blending (HARD-004: named ratio).
        theta = CLUSTER_CONS_BLEND * theta + (1.0 - CLUSTER_CONS_BLEND) * vowel_theta

    return PolarTarget(rho, theta, polar_target.label, is_vowel=False)


def phoneme_base_token(c: str, polar_target: 'PolarTarget') -> str:
    """Return the envelope token type for a phoneme.

    Used by ``envelope.build_envelope_tokens`` and
    ``trajectory._cluster_block_info`` to assign each phoneme
    a token type that drives the COVTL amplitude envelope.

    Parameters
    ----------
    c : str
        IPA key of the phoneme.
    polar_target : PolarTarget
        Polar target (is_vowel flag used for vowel detection).

    Returns
    -------
    str
        Envelope token type: 'V', 'C', 'N', 'L', 'R', or 'r'.

    Token mapping
    -------------
    V   : vowels (is_vowel=True)
    C   : plosives, fricatives, affricates, glottal
    N   : nasals (m, n, N, J)
    L   : laterals (l, L)
    R   : uvular rhotic
    r   : approximants (w, j, C)
    """
    if polar_target.is_vowel:
        return 'V'
    # Consonant categories
    if c in ('m', 'n', 'N', 'J'):
        return 'N'
    if c in ('l', 'L'):
        return 'L'
    if c == 'R':
        return 'R'
    if c in ('w', 'j', 'C'):
        return 'r'
    # All other consonants (plosives, fricatives, affricates, h)
    return 'C'
