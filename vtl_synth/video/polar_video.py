# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
polar_video.py
==============
Dynamic polar figure + dual-panel MP4 (vocal tract | polar figure) — v3.

Chain (mirrors the pipeline of ``build_phrase_tract``, engine 'syl'):

  phrase (internal notation)
    → ``syltraj.build_phrase_pval`` re-run with the SAME parameters
      (same normalization, same t_cons / t_voy / pauses ⇒ same 100 Hz
      block timing as the synthesis), with the block helpers of
      ``build_global_pval`` instrumented (temporary monkeypatching,
      technique already used by the v1 of this module) so that each
      block of ``block_info`` is recorded with the polar endpoints the
      engine actually drives toward: anchor pair (or stationary point)
      for the vocalic blocks, anchor pair + consonant node targets
      (rho, theta) for the cluster blocks
    → **direct reconstruction of the two branches in the complex
      plane** from these engine points with ``polar.polar_arc`` /
      ``polar.stationary_point`` (Berthommier v15g geometry, display
      curvature K = K_VOWEL_DEFAULT = 30, nu = +1 vocalic / −1
      consonantal — a deliberate visualization choice: the geometry is
      that of the reference model, not that of the quasi-rectilinear
      SYL_K = 1000 parameter arcs of the syl engine):
        · vocalic branch z_v (RED): always active — anchor-to-anchor
          background arcs + vowel plateaus; during a cluster the
          background keeps flowing from anchor to anchor underneath
          (cf. the ``bg`` of ``build_cluster_pval``);
        · consonantal branch z_c (BLUE): cluster blocks only —
          sub-arcs departure anchor → C₁ → ⋯ → C_m → arrival anchor,
          peaking exactly on the consonant node targets.
      The two branches are simultaneous and dissociated during the
      clusters (superposition model of Berthommier), each with its own
      trail and current position.
    → intermediate **.polar** file (JSON, self-documented, version 3):
      100 Hz trajectories of BOTH branches (null while a branch is
      inactive) + phoneme targets + per-phoneme timing
    → 25 Hz video: left panel = existing VTL sagittal tract view,
      right panel = the polar figure (trigonometric orientation:
      theta = 0 East, counter-clockwise), vocalic branch in RED,
      consonantal branch in BLUE, slightly fading trails, inventory
      dots, transient phonetic labels in the internal input notation.

The .polar file is the single source of the polar figure: the video
never reads the .tract for it.

``polar_from_pval`` (the v2 exact least-squares inversion of the Pval
parameter frames) is kept below as a **diagnostic only**: the blended
parameter frames are off-manifold during the clusters, so the single
inverted path zigzags and the two branches are not dissociated — which
is why v3 reconstructs from the engine's polar points instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

POLAR_SR = 100          # Hz, native sampling of the .polar trajectories
POLAR_VERSION = 3
STEP_MS = 10.0          # 1 gesture step = 10 ms @ 100 Hz

# Display curvature: the reference-model geometry (K_VOWEL_DEFAULT =
# 30, Berthommier v15g) gives visibly curved arcs, while the engine
# drives the parameters with SYL_K = 1000 (quasi-rectilinear in the
# z-plane).  nu = +1 bows the vocalic arcs one way, −1 the consonantal
# sub-arcs the other way, as in the reference CV superposition.
K_DISPLAY = 30.0
NU_VOCALIC = 1
NU_CONSONANTAL = -1
ORIENTATION = 'inverse'     # polar_arc sweep giving dep → arr


# --------------------------------------------------------------------------
# Diagnostic: exact inversion of the real Pval back to polar coordinates
# (v2 rendering path — the two branches are NOT dissociated by it)
# --------------------------------------------------------------------------


def polar_from_pval(Pval: np.ndarray, n_theta: int = 1441,
                    cols=None) -> np.ndarray:
    """(n, 15) COVTL parameter frames → (n, 2) polar (rho, theta).

    Diagnostic tool (not on the v3 rendering path): least-squares fit
    of the Berthommier polar projection
    ``P(rho, theta) = CO[:,1] + rho*CO[:,0]*cos(CO[:,2] - theta)``
    on each parameter frame.  ``cols`` restricts the fit to a subset
    of parameters (for cluster frames: the union of the consonant-owned
    selectors).

    The projection only depends on theta through cos(c2 - theta), so
    (rho, theta) and (-rho, theta + pi) give the SAME parameter frame:
    the LS score is exactly pi-periodic.  The search therefore runs
    over a pi-wide theta grid with a SIGNED closed-form rho, and the
    canonical solution (rho >= 0, theta in (-pi, pi]) is restored
    afterwards — no tie-breaking luck involved.
    """
    from vtl_synth.core.constants import CO

    CO = np.asarray(CO, dtype=float)
    c0, c1, c2 = CO[:, 0], CO[:, 1], CO[:, 2]
    if cols is None:
        cols = np.arange(len(c0))
    cols = np.asarray(cols, dtype=int)
    y = Pval[:, cols] - c1[cols]                   # (n, P)
    theta_grid = np.linspace(-np.pi / 2.0, np.pi / 2.0, n_theta)

    # w[p, t] = c0[p] * cos(c2[p] - theta): (P, T)
    w = c0[cols][:, None] * np.cos(c2[cols][:, None]
                                   - theta_grid[None, :])
    ww = np.sum(w * w, axis=0)                     # (T,)
    yw = y @ w                                     # (n, T)
    # RSS(theta) = ||y||^2 - (y.w)^2 / ||w||^2  → argmin = argmax (yw)^2/ww
    score = yw * yw / ww
    j = np.argmax(score, axis=1)                   # (n,)

    # parabolic refinement around the grid optimum
    jm = np.clip(j - 1, 0, n_theta - 1)
    jp = np.clip(j + 1, 0, n_theta - 1)
    ym, y0, yp = yw[np.arange(len(j)), jm], \
        yw[np.arange(len(j)), j], yw[np.arange(len(j)), jp]
    wm, w0, wp = ww[jm], ww[j], ww[jp]
    sm, s0, sp = ym * ym / wm, y0 * y0 / w0, yp * yp / wp
    denom = sm - 2.0 * s0 + sp
    delta = np.divide(0.5 * (sm - sp), denom,
                      out=np.zeros_like(denom), where=np.abs(denom) > 1e-12)
    delta = np.clip(delta, -0.5, 0.5)
    step = theta_grid[1] - theta_grid[0]
    theta = theta_grid[j] + delta * step

    # closed-form SIGNED rho at the refined theta, then canonicalize
    wt = c0[cols][:, None] * np.cos(c2[cols][:, None]
                                    - theta[None, :])         # (P, n)
    rho = np.sum(y * wt.T, axis=1) / np.sum(wt * wt, axis=0)
    flip = rho < 0.0
    rho = np.where(flip, -rho, rho)
    theta = np.where(flip, theta + np.pi, theta)
    theta = (theta + np.pi) % (2.0 * np.pi) - np.pi   # → (-pi, pi]

    out = np.column_stack([rho, theta])
    out[~np.isfinite(out)] = 0.0
    return out


# --------------------------------------------------------------------------
# .polar building: instrumented re-run of the syl engine
# --------------------------------------------------------------------------


def _normalize_phrase(phrase: str) -> str:
    """Same normalization chain as build_phrase_tract (engine 'syl')."""
    from vtl_synth.core.syltraj import _normalize_word as _syl_norm
    from vtl_synth.core.continuous import _normalize_ipa
    return _normalize_ipa(_syl_norm(phrase))


def _recorded_build_pval(phrase: str, t_cons: int, t_voy: int,
                         pause_short_ms: float, pause_long_ms: float):
    """Instrumented ``syl.build_phrase_pval`` → (block_info, queues).

    The helpers of ``build_global_pval`` that carry the polar geometry
    (``_append_arc``, ``_append_background``, ``_append_decay``,
    ``_append_attack``, ``build_cluster_pval``) are temporarily
    monkeypatched (technique already used by the v1 of this module) to
    record, per appended block and in ``block_info`` order, the polar
    points the engine drives toward:

      'arc'     : (dep, arr, n)   pause / initial / terminal arcs
      'bg'      : (dep, arr, n)   background arcs (1 or 2 per call:
                                  the schwa routing of closing VV arcs
                                  appends two blocks dep→@ then @→arr)
      'hold'    : (pt, n)         decay / attack stationary holds
                                  (only when the engine really appends)
      'cluster' : (dep, arr, targets, T)  anchor pair + [(rho, theta)]
                                  of the cluster consonant NODES
                                  (context-adjusted targets)

    Plateau blocks are appended INLINE by ``build_global_pval``
    (``_append_plateau`` is never called there): they are rebuilt by
    the caller from ``VOWEL_TARGETS[vowel_key]``.
    """
    import vtl_synth.core.syltraj as syl

    q_arc: list = []
    q_bg: list = []
    q_hold: list = []
    q_cluster: list = []

    orig = {name: getattr(syl, name) for name in
            ('_append_arc', '_append_background', '_append_decay',
             '_append_attack', 'build_cluster_pval')}

    def _pt(p):
        return [float(p[0]), float(p[1])]

    def arc(blocks, pt_dep, pt_arr, D, nu, K, Pexp):
        q_arc.append((_pt(pt_dep), _pt(pt_arr), int(D)))
        return orig['_append_arc'](blocks, pt_dep, pt_arr, D, nu, K, Pexp)

    def background(blocks, block_info, pt_dep, pt_arr, D, nu, K, Pexp):
        n0 = len(block_info)
        orig['_append_background'](blocks, block_info, pt_dep, pt_arr,
                                   D, nu, K, Pexp)
        added = block_info[n0:]
        if len(added) == 2:      # schwa routing: dep → @ → arr
            wp = syl._vv_waypoint()
            q_bg.append((_pt(pt_dep), _pt(wp), added[0].n_steps))
            q_bg.append((_pt(wp), _pt(pt_arr), added[1].n_steps))
        else:
            q_bg.append((_pt(pt_dep), _pt(pt_arr), int(D)))

    def decay(blocks, block_info, pt, D, pre_amp):
        n0 = len(block_info)
        orig['_append_decay'](blocks, block_info, pt, D, pre_amp)
        if len(block_info) > n0:
            q_hold.append((_pt(pt), int(D)))

    def attack(blocks, block_info, pt, D, post_amp):
        n0 = len(block_info)
        orig['_append_attack'](blocks, block_info, pt, D, post_amp)
        if len(block_info) > n0:
            q_hold.append((_pt(pt), int(D)))

    def cluster(anchor_dep, anchor_arr, consonants, T, nu, K, Kvoy, Pexp):
        q_cluster.append((_pt(anchor_dep), _pt(anchor_arr),
                          [[float(c.rho), float(c.theta)]
                           for c in consonants], int(T)))
        return orig['build_cluster_pval'](anchor_dep, anchor_arr,
                                          consonants, T, nu, K, Kvoy,
                                          Pexp)

    try:
        setattr(syl, '_append_arc', arc)
        setattr(syl, '_append_background', background)
        setattr(syl, '_append_decay', decay)
        setattr(syl, '_append_attack', attack)
        setattr(syl, 'build_cluster_pval', cluster)
        _, block_info, _, _ = syl.build_phrase_pval(
            phrase, t_cons=t_cons, t_voy=t_voy,
            pause_short_ms=pause_short_ms, pause_long_ms=pause_long_ms)
    finally:
        for name, fn in orig.items():
            setattr(syl, name, fn)

    return block_info, dict(arc=q_arc, bg=q_bg, hold=q_hold,
                            cluster=q_cluster)


def build_phrase_polar(phrase: str,
                       t_cons: int,
                       t_voy: int,
                       pause_short_ms: float,
                       pause_long_ms: float) -> dict:
    """One phrase → .polar dict (two branch trajectories 100 Hz + timing).

    The phrase is re-run through the instrumented
    ``syltraj.build_phrase_pval`` with the same parameters as the
    synthesis, so the block timing and hence the phoneme onsets /
    offsets are identical to the .tract timeline (1 step = 10 ms;
    .tract frame @400 Hz = 4 steps).

    Branch reconstruction (one pass over ``block_info``, aligned 1:1
    with the recorded events, total = n_steps of the .tract / 4):

      plateau                          z_v = stationary(VOWEL_TARGETS)
      background / pause / initial /
      terminal                         z_v = arc(dep, arr, K=30, nu=+1)
      decay / attack                   z_v = stationary(anchor pt)
      cluster (n = (m+1)·T)            z_v = arc(dep_anchor, arr_anchor,
                                        n, K=30, nu=+1)  — the vocalic
                                        background keeps flowing;
                                       z_c = sub-arcs dep → C₁ → ⋯ →
                                        C_m → arr, T steps each,
                                        K=30, nu=−1 (blue), peaking
                                        exactly on the node targets.
    """
    from vtl_synth.core.constants import VOWEL_TARGETS
    from vtl_synth.core.polar import polar_arc, stationary_point

    ipa = _normalize_phrase(phrase)
    block_info, ev = _recorded_build_pval(ipa, t_cons, t_voy,
                                          pause_short_ms, pause_long_ms)
    q_arc, q_bg, q_hold, q_cluster = (ev['arc'], ev['bg'], ev['hold'],
                                      ev['cluster'])

    def arc_z(dep, arr, n, nu):
        """(n, 2) curved polar arc dep → arr (reference geometry)."""
        return polar_arc(dep[0], dep[1], arr[0], arr[1],
                         n * STEP_MS, sr=POLAR_SR, K=K_DISPLAY, nu=nu,
                         orientation=ORIENTATION)[1]

    def hold_z(pt, n):
        """(n, 2) stationary point."""
        return stationary_point(pt[0], pt[1], n * STEP_MS,
                                sr=POLAR_SR)[1]

    def _check(kind, recorded_n, block_n):
        if recorded_n != block_n:
            raise RuntimeError(
                f'polar v3 alignment drift on a {kind!r} block: '
                f'{recorded_n} recorded vs {block_n} block steps '
                f'(syl engine block structure changed?)')

    zv_parts: list = []
    zc_spans: list = []       # (t0, t1, (n, 2) array)
    phonemes: list = []       # {key, category, rho, theta, t0, t1}
    step = 0
    for b in block_info:
        n = b.n_steps
        if b.kind == 'plateau':
            key = b.vowel_key or '@'
            rv, tv = VOWEL_TARGETS.get(key, VOWEL_TARGETS['@'])
            zv_parts.append(hold_z((rv, tv), n))
            phonemes.append(dict(key=key, category='V', rho=float(rv),
                                 theta=float(tv), t0=step, t1=step + n))
        elif b.kind == 'background':
            dep, arr, ne = q_bg.pop(0)
            _check(b.kind, ne, n)
            zv_parts.append(arc_z(dep, arr, ne, NU_VOCALIC))
        elif b.kind in ('pause', 'initial', 'terminal'):
            dep, arr, ne = q_arc.pop(0)
            _check(b.kind, ne, n)
            zv_parts.append(arc_z(dep, arr, ne, NU_VOCALIC))
        elif b.kind in ('decay', 'attack'):
            pt, ne = q_hold.pop(0)
            _check(b.kind, ne, n)
            zv_parts.append(hold_z(pt, ne))
        elif b.kind == 'cluster' and b.cons_keys:
            dep, arr, targets, T = q_cluster.pop(0)
            m = len(targets)
            _check(b.kind, (m + 1) * T, n)
            # red: the vocalic background keeps flowing anchor→anchor
            zv_parts.append(arc_z(dep, arr, n, NU_VOCALIC))
            # blue: dep → C₁ → ⋯ → C_m → arr, T steps per sub-arc
            pts = [tuple(p) for p in [dep] + targets + [arr]]
            zc = np.vstack([arc_z(pts[k], pts[k + 1], T, NU_CONSONANTAL)
                            for k in range(m + 1)])
            zc_spans.append((step, step + n, zc))
            for k, (ck, tgt) in enumerate(zip(b.cons_keys, targets)):
                phonemes.append(dict(key=ck, category='C',
                                     rho=float(tgt[0]),
                                     theta=float(tgt[1]),
                                     t0=step + k * T,
                                     t1=step + (k + 1) * T))
        else:      # defensive: unknown block kind — neutral hold
            zv_parts.append(hold_z((0.0, 0.0), n))
        step += n

    if q_arc or q_bg or q_hold or q_cluster:
        raise RuntimeError(
            'polar v3 alignment drift: unconsumed engine events '
            f'({len(q_arc)} arc, {len(q_bg)} bg, {len(q_hold)} hold, '
            f'{len(q_cluster)} cluster) — syl engine block structure '
            'changed?')

    traj_v = np.vstack(zv_parts) if zv_parts else np.zeros((0, 2))
    traj_c = np.full_like(traj_v, np.nan)
    for t0, t1, zc in zc_spans:
        traj_c[t0:t1] = zc
    return dict(
        phrase=ipa,
        n_steps=int(step),
        traj_v=traj_v,
        traj_c=traj_c,
        phonemes=phonemes,
    )


def _inventory() -> list:
    """All speaker phoneme targets for the active language pack state.

    Vowels (red) straight from VOWEL_TARGETS; consonants (blue) from
    CONSONANT_TARGETS, resolved through the same rules as the engine
    (g palatal/velar resolved with a neutral context).
    """
    from vtl_synth.core.constants import VOWEL_TARGETS, CONSONANT_TARGETS
    from vtl_synth.core.projection import get_consonant_target

    out = []
    for key, (rho, theta) in VOWEL_TARGETS.items():
        out.append(dict(key=key, category='V',
                        rho=float(rho), theta=float(theta)))
    for key in CONSONANT_TARGETS:
        if key in ('g_vel', 'g_pal', 'z_front'):
            continue      # contextual variants of g / z
        ct = get_consonant_target(key, np.pi)
        if ct is None:
            continue
        out.append(dict(key=key, category='C',
                        rho=float(ct[0]), theta=float(ct[1])))
    return out


def build_polar(phrases: list,
                t_cons: int,
                t_voy: int,
                pause_short_ms: float,
                pause_long_ms: float) -> dict:
    """Full utterance (list of phrases) → .polar dict.

    Phrase timelines are concatenated (the .tract of ``Pipeline.run``
    stacks the phrase tracts in the same order), so the polar time axis
    matches the audio/video time axis.
    """
    traj_v = np.zeros((0, 2))
    traj_c = np.zeros((0, 2))
    phonemes = []
    offset = 0
    for phrase in phrases:
        p = build_phrase_polar(phrase, t_cons, t_voy,
                               pause_short_ms, pause_long_ms)
        traj_v = np.vstack([traj_v, p['traj_v']])
        traj_c = np.vstack([traj_c, p['traj_c']])
        for ph in p['phonemes']:
            ph = dict(ph)
            ph['t0'] += offset
            ph['t1'] += offset
            phonemes.append(ph)
        offset += p['n_steps']
    return dict(
        version=POLAR_VERSION,
        sr=POLAR_SR,
        speaker='JD3',
        n_steps=int(offset),
        duration_s=offset / POLAR_SR,
        traj_v=traj_v,
        traj_c=traj_c,
        phonemes=phonemes,
        inventory=_inventory(),
    )


# --------------------------------------------------------------------------
# .polar file (JSON, self-documented)
# --------------------------------------------------------------------------


def _jfloats(col) -> list:
    """Float column with NaN → None (branch inactive)."""
    return [None if not np.isfinite(x) else float(x) for x in col]


def write_polar(path, polar: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(
        format='covtl-polar',
        version=polar['version'],
        sample_rate=polar['sr'],
        speaker=polar['speaker'],
        n_steps=polar['n_steps'],
        duration_s=polar['duration_s'],
        columns=dict(
            vocalic_rho='vocalic branch (red): polar radius (cm), 100 Hz, '
                        'always active',
            vocalic_theta='vocalic branch (red): polar angle (rad), '
                          'always active',
            consonantal_rho='consonantal branch (blue): polar radius (cm); '
                            'null while the branch is inactive (outside '
                            'the clusters)',
            consonantal_theta='consonantal branch (blue): polar angle '
                              '(rad); null outside the clusters'),
        orientation='trigonometric: theta=0 East, counter-clockwise',
        trajectory_source='direct reconstruction from the engine polar '
                          'anchors and consonant node targets '
                          '(core.polar.polar_arc / stationary_point at '
                          '100 Hz; display curvature K=30, nu=+1 vocalic '
                          '/ -1 consonantal — reference-model geometry, '
                          'not the quasi-rectilinear SYL_K=1000 parameter '
                          'arcs)',
        notation='internal input notation (engine keys, e.g. tS, a~)',
        trajectory=dict(
            vocalic=dict(rho=polar['traj_v'][:, 0].tolist(),
                         theta=polar['traj_v'][:, 1].tolist()),
            consonantal=dict(rho=_jfloats(polar['traj_c'][:, 0]),
                             theta=_jfloats(polar['traj_c'][:, 1]))),
        phonemes=polar['phonemes'],
        inventory=polar['inventory'],
    )
    path.write_text(json.dumps(doc), encoding='utf-8')
    return path


def read_polar(path) -> dict:
    """Read a .polar file (v3 two-branch, or v2 single-trajectory).

    v2 files (single blended trajectory + per-step categories) are
    mapped conservatively: vocalic = the whole trajectory, consonantal
    = the samples categorized 'C' (blue), so old files keep rendering.
    """
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    version = int(doc.get('version', 0))
    if version >= 3:
        v = doc['trajectory']['vocalic']
        traj_v = np.column_stack([v['rho'], v['theta']]).astype(float)
        c = doc['trajectory'].get('consonantal', {})
        crho = [np.nan if x is None else float(x)
                for x in c.get('rho', [])]
        cth = [np.nan if x is None else float(x)
               for x in c.get('theta', [])]
        if crho:
            traj_c = np.column_stack([crho, cth])
        else:
            traj_c = np.full_like(traj_v, np.nan)
        return dict(version=version, sr=doc['sample_rate'],
                    speaker=doc['speaker'], n_steps=doc['n_steps'],
                    duration_s=doc['duration_s'], traj_v=traj_v,
                    traj_c=traj_c, phonemes=doc['phonemes'],
                    inventory=doc['inventory'])
    # v2 fallback
    traj = np.column_stack([doc['trajectory']['rho'],
                            doc['trajectory']['theta']])
    cats = np.asarray(doc['trajectory'].get(
        'categories', ['T'] * traj.shape[0]))
    traj_c = np.where((cats == 'C')[:, None], traj, np.nan)
    return dict(version=version, sr=doc['sample_rate'],
                speaker=doc['speaker'], n_steps=doc['n_steps'],
                duration_s=doc['duration_s'], traj_v=traj,
                traj_c=traj_c, phonemes=doc['phonemes'],
                inventory=doc['inventory'])


# --------------------------------------------------------------------------
# Polar figure rendering (matplotlib, Agg)
# --------------------------------------------------------------------------

_COLOR_V = '#d62728'      # vocalic branch / vowel targets: red
_COLOR_C = '#1f77b4'      # consonantal branch / consonant targets: blue
_TRAIL_S = 0.75           # s of visible fading trail
_LABEL_S = 0.5            # s of transient label display


def _rho_max(polar: dict) -> float:
    """Largest radius over both branches + the inventory."""
    vals = [float(polar['traj_v'][:, 0].max())]
    tc = polar.get('traj_c')
    if tc is not None and tc.size and np.any(np.isfinite(tc[:, 0])):
        vals.append(float(np.nanmax(tc[:, 0])))
    vals.append(max(p['rho'] for p in polar['inventory']))
    return max(vals)


def render_polar_frame(ax, polar: dict, t: float,
                       rho_max: float = None) -> None:
    """Draw the polar figure at time ``t`` (s) into matplotlib polar axes.

    Two dissociated curves: the vocalic branch (red, always active)
    and — during the clusters — the consonantal branch (blue), each
    with its own fading trail and current position.  Sober by design:
    inventory dots (small), transient label of the current phoneme
    (internal notation) near the active target.
    """
    sr = polar['sr']
    traj_v = polar['traj_v']
    traj_c = polar.get('traj_c')
    n = traj_v.shape[0]

    ax.clear()
    ax.set_theta_zero_location('E')     # theta = 0 on the right
    ax.set_theta_direction(1)           # counter-clockwise (trigonometric)
    if rho_max is None:
        rho_max = 1.25 * _rho_max(polar)
    ax.set_rlim(0, rho_max)
    ax.set_rlabel_position(22.5)
    ax.grid(alpha=0.25, lw=0.5)
    ax.tick_params(labelsize=7)

    # inventory: all speaker phonemes of the language, always visible
    inv = polar['inventory']
    for cat, color in (('V', _COLOR_V), ('C', _COLOR_C)):
        pts = [p for p in inv if p['category'] == cat]
        ax.plot([p['theta'] for p in pts], [p['rho'] for p in pts],
                'o', color=color, ms=4.5, mew=0.4, zorder=3)

    if n == 0:
        return

    i = min(int(round(t * sr)), n - 1)
    i0 = max(0, int((t - _TRAIL_S) * sr))

    # vocalic trail (red): continuous, anchor-to-anchor arcs + plateaus
    for k in range(i0, i):
        frac = (k - i0 + 1) / max(1, i - i0)
        ax.plot(traj_v[k:k + 2, 1], traj_v[k:k + 2, 0], '-',
                color=_COLOR_V, alpha=0.15 + 0.75 * frac,
                lw=0.8 + 1.6 * frac, solid_capstyle='round', zorder=4)
    ax.plot([traj_v[i, 1]], [traj_v[i, 0]], 'o', color=_COLOR_V,
            ms=5.5, mec='black', mew=0.5, zorder=6)

    # consonantal trail (blue): clusters only; break at inactive samples
    if traj_c is not None and traj_c.shape == traj_v.shape \
            and np.any(np.isfinite(traj_c[:, 0])):
        for k in range(i0, i):
            if not (np.isfinite(traj_c[k, 0])
                    and np.isfinite(traj_c[k + 1, 0])):
                continue
            frac = (k - i0 + 1) / max(1, i - i0)
            ax.plot(traj_c[k:k + 2, 1], traj_c[k:k + 2, 0], '-',
                    color=_COLOR_C, alpha=0.15 + 0.75 * frac,
                    lw=0.8 + 1.6 * frac, solid_capstyle='round', zorder=5)
        if np.isfinite(traj_c[i, 0]):
            ax.plot([traj_c[i, 1]], [traj_c[i, 0]], 'o', color=_COLOR_C,
                    ms=5.5, mec='black', mew=0.5, zorder=7)

    # active phoneme(s): branch-to-target segment + transient label
    for ph in polar['phonemes']:
        if ph['t0'] <= i < ph['t1']:
            color = _COLOR_V if ph['category'] == 'V' else _COLOR_C
            src = traj_v[i]
            if ph['category'] == 'C' and traj_c is not None \
                    and np.isfinite(traj_c[i, 0]):
                src = traj_c[i]
            ax.plot([src[1], ph['theta']], [src[0], ph['rho']],
                    '-', color=color, lw=1.8, alpha=0.9, zorder=5)
            if t <= ph['t0'] / sr + _LABEL_S:
                ax.annotate(ph['key'],
                            xy=(ph['theta'], ph['rho']),
                            xytext=(0, 7), textcoords='offset points',
                            ha='center', fontsize=10, color=color,
                            fontweight='bold', zorder=7)


def render_polar_frames(polar: dict, png_dir, fps: int = 25,
                        n_frames: int = None,
                        px: int = 840) -> tuple:
    """Render the polar figure sequence as frame_%05d.png files.

    Returns (png_dir, n_frames)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    png_dir = Path(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)
    if n_frames is None:
        n_frames = int(np.ceil(polar['duration_s'] * fps))
    rho_max = 1.25 * _rho_max(polar)
    for k in range(n_frames):
        fig = plt.figure(figsize=(px / 100, px / 100), dpi=100)
        ax = fig.add_subplot(111, projection='polar')
        render_polar_frame(ax, polar, t=k / fps, rho_max=rho_max)
        fig.tight_layout(pad=0.4)
        fig.savefig(png_dir / f'frame_{k:05d}.png', dpi=100)
        plt.close(fig)
    return png_dir, n_frames


# --------------------------------------------------------------------------
# Dual-panel composition + encoding
# --------------------------------------------------------------------------


def compose_frames(sagittal_png_dir, polar_png_dir, out_png_dir,
                   n_frames: int = None) -> tuple:
    """Side-by-side composition: sagittal (left) | polar (right)."""
    from PIL import Image
    out_png_dir = Path(out_png_dir)
    out_png_dir.mkdir(parents=True, exist_ok=True)
    if n_frames is None:
        n_frames = len(list(Path(sagittal_png_dir).glob('frame_*.png')))
    for k in range(n_frames):
        left = Image.open(Path(sagittal_png_dir) / f'frame_{k:05d}.png')
        right = Image.open(Path(polar_png_dir) / f'frame_{k:05d}.png')
        h = max(left.height, right.height)
        if left.height != h:
            left = left.resize((int(left.width * h / left.height), h))
        if right.height != h:
            right = right.resize((int(right.width * h / right.height), h))
        canvas = Image.new('RGB', (left.width + right.width + 2, h),
                           (200, 200, 200))
        canvas.paste(left, (0, 0))
        canvas.paste(right, (left.width + 2, 0))
        canvas.save(out_png_dir / f'frame_{k:05d}.png')
    return out_png_dir, n_frames


def _purge_frames(*dirs) -> None:
    """Delete stale frame_*.png in the work subdirectories.

    The work directories persist across runs; without this purge, a
    previous LONGER render leaves higher-indexed frames behind, and
    the sequential ``frame_%05d.png`` glob of the encoder silently
    appends them to the new video (observed: a 'ba.da.ga' demo 0.64 s
    longer than its audio, ending with frames of the previous
    'this is easy for us' render).
    """
    for d in dirs:
        d = Path(d)
        if d.is_dir():
            for f in d.glob('frame_*.png'):
                f.unlink()


def make_polar_video(tract_path, polar_path, wav_path=None, out_path=None,
                     fps: int = 25, scale: int = 2,
                     work_dir=None) -> Path:
    """Dual-panel MP4: existing sagittal view (left) + polar figure (right).

    Reads the .polar (single source of the polar figure, 100 Hz
    trajectories downsampled/restored to ``fps``), renders the sagittal
    frames from the .tract at ``fps``, composes both panels and encodes
    H.264 + AAC (audio muxed from ``wav_path``).
    """
    from vtl_synth.video.renderer import read_tract, render_frames
    from vtl_synth.video.encoder import encode_mp4

    tract_path, polar_path = Path(tract_path), Path(polar_path)
    out_path = Path(out_path) if out_path is not None \
        else tract_path.with_suffix('.mp4')
    work = Path(work_dir) if work_dir is not None else Path('temp_video')

    polar = read_polar(polar_path)

    _purge_frames(work / 'sagittal', work / 'polar' / 'png',
                  work / 'compo')

    data, sr = read_tract(tract_path)
    sag_dir, n_sag = render_frames(data, sr, fps=fps, scale=scale,
                                   work_dir=work / 'sagittal')

    n_frames = min(n_sag, int(np.ceil(polar['duration_s'] * fps)))
    polar_dir, n_pol = render_polar_frames(
        polar, work / 'polar' / 'png', fps=fps, n_frames=n_frames)

    compo_dir, n_frames = compose_frames(sag_dir, polar_dir,
                                         work / 'compo', n_frames)
    n_files = len(list(compo_dir.glob('frame_*.png')))
    if n_files != n_frames:
        raise RuntimeError(
            f'composed frame count mismatch: {n_files} files in '
            f'{compo_dir} vs {n_frames} expected (stale work dir?)')
    mp4 = encode_mp4(compo_dir, out_path, fps=fps, wav_path=wav_path)
    print(f'polar video: {mp4} ({n_files} frames @{fps} Hz, '
          f'{mp4.stat().st_size / 1e6:.1f} MB)')
    return mp4
