# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Targeted tests for glottal_source.py (P1 hardening).

Complements test_glottal_classification.py (which locks the BUG-ACTIVE
classifications) with the rule engine's numeric layers:

  * the remaining classification branches (nasals, approximants, h, ?),
  * preset lookup fallbacks (_lookup_preset_vector),
  * the smoothing primitives (_exponential_smoothing_1st_order,
    _asymmetric_smoothing) and smooth_glottal_trajectory edges,
  * compute_f0_contour (micro-prosody / hold / clamp),
  * compute_pressure (E^1.2 mapping + phonation floor),
  * compute_pulmonary_effort (+ _from_timers),
  * build_glottis_trajectory silence / pre-voicing closures,
  * classify_nodes_to_shape_events (block-kind coverage).
"""
import numpy as np
import pytest

import vtl_synth.core.glottal_source as gs
from vtl_synth.core.constants import EFFORT_DEFAULTS, JD3_GLOTTIS_PRESETS
from vtl_synth.core.glottal_source import (
    P_MIN,
    P_MIN_PHONATION,
    _asymmetric_smoothing,
    _exponential_smoothing_1st_order,
    _lookup_preset_vector,
    build_glottis_trajectory,
    classify_nodes_to_shape_events,
    compute_f0_contour,
    compute_pressure,
    compute_pulmonary_effort,
    compute_pulmonary_effort_from_timers,
    glottal_shape_for_segment,
    smooth_glottal_trajectory,
)
from vtl_synth.core.timers import TimerData, VoicingMark
from vtl_synth.core.types import BlockInfo, GestureNode


class TestClassificationCompletion:
    @pytest.mark.parametrize('key', ['m', 'n', 'N', 'J'])
    def test_nasals_always_modal(self, key):
        assert glottal_shape_for_segment(key, 0.0) == 'modal'

    @pytest.mark.parametrize('key', ['l', 'L', 'w', 'j', 'R'])
    def test_approximants_modal(self, key):
        assert glottal_shape_for_segment(key, 0.0) == 'modal'

    @pytest.mark.parametrize('key', ['h', '?'])
    def test_glottal_constriction_voiceless_fricative(self, key):
        # 'h' and the glottal stop share the voiceless-fricative preset
        assert glottal_shape_for_segment(key, 1.0) == 'voiceless-fricative'


class TestPresetLookup:
    def test_valid_label_returns_preset_vector(self):
        v = _lookup_preset_vector('modal')
        assert v.shape == (11,)
        np.testing.assert_allclose(v, JD3_GLOTTIS_PRESETS['modal'].to_vector())

    def test_voiceless_label_normalized(self):
        np.testing.assert_allclose(
            _lookup_preset_vector('voiceless'),
            JD3_GLOTTIS_PRESETS['voiceless-fricative'].to_vector())

    def test_unknown_label_falls_back_to_modal(self):
        np.testing.assert_allclose(
            _lookup_preset_vector('no-such-shape'),
            JD3_GLOTTIS_PRESETS['modal'].to_vector())

    def test_absolute_fallback_when_presets_empty(self, monkeypatch):
        monkeypatch.setattr(gs, 'JD3_GLOTTIS_PRESETS', {})
        v = _lookup_preset_vector('modal')
        assert v[0] == 120.0        # f0
        assert v[1] == 8000.0       # pressure
        assert v[6] == 1.0          # rel_amp


class TestSmoothingPrimitives:
    def test_first_order_smoothing_passthrough_on_zero_tau(self):
        x = np.array([0.0, 1.0, 0.5])
        out = _exponential_smoothing_1st_order(x, tau_ms=0.0, sr=100.0)
        np.testing.assert_array_equal(out, x)

    def test_first_order_smoothing_empty(self):
        out = _exponential_smoothing_1st_order(np.array([]), 12.0, 100.0)
        assert len(out) == 0

    def test_first_order_smoothing_converges_to_constant(self):
        out = _exponential_smoothing_1st_order(np.ones(50), 12.0, 100.0)
        np.testing.assert_allclose(out, 1.0, atol=1e-12)

    def test_asymmetric_smoothing_empty(self):
        out = _asymmetric_smoothing(np.array([]), sr=100.0)
        assert len(out) == 0

    def test_asymmetric_rise_faster_than_fall(self):
        # step 0 -> 1: the rise output reaches further in one frame
        # than the fall output drops in one frame from 1 -> 0
        rise = _asymmetric_smoothing(
            np.array([0.0, 1.0]), sr=100.0, tau_rise_ms=6.0, tau_fall_ms=20.0)
        fall = _asymmetric_smoothing(
            np.array([1.0, 0.0]), sr=100.0, tau_rise_ms=6.0, tau_fall_ms=20.0)
        assert rise[1] > 0.5          # fast attack
        assert fall[1] > 0.5          # slow release (energy retention)


class TestSmoothTrajectory:
    def test_empty_events_return_zeros(self):
        out = smooth_glottal_trajectory([], n_frames=10)
        assert out.shape == (10, 11)
        assert (out == 0.0).all()

    def test_out_of_range_event_frames_clipped(self):
        # events beyond n_frames and zero-length spans must not raise
        out = smooth_glottal_trajectory(
            [('modal', 5), ('stop', 30), ('breathy', 40)], n_frames=20)
        assert out.shape == (20, 11)

    def test_columns_0_and_1_left_to_f0_pressure(self):
        out = smooth_glottal_trajectory([('modal', 0)], n_frames=30)
        # cols 0/1 carry the preset's own f0/pressure (Step 3/4 overwrite
        # them later); the shape columns 2+ are the filtered preset
        modal = JD3_GLOTTIS_PRESETS['modal'].to_vector()
        np.testing.assert_allclose(out[:, 0], modal[0])
        np.testing.assert_allclose(out[:, 1], modal[1])
        assert not np.allclose(out[:, 2:], 0.0)


class TestF0Contour:
    def test_micro_prosody_follows_effort_deviation(self):
        n = 10
        E = np.ones(n)
        E[:5] = 0.5                       # 0.25 below the mean of 0.75
        f0 = compute_f0_contour(n, 100.0, E, np.ones(n))
        assert f0[0] < f0[-1]
        np.testing.assert_allclose(f0[-1], 100.0 + 10.0 * 0.25)

    def test_unvoiced_stretch_holds_last_voiced_value(self):
        n = 12
        E = np.ones(n)
        V = np.array([1., 1., 1., 0., 0., 0., 1., 1., 1., 1., 1., 1.])
        f0 = compute_f0_contour(n, 100.0, E, V)
        np.testing.assert_allclose(f0[3:6], f0[2])

    def test_clamped_to_physiological_range(self):
        E = np.full(4, 100.0)             # huge micro-prosody deviation
        f0 = compute_f0_contour(4, 100.0, E, np.ones(4), k_micro=1000.0)
        assert (f0 <= 600.0).all() and (f0 >= 40.0).all()


class TestPressure:
    def test_e_clamped_and_mapped(self):
        P = compute_pressure(np.array([0.0, 1.0, 3.0]))
        assert P[0] == 0.0
        np.testing.assert_allclose(
            P[1], EFFORT_DEFAULTS.P_max)
        np.testing.assert_allclose(
            P[2], EFFORT_DEFAULTS.P_max * 1.5 ** 1.2)

    def test_phonation_floor_on_voiced_frames(self):
        E = np.array([0.0, 0.0])
        V = np.array([1.0, 0.0])
        P = compute_pressure(E, V=V)
        assert P[0] == P_MIN_PHONATION
        assert P[1] == P_MIN


class TestPulmonaryEffort:
    DOC_E = np.array([0.0, 0.0, 0.5, 1.0, 1.0, 0.5, 0.0, 0.0])
    DOC_V = np.array([0.8, 0.9, 0.5, 1.0, 1.0, 0.5, 0.1, 0.0])
    DOC_VO = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.5])

    def test_empty_input(self):
        out = compute_pulmonary_effort(np.array([]), np.array([]),
                                       np.array([]))
        assert len(out) == 0

    def test_prevoicing_floor_sustained(self):
        # 30 silent frames, then a voiced mark (V>threshold) with E=0:
        # the demand jumps to 0.30 and the smoothing (alpha~0.45/frame)
        # has converged by the end of the mark
        n = 30
        E = np.zeros(n)
        V = np.zeros(n)
        V[20:] = 1.0
        out = compute_pulmonary_effort(E, V, np.zeros(n))
        assert out[-1] == pytest.approx(0.30, abs=0.02)

    def test_nasal_floor_sustained(self):
        # same with a nasal mark (VO>threshold, V=0): demand 0.25
        n = 30
        E = np.zeros(n)
        VO = np.zeros(n)
        VO[20:] = 1.0
        out = compute_pulmonary_effort(E, np.zeros(n), VO)
        assert out[-1] == pytest.approx(0.25, abs=0.02)

    def test_envelope_dominates_when_higher(self):
        out = compute_pulmonary_effort(np.ones(20), np.zeros(20),
                                       np.zeros(20))
        np.testing.assert_allclose(out, 1.0, atol=1e-9)

    def test_envelope_clamped_at_1_5(self):
        out = compute_pulmonary_effort(np.full(20, 2.0), np.zeros(20),
                                       np.zeros(20))
        np.testing.assert_allclose(out, 1.5, atol=1e-9)

    def test_vo_and_v_aligned_when_longer(self):
        # V/VO longer than E are truncated to len(E)
        out = compute_pulmonary_effort(
            np.ones(2), np.ones(10), np.ones(10))
        assert len(out) == 2

    def test_output_never_negative(self):
        rng = np.random.default_rng(1)
        E = rng.uniform(0.0, 1.5, 50)
        out = compute_pulmonary_effort(E, rng.uniform(0, 1, 50),
                                       rng.uniform(0, 1, 50))
        assert (out >= 0.0).all()

    def test_from_timers_uses_voicing_marks(self):
        # one voiced stop mark over the first half of a 1000 ms utterance
        td = TimerData(
            voicing_marks=[VoicingMark(
                seg_key='b', t_target_ms=250.0, is_voiced=True,
                t_start_ms=0.0, t_end_ms=500.0, glottal_shape='modal')],
            total_duration_ms=1000.0, sr=100.0)
        E = np.zeros(100)
        out = compute_pulmonary_effort_from_timers(E, td)
        assert len(out) == 100
        # during the voiced mark the effort is sustained around the floor
        assert out[20:50].min() > 0.0


class TestBuildGlottisTrajectory:
    # n_frames must exceed filtfilt's padlen (~9 at 100 Hz)
    N = 20

    def _run(self, E, V):
        assert len(E) == self.N
        return build_glottis_trajectory(
            [('modal', 0)], len(E), E, V, f0_base=100.0)

    def test_true_silence_zeroed(self):
        E = np.zeros(self.N)
        V = np.zeros(self.N)
        g = self._run(E, V)
        assert (g[:, 1] == P_MIN).all()     # pressure
        assert (g[:, 6] == 0.0).all()       # rel_amp

    def test_voiced_closure_prevoicing_bounds(self):
        # E collapsed (closure) but voicing maintained: rel_amp bounded
        # to [0.10, 0.18] and pressure forced to 1800 dPa (C3)
        E = np.zeros(self.N)
        V = np.ones(self.N)
        g = self._run(E, V)
        assert (g[1:, 6] >= 0.10 - 1e-9).all()
        assert (g[1:, 6] <= 0.18 + 1e-9).all()
        np.testing.assert_allclose(g[1:, 1], 1800.0)

    def test_normal_phonation_rel_amp_follows_effort(self):
        E = np.full(self.N, 1.0)
        V = np.ones(self.N)
        g = self._run(E, V)
        np.testing.assert_allclose(g[:, 6], 1.0, atol=0.02)
        assert g[0, 0] > 0.0                # f0 defined everywhere


def _node(key, kind):
    return GestureNode(seg_key=key, kind=kind)


def _blocks(specs):
    return [BlockInfo(n_steps=n, kind=k, pre_token=pre, post_token=post)
            for (n, k, pre, post) in specs]


class TestClassifyNodesToShapeEvents:
    def test_silence_blocks_emit_voiceless(self):
        nodes = [_node('|', 'pause'), _node('a', 'V')]
        blocks = _blocks([
            (5, 'initial', '', ''),
            (10, 'plateau', 'V', 'V'),
            (5, 'terminal', '', ''),
        ])
        events = classify_nodes_to_shape_events(nodes, blocks)
        by_frame = {frame: label for label, frame in events}
        assert by_frame[0] == 'voiceless'      # initial
        assert by_frame[5] == 'modal'          # plateau
        assert by_frame[15] == 'voiceless'     # terminal

    def test_background_emits_modal(self):
        events = classify_nodes_to_shape_events(
            [_node('a', 'V')],
            _blocks([(10, 'background', 'V', 'V')]))
        assert events == [('modal', 0)]

    def test_vowel_context_cluster_modal(self):
        nodes = [_node('b', 'C'), _node('a', 'V')]
        events = classify_nodes_to_shape_events(
            nodes, _blocks([(10, 'cluster', 'V', 'V')]))
        assert events == [('modal', 0)]

    def test_consonant_context_cluster_voiceless_without_nodes(self):
        # no non-pause nodes: C->V transition reads as voiceless
        events = classify_nodes_to_shape_events(
            [_node('|', 'pause')],
            _blocks([(10, 'decay', 'O', 'V')]))
        assert events == [('voiceless', 0)]

    def test_default_block_kind_modal(self):
        events = classify_nodes_to_shape_events(
            [_node('a', 'V')],
            _blocks([(10, 'whatever-else', '', '')]))
        assert events == [('modal', 0)]
