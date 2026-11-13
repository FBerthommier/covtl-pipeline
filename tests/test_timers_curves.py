# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Targeted tests for timers.py (P1 hardening).

Covers the timer machinery the synthesis smoke tests do not reach:

  * rescale_timer_data (degenerate + uniform rescaling),
  * build_occlusion_traces / update_occlusion_traces (plosive per-parameter
    corrections, velar TBX bonus, out-of-range peak guards, fricatives),
  * build_pexp_curve (burst / frication / degenerate inputs),
  * build_reference_timers (voicing, nasality, laterality marks from the
    reference pipeline structures),
  * the debug printers.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from vtl_synth.core.timers import (
    NasalityMark,
    OcclusionTrace,
    OcclusionTraceResult,
    PexpMark,
    TimerData,
    VoicingMark,
    build_occlusion_traces,
    build_pexp_curve,
    build_reference_timers,
    print_lateral_timer,
    print_nasality_timer,
    print_voicing_timer,
    rescale_timer_data,
    update_occlusion_traces,
)
from vtl_synth.core.types import BlockInfo, GestureNode


# =============================================================================
# rescale_timer_data
# =============================================================================

class TestRescaleTimerData:
    def test_zero_duration_adopts_trajectory_duration(self):
        td = TimerData(total_duration_ms=0.0)
        out = rescale_timer_data(td, 1500.0)
        assert out.total_duration_ms == 1500.0

    def test_unit_scale_is_noop(self):
        td = TimerData(
            voicing_marks=[VoicingMark(seg_key='b', t_target_ms=100.0)],
            total_duration_ms=1000.0)
        out = rescale_timer_data(td, 1000.0)
        assert out.voicing_marks[0].t_target_ms == 100.0

    def test_uniform_rescaling_scales_every_mark(self):
        td = TimerData(
            voicing_marks=[VoicingMark(
                seg_key='b', t_target_ms=100.0, t_start_ms=75.0,
                t_end_ms=150.0)],
            nasality_marks=[NasalityMark(t_open_ms=200.0, t_close_ms=400.0)],
            pexp_marks=[PexpMark(t_start_ms=100.0, t_peak_ms=120.0,
                                 t_end_ms=140.0)],
            total_duration_ms=1000.0)
        out = rescale_timer_data(td, 2000.0)      # scale = 2
        assert out.total_duration_ms == 2000.0
        m = out.voicing_marks[0]
        assert (m.t_target_ms, m.t_start_ms, m.t_end_ms) == (200., 150., 300.)
        n = out.nasality_marks[0]
        assert (n.t_open_ms, n.t_close_ms) == (400., 800.)
        p = out.pexp_marks[0]
        assert (p.t_start_ms, p.t_peak_ms, p.t_end_ms) == (200., 240., 280.)


# =============================================================================
# build_occlusion_traces / update_occlusion_traces
# =============================================================================

def _elements(*durations_ms, pause=()):
    """Duck-typed ChainElements: (duration, is_pause) pairs."""
    out = []
    for i, d in enumerate(durations_ms):
        if i in pause:
            out.append(SimpleNamespace(is_pause=True,
                                       pause_duration_ms=d))
        else:
            out.append(SimpleNamespace(is_pause=False, duration_ms=d))
    return out


class TestBuildOcclusionTraces:
    def test_frames_from_elements_when_n_frames_none(self):
        marks = [PexpMark(seg_key='b', pexp_type='burst',
                          t_start_ms=0.0, t_peak_ms=40.0, t_end_ms=80.0)]
        res = build_occlusion_traces(
            _elements(100, 200, 300, pause=(1,)), marks, sr=100.0)
        # 100 + 300 ms of non-pause (pause counts too in the total: the
        # builder sums every element) -> 600 ms at 100 Hz = 60 frames
        assert res.n_frames == 60
        assert len(res.traces) == 1
        assert res.traces[0].occlusion_type == 'plosive'
        assert res.traces[0].frame_start == 0
        assert res.traces[0].frame_peak == 4

    def test_n_frames_override_and_bounds_clamping(self):
        marks = [PexpMark(seg_key='s', pexp_type='frication',
                          t_start_ms=0.0, t_peak_ms=500.0, t_end_ms=900.0)]
        res = build_occlusion_traces([], marks, sr=100.0, n_frames=10)
        tr = res.traces[0]
        assert tr.occlusion_type == 'fricative'
        assert tr.frame_end == 9        # clamped to n_frames-1
        assert tr.frame_peak == 50      # NOT clamped here (guard downstream)


class TestUpdateOcclusionTraces:
    N = 30

    @staticmethod
    def _pval(overrides=None, n=N):
        """Flat trajectory; per-column value overrides {COVTL idx: value}."""
        arr = np.zeros((n, 15))
        for idx, val in (overrides or {}).items():
            arr[:, idx] = val
        return arr

    @staticmethod
    def _result(*traces, n=N):
        return OcclusionTraceResult(
            traces=list(traces),
            rho_correction_curve=np.zeros(n), n_frames=n)

    def test_empty_trajectory_returns_unchanged(self):
        res = OcclusionTraceResult()
        assert update_occlusion_traces(res, np.zeros((0, 15))) is res

    def test_bilabial_ld_correction(self):
        # 'b': LD (idx 5) must reach 0.10; measured 0.40 -> push down
        tr = OcclusionTrace(seg_key='b', frame_start=10, frame_end=20,
                            frame_peak=15, occlusion_type='plosive')
        res = update_occlusion_traces(
            self._result(tr), self._pval({5: 0.40}))
        assert tr.rho_measured == 0.40
        assert bool(tr.needs_correction) is True
        corr = res.rho_correction_curve
        assert corr.shape == (self.N, 15)
        # peak frame gets the full -0.30 deficit on LD
        assert corr[15, 5] == pytest.approx(-0.30)
        # zero outside the occlusion window
        assert (corr[:10, 5] == 0.0).all() and (corr[21:, 5] == 0.0).all()

    def test_alveolar_tty_above_threshold_no_correction(self):
        # 'd': TTY (idx 9) must exceed 0.50; measured 0.80 -> OK
        tr = OcclusionTrace(seg_key='d', frame_start=10, frame_end=20,
                            frame_peak=15, occlusion_type='plosive')
        res = update_occlusion_traces(
            self._result(tr), self._pval({9: 0.80}))
        assert not tr.needs_correction
        assert (res.rho_correction_curve == 0.0).all()

    def test_velar_tcy_correction_with_tbx_bonus(self):
        # 'g': TCY (idx 7) must exceed 1.50 (measured 0.0 -> +1.50),
        # TBX (idx 10) below 3.50 -> bonus deficit*0.5 = +1.75
        tr = OcclusionTrace(seg_key='g', frame_start=10, frame_end=20,
                            frame_peak=15, occlusion_type='plosive')
        res = update_occlusion_traces(self._result(tr), self._pval())
        corr = res.rho_correction_curve
        assert corr[15, 7] == pytest.approx(1.50)
        assert corr[15, 10] == pytest.approx(1.75)

    def test_peak_in_final_pause_guarded(self):
        tr = OcclusionTrace(seg_key='b', frame_start=10, frame_end=20,
                            frame_peak=self.N + 5, occlusion_type='plosive')
        res = update_occlusion_traces(
            self._result(tr), self._pval({5: 0.5}))
        assert not tr.needs_correction
        assert tr.rho_measured == 0.0
        assert (res.rho_correction_curve == 0.0).all()

    def test_negative_peak_guarded(self):
        tr = OcclusionTrace(seg_key='b', frame_start=0, frame_end=20,
                            frame_peak=-3, occlusion_type='plosive')
        update_occlusion_traces(self._result(tr), self._pval())
        assert not tr.needs_correction

    def test_empty_window_skipped(self):
        tr = OcclusionTrace(seg_key='b', frame_start=12, frame_end=12,
                            frame_peak=12, occlusion_type='plosive')
        res = update_occlusion_traces(
            self._result(tr), self._pval({5: 0.5}))
        assert (res.rho_correction_curve == 0.0).all()

    def test_fricative_measures_norm_without_correction(self):
        pval = self._pval()
        pval[15, :4] = [3.0, 4.0, 0.0, 0.0]
        tr = OcclusionTrace(seg_key='s', frame_start=10, frame_end=20,
                            frame_peak=15, occlusion_type='fricative')
        res = update_occlusion_traces(self._result(tr), pval)
        assert tr.rho_measured == pytest.approx(5.0)
        assert not tr.needs_correction
        assert (res.rho_correction_curve == 0.0).all()


# =============================================================================
# build_pexp_curve
# =============================================================================

class TestBuildPexpCurve:
    def test_degenerate_inputs_return_zeros(self):
        assert (build_pexp_curve(TimerData(), 10) == 0.0).all()
        td = TimerData(total_duration_ms=500.0)      # no marks
        assert (build_pexp_curve(td, 10) == 0.0).all()

    def test_burst_shape_rise_peak_decay(self):
        # 1000 ms, 100 frames (10 ms each); burst peaking at 300 ms
        td = TimerData(
            pexp_marks=[PexpMark(pexp_type='burst', amplitude=1.0,
                                 t_start_ms=200.0, t_peak_ms=300.0,
                                 t_end_ms=600.0)],
            total_duration_ms=1000.0, sr=100.0)
        curve = build_pexp_curve(td, 100)
        assert curve.shape == (100,)
        assert (curve >= 0.0).all() and (curve <= 1.5).all()
        i_peak = int(np.argmax(curve))
        assert 29 <= i_peak <= 35                 # around the 300 ms peak
        assert curve[10] == pytest.approx(0.0, abs=1e-9)   # before onset
        assert curve[i_peak] == pytest.approx(1.0, abs=0.3)
        assert curve[70] < curve[i_peak]          # decayed after t_end

    def test_frication_ramp_then_plateau(self):
        td = TimerData(
            pexp_marks=[PexpMark(pexp_type='frication', amplitude=0.8,
                                 t_start_ms=100.0, t_peak_ms=300.0,
                                 t_end_ms=500.0)],
            total_duration_ms=1000.0, sr=100.0)
        curve = build_pexp_curve(td, 100)
        assert curve[5] == pytest.approx(0.0, abs=1e-9)
        # rising through the ramp, plateau at the end of the mark
        assert curve[15] < curve[35]
        assert curve[45] == pytest.approx(0.8, abs=0.1)
        assert curve[60] < 0.8                    # released after t_end

    def test_overlapping_marks_take_the_max(self):
        td = TimerData(
            pexp_marks=[
                PexpMark(pexp_type='frication', amplitude=0.5,
                         t_start_ms=0.0, t_peak_ms=100.0, t_end_ms=500.0),
                PexpMark(pexp_type='burst', amplitude=1.2,
                         t_start_ms=0.0, t_peak_ms=200.0, t_end_ms=400.0),
            ],
            total_duration_ms=500.0, sr=100.0)
        curve = build_pexp_curve(td, 50)
        assert curve.max() <= 1.5
        assert curve.max() > 0.9                  # the burst dominates


# =============================================================================
# build_reference_timers
# =============================================================================

class TestBuildReferenceTimers:
    @staticmethod
    def _build():
        flat = ['b', 'a', 'n', 'l', 'i']
        nodes = [
            GestureNode(seg_key='b', kind='C'),
            GestureNode(seg_key='a', kind='V'),
            GestureNode(seg_key='n', kind='C'),
            GestureNode(seg_key='l', kind='C'),
            GestureNode(seg_key='i', kind='V'),
        ]
        blocks = [
            BlockInfo(n_steps=20, kind='cluster'),
            BlockInfo(n_steps=20, kind='plateau'),
            BlockInfo(n_steps=20, kind='cluster'),
            BlockInfo(n_steps=20, kind='plateau'),
            BlockInfo(n_steps=20, kind='terminal'),
        ]
        return build_reference_timers(flat, nodes, blocks, sr=100.0)

    def test_voicing_marks_consonants_only(self):
        td = self._build()
        keys = [m.seg_key for m in td.voicing_marks]
        assert keys == ['b', 'n', 'l']
        b = td.voicing_marks[0]
        assert b.is_voiced is True                 # b in VOICED_CONSONANT_KEYS
        assert b.glottal_shape == 'modal'
        assert b.supraglottic_track == 'lip'
        assert b.t_start_ms < b.t_target_ms        # 25 ms pre-voicing

    def test_nasality_marks(self):
        td = self._build()
        assert len(td.nasality_marks) == 1
        m = td.nasality_marks[0]
        assert m.seg_key == 'n'
        assert m.t_close_ms > m.t_open_ms

    def test_lateral_marks_without_virtual_target(self):
        td = self._build()
        assert len(td.lateral_marks) == 1
        m = td.lateral_marks[0]
        assert m.seg_key == 'l'
        assert m.has_virtual_target is False
        assert m.ts3_target == -1.0

    def test_total_duration_follows_blocks(self):
        td = self._build()
        assert td.total_duration_ms == pytest.approx(100 * 1000.0 / 100.0)

    def test_pause_nodes_ignored(self):
        flat = ['b', 'a']
        nodes = [GestureNode(seg_key='b', kind='C'),
                 GestureNode(seg_key='a', kind='V'),
                 GestureNode(seg_key='|', kind='pause')]
        blocks = [BlockInfo(n_steps=10, kind='cluster'),
                  BlockInfo(n_steps=10, kind='plateau')]
        td = build_reference_timers(flat, nodes, blocks, sr=100.0)
        assert [m.seg_key for m in td.voicing_marks] == ['b']


# =============================================================================
# debug printers
# =============================================================================

class TestDebugPrinters:
    def test_print_empty(self, capsys):
        print_voicing_timer([])
        print_nasality_timer([])
        print_lateral_timer([])
        out = capsys.readouterr().out
        assert out.count('No marks') == 3

    def test_print_marks(self, capsys):
        print_voicing_timer([VoicingMark(
            seg_key='b', t_target_ms=100.0, t_start_ms=75.0, t_end_ms=150.0,
            supraglottic_track='lip', glottal_shape='modal')])
        print_nasality_timer([NasalityMark(t_open_ms=100.0, t_close_ms=200.0)])
        print_lateral_timer([])
        out = capsys.readouterr().out
        assert '[voicing_timer] 1 marks' in out
        assert 'PRE-VOICING' in out
        assert '[nasality_timer] 1 marks' in out
