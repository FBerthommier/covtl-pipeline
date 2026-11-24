# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Non-regression of the 2026-11-24 schwa recentring (audit).

VOWEL_TARGETS['@'] moved from the polar centroid (0.7167, pi) of
2026-09-04 to the INTERIOR mid-central (0.580, pi). The schwa is the
waypoint of the closing VV arcs (syl._vv_waypoint) and a phoneme entry
of the polar manifest (.polar inventory). Acceptance criteria of the
audit, locked in here:

  - the corridor crosses at quasi-constant aperture (rho bump <= 0.03
    on the u->i window of « buib »);
  - the routed legs stay above the /u/ plateau (min area >= 0.15 cm2,
    real VTL probe);
  - the trajectory of « buib » is measurably LESS similar to « buaib »
    than the centroid waypoint (Hausdorff >= 0.40 on the polar disk,
    was 0.2833);
  - the display re-run (polar_video) applies the same schwa routing as
    the motor chain when the display_schwa_route toggle is ON (stubbed
    probe: two routed legs through the waypoint); OFF — the default —
    draws the legacy direct arcs, identical to the .polar of the
    pre-audit revision (6536f5a). The motor routing itself is never
    conditional.

The VTL-dependent criteria are skipped gracefully when
vocaltractlab_cython is not installed (display-only environments).
"""
import numpy as np
import pytest

import vtl_synth.core.syltraj as syl
from vtl_synth.core.syltraj import build_phrase_pval
from vtl_synth.core.constants import VOWEL_TARGETS

try:
    from vtl_synth.core.build_phrase_tract import _make_vv_closure_probe
    _HAS_VTL = True
except Exception:                                     # pragma: no cover
    _HAS_VTL = False


def _close_everything_probe(block):                   # stub, no VTL
    """Stub closure probe: every background arc 'closes' -> routing."""
    return 0.0


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


class TestRoutingGeometry:
    """Stubbed probe (no VTL): the routed structure and the display."""

    def test_buib_routes_two_legs(self, monkeypatch):
        # direct (unrouted) reference FIRST, before the stub is set
        _, blocks_d, _, _ = build_phrase_pval('buib')
        bgs_d = [b for b in blocks_d if b.kind == 'background']
        monkeypatch.setattr(syl, 'VV_CLOSURE_PROBE',
                            _close_everything_probe)
        _, blocks, _, _ = build_phrase_pval('buib')
        # routing: two half-arcs dep -> @ -> arr, total D preserved
        bgs = [b for b in blocks if b.kind == 'background']
        assert len(bgs) == 2
        assert bgs[0].vowel_key == '@'
        assert bgs[1].vowel_key == ''
        assert sum(b.n_steps for b in bgs) == \
            sum(b.n_steps for b in bgs_d)

    def test_display_routes_like_motor(self, monkeypatch):
        """Display toggle ON: the routed display passes EXACTLY through
        the waypoint (rho 0.580, theta pi) at the leg junction, as the
        motor does."""
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

    def test_buib_legs_above_u_plateau(self):
        _, _, areas = self._motor('buib')
        assert areas, 'buib must route (two background legs)'
        assert min(areas) >= 0.15        # /u/ plateau: 0.152 (probe)

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
