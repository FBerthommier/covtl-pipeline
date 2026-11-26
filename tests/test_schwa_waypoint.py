# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Non-regression of the schwa treatment of closing VV arcs.

Two audits, two layers:

  - 2026-11-24: VOWEL_TARGETS['@'] moved from the polar centroid
    (0.7167, pi) of 2026-09-04 to the INTERIOR mid-central (0.580,
    pi). The schwa target is locked here (target value, waypoint,
    polar manifest entry).

  - 2026-11-26: the closing VV arcs keep their DIRECT path and are
    SOFTLY RECTIFIED on the TCY/TBY columns toward the schwa values
    (probe-tuned amplitude, sin² bump zero at the endpoints) — the
    2026-11-24 two-half-arc routing put a STATIONARY schwa at the leg
    junction (motor states [dep, @, @, arr] at the production D=4:
    half the diphthong frozen on P(@), an unjustified pause). The
    two-leg routing through @ survives only as the FALLBACK when no
    amplitude of VV_RECTIFY_STEPS opens the corridor.

Acceptance criteria of the 2026-11-26 audit, locked in here:

  - the rectified block is a SINGLE background block: exact anchors,
    TCY/TBY the only modified columns, no repeated state (no pause),
    probe area >= SYL_VV_CLOSURE_THRESH on the fine sampling;
  - the always-closing stub still produces the two fallback legs
    (dep -> @ -> arr, total D preserved, junction at the waypoint);
  - the display re-run (polar_video) with display_schwa_route ON shows
    the fallback legs exactly at the waypoint; OFF (default) draws the
    legacy direct arcs, identical to the no-probe re-run;
  - « buib » stays measurably dissimilar from « buaib » (Hausdorff
    >= 0.40 on the polar disk — the rectified trajectory sweeps
    through 0 deg, never the pi meridian).

The VTL-dependent criteria are skipped gracefully when
vocaltractlab_cython is not installed (display-only environments).
"""
import numpy as np
import pytest

import vtl_synth.core.syltraj as syl
from vtl_synth.core.syltraj import build_phrase_pval
from vtl_synth.core.constants import VOWEL_TARGETS, CO_VTL

try:
    from vtl_synth.core.build_phrase_tract import _make_vv_closure_probe
    _HAS_VTL = True
except Exception:                                     # pragma: no cover
    _HAS_VTL = False

_COVTL_KEYS = list(CO_VTL.keys())
_P_TCY = _COVTL_KEYS.index('TCY')
_P_TBY = _COVTL_KEYS.index('TBY')


def _close_everything_probe(block):                   # stub, no VTL
    """Stub closure probe: every background arc 'closes' -> the
    rectification amplitude sweep is exhausted -> FALLBACK routing."""
    return 0.0


def _rectifying_probe(block):
    """Stub probe (no VTL): a fake lingual area driven by the TCY pull
    toward the schwa value — the rectification's own mechanism. The
    direct u→i arc pulls 0.63 away from the schwa TCY on its central
    half (calibrated); each amplitude s shrinks the pull by
    (1 − s·ramp). Threshold 0.56 / gain 4.0: the direct arc 'closes'
    (0.02 < 0.18), s = 0.1/0.2 stay closed, s = 0.3 opens (0.30) —
    the engine's amplitude sweep must pick s = 0.3 on « buib »."""
    wp = syl.compute_P(*syl._vv_waypoint())
    n = len(block)
    lo, hi = max(1, n // 4), max(2, 3 * n // 4)
    pull = float(np.abs(block[lo:hi, _P_TCY] - wp[_P_TCY]).max())
    return 0.02 + 4.0 * max(0.0, 0.56 - pull)


class TestSchwaTarget:
    def test_target_value(self):
        """The schwa is the interior mid-central (audit 2026-11-24)."""
        rho, theta = VOWEL_TARGETS['@']
        assert rho == pytest.approx(0.580, abs=1e-9)
        assert theta == pytest.approx(np.pi, abs=1e-9)

    def test_vv_waypoint_follows_target(self):
        assert syl._vv_waypoint() == [0.580, np.pi]

    def test_waypoint_interior(self):
        """Interior waypoint: between the neutral anchor (0.42) and the
        close-vowel periphery (rho_i 0.60) — the former centroid 0.7167
        reached the open-central periphery (cf. 'buaib')."""
        from vtl_synth.core.constants import NEUTRAL_RHO
        rho, _ = syl._vv_waypoint()
        assert NEUTRAL_RHO < rho <= 0.60

    def test_waypoint_neutral_fallback(self):
        """No '@' in VOWEL_TARGETS -> NEUTRAL anchor (schwa by
        definition)."""
        saved = VOWEL_TARGETS.pop('@')
        try:
            wp = syl._vv_waypoint()
        finally:
            VOWEL_TARGETS['@'] = saved
        from vtl_synth.core.constants import (NEUTRAL_RHO,
                                              NEUTRAL_THETA)
        assert wp == [NEUTRAL_RHO, NEUTRAL_THETA]


class TestPolarManifest:
    def test_inventory_schwa_entry(self):
        """The '@' phoneme entry of the polar manifest follows the
        target (interior mid-central)."""
        from vtl_synth.video.polar_video import _inventory
        entry = [e for e in _inventory() if e['key'] == '@']
        assert len(entry) == 1
        assert entry[0]['category'] == 'V'
        assert entry[0]['rho'] == pytest.approx(0.580, abs=1e-9)
        assert entry[0]['theta'] == pytest.approx(np.pi, abs=1e-9)


class TestRectification:
    """Stubbed probes (no VTL): the rectification and its fallback."""

    @staticmethod
    def _bg_blocks(phrase, probe):
        monkey_probe = probe
        saved = syl.VV_CLOSURE_PROBE
        syl.VV_CLOSURE_PROBE = monkey_probe
        try:
            _, blocks, _, _ = build_phrase_pval(phrase)
        finally:
            syl.VV_CLOSURE_PROBE = saved
        return [b for b in blocks if b.kind == 'background']

    def test_buib_rectifies_single_block(self):
        """Tunable stub: ONE rectified background block, amplitude
        strictly interior, exact anchors, TCY/TBY the only rectified
        columns, no repeated state (the schwa pause is gone)."""
        bgs = self._bg_blocks('buib', _rectifying_probe)
        assert len(bgs) == 1
        b = bgs[0]
        assert 0.0 < b.rectify_s < 1.0
        assert b.vowel_key == ''
        # total duration preserved vs the direct reference
        bgs_d = self._bg_blocks('buib', None)
        assert b.n_steps == bgs_d[0].n_steps

    def test_rectified_columns_and_anchors(self):
        """The rectified block deviates from the pure direct arc ONLY
        on the selector columns, and keeps the anchors bit-exact."""
        saved = syl.VV_CLOSURE_PROBE
        syl.VV_CLOSURE_PROBE = _rectifying_probe
        try:
            Pval, blocks, _, _ = build_phrase_pval('buib')
        finally:
            syl.VV_CLOSURE_PROBE = saved
        t0 = 0
        blk = bg = None
        for bb in blocks:
            if bb.kind == 'background':
                bg = bb
                blk = Pval[t0:t0 + bb.n_steps]
                break
            t0 += bb.n_steps
        # direct reference rebuilt from the KNOWN polar targets
        direct = syl.arc_B(list(VOWEL_TARGETS['u']),
                           list(VOWEL_TARGETS['i']),
                           list(range(15)), len(blk),
                           [-np.pi, 0], 0, syl.SYL_NU, syl.SYL_K,
                           syl.SYL_PEXP)
        dev = np.abs(blk - direct)
        others = [p for p in range(15) if p not in (_P_TCY, _P_TBY)]
        assert dev[:, others].max() == pytest.approx(0.0, abs=1e-12)
        assert dev[:, [_P_TCY, _P_TBY]].max() > 0.05
        # anchors exact
        Pu = syl.compute_P(*VOWEL_TARGETS['u'])
        Pi = syl.compute_P(*VOWEL_TARGETS['i'])
        assert np.allclose(blk[0], Pu, atol=1e-12)
        assert np.allclose(blk[-1], Pi, atol=1e-12)

    def test_rectified_never_stalls(self):
        """No schwa pause: every consecutive state pair moves (the
        2026-11-24 routed legs had a zero-velocity junction)."""
        saved = syl.VV_CLOSURE_PROBE
        syl.VV_CLOSURE_PROBE = _rectifying_probe
        try:
            Pval, blocks, _, _ = build_phrase_pval('buib')
        finally:
            syl.VV_CLOSURE_PROBE = saved
        t0 = 0
        for bb in blocks:
            if bb.kind == 'background':
                break
            t0 += bb.n_steps
        win = Pval[t0:t0 + bb.n_steps]
        d = np.linalg.norm(np.diff(win, axis=0), axis=1)
        assert d.min() > 0.0

    def test_fallback_two_legs(self):
        """Always-closing stub: the amplitude sweep is exhausted, the
        2026-11-24 fallback routing applies — two half-arcs
        dep -> @ -> arr, total D preserved, waypoint at the junction."""
        bgs_d = self._bg_blocks('buib', None)
        bgs = self._bg_blocks('buib', _close_everything_probe)
        assert len(bgs) == 2
        assert bgs[0].vowel_key == '@'
        assert bgs[1].vowel_key == ''
        assert bgs[0].rectify_s == 0.0
        assert sum(b.n_steps for b in bgs) == \
            sum(b.n_steps for b in bgs_d)

    def test_display_routes_like_motor(self, monkeypatch):
        """Display toggle ON with the fallback (stub probe): the routed
        display passes EXACTLY through the waypoint (rho 0.580, theta
        pi) at the leg junction, as the motor does."""
        from vtl_synth.video import polar_video as pv
        monkeypatch.setattr(pv, '_vv_probe',
                            lambda: _close_everything_probe)
        p = pv.build_phrase_polar('buib', 6, 2, 200.0, 320.0,
                                  display_schwa_route=True)
        tv = p['traj_v']
        th, rh = tv[:, 1], tv[:, 0]
        i = int(np.argmin(np.abs(th - np.pi)))
        assert abs(th[i] - np.pi) < 1e-6
        assert rh[i] == pytest.approx(0.580, abs=1e-9)

    def test_display_direct_legacy(self, monkeypatch):
        """Display toggle OFF (default) and no-probe: the LEGACY direct
        arcs.

        OFF must be identical to the no-probe re-run — i.e. to the
        .polar of the pre-audit revision (6536f5a): direct arc u→i with
        its rho dip (~0.29), sweeping through 0°, never pi. The probe
        is never even consulted when the flag is off.
        """
        from vtl_synth.video import polar_video as pv
        # 1) no probe available (display-only env)
        monkeypatch.setattr(pv, '_vv_probe', lambda: None)
        p_none = pv.build_phrase_polar('buib', 6, 2, 200.0, 320.0)
        # 2) a probe IS available but the toggle is OFF (default)
        monkeypatch.setattr(pv, '_vv_probe',
                            lambda: _close_everything_probe)
        p_off = pv.build_phrase_polar('buib', 6, 2, 200.0, 320.0)
        th = p_off['traj_v'][:, 1]
        # direct arc u(60°) -> i(300°): sweeps through 0°, never pi
        assert not np.any(np.abs(np.abs(th) - np.pi) < 1e-6)
        assert float(p_off['traj_v'][:, 0].min()) < 0.35   # rho dip
        # identity with the legacy display: same steps, same points
        assert p_off['traj_v'].shape == p_none['traj_v'].shape
        assert np.array_equal(p_off['traj_v'], p_none['traj_v'])
        assert p_off['n_steps'] == p_none['n_steps']


@pytest.mark.skipif(not _HAS_VTL, reason='vocaltractlab_cython absent')
class TestRoutingAcoustics:
    """Real VTL probe: the audit acceptance criteria.

    The motor build uses the fine transition sampling (t_voy=6, D=12):
    the polar PATH is D-independent (arc_B sweeps the same parameter
    curve), and the 400 Hz chain interpolates the default D=4 states
    through exactly these blend states — the fine sampling measures the
    physical worst case of the aperture.
    """

    @staticmethod
    def _motor(phrase):
        probe = _make_vv_closure_probe()
        saved = syl.VV_CLOSURE_PROBE
        syl.VV_CLOSURE_PROBE = probe
        try:
            Pval, blocks, _, _ = build_phrase_pval(
                phrase, t_cons=16, t_voy=6)
        finally:
            syl.VV_CLOSURE_PROBE = saved
        win, t = [], 0
        for b in blocks:
            if b.kind == 'background':
                win.append((t, t + b.n_steps))
            t += b.n_steps
        areas = [probe(Pval[t0:t1]) if t1 - t0 >= 4 else
                 probe(np.tile(Pval[(t0 + t1) // 2], (8, 1)))
                 for t0, t1 in win]
        return Pval, win, [float(a) for a in areas]

    def test_buib_rectified_above_threshold(self):
        """« buib » closes direct (0.062): ONE rectified background
        block, amplitude strictly interior, central area above the
        closure threshold (>= 0.15, margin vs the /u/ plateau 0.152)."""
        saved = syl.VV_CLOSURE_PROBE
        syl.VV_CLOSURE_PROBE = _make_vv_closure_probe()
        try:
            _, blocks, _, _ = build_phrase_pval('buib', t_cons=16,
                                                t_voy=6)
        finally:
            syl.VV_CLOSURE_PROBE = saved
        bgs = [b for b in blocks if b.kind == 'background']
        assert len(bgs) == 1
        assert 0.0 < bgs[0].rectify_s < 1.0
        _, _, areas = self._motor('buib')
        assert areas, 'buib must have a background VV arc'
        assert min(areas) >= 0.15

    def test_buib_no_schwa_pause(self):
        """The rectified trajectory never stalls (no repeated state,
        min |dP| > 0) and never reaches the schwa state: the schwa is
        the RECTIFICATION TARGET of two columns, not a passage point —
        the 2026-11-24 routed legs held P(@) for half the diphthong."""
        Pval, win, _ = self._motor('buib')
        t0, t1 = win[0][0], win[-1][1]
        seg = Pval[t0:t1]
        d = np.linalg.norm(np.diff(seg, axis=0), axis=1)
        assert d.min() > 0.0
        P_at = syl.compute_P(*syl._vv_waypoint())
        dist = np.linalg.norm(seg - P_at, axis=1)
        assert dist.min() > 1.0          # never near the schwa state

    def test_buib_quasi_constant_aperture(self):
        from vtl_synth.video.polar_video import polar_from_pval
        Pval, win, _ = self._motor('buib')
        rt = polar_from_pval(Pval)
        t0, t1 = win[0][0], win[-1][1]
        seg = rt[t0:t1 + 1]
        rho_u, rho_i = VOWEL_TARGETS['u'][0], VOWEL_TARGETS['i'][0]
        assert seg[:, 0].max() <= rho_i + 0.03   # no peripheral bump

    def test_buib_less_similar_to_buaib(self):
        from vtl_synth.video.polar_video import polar_from_pval

        def zres(rt, n=240):
            z = rt[:, 0] * np.exp(1j * rt[:, 1])
            t = np.linspace(0, 1, len(z))
            ti = np.linspace(0, 1, n)
            return (np.interp(ti, t, z.real)
                    + 1j * np.interp(ti, t, z.imag))

        def hausdorff(z1, z2):
            d = np.abs(z1[:, None] - z2[None, :])
            return max(d.min(axis=0).max(), d.min(axis=1).max())

        pval_buaib, _, _ = self._motor('buaib')
        pval_buib, _, _ = self._motor('buib')
        H = hausdorff(zres(polar_from_pval(pval_buib)),
                      zres(polar_from_pval(pval_buaib)))
        assert H >= 0.40                # was 0.2833 at the centroid
