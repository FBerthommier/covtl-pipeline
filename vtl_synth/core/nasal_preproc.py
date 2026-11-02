# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
nasal_preproc.py — nasality/formant port (V1V2 pre-processing layer)
====================================================================
Orthogonalized factoring of nasality for linked V1.V2 hiatuses
(V1V2 audit / AUDIT.md §6 — the prescribed "non-perturbing" variant
for the motor correction).

Principle
---------
1. The elaboration of the parametric space by ``syltraj`` is left
   INTACT. It is already built on the oral basis: a nasal vowel
   shares the polar target of its oral counterpart
   (``syltraj.build_nodes``: ``base = key.rstrip('~')`` — nasality
   only enters there as a flag). The background arc of the hiatus
   (``background``, 2·T_voy) IS the base diphthong transition.
2. This pre-processing layer oralizes ONLY the nasal vowels that are
   members of a hiatus (adjacent vowel sequence of
   length ≥ 2): the ``syltraj`` engine receives a purely
   oral string for those positions, and nasality is captured as an
   EVENT (vowel membership rule + oral target).
3. Nasality is re-injected downstream in the orthogonal control
   space of the velar port that already exists (``VO`` extension of
   ``build_phrase_tract``: target ``VO_NASALIZED_VOWEL`` = 0.5, symmetric
   ramps 20%) and is shaped by the existing associated timer
   (first-order anti-click smoothing, τ = 20 ms). No other channel
   is modified: F1..F3/tract parameters, E envelope, voicing V,
   glottal source remain those of the oral string.

Non-perturbation
----------------
* without a nasal vowel in hiatus, the motor string is IDENTICAL to
  the input (verified tokenizer round-trip, otherwise conservative
  fallback) → bit-identical outputs;
* nasal vowels outside a hiatus (held plateaus) keep the existing
  motor path (``nasal`` flag of ``plateau`` blocks);
* ``syltraj.py`` is not modified; any regression of the
  runs↔blocks mapping is detected and cleanly disabled
  (fallback to the previous behavior, with a warning).

The module-level state scheme (``get_last_nasal_plan``) follows the
repository pattern (``syltraj.get_last_build``,
``continuous.get_last_pval_state``).
"""
from __future__ import annotations

import warnings

import numpy as np

# ---------------------------------------------------------------------------
# State of the last pass (get_last_build pattern)
# ---------------------------------------------------------------------------

_LAST_PLAN: dict | None = None


def get_last_nasal_plan():
    """Plan of the last run of :func:`split_nasal_hiatus`.

    dict(original=..., motor=..., nodes_view=..., runs=..., events=...,
         intervals=...) — ``nodes_view`` reflects the ORIGINAL string
     (``nasal`` flags true), unlike the nodes of
     ``syltraj.get_last_build()`` which see the oralized string.
    ``intervals`` is filled by ``build_phrase_tract`` at VO re-injection
    time (list of (t0, t1, keys) in steps @100 Hz).
    """
    return _LAST_PLAN


# ---------------------------------------------------------------------------
# Node view of the string (same tokenizer as the engine, unmodified)
# ---------------------------------------------------------------------------

def _node_view(phrase: str):
    """String → (tokens, node view kind/key/nasal).

    Reproduces the view of ``syltraj.build_nodes``: '.' (DOT) entries are
    not nodes, GAP/PAUSE/BREATH are pauses. The insertion of '@' for
    vowel-less words (build_flat) is not reproduced: '@' is never
    adjacent to another vowel, so it does not affect
    vowel sequences (runs).
    """
    from .syltraj import _normalize_word, _is_vowel_key, tokenize_phrase
    norm = ' '.join(_normalize_word(w) for w in phrase.strip().split())
    tokens = tokenize_phrase(norm)
    nodes: list[dict] = []
    for tok in tokens:
        if tok == 'DOT':
            continue
        if isinstance(tok, tuple) and tok[0] == 'S':
            key = tok[1]
            if _is_vowel_key(key):
                nodes.append({'kind': 'V', 'key': key.rstrip('~'),
                              'nasal': key.endswith('~')})
            else:
                nodes.append({'kind': 'C', 'key': key, 'nasal': False})
        else:                       # GAP / PAUSE / BREATH
            nodes.append({'kind': 'pause', 'key': '', 'nasal': False})
    return tokens, nodes


def _vowel_runs(nodes: list[dict]) -> list[list[dict]]:
    """Maximal sequences of adjacent vowels (length ≥ 2)."""
    runs, cur = [], []
    for nd in nodes:
        if nd['kind'] == 'V':
            cur.append(nd)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def _rebuild_phrase(tokens: list, strip_marks: set) -> str:
    """Rebuilds the phrase from the tokens (stable round-trip).

    ``strip_marks``: token indices ('S', …) whose '~' marker
    must be removed (oralization). Separators are re-emitted
    unchanged: GAP → space, PAUSE → '|', BREATH → '%', DOT → '.'.
    """
    out: list[str] = []
    for i, tok in enumerate(tokens):
        if tok == 'GAP':
            out.append(' ')
        elif tok == 'PAUSE':
            out.append('|')
        elif tok == 'BREATH':
            out.append('%')
        elif tok == 'DOT':
            out.append('.')
        else:
            key = tok[1]
            if i in strip_marks:
                key = key.rstrip('~')
            out.append(key)
    return ''.join(out).strip()


# ---------------------------------------------------------------------------
# Pre-processing layer: nasality / oral base split
# ---------------------------------------------------------------------------

def split_nasal_hiatus(phrase: str) -> tuple[str, dict]:
    """Oralizes nasal vowels that are members of a hiatus, capturing nasality.

    Returns
    -------
    (motor_phrase, plan)
        ``motor_phrase``: string for ``syltraj`` (identical to
        ``phrase`` outside nasal hiatuses);
        ``plan``: nasality events for VO re-injection
        (see :func:`get_last_nasal_plan`).

    Conservative fallback: if the tokenizer round-trip does not
    reproduce exactly the expected string, the ORIGINAL string is
    returned without events (previous engine behavior) — the
    correction can never produce an unexpected string.
    """
    global _LAST_PLAN
    tokens, nodes = _node_view(phrase)
    runs = _vowel_runs(nodes)

    # token indices to oralize: nasal vowels belonging to a
    # run (hiatus members). Held nasal vowels (outside a run)
    # keep the existing engine path (plateau + nasal flag).
    node_tok: list[int] = []      # node -> token index in `tokens`
    for ti, tok in enumerate(tokens):
        if tok == 'DOT':
            continue              # '.' entries are not nodes
        node_tok.append(ti)       # (FULL index, '.' included)
    strip_marks: set[int] = set()
    runs_events: list[list[dict]] = []
    idx = 0
    for run in runs:
        # position of the run's first node in the node view (runs
        # are consecutive slices of `nodes`)
        while idx < len(nodes) and nodes[idx] is not run[0]:
            idx += 1
        members = []
        for j, member in enumerate(run):
            members.append({'key': member['key'],
                            'nasal': member['nasal']})
            if member['nasal']:
                tok_i = node_tok[idx + j]
                if tok_i is not None:
                    strip_marks.add(tok_i)
        runs_events.append(members)
        idx += len(run)
    events = [{'run': ri, 'member': j, 'key': m['key']}
              for ri, run in enumerate(runs_events)
              for j, m in enumerate(run) if m['nasal']]

    motor = _rebuild_phrase(tokens, strip_marks) if strip_marks else \
        ' '.join(_norm_word(w) for w in phrase.strip().split())
    # (without oralization, the returned string is the normalized
    # word-by-word form — exactly the one build_phrase_pval computes
    # itself before tokenization: unchanged outputs)

    plan = {
        'original': phrase,
        'motor': motor,
        'nodes_view': nodes,
        'runs': runs_events,
        'events': events,
        'intervals': None,
        'fallback': False,
    }

    if strip_marks:
        # round-trip: the engine must see exactly the expected
        # tokens (originals, with '~' removed at marked positions)
        expected = []
        for i, tok in enumerate(tokens):
            if isinstance(tok, tuple) and tok[0] == 'S' and i in strip_marks:
                expected.append(('S', tok[1].rstrip('~'), False))
            else:
                expected.append(tok)
        try:
            _, rt_nodes = _node_view(motor)
            rt_tokens = _tokenize(motor)
            ok = (rt_tokens == expected)
        except Exception:                                    # noqa: BLE001
            ok = False
        if not ok:
            warnings.warn(
                'nasal_preproc: tokenizer round-trip failed '
                f'({phrase!r} → {motor!r}) — falling back to the '
                'original string (hiatus nasality not re-injected).',
                stacklevel=2)
            plan['motor'] = ' '.join(_norm_word(w)
                                     for w in phrase.strip().split())
            plan['events'] = []
            plan['fallback'] = True
    _LAST_PLAN = plan
    return plan['motor'], plan


def _norm_word(w: str) -> str:
    from .syltraj import _normalize_word
    return _normalize_word(w)


def _tokenize(phrase: str) -> list:
    from .syltraj import tokenize_phrase
    norm = ' '.join(_norm_word(w) for w in phrase.strip().split())
    return tokenize_phrase(norm)


# ---------------------------------------------------------------------------
# Temporal localization: runs ↔ background block groups
# ---------------------------------------------------------------------------

def _background_groups(block_info) -> list[tuple[int, int]]:
    """Groups of consecutive 'background' blocks → (start, total) steps."""
    groups: list[tuple[int, int]] = []
    off, start, total, inside = 0, 0, 0, False
    for b in block_info:
        if getattr(b, 'kind', '') == 'background':
            if not inside:
                start, total, inside = off, 0, True
            total += int(b.n_steps)
        elif inside:
            groups.append((start, total))
            inside = False
        off += int(b.n_steps)
    if inside:
        groups.append((start, total))
    return groups


def nasal_hiatus_intervals(block_info, plan: dict,
                           t_voy: int | None = None) -> list[tuple[int, int, str]]:
    """Nasality events → VO intervals (steps @100 Hz).

    Structural mapping (verified, otherwise fallback): the g-th vowel
    run (length k ≥ 2) ↔ the g-th group of consecutive background
    blocks, totaling (k−1)·2·T_voy steps — each internal pair of the
    run emits exactly one 2·T_voy background arc (a schwa may be split
    into two blocks; the total is preserved). Member j of the run
    owns the slot [j·T, (j+1)·T) as the first member of
    pair j, extended by the slot [(2j−1)·T, 2j·T) as the
    second member of pair j−1 (middle vowels of VVV runs
    thus get 2·T_voy, matching the time allotted by the
    engine). Adjacent nasal intervals are MERGED: the nasal/oral
    toggle must only occur at true nasal↔oral boundaries
    (e.g. 9~.a~: velum open from start to end).
    """
    runs = plan.get('runs') or []
    if not any(m.get('nasal') for run in runs for m in run):
        return []
    groups = _background_groups(block_info)
    if len(groups) != len(runs):
        warnings.warn(
            f'nasal_preproc: {len(runs)} vowel run(s) but '
            f'{len(groups)} background group(s) — mapping '
            'unverified, hiatus nasality not re-injected.',
            stacklevel=2)
        return []

    # effective T_voy: direct parameter, else plateaus, else derivation
    cands: list[int] = []
    if t_voy is not None:
        cands.append(int(t_voy))
    plateaus = [int(b.n_steps) for b in block_info
                if getattr(b, 'kind', '') == 'plateau']
    if plateaus:
        cands.append(plateaus[0])
    for (g0, gt), run in zip(groups, runs):
        if len(run) >= 2:
            cands.append(gt // (2 * (len(run) - 1)))
    if not cands:
        warnings.warn('nasal_preproc: cannot determine T_voy — '
                      'hiatus nasality not re-injected.', stacklevel=2)
        return []
    T = cands[0]
    if any(c != T for c in cands):
        warnings.warn(
            f'nasal_preproc: inconsistent T_voy {sorted(set(cands))} — '
            'hiatus nasality not re-injected.', stacklevel=2)
        return []

    raw: list[tuple[int, int, str]] = []
    for (g0, gt), run in zip(groups, runs):
        k = len(run)
        for j, m in enumerate(run):
            if not m.get('nasal'):
                continue
            t0 = g0 + (0 if j == 0 else (2 * j - 1) * T)
            t1 = g0 + (gt if j == k - 1 else (2 * j + 1) * T)
            raw.append((t0, t1, m['key']))
    raw.sort(key=lambda x: (x[0], x[1]))

    merged: list[list] = []
    for t0, t1, key in raw:
        if merged and t0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], t1)
            merged[-1][2] = merged[-1][2] + '+' + key
        else:
            merged.append([t0, t1, key])
    return [(a, b, c) for a, b, c in merged]


# ---------------------------------------------------------------------------
# VO ramp (same shape as the plateau path of build_phrase_tract)
# ---------------------------------------------------------------------------

def vo_nasal_segment(n: int, target: float, baseline: float = -0.1,
                     sr: int = 100) -> np.ndarray:
    """Nasalized VO segment: held target + 20% ramps (max 40 ms).

    Exactly replicates the shape of the existing nasal plateau
    path (build_phrase_tract, step 3b): symmetric ramps
    min(max(2, 0.04·sr), n//4), anchored on the closed velar
    baseline (−0.1). The τ = 20 ms smoothing of build_phrase_tract
    (existing timer) applies downstream, unmodified.
    """
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    ramp = min(max(2, int(0.04 * sr)), max(1, n // 4))
    seg = np.full(n, float(target), dtype=np.float64)
    if ramp > 0:
        seg[:ramp] = np.linspace(baseline, target, ramp)
        seg[-ramp:] = np.linspace(target, baseline, ramp)
    return seg
