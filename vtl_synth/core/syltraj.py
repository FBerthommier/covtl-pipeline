# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
syltraj.py — Syllabic trajectory engine conforming to the COVTL
specification (reference publications: Berthommier, arXiv:2307.02299,
2023; Berthommier, JEP 2024, pp. 541-550).

Port of the reference model (parsing → gesture → trajectory) onto the
15-param COVTL parameterization of this project:

  1. Nodes: each phoneme (V and C) carries its OWN polar target
     (ρ_C, θ_C). No consonant position interpolation: the
     targets are possibly adjusted by `adjust_consonant_theta`
     (reference rules: d/t→θ_CC_D in a cluster, g/k→θ_CC_G with
     ρ 1.1, l/n → ρ_STOP; outside a cluster d/t→θ_DENTAL, g/k velar or
     backed after a back vowel).
  2. Anchors: vowels only (hold if isolated) + synthetic
     VOCALIC anchors: word end (COEFCEN·ρ of the last
     vowel), syllabic onset (weight·ρ), word onset ([0.5, θ_v]),
     terminals [0, 0].  COEFCEN = 0.5 (reference).
  3. Trajectory: walk over anchor pairs (build_global_pval);
     for m consonants between two anchors, `build_cluster_pval` writes
     (m+1) sub-arcs of T_cons steps whose ENDPOINTS are the consonant
     targets themselves (C₀→dep. anchor, Cₖ₋₁→Cₖ, Cₘ₋₁→arr.
     anchor), injecting only the selector parameters. The vocalic
     background (full arc between the anchors) remains for the
     parameters outside the selector.

Synchronization: time is in gesture STEPS (T_cons, T_voy,
T_pause_short, T_pause_long — a deliberate archaism that guarantees
perfect branch synchronization). The gesture rate = 100 Hz
(1 step = 10 ms); T_cons/T_voy/T_pause are derived from the target durations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .notation import (
    CHAR_ALIAS,
    NASAL_PRECOMPOSED as _NASAL_PRECOMPOSED,
    _TILDE,
    normalize_text as _normalize_word,
)
from .constants import (
    ALL_PHONEME_KEYS,
    CO_VTL,
    COVTL_PARAMS,
    N_VTL_PARAMS,
    VOWEL_TARGETS,
    CONSONANT_TARGETS,
)

# ==========================================================================
# Reference model constants (COVTL constants.py)
# ==========================================================================

SYL_COEFCEN: float = 0.5            # word-end / onset anchor weight
SYL_THETA_DENTAL: float = 23 * np.pi / 16       # d, t outside a cluster
SYL_THETA_CC_D: float = -2.5 * np.pi / 6        # d, t in a cluster
SYL_THETA_CC_G: float = -np.pi / 12             # g, k in a cluster
SYL_THETA_VELAR: float = np.pi / 3              # g, k outside a cluster (front)
SYL_THETA_VELAR_BACK: float = 23 * np.pi / 12   # g, k after a back vowel
SYL_RHO_STOP: float = 1.2
SYL_RHO_CLUSTER_VELAR: float = 1.1
SYL_NU: int = -1
SYL_K: float = 1000.0
SYL_PEXP: int = 2

# Cluster alias (reference phonology._CC_ALIAS, adapted to the K keys):
# consonant → COVTL representative for the cluster rules.
_CC_ALIAS = {
    'l': 'd', 'n': 'd', 'm': 'b', 'f': 'b', 'v': 'b',
    's': 'd', 'z': 'd', 'S': 'g', 'Z': 'g', 'R': 'g', 'J': 'g',
    'w': 'b', 'j': 'g',
}
# Consonants whose ρ switches to the stop value in a cluster (reference
# _CC_RHO_OVERRIDE: l, n — liquid/nasal realized stop-like).
_CC_RHO_OVERRIDE = {'l', 'n'}

# 15-param targets of this project to which the reference place
# rules apply (d/t/g/k); the other consonants (sibilants etc.)
# keep their own calibrated targets (z_front, Z −TCY, v θ353).
_REF_PLACE_KEYS = {'d', 't', 'g', 'k'}

SR_GESTURE: float = 100.0   # gesture step = 10 ms

# Waypoint of closing VV arcs: schwa @ (the most open central
# vowel of the model) — the direct polar arc between distant vowels
# can close the tract mid-transition (superposition of the
# contributions of the two anchors, e.g. iu/ui 0.062 cm² over 132
# swept pairs, 11 closing — cf. _diag_vv_mid).
SYL_VV_WAYPOINT_DTHETA: float = np.pi  # (reserved: angular threshold)
SYL_VV_CLOSURE_THRESH: float = 0.18   # cm² (margin ~0.03 vs the full
# chain: the probe measures on the 19-param resting state, the chain
# adds V/VO/TS3 extensions — measured eu: probe 0.152 vs chain 0.120)

# Optional probe injected by build_phrase_tract:
# callable(Pval_block (n,15)) -> min area (cm²) at the middle of the block.
# If the probe returns < SYL_VV_CLOSURE_THRESH, the vocalic background arc
# is routed through the schwa as two half-arcs (exact continuity at the
# junctions: the arcs go anchor to anchor, exact endpoints).
VV_CLOSURE_PROBE = None


def _vv_waypoint() -> list:
    """Schwa waypoint of closing VV arcs.

    Languages without '@' in their VOWEL_TARGETS (Italian, Spanish:
    no phonological schwa) fall back to the NEUTRAL anchor, which IS
    the schwa by definition (constants.NEUTRAL_RHO/NEUTRAL_THETA).
    """
    wp = VOWEL_TARGETS.get('@')
    if wp is None:
        from vtl_synth.core.constants import NEUTRAL_RHO, NEUTRAL_THETA
        wp = (NEUTRAL_RHO, NEUTRAL_THETA)
    return list(wp)

# Nasal vowels: Unicode precomposed → oral key + nasal flag.
# Also handles: combining tilde U+0303 after the key, and a direct '~' suffix.
_NASAL_PRECOMPOSED = {
    'ã': 'a', 'ẽ': 'e', 'ĩ': 'i', 'õ': 'o', 'ũ': 'u',
    'à̃': 'a', 'ɛ̃': 'E', 'ɔ̃': 'O', 'œ̃': '9', 'Ẽ': 'E',
}
_TILDE = '\u0303'


# ==========================================================================
# Structures
# ==========================================================================

@dataclass
class SylNode:
    kind: str                    # 'V', 'C', 'pause'
    key: str = ''
    rho: float = 0.0
    theta: float = 0.0
    params: list = field(default_factory=list)   # indices COVTL
    in_cluster: bool = False
    long: bool = False           # long pause ('|')
    nasal: bool = False          # nasal vowel (partial VO extension)
    breath: bool = False         # breath pause ('%', expressive prosody)


@dataclass
class SylAnchor:
    i: int                       # node index
    kind: str                    # 'V', 'pause', 'synth'
    pt: list | None
    hold: bool = False
    long: bool = False
    is_vowel_onset: bool = False
    is_word_end: bool = False
    is_syl_vowel_onset: bool = False
    breath: bool = False         # breath pause anchor ('%')


@dataclass
class SylBlock:
    n_steps: int
    kind: str
    n_cons: int = 0
    cons_tokens: list = field(default_factory=list)
    cons_keys: list = field(default_factory=list)   # real IPA keys
    vowel_key: str = ''                             # vocalic plateau
    pre_token: str = ''
    post_token: str = ''
    has_following_plateau: bool = False
    long: bool = False
    pre_amp: float = 0.0
    post_amp: float = 0.0
    nasal: bool = False           # nasal vowel plateau (partial VO)
    breath: bool = False          # breath pause block ('%', v1.0.8)


# ==========================================================================
# 15-param projection (reference polar.py on our 15-param CO)
# ==========================================================================

def compute_P(rho: float, theta: float) -> np.ndarray:
    CO = _co_matrix()
    return CO[:, 1] + rho * CO[:, 0] * np.cos(CO[:, 2] - theta)


_CO_CACHE = None


def _co_matrix() -> np.ndarray:
    global _CO_CACHE
    if _CO_CACHE is None:
        from .constants import CO
        _CO_CACHE = np.asarray(CO, dtype=np.float64)
    return _CO_CACHE


def arc_B(pt_dep, pt_arr, params, D: int, thetabounds, opint: int,
          nu: int, K: float, Pexp: int) -> np.ndarray:
    """Reference arc: rk = cos(th/2)^Pexp; phase θ_arr + (nu/K)·th."""
    if D <= 0:
        return np.zeros((0, len(params)))
    if opint == 0:
        th = np.linspace(thetabounds[0], thetabounds[1], D)
    elif opint == -1:
        th1 = np.linspace(thetabounds[0], thetabounds[1], D + 1)
        th = th1[1:D + 1]
    else:
        th = np.linspace(thetabounds[0], thetabounds[1], D)
    pa_theta_uw = np.unwrap([pt_dep[1], pt_arr[1]])[1]
    if abs(pa_theta_uw - pt_dep[1]) < abs(pt_arr[1] - pt_dep[1]):
        pa_theta = pa_theta_uw
    else:
        pa_theta = pt_arr[1]
    pd = np.array(pt_dep, dtype=float)
    pa = np.array([pt_arr[0], pa_theta], dtype=float)
    CO = _co_matrix()
    Pt = np.zeros((D, len(params)))
    for k in range(D):
        rk = np.cos(th[k] / 2) ** Pexp
        for j, p in enumerate(params):
            Pt[k, j] = (CO[p, 1]
                        + rk * pa[0] * CO[p, 0] * np.cos(CO[p, 2] - pa[1]
                                                         - (nu / K) * th[k])
                        + (1 - rk) * pd[0] * CO[p, 0]
                        * np.cos(CO[p, 2] - pd[1]))
    return Pt


# ==========================================================================
# Tokenization + syllabification (dot rule: C.C split, otherwise merge)
# ==========================================================================

_TOKEN_RE = None

# Aliases for non-SAMPA characters (French accents, uvular r, etc.)
CHAR_ALIAS = {
    'é': 'e', 'è': 'E', 'ê': 'E', 'ë': 'E', 'à': 'a', 'â': 'a',
    'î': 'i', 'ï': 'i', 'ô': 'o', 'ö': 'o', 'û': 'u', 'ù': 'u',
    'ü': 'u', 'ç': 's', 'É': 'e', 'È': 'E', 'À': 'a',
    'r': 'R',          # graphemic r → French uvular (target R)
    'ɡ': 'g',
}


def _token_re() -> re.Pattern:
    global _TOKEN_RE
    if _TOKEN_RE is None:
        keys = sorted((k for k in ALL_PHONEME_KEYS if k != 'g_vel'
                       and k != 'z_front' and k != 'g_pal'),
                      key=len, reverse=True)
        _TOKEN_RE = re.compile('(' + '|'.join(re.escape(k) for k in keys)
                               + ')')
    return _TOKEN_RE


def preprocess_phrase(phrase: str) -> tuple[str, list[str]]:
    """Normalize the phrase (notation gateway) and list the ignored characters."""
    from .notation import normalize_text as _n_text
    from .notation import unknown_chars as _u_chars
    normalized = _n_text(phrase)
    ignored = _u_chars(phrase)
    return normalized, ignored


def _is_vowel_key(key: str) -> bool:
    return key.rstrip('~') in VOWEL_TARGETS


def _normalize_word(word: str) -> str:
    """Delegates to the notation gateway (normalize_text is global)."""
    from .notation import normalize_text
    return normalize_text(word)


def tokenize_phrase(phrase: str) -> list:
    """Phrase → list of tokens: ('S', key, nasal) | 'GAP' | 'PAUSE' | 'BREATH' | 'DOT'.

    Punctuation '|' = long pause; space = pause (GAP); '%' = breath
    pause (expressive prosody, v1.0.8 — duration T_pause_breath,
    shorter than the comma pause; see build_phrase_pval).
    Nasal vowels: precomposed (ã ẽ ĩ õ ũ), combining tilde U+0303
    attached to the vowel, or '~' suffix → ('S', oral_key + '~', True).
    Characters outside the inventory are ignored (see preprocess_phrase).
    """
    tokens: list = []
    prev_marker = False          # previous word was a pause marker
    for wi, word in enumerate(phrase.strip().split()):
        if word == '%':
            # breath marker: standalone word (like '|'), and the
            # inter-word GAP is NOT emitted around it — a single
            # pause node results (unlike '|', kept unchanged for
            # bit-identity with the pre-1.0.8 behaviour)
            tokens.append('BREATH')
            prev_marker = True
            continue
        if wi > 0 and not prev_marker:
            tokens.append('GAP')
        prev_marker = False
        if word == '|':
            tokens.append('PAUSE')
            continue
        word = _normalize_word(word)
        for m in _token_re().finditer(word):
            key = m.group(0)
            end = m.end()
            nasal = key.endswith('~')
            if not nasal and end < len(word) and word[end] == '~':
                # direct '~' suffix: KEEP it in the key (nasal marker
                # carried through syllables → nodes → plateaus)
                key = key + '~'
                nasal = True
                end += 1
            tokens.append(('S', key, nasal))
            if end < len(word) and word[end] == '.':
                tokens.append('DOT')
    return tokens


def _limit_long_sequences(word_toks: list) -> list:
    """Length cap for sequences (reference timit_adapter).

    Inserts a DOT after the 1st consonant of any 4+ C sequence
    (schwa principle: the cluster is split into two
    syllables by the C.C dot engine) and after the 1st vowel of
    any 3+ V sequence.  Existing DOTs cut the sequences,
    as in the reference (single sweep, without re-checking the
    remaining segment).
    """
    out: list = []
    run: list = []          # consecutive segment tokens (excluding DOT)
    run_is_cons = None

    def flush():
        nonlocal run, run_is_cons
        if not run:
            return
        if run_is_cons and len(run) >= 4:
            out.append(run[0])
            out.append('DOT')
            out.extend(run[1:])
        elif not run_is_cons and len(run) >= 3:
            out.append(run[0])
            out.append('DOT')
            out.extend(run[1:])
        else:
            out.extend(run)
        run = []
        run_is_cons = None

    for tok in word_toks:
        if tok == 'DOT':
            flush()
            out.append('DOT')
            continue
        key = tok[1]
        is_cons = not _is_vowel_key(key)
        if run_is_cons is None or is_cons == run_is_cons:
            run.append(tok)
            run_is_cons = is_cons
        else:
            flush()
            run = [tok]
            run_is_cons = is_cons
    flush()
    return out


def build_flat(phrase: str):
    """Phrase → (flat, syllables, syl_boundaries, boundary_info, word_starts).

    flat: list of ('S', key) | 'GAP' | 'PAUSE' | 'BREATH' | 'DOT'
    syllables: list[list[list[str]]] (words → syllables → keys)
    """
    tokens = tokenize_phrase(phrase)
    # group into words (GAP/PAUSE/BREATH separate)
    words: list[list] = []
    cur: list = []
    for tok in tokens:
        if tok in ('GAP', 'PAUSE', 'BREATH'):
            if cur:
                words.append(cur)
                cur = []
            words.append([tok])
        else:
            cur.append(tok)
    if cur:
        words.append(cur)

    syllables: list[list[list[str]]] = []
    flat: list = []
    word_starts: list[int] = []
    syl_bounds: set[int] = set()
    boundary_info: list = []

    for word in words:
        if word and word[0] in ('GAP', 'PAUSE', 'BREATH'):
            flat.append(word[0])
            continue
        word_starts.append(len(flat))
        # sequence cap (schwa) before construction
        word = _limit_long_sequences(word)
        # ISOLATED consonant (word with no vowel at all) before pause:
        # insert the mute vowel @ (center of the vowel triangle).  For a
        # word-final CVC, NO schwa: the reference centralizes the last
        # vowel V via the word-end anchor COEFCEN×ρV (build_anchors,
        # is_word_end) — cf. COVTL reference.
        if not any(_is_vowel_key(t[1]) for t in word if t != 'DOT'):
            word = list(word) + [('S', '@')]
        # word syllables: C.C dot → split; otherwise merge
        word_syls: list[list[str]] = []
        cur_syl: list[str] = []
        toks = [t for t in word if t != 'DOT']
        dots = [i for i, t in enumerate(word) if t == 'DOT']
        # segment indices (excluding dots) and dot positions between them
        si = 0
        dot_set = set()
        seg_positions = []
        for i, t in enumerate(word):
            if t == 'DOT':
                dot_set.add(len(seg_positions))
            else:
                seg_positions.append(i)
        # rebuild: walk the word, split at C.C dots
        prev_key = None
        for i, t in enumerate(word):
            if t == 'DOT':
                nxt = None
                for j in range(i + 1, len(word)):
                    if word[j] != 'DOT':
                        nxt = word[j][1]
                        break
                if prev_key is not None and nxt is not None:
                    if not _is_vowel_key(prev_key) and \
                            not _is_vowel_key(nxt):
                        if cur_syl:
                            word_syls.append(list(cur_syl))
                            cur_syl = []
                continue
            key = t[1]
            cur_syl.append(key)
            prev_key = key
        if cur_syl:
            word_syls.append(list(cur_syl))

        syllables.append([list(s) for s in word_syls])

        # inject into flat + boundaries
        for idx_syl, syl in enumerate(word_syls):
            start = len(flat)
            if idx_syl > 0:
                syl_bounds.add(start)
                prev_segs = word_syls[idx_syl - 1]
                boundary_info.append(
                    (start, prev_segs, list(syl)))
            for key in syl:
                flat.append(('S', key))

    # implicit final pause
    if flat and flat[-1] not in ('GAP', 'PAUSE', 'BREATH'):
        flat.append('GAP')
    return flat, syllables, syl_bounds, boundary_info, word_starts


# ==========================================================================
# Consonant targets + context adjustment (reference)
# ==========================================================================

def _selector_indices(key: str, theta_ctx: float) -> list:
    from .projection import get_selector_list
    sel = get_selector_list(key, theta_ctx)
    if not sel:
        return []
    idx = []
    for name in sel:
        if name in COVTL_PARAMS:
            idx.append(COVTL_PARAMS.index(name))
    return idx


def _c_target(key: str, theta_ctx: float) -> tuple[float, float]:
    from .projection import get_consonant_target
    t = get_consonant_target(key, theta_ctx)
    if t is None:
        return 1.1, np.pi
    return t


def adjust_consonant_theta(key: str, rho: float, theta: float,
                           in_cluster: bool, voy_theta: float,
                           theta_ctx: float):
    """Reference rules (phonology.adjust_consonant_theta) on our targets.

    d/t/g/k follow the reference constants (place + cluster);
    **CC-eligible glides and liquids** (reference _CC_ALIAS):
      - l, n in a cluster → alveolar stop (ρ 1.15, θ 270°) — stop-like
        realization of pL/kN clusters (reference _CC_RHO_OVERRIDE {l,n});
      - j in a cluster → velarized (θ_CC_G 345°, ρ unchanged — alias j→g);
      - w unchanged (labio-velar, opening preserved);
    the other consonants keep their calibrated target (own ρ/θ,
    conditional z_front resolution already done upstream).
    """
    if key in ('d', 't'):
        if in_cluster:
            return (SYL_RHO_STOP, SYL_THETA_CC_D)
        return (SYL_RHO_STOP, SYL_THETA_DENTAL)
    if key in ('g', 'k'):
        if in_cluster:
            return (SYL_RHO_CLUSTER_VELAR, SYL_THETA_CC_G)
        if voy_theta <= np.pi:
            # project-calibrated ρ (max with RHO_STOP): g_vel 1.45 closes
            # the velum (0.000 verified); RHO_STOP 1.2 alone leaves
            # 0.028 cm².
            return (max(SYL_RHO_STOP, rho), SYL_THETA_VELAR)
        return (max(SYL_RHO_CLUSTER_VELAR, rho), SYL_THETA_VELAR_BACK)
    if in_cluster and key in ('l', 'n'):
        # CC-eligible glides/liquids: alveolar stop (reference
        # _CC_RHO_OVERRIDE {l, n} → RHO_STOP + THETA_CC_D, adapted to
        # our calibrated 270° alveolar).
        return (1.15, np.radians(270))
    if in_cluster and key == 'j':
        # glide j: velarized in a cluster (alias j→g, ρ unchanged)
        return (rho, np.radians(345))
    # other consonants: project-calibrated target (own θ_C)
    return (rho, theta)


# ==========================================================================
# Nodes + anchors (port of gesture.py)
# ==========================================================================

def build_nodes(flat, syllables, syl_bounds, boundary_info, word_starts):
    # polar targets by flat position
    syllables_flat = []
    for word in syllables:
        for syl in word:
            syllables_flat.append(list(syl))

    # associate each ('S', key) of flat with its syllable (for context θ)
    nodes: list[SylNode] = []
    polar_by_pos = {}
    for i, tok in enumerate(flat):
        if isinstance(tok, tuple) and tok[0] == 'S':
            key = tok[1]
            nasal = key.endswith('~')
            base = key.rstrip('~')
            if _is_vowel_key(key):
                rho, th = VOWEL_TARGETS[base]
                polar_by_pos[i] = (rho, th, True)
                nodes.append(SylNode('V', base, rho, th, nasal=nasal))
            else:
                rho, th = _c_target(key, 0.0)
                polar_by_pos[i] = (rho, th, False)
                nodes.append(SylNode('C', key, rho, th,
                                     params=_selector_indices(key, th)))
        elif tok == 'PAUSE':
            nodes.append(SylNode('pause', long=True))
        elif tok == 'GAP':
            nodes.append(SylNode('pause', long=False))
        elif tok == 'BREATH':
            nodes.append(SylNode('pause', long=False, breath=True))
        # 'DOT': not represented (pure boundary)

    # clusters: C adjacent to C with no syllable boundary between
    cluster_mask = [False] * len(nodes)
    node_of_flat = {}
    fi = 0
    for i, tok in enumerate(flat):
        if tok == 'DOT':
            continue
        node_of_flat[fi] = i
        fi += 1
    # flat index → node index: 1:1 (DOT skipped here); rebuild:
    nodes_by_flat: dict[int, int] = {}
    ni = 0
    for i, tok in enumerate(flat):
        if tok == 'DOT':
            nodes_by_flat[i] = -1
            continue
        nodes_by_flat[i] = ni
        ni += 1

    for i in range(1, len(flat)):
        if flat[i] == 'DOT' or flat[i - 1] == 'DOT':
            # forced syllable boundary → not a cluster
            continue
        n0, n1 = nodes_by_flat[i - 1], nodes_by_flat[i]
        if n1 in syl_bounds:
            continue
        if (nodes[n0].kind == 'C' and nodes[n1].kind == 'C'):
            cluster_mask[n0] = True
            cluster_mask[n1] = True

    # consonant θ/ρ adjustment (nearest vowel, pauses skipped)
    nv = [-1] * len(nodes)
    pv = [-1] * len(nodes)
    last = -1
    for i, nd in enumerate(nodes):
        if nd.kind == 'V':
            last = i
        pv[i] = last
    last = -1
    for i in range(len(nodes) - 1, -1, -1):
        if nodes[i].kind == 'V':
            last = i
        nv[i] = last

    def nearest_v_theta(i):
        for cand in (nv[i], pv[i]):
            if cand == -1:
                continue
            lo, hi = (min(i, cand), max(i, cand))
            if not any(nodes[j].kind == 'pause' for j in range(lo, hi + 1)):
                return nodes[cand].theta
        return np.pi

    for i, nd in enumerate(nodes):
        if nd.kind != 'C':
            continue
        vth = nearest_v_theta(i)
        # conditional target (g_vel/g_pal, z_front) via the project module
        from .projection import get_consonant_target
        t = get_consonant_target(nd.key, vth)
        rho, th = t if t else (nd.rho, nd.theta)
        rho, th = adjust_consonant_theta(nd.key, rho, th,
                                         cluster_mask[i], vth, vth)
        nd.rho, nd.theta, nd.in_cluster = rho, th, cluster_mask[i]
        # the selector follows the conditional resolution: g_vel (5 params,
        # with TCX) vs g_pal (4 params, without TCX) — cf. cluster review:
        # a selector frozen at θ=0 was driving TCX in a palatal context.
        nd.params = _selector_indices(nd.key, vth)
    return nodes


def build_anchors(nodes, word_starts, boundary_info):
    anchors: list[SylAnchor] = []
    n = len(nodes)
    for i, nd in enumerate(nodes):
        if nd.kind == 'V':
            prev_v = i > 0 and nodes[i - 1].kind == 'V'
            next_v = i < n - 1 and nodes[i + 1].kind == 'V'
            anchors.append(SylAnchor(i=i, kind='V',
                                     pt=[nd.rho, nd.theta],
                                     hold=not prev_v and not next_v))
        elif nd.kind == 'pause':
            anchors.append(SylAnchor(i=i, kind='pause', pt=None,
                                     long=nd.long, breath=nd.breath))

    # word end: COEFCEN·ρ anchor before a pause that follows a consonant
    inserts = []
    for ai, a in enumerate(anchors):
        if a.kind == 'pause' and ai > 0:
            pi_ = a.i
            if pi_ > 0 and nodes[pi_ - 1].kind == 'C':
                rho_v, th_v = np.pi, np.pi
                for j in range(pi_ - 1, -1, -1):
                    if nodes[j].kind == 'pause':
                        break
                    if nodes[j].kind == 'V':
                        rho_v, th_v = nodes[j].rho, nodes[j].theta
                        break
                inserts.append((ai, SylAnchor(
                    i=pi_, kind='V', pt=[SYL_COEFCEN * rho_v, th_v],
                    is_word_end=True)))
    for pos, we in sorted(inserts, key=lambda x: x[0], reverse=True):
        anchors.insert(pos, we)

    # onset of a word starting with a consonant: [0.5, θ_next_vowel]
    inserts = []
    for ws in word_starts:
        if ws < n and nodes[ws].kind == 'C':
            th_v = np.pi
            for j in range(ws, n):
                if nodes[j].kind == 'pause':
                    break
                if nodes[j].kind == 'V':
                    th_v = nodes[j].theta
                    break
            inserts.append((_find_anchor_pos(anchors, ws), SylAnchor(
                i=ws, kind='V', pt=[0.5, th_v], is_vowel_onset=True)))
    for pos, vd in sorted(inserts, key=lambda x: x[0], reverse=True):
        anchors.insert(pos, vd)

    # syllabic onset: weight = (1−prev_boolfin) + COEFCEN·prev_boolfin
    for flat_idx, prev_segs, curr_segs in boundary_info:
        if _is_vowel_key(curr_segs[0]):
            continue
        prev_boolfin = 0 if _is_vowel_key(prev_segs[-1]) else 1
        prev_rho, prev_theta = np.pi, np.pi
        for seg in reversed(prev_segs):
            if _is_vowel_key(seg):
                # nasal keys carry the '~' marker — the polar target is
                # the oral counterpart (nasality is the VO extension).
                prev_rho, prev_theta = VOWEL_TARGETS[seg.rstrip('~')]
                break
        weight = (1 - prev_boolfin) + SYL_COEFCEN * prev_boolfin
        pos = _find_anchor_pos(anchors, flat_idx)
        anchors.insert(pos, SylAnchor(
            i=flat_idx, kind='V', pt=[weight * prev_rho, prev_theta],
            is_vowel_onset=True, is_syl_vowel_onset=True))

    # terminals
    if not anchors or anchors[0].kind != 'synth':
        anchors.insert(0, SylAnchor(i=-1, kind='synth', pt=[0.0, 0.0]))
    anchors.append(SylAnchor(i=n, kind='synth', pt=[0.0, 0.0]))
    return anchors


def _find_anchor_pos(anchors, node_idx):
    pos = 0
    for ai, a in enumerate(anchors):
        if a.i >= node_idx:
            break
        pos = ai + 1
    return pos


# ==========================================================================
# Trajectory (port of trajectory.py)
# ==========================================================================

def _append_plateau(blocks, block_info, pt, D):
    blocks.append(np.tile(compute_P(*pt), (D, 1)))
    block_info.append(SylBlock(n_steps=D, kind='plateau'))


def _append_arc(blocks, pt_dep, pt_arr, D, nu, K, Pexp):
    blocks.append(arc_B(pt_dep, pt_arr, list(range(N_VTL_PARAMS)), D,
                        [-np.pi, 0], 0, nu, K, Pexp))


def _pre_amp_backward_scan(anchors, idx):
    for look in range(idx - 1, -1, -1):
        la = anchors[look]
        if la.kind in ('pause', 'synth'):
            continue
        if la.kind == 'V' and not la.is_vowel_onset:
            return 1.0
        break
    return 0.0


def _amp(cond):
    return 1.0 if cond else 0.0


def _append_decay(blocks, block_info, pt, D, pre_amp):
    if D > 0 and pre_amp > 0.01:
        blocks.append(np.tile(compute_P(*pt), (D, 1)))
        block_info.append(SylBlock(n_steps=D, kind='decay'))


def _append_attack(blocks, block_info, pt, D, post_amp):
    if D > 0 and post_amp > 0.01:
        blocks.append(np.tile(compute_P(*pt), (D, 1)))
        block_info.append(SylBlock(n_steps=D, kind='attack'))


def build_cluster_pval(anchor_dep, anchor_arr, consonants, T, nu, K,
                       Kvoy, Pexp):
    """Cluster sub-arcs: endpoints = SCOPED consonant targets.

    SELECTION VECTOR: global union (cf. reference uniform_params)
    active on ALL (m+1) sub-arcs, with PER-PARAMETER SCOPING of the
    endpoints (fix A, 2026-09-04):

    - for each parameter p and each sub-arc k, the endpoint equals the
      polar target of Cₖ if p ∈ sel(Cₖ), otherwise the value of the
      VOCALIC BACKGROUND (anchor→anchor arc) at that frame;
    - exact C⁰ continuity at sub-arc boundaries: a parameter
      owned by Cₖ arrives at its target and departs from it at Cₖ;
      a non-owned parameter follows the background at both frames
      (jump = 0, versus 2.1 with the global polar projections and
      1.9 with the adjacent unions);
    - non-owned parameters are no longer driven by the (uncalibrated)
      polar projection of consonants whose selector is a
      subset — e.g. b (θ 50°, velar direction) no longer closes the
      velum during its hold;
    - the temporal mixing rk = cos(θ/2)^Pexp is that of the
      reference arcs (ν=−1, K=1000, Pexp=2); m=1 effectively unchanged
      (the union reduces to the selector of the consonant, owner of
      both ends).

    The cap m ≤ 3 (schwa) is guaranteed UPSTREAM by
    ``_limit_long_sequences`` (DOT after the 1st consonant of any
    4+ C sequence, timit_adapter rule), not here.
    """
    m = len(consonants)
    Dtot = (m + 1) * T
    CO = _co_matrix()
    Pval = np.zeros((Dtot, N_VTL_PARAMS))
    bg = arc_B(anchor_dep, anchor_arr, list(range(N_VTL_PARAMS)),
               Dtot, [-np.pi, 0], 0, nu, Kvoy, Pexp)
    Pval[:, :] = bg
    act = sorted(set().union(*(c.params for c in consonants)))
    if not act:
        return Pval
    pts = [[c.rho, c.theta] for c in consonants]
    owned = [set(c.params) for c in consonants]
    for k in range(m + 1):
        dep_owner = k - 1 if k >= 1 else None
        arr_owner = k if k < m else None
        # endpoints per parameter: polar target if owned, otherwise background
        dep_v = bg[k * T].copy() if k > 0 else \
            compute_P(*anchor_dep)
        arr_v = bg[min((k + 1) * T, Dtot - 1)].copy()
        if dep_owner is not None:
            dep_full = compute_P(*pts[dep_owner])
            for p in owned[dep_owner]:
                dep_v[p] = dep_full[p]
        if arr_owner is not None:
            arr_full = compute_P(*pts[arr_owner])
            for p in owned[arr_owner]:
                arr_v[p] = arr_full[p]
        th1 = np.linspace(-np.pi, 0, T + 1)
        th = th1[1:T + 1]
        for t in range(T):
            rk = np.cos(th[t] / 2) ** Pexp
            Pval[k * T + t, act] = (rk * arr_v[act]
                                    + (1 - rk) * dep_v[act])
    return Pval


def _collect_consonants(nodes, start, end):
    out = []
    for k in range(start, end):
        if 0 <= k < len(nodes) and nodes[k].kind == 'C':
            out.append(nodes[k])
    return out


def _has_following_plateau(anchors, idx):
    for fwd in range(idx + 1, len(anchors) - 1):
        fa = anchors[fwd]
        if (fa.hold and fa.kind == 'V' and not fa.is_vowel_onset
                and not fa.is_word_end):
            return True
        if fa.kind in ('pause', 'synth'):
            break
    return False


def _append_background(blocks, block_info, pt_dep, pt_arr, D, nu, K,
                       Pexp):
    """Vocalic background arc, with schwa routing if the middle closes.

    The direct polar arc between distant vowels can close the tract
    mid-transition (superposition of the contributions of the two
    anchors).  If the VV_CLOSURE_PROBE probe is hooked up and measures
    an area < SYL_VV_CLOSURE_THRESH in the central half, the arc is
    routed through the schwa @ as two half-arcs (exact endpoints at
    the junctions; the total time D is preserved, the 'background'
    envelope being constant there is no side effect on the other branches).
    """
    from vtl_synth.core.constants import VOWEL_TARGETS as _VT
    arc = arc_B(pt_dep, pt_arr, list(range(N_VTL_PARAMS)), D,
                [-np.pi, 0], 0, nu, K, Pexp)
    if VV_CLOSURE_PROBE is not None and D >= 4:
        area = VV_CLOSURE_PROBE(arc)
        if area < SYL_VV_CLOSURE_THRESH:
            wp = _vv_waypoint()
            half = D // 2
            leg1 = arc_B(pt_dep, wp, list(range(N_VTL_PARAMS)), half,
                         [-np.pi, 0], 0, nu, K, Pexp)
            leg2 = arc_B(wp, pt_arr, list(range(N_VTL_PARAMS)),
                         D - half, [-np.pi, 0], 0, nu, K, Pexp)
            blocks.append(leg1)
            block_info.append(SylBlock(n_steps=half, kind='background',
                                       vowel_key='@'))
            blocks.append(leg2)
            block_info.append(SylBlock(n_steps=D - half, kind='background'))
            return
    blocks.append(arc)
    block_info.append(SylBlock(n_steps=D, kind='background'))


def build_global_pval(nodes, anchors, T_cons, T_voy, T_pause_short,
                      T_pause_long, nu=SYL_NU, K=SYL_K, Kvoy=SYL_K,
                      Pexp=SYL_PEXP, T_pause_breath=None):
    """T_pause_breath: duration (steps) of the '%' breath pause
    (expressive prosody, v1.0.8). None → T_pause_short. The breath
    pauses only occur when the phrase string contains '%' markers —
    without them this function is bit-identical to the previous
    behaviour."""
    if T_pause_breath is None:
        T_pause_breath = T_pause_short
    blocks: list[np.ndarray] = []
    block_info: list[SylBlock] = []
    n = len(nodes)
    pending_pt = None
    pending_long = False
    pending_breath = False

    def _pause_steps() -> int:
        if pending_breath:
            return T_pause_breath
        return T_pause_long if pending_long else T_pause_short

    for idx in range(len(anchors) - 1):
        A, B = anchors[idx], anchors[idx + 1]
        a_term = A.kind in ('pause', 'synth')
        b_term = B.kind in ('pause', 'synth')
        a_vonset = A.is_vowel_onset
        b_vonset = B.is_vowel_onset
        a_V = A.kind == 'V' and not a_vonset
        b_V = B.kind == 'V' and not b_vonset

        if A.hold and A.kind == 'V' and not a_vonset:
            blocks.append(np.tile(compute_P(*A.pt), (T_voy, 1)))
            _vi = min(max(A.i, 0), len(nodes) - 1)
            block_info.append(SylBlock(n_steps=T_voy, kind='plateau',
                                       vowel_key=nodes[_vi].key.rstrip('~'),
                                       nasal=nodes[_vi].nasal))

        search_start = A.i if a_vonset else A.i + 1
        consonants = _collect_consonants(nodes, search_start, B.i)
        m = len(consonants)

        if a_term and b_term:
            if pending_pt is not None and B.kind == 'synth':
                T_use = _pause_steps()
                _append_arc(blocks, pending_pt, B.pt or [0.0, 0.0], T_use,
                            nu, K, Pexp)
                pre = _pre_amp_backward_scan(anchors, idx)
                block_info.append(SylBlock(n_steps=T_use, kind='terminal',
                                           pre_amp=pre,
                                           breath=pending_breath))
                pending_pt = None
                pending_breath = False
            elif B.kind == 'pause':
                pending_pt = A.pt or [0.0, 0.0]
                pending_long = B.long
                pending_breath = B.breath
            continue

        if a_term:
            was_pending = pending_pt is not None
            was_breath = pending_breath
            if pending_pt is not None:
                pt_A = pending_pt
                T_use = _pause_steps()
                pending_pt = None
                pending_breath = False
            else:
                pt_A = A.pt or [0.0, 0.0]
                T_use = T_pause_short
            pt_B = B.pt or [0.0, 0.0]
            if m == 0:
                _append_arc(blocks, pt_A, pt_B, T_use, nu, K, Pexp)
                post = _amp(B.kind == 'V')
                pre = _pre_amp_backward_scan(anchors, idx) if was_pending \
                    else 0.0
                block_info.append(SylBlock(
                    n_steps=T_use, kind='initial', long=False,
                    pre_amp=pre, post_amp=post, breath=was_breath))
                if post > 0.01 and not b_vonset:
                    _append_attack(blocks, block_info, pt_B, T_cons, post)
            else:
                blocks.append(build_cluster_pval(pt_A, pt_B, consonants,
                                                 T_cons, nu, K, Kvoy,
                                                 Pexp))
                block_info.append(SylBlock(
                    n_steps=(len(consonants) + 1) * T_cons, kind='cluster',
                    n_cons=len(consonants),
                    cons_tokens=['C'] * len(consonants), cons_keys=[c.key for c in consonants],
                    pre_token='O',
                    post_token=('y' if B.is_syl_vowel_onset
                                else ('V' if B.kind == 'V' else 'O')),
                    has_following_plateau=_has_following_plateau(anchors,
                                                                 idx)))
            continue

        if b_term:
            if m > 0:
                blocks.append(build_cluster_pval(
                    A.pt or [0.0, 0.0], B.pt or [0.0, 0.0], consonants,
                    T_cons, nu, K, Kvoy, Pexp))
                block_info.append(SylBlock(
                    n_steps=(len(consonants) + 1) * T_cons, kind='cluster',
                    n_cons=len(consonants),
                    cons_tokens=['C'] * len(consonants), cons_keys=[c.key for c in consonants],
                    pre_token=('y' if A.is_syl_vowel_onset
                               else ('O' if a_vonset
                                     else ('V' if a_V else 'O'))),
                    post_token='F' if B.kind == 'synth' else 'O'))
            elif A.kind == 'V' and B.kind == 'pause':
                _append_decay(blocks, block_info, A.pt or [0.0, 0.0],
                              T_cons, pre_amp=1.0)
            if B.kind == 'pause':
                pending_pt = A.pt or [0.0, 0.0]
                pending_long = B.long
                pending_breath = B.breath
            continue

        if pending_pt is not None:
            T_use = _pause_steps()
            _append_arc(blocks, pending_pt, B.pt or [0.0, 0.0], T_use,
                        nu, K, Pexp)
            pre_a = _amp(a_V)
            block_info.append(SylBlock(n_steps=T_use, kind='pause',
                                       long=pending_long, pre_amp=pre_a,
                                       breath=pending_breath))
            _append_decay(blocks, block_info, A.pt or [0.0, 0.0], T_cons,
                          pre_amp=pre_a)
            _append_attack(blocks, block_info, B.pt or [0.0, 0.0], T_cons,
                           post_amp=_amp(b_V))
            pending_pt = None
            pending_breath = False

        if m == 0:
            if b_vonset and not b_V:
                continue
            _append_background(blocks, block_info,
                               A.pt or [0.0, 0.0], B.pt or [0.0, 0.0],
                               2 * T_voy, nu, Kvoy, Pexp)
        else:
            blocks.append(build_cluster_pval(
                A.pt or [0.0, 0.0], B.pt or [0.0, 0.0], consonants,
                T_cons, nu, K, Kvoy, Pexp))
            _pre = ('V' if a_V else ('y' if A.is_syl_vowel_onset
                                     else 'O'))
            _post = ('V' if b_V else ('y' if B.is_syl_vowel_onset
                                      else 'O'))
            block_info.append(SylBlock(
                n_steps=(len(consonants) + 1) * T_cons, kind='cluster',
                n_cons=len(consonants),
                cons_tokens=['C'] * len(consonants), cons_keys=[c.key for c in consonants],
                pre_token=_pre, post_token=_post,
                has_following_plateau=_has_following_plateau(anchors,
                                                             idx)))

    if anchors:
        Blast = anchors[-1]
        if Blast.hold and Blast.kind == 'V':
            blocks.append(np.tile(compute_P(*Blast.pt), (T_voy, 1)))
            _vi = min(max(Blast.i, 0), len(nodes) - 1)
            block_info.append(SylBlock(n_steps=T_voy, kind='plateau',
                                       vowel_key=nodes[_vi].key.rstrip('~'),
                                       nasal=nodes[_vi].nasal))

    if pending_pt is not None and anchors:
        T_use = _pause_steps()
        _append_arc(blocks, pending_pt, anchors[-1].pt or [0.0, 0.0],
                    T_use, nu, K, Pexp)
        block_info.append(SylBlock(n_steps=T_use, kind='terminal',
                                   breath=pending_breath))
        pending_pt = None
        pending_breath = False

    Pval = np.vstack(blocks) if blocks else \
        np.zeros((T_cons, N_VTL_PARAMS))
    return Pval, block_info


# ==========================================================================
# Driver: phrase → (Pval 100 Hz, block_info)
# ==========================================================================

# Last build state (phrase, flat, nodes, anchors, block_info) — set by
# build_phrase_pval, read back by the expressive-prosody layer
# (utils/prosody_f0.py) to locate chunks/plateaus in time without
# changing the return signature. Same pattern as
# continuous.get_last_pval_state().
_LAST_BUILD: dict | None = None


def get_last_build():
    """State of the last build_phrase_pval call (or None).

    dict(phrase=..., flat=..., nodes=..., anchors=..., block_info=...)
    — frames of block_info/n_steps are @100 Hz (TARGET_SR).
    """
    return _LAST_BUILD


def build_phrase_pval(phrase: str,
                      cons_ms: float = 60.0,
                      vowel_ms: float = 60.0,
                      pause_short_ms: float = 200.0,
                      pause_long_ms: float = 320.0,
                      pause_breath_ms: float | None = None,
                      t_cons: int | None = None,
                      t_voy: int | None = None):
    """Phrase → (Pval (n,15) @100 Hz, blocks, nodes, anchors).

    T_cons: steps per consonant sub-arc = consonant duration / 10 ms
    (16 steps = 160 ms derived by default; direct override possible).
    T_voy : steps of the vocalic plateau; the transition arc equals 2·T_voy
    (synchronized branches: 2·T_cons = 2·T_voy ⇔ T_cons = T_voy in steps).
    t_cons / t_voy: direct override in steps (e.g. 16 = 160 ms).
    pause_breath_ms: duration of the '%' breath pause (expressive
    prosody, v1.0.8); None → = pause_short_ms (bit-identical to the
    pre-1.0.8 behaviour for phrases without '%').
    """
    global _LAST_BUILD
    flat, syllables, syl_bounds, boundary_info, word_starts = \
        build_flat(phrase)
    nodes = build_nodes(flat, syllables, syl_bounds, boundary_info,
                        word_starts)
    anchors = build_anchors(nodes, word_starts, boundary_info)

    T_cons = t_cons if t_cons is not None else \
        max(1, round(cons_ms / 10.0))
    T_voy = t_voy if t_voy is not None else \
        max(1, round(vowel_ms / 10.0 / 3.0))
    T_pause_short = max(1, round(pause_short_ms / 10.0))
    T_pause_long = max(1, round(pause_long_ms / 10.0))
    T_pause_breath = (max(1, round(pause_breath_ms / 10.0))
                      if pause_breath_ms is not None else None)

    Pval, blocks = build_global_pval(nodes, anchors, T_cons, T_voy,
                                     T_pause_short, T_pause_long,
                                     T_pause_breath=T_pause_breath)
    _LAST_BUILD = {
        'phrase': phrase,
        'flat': flat,
        'nodes': nodes,
        'anchors': anchors,
        'block_info': blocks,
        't_pause': (T_pause_short, T_pause_long, T_pause_breath),
    }
    return Pval, blocks, nodes, anchors
