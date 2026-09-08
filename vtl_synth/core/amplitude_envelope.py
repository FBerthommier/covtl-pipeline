# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
amplitude_envelope.py — Amplitude envelope of the COVTL model.

(previously ``envelope.py`` — renamed on 2026-09-04 to resolve the
confusion with ``enveloppe.py`` / TimedEnvelope; cf. RISK-003.)

Builds the amplitude envelope from token sequences and block information.
This is Step 4(b) of the synthesis pipeline.

Uses ``BlockInfo`` dataclass for block descriptors and ``PolarTarget``
for polar target data, ensuring type safety across module boundaries.
"""

from __future__ import annotations

import numpy as np

from .constants import (
    FS,
    T_S,
    TOKEN_AMPL_MIN,
    _PLOSIVE_TOKENS,
)
from .phonology import phoneme_base_token
from .types import BlockInfo, GestureAnchor, GestureNode, PolarTarget


# ═══════════════════════════════════════════════════════════════════════════
# Envelope token building
# ═══════════════════════════════════════════════════════════════════════════

def build_envelope_tokens(flat: list[str], all_polars: list[PolarTarget],
                           nodes: list[GestureNode],
                           syl_boundaries: set[int] | None = None,
                           long_pause_duration_factor: float = 10.0,
                           T: int = 16) -> list[str]:
    """Build the sequence of envelope tokens from the flat segment list.

    Each segment maps to a token type (V, C, c, R, r, N, L, O, F, y):
    V vowel, C/c plosive (full / cluster-reduced), R/r fricative
    (full / reduced), N nasal, L lateral, O silence or pause, F
    utterance-final silence, y vowel-onset glide. The sequence is
    bracketed by a leading 'O' and a trailing 'F'.

    Parameters
    ----------
    flat : list[str]
        Flat list of segment keys; 'GAP' emits one 'O' token and '|'
        (word boundary) emits several.
    all_polars : list[PolarTarget]
        Polar targets aligned with the non-pause segments; used by
        ``phoneme_base_token`` to classify each segment.
    nodes : list[GestureNode]
        Gesture nodes of the phrase. Unused here; kept for interface
        symmetry with the COVTL reference.
    syl_boundaries : set[int], optional
        Indices of ``flat`` segments that start a new syllable. A
        plosive that directly follows another plosive is downgraded
        C → c only when both belong to the same syllable (cluster).
    long_pause_duration_factor : float, optional
        Number of 'O' tokens emitted for a '|' word boundary
        (rounded, at least 1). Default: 10.
    T : int, optional
        Unused legacy parameter (COVTL signature compatibility).
        Default: 16.

    Returns
    -------
    list[str]
        Token sequence, e.g. ``['O', 'C', 'V', 'C', 'V', 'F']`` for
        "ba da".
    """
    if syl_boundaries is None:
        syl_boundaries = set()

    tokens: list[str] = ["O"]
    token_flat_map: list[int] = [-1]
    pol_idx = 0
    for i, seg in enumerate(flat):
        if seg == "GAP":
            tokens.append("O")
            token_flat_map.append(i)
            continue
        if seg == "|":
            n_O = max(1, int(round(long_pause_duration_factor)) - 1)
            for _ in range(n_O):
                tokens.append("O")
                token_flat_map.append(i)
            continue
        if pol_idx < len(all_polars):
            pol = all_polars[pol_idx]
            pol_idx += 1
        else:
            pol = all_polars[-1]
        base = phoneme_base_token(seg, pol)
        tokens.append(base)
        token_flat_map.append(i)
    tokens.append("F")
    token_flat_map.append(-1)

    # Post-process: convert C → c for non-syllable-boundary plosive clusters
    out = list(tokens)
    i = 1
    while i < len(out):
        if out[i] == "C" and i > 0 and out[i - 1] in _PLOSIVE_TOKENS:
            flat_idx = token_flat_map[i] if i < len(token_flat_map) else -1
            if flat_idx >= 0 and flat_idx not in syl_boundaries:
                out[i] = "c"
        i += 1

    return out


# ═══════════════════════════════════════════════════════════════════════════
# Envelope primitives
# ═══════════════════════════════════════════════════════════════════════════

def _env_rise(n: int, cexp: float = 1) -> np.ndarray:
    """Rising Hanning envelope."""
    if n <= 0:
        return np.array([], dtype=float)
    w = np.hanning(2 * n)
    return w[:n] ** cexp


def _env_fall(n: int, cdec: float = 3) -> np.ndarray:
    """Falling Hanning envelope."""
    if n <= 0:
        return np.array([], dtype=float)
    w = np.hanning(2 * n)
    return w[n:] ** cdec


def _env_fall3(n: int, cdec: float = 3) -> np.ndarray:
    """Falling Hanning envelope with steeper decay."""
    if n <= 0:
        return np.array([], dtype=float)
    w = np.hanning(2 * n)
    return w[n:] ** (3 * cdec)


# ═══════════════════════════════════════════════════════════════════════════
# Transition envelope
# ═══════════════════════════════════════════════════════════════════════════

def _env_transition(A: str, B: str, n: int,
                    cexp: float = 1, cdec: float = 3) -> np.ndarray:
    """Compute the envelope transition between two token types.

    This is the exact logic from the original monolithic function.
    """
    if n <= 0:
        return np.array([], dtype=float)
    rise = _env_rise(n, cexp)
    fall = _env_fall(n, cdec)
    fall3 = _env_fall3(n, cdec)
    syl = A + B

    # ── Direct token-pair cases ──
    if syl == "OO":
        return np.zeros(n)
    elif syl in ("OC", "Oc"):
        return np.zeros(n)
    elif syl == "OV":
        return rise
    elif syl == "OF":
        return np.array([], dtype=float)
    elif syl in ("CF", "cF"):
        return rise
    elif syl == "VF":
        return np.array([], dtype=float)
    elif syl == "VV":
        return np.ones(n)
    elif syl in ("CV", "cV"):
        nr = max(1, n // 2)
        no = n - nr
        return np.concatenate([_env_rise(nr, cexp), np.ones(no)])
    elif syl in ("VC", "Vc"):
        return fall
    elif syl == "CC":
        nr = max(1, n // 2)
        nf = n - nr
        return np.concatenate([0.5 * _env_rise(nr, cexp), 0.5 * _env_fall3(nf, cdec)])
    elif syl in ("Cc", "cC"):
        return _env_rise(n, cexp) * _env_fall3(n, cdec)

    # ── Token amplitude minimums ──
    aA = TOKEN_AMPL_MIN.get(A, 0.0)
    aB = TOKEN_AMPL_MIN.get(B, 0.0)

    # ── 'y' (vowel-onset) special cases ──
    if A == "y" or B == "y":
        return _env_transition_y(A, B, n, aA, aB, cexp, cdec)

    # ── Generic cases ──
    return _env_transition_generic(A, B, n, aA, aB, cexp, cdec)


def _env_transition_y(A: str, B: str, n: int,
                       aA: float, aB: float,
                       cexp: float, cdec: float) -> np.ndarray:
    """Handle envelope transitions involving the 'y' (vowel-onset) token."""
    rise = _env_rise(n, cexp)
    fall = _env_fall(n, cdec)

    if A == "y" and B == "V":
        nr = max(1, n // 2)
        no = n - nr
        return np.concatenate([aA + (1.0 - aA) * _env_rise(nr, cexp), np.ones(no)])
    elif A == "V" and B == "y":
        return aB + (1.0 - aB) * _env_fall(n, cdec)
    elif A == "y" and B == "C":
        return aA * _env_fall(n, cdec)
    elif A == "C" and B == "y":
        return aB * _env_rise(n, cexp)
    elif A == "y" and B == "c":
        return aA * _env_fall(n, cdec)
    elif A == "c" and B == "y":
        return aB * _env_rise(n, cexp)
    elif A == "O" and B == "y":
        return aB * _env_rise(n, cexp)
    elif A == "y" and B == "O":
        return aA * _env_fall(n, cdec)
    elif A == "y" and B == "F":
        return aA + (1.0 - aA) * _env_rise(n, cexp)
    elif A == "F" and B == "y":
        return aB + (1.0 - aB) * _env_fall(n, cdec)
    elif A == "y" and B == "y":
        return np.full(n, aA)
    else:
        if aB > aA:
            return aA + (aB - aA) * _env_rise(n, cexp)
        else:
            return aB + (aA - aB) * _env_fall(n, cdec)


def _env_transition_generic(A: str, B: str, n: int,
                             aA: float, aB: float,
                             cexp: float, cdec: float) -> np.ndarray:
    """Handle generic envelope transitions."""
    rise = _env_rise(n, cexp)
    fall = _env_fall(n, cdec)

    if A == "O" and B not in ("O", "V", "C", "c", "F"):
        return aB * rise
    elif A == "V" and B not in ("V", "C", "c", "O", "F"):
        return aB + (1.0 - aB) * fall
    elif B == "V" and A not in ("V", "C", "c", "O", "F"):
        nr = max(1, n // 2)
        no = n - nr
        return np.concatenate([aA + (1.0 - aA) * _env_rise(nr, cexp), np.ones(no)])
    elif B == "F" and A not in ("V", "C", "c", "O", "F"):
        return aA + (1.0 - aA) * rise
    elif A in ("C", "c") and B not in ("V", "C", "c", "O", "F"):
        return aB * rise
    elif B in ("C", "c") and A not in ("V", "C", "c", "O", "F"):
        return aA * fall
    elif (A not in ("O", "V", "C", "c", "F") and
          B not in ("O", "V", "C", "c", "F")):
        if aA == aB:
            return np.full(n, aA)
        elif aB > aA:
            return aA + (aB - aA) * rise
        else:
            return aB + (aA - aB) * fall
    else:
        if aB > aA:
            return aA + (aB - aA) * rise
        else:
            return aB + (aA - aB) * fall


# ═══════════════════════════════════════════════════════════════════════════
# Cluster envelope
# ═══════════════════════════════════════════════════════════════════════════

def _build_cluster_env(pre_token: str, cons_tokens: list[str],
                        post_token: str, n_samples: int,
                        has_following_plateau: bool,
                        cexp: float = 1, cdec: float = 3) -> np.ndarray:
    """Build the envelope for a consonant cluster."""
    m = len(cons_tokens)
    all_toks = [pre_token] + cons_tokens + [post_token]
    n_trans = len(all_toks) - 1

    if n_trans <= 0 or n_samples <= 0:
        return np.array([], dtype=float)

    segments: list[np.ndarray] = []
    remaining = n_samples
    for k in range(n_trans):
        if k == n_trans - 1:
            nk = remaining
        else:
            nk = n_samples // n_trans
        remaining -= nk

        if nk <= 0:
            segments.append(np.array([], dtype=float))
            continue

        A, B = all_toks[k], all_toks[k + 1]
        is_last_to_V = k == n_trans - 1 and B in ("V", "y")

        if is_last_to_V:
            aA = TOKEN_AMPL_MIN.get(A, 0.0)
            aB = TOKEN_AMPL_MIN.get(B, 0.0)
            if A in ("C", "c"):
                segments.append(aB * _env_rise(nk, cexp))
            elif A == "O":
                segments.append(aB * _env_rise(nk, cexp))
            elif A == "y":
                if B == "V":
                    nr = max(1, nk // 2)
                    no = nk - nr
                    segments.append(np.concatenate([aA + (1.0 - aA) * _env_rise(nr, cexp), np.ones(no)]))
                elif B == "y":
                    segments.append(np.full(nk, aA))
                else:
                    segments.append(aA + (aB - aA) * _env_rise(nk, cexp))
            elif A == "V" and B == "y":
                segments.append(aB + (1.0 - aB) * _env_fall(nk, cdec))
            elif A not in ("V", "C", "c", "O", "F"):
                segments.append(aA + (aB - aA) * _env_rise(nk, cexp))
            elif A == "V":
                segments.append(np.ones(nk))
            else:
                segments.append(_env_rise(nk, cexp) * aB)
        else:
            seg = _env_transition(A, B, nk, cexp, cdec)
            segments.append(seg)

    return np.concatenate(segments) if segments else np.array([], dtype=float)


# ═══════════════════════════════════════════════════════════════════════════
# Full envelope from block info
# ═══════════════════════════════════════════════════════════════════════════

def build_envelope_from_blocks(block_info: list[BlockInfo], nodes: list[GestureNode],
                                anchors: list[GestureAnchor], all_polars: list[PolarTarget],
                                flat: list[str], syl_boundaries: set[int],
                                sps: int, cexp: float = 1,
                                cdec: float = 3) -> np.ndarray:
    """Build the full amplitude envelope from block information.

    Parameters
    ----------
    block_info : list[BlockInfo]
        Per-block information from ``build_global_pval``; each block
        contributes n_steps·sps samples (plateau, transition, cluster...).
    nodes : list[GestureNode]
        Gesture nodes. Unused here; kept for interface symmetry with
        the COVTL reference.
    anchors : list[GestureAnchor]
        Gesture anchors. Unused here; kept for interface symmetry.
    all_polars : list[PolarTarget]
        Polar targets. Unused here; kept for interface symmetry.
    flat : list[str]
        Flat segment list. Unused here; kept for interface symmetry.
    syl_boundaries : set[int]
        Syllable boundary indices. Unused here; kept for interface
        symmetry.
    sps : int
        Steps per sample (T_S * FS).
    cexp, cdec : float
        Envelope rise/decay exponents.

    Returns
    -------
    np.ndarray
        Amplitude envelope E(t) sampled at FS (10 kHz), one value per
        step of the concatenated blocks.
    """
    env_blocks: list[np.ndarray] = []

    for bi in block_info:
        kind = bi.kind
        n_samples = bi.n_steps * sps

        if kind == "plateau":
            env_blocks.append(np.ones(n_samples))
        elif kind == "background":
            env_blocks.append(np.ones(n_samples))
        elif kind == "pause":
            env_blocks.append(np.zeros(n_samples))
        elif kind == "cluster":
            cons_tokens = bi.cons_tokens
            pre_token = bi.pre_token
            post_token = bi.post_token
            has_plateau = bi.has_following_plateau
            seg = _build_cluster_env(pre_token, cons_tokens, post_token,
                                     n_samples, has_plateau, cexp, cdec)
            env_blocks.append(seg)
        elif kind == "initial":
            env_blocks.append(np.zeros(n_samples))
        elif kind == "terminal":
            env_blocks.append(np.zeros(n_samples))
        elif kind == "decay":
            pre_amp = bi.pre_amp
            if n_samples > 0 and pre_amp > 0.01:
                env_blocks.append(pre_amp * _env_fall(n_samples, cdec))
            else:
                env_blocks.append(np.zeros(n_samples))
        elif kind == "attack":
            post_amp = bi.post_amp
            if n_samples > 0 and post_amp > 0.01:
                env_blocks.append(post_amp * _env_rise(n_samples, cexp))
            else:
                env_blocks.append(np.zeros(n_samples))
        else:
            env_blocks.append(np.zeros(n_samples))

    if env_blocks:
        return np.concatenate(env_blocks)
    return np.array([], dtype=float)
