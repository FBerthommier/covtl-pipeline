# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Targeted tests for assemble_tract.py (P1 hardening).

Focuses on the branches the synthesis smoke tests do not reach:
  * _upsample pass-through / 1-D / >2-D paths,
  * extension alignment (truncate / pad) in AssembleTract.assemble,
  * the structured-dtype tract input and the COVTL column mapping,
  * the legacy glottis fallback (direct + via assemble exception path),
  * the hard downstream corrections (velar TBY/TCX/TCY clamps + LD floor),
  * write_tract_file_vtl_native.
"""
import numpy as np
import pytest

import vtl_synth.core.assemble_tract as at
from vtl_synth.core.assemble_tract import AssembleTract, _upsample
from vtl_synth.core.constants import (
    COVTL_PARAMS,
    COVTL_TO_FULL,
    IDX_TS3,
    IDX_VO,
    IDX_VS,
    TCX_VELAR_OCCLUSION_MAX,
    TCY_VELAR_OCCLUSION_MIN,
    TBY_VELAR_OCCLUSION_MIN,
)

N_COVTL = len(COVTL_PARAMS)          # 15
IDX_LD = at.IDX_LD                    # 5 in the 19-param vector
IDX_TBY = at.IDX_TBY
IDX_TCX = at.IDX_TCX
IDX_TCY = at.IDX_TCY


def _tract_frames(n=20):
    """Plain (n, 15) COVTL-ordered trajectory, value = column index."""
    frames = np.tile(np.arange(N_COVTL, dtype=float), (n, 1))
    frames[:, 0] *= -1.0              # negative HX to spot mapping errors
    return frames


def _extensions(n=20, with_ev=False):
    ext = {
        'VO': np.linspace(0.0, 1.0, n),
        'VS': np.full(n, 0.25),
        'glottis': np.zeros((n, 11)),
    }
    if with_ev:
        ext['E'] = np.full(n, 1.0)
        ext['V'] = np.ones(n)
    return ext


class TestUpsample:
    def test_passthrough_sr_equal_returns_copy(self):
        data = _tract_frames(20)
        out = _upsample(data, sr_in=400.0, sr_out=400.0)
        assert out is not data
        np.testing.assert_array_equal(out, data)

    def test_1d_linear_interpolation(self):
        data = np.array([0.0, 10.0])
        out = _upsample(data, sr_in=100.0, sr_out=400.0)
        assert out.shape == (8,)
        np.testing.assert_allclose(out[:4], [0.0, 2.5, 5.0, 7.5])
        # indices are clipped below n_in-1: the tail sits just under 10
        np.testing.assert_allclose(out[4:], 9.99)

    def test_2d_frame_interpolation(self):
        data = np.array([[0.0, 1.0], [10.0, -1.0]])
        out = _upsample(data, sr_in=100.0, sr_out=400.0)
        assert out.shape == (8, 2)
        assert out.dtype == data.dtype

    def test_general_nd_preserves_trailing_shape(self):
        data = np.random.default_rng(0).normal(size=(2, 3, 2))
        out = _upsample(data, sr_in=100.0, sr_out=400.0)
        assert out.shape == (8, 3, 2)


class TestAssembleAlignment:
    def test_sr_passthrough_keeps_frames(self):
        asm = AssembleTract()
        n = 20
        tract, glottis = asm.assemble(
            _tract_frames(n), _extensions(n), sr_in=400.0, sr_out=400.0)
        assert tract.shape == (n, 19)
        assert glottis.shape == (n, 11)

    # alignment tests run at sr_in == sr_out so the frame grid is
    # preserved (no interpolation) and assertions stay exact
    def test_longer_extensions_truncated(self):
        asm = AssembleTract()
        n = 20
        ext = _extensions(n)
        ext['VO'] = np.linspace(0.0, 1.0, n + 5)
        ext['glottis'] = np.zeros((n + 5, 11))
        tract, glottis = asm.assemble(_tract_frames(n), ext,
                                      sr_in=100.0, sr_out=100.0)
        np.testing.assert_allclose(
            tract[:, IDX_VO], np.linspace(0.0, 1.0, n + 5)[:n])
        assert glottis.shape == (n, 11)

    def test_shorter_extensions_zero_padded(self):
        asm = AssembleTract()
        n = 20
        ext = _extensions(n)
        ext['VO'] = np.ones(12)
        tract, _ = asm.assemble(_tract_frames(n), ext,
                                sr_in=100.0, sr_out=100.0)
        assert (tract[:12, IDX_VO] == 1.0).all()
        assert (tract[12:, IDX_VO] == 0.0).all()

    def test_ts3_ortho_shorter_is_padded(self):
        asm = AssembleTract()
        n = 20
        ts3 = np.full(12, 1.0)
        tract, _ = asm.assemble(_tract_frames(n), _extensions(n),
                                sr_in=100.0, sr_out=100.0, ts3_ortho=ts3)
        core_ts3 = _tract_frames(n)[:, COVTL_PARAMS.index('TS3')]
        # additive override on the first 12 frames only
        np.testing.assert_allclose(tract[:12, IDX_TS3], core_ts3[:12] + 1.0)
        np.testing.assert_allclose(tract[12:, IDX_TS3], core_ts3[12:])

    def test_vs_ortho_longer_is_truncated_and_wins(self):
        asm = AssembleTract()
        n = 20
        ext = _extensions(n)
        tract, _ = asm.assemble(_tract_frames(n), ext,
                                vs_ortho=np.full(n + 7, 0.75))
        np.testing.assert_allclose(tract[:, IDX_VS], 0.75)

    def test_vs_falls_back_to_extension_data(self):
        asm = AssembleTract()
        tract, _ = asm.assemble(_tract_frames(20), _extensions(20))
        np.testing.assert_allclose(tract[:, IDX_VS], 0.25)


class TestAssembleMapping:
    def test_structured_dtype_uses_field_names(self):
        n = 10
        frames = np.zeros(
            n, dtype=[('HX', 'f8'), ('JA', 'f8'), ('TS3', 'f8')])
        frames['HX'] = -1.5
        frames['JA'] = 0.5
        frames['TS3'] = 2.0
        tract, _ = AssembleTract().assemble(
            frames, _extensions(n), sr_in=100.0, sr_out=100.0)
        np.testing.assert_allclose(tract[:, COVTL_TO_FULL['HX']], -1.5)
        np.testing.assert_allclose(tract[:, COVTL_TO_FULL['JA']], 0.5)
        np.testing.assert_allclose(tract[:, COVTL_TO_FULL['TS3']], 2.0)

    def test_plain_array_maps_covtl_order(self):
        tract, _ = AssembleTract().assemble(
            _tract_frames(20), _extensions(20),
            sr_in=100.0, sr_out=100.0)
        frames = _tract_frames(20)
        for j, key in enumerate(COVTL_PARAMS):
            np.testing.assert_allclose(
                tract[:, COVTL_TO_FULL[key]], frames[:, j],
                err_msg=key)

    def test_trx_try_left_at_zero(self):
        tract, _ = AssembleTract().assemble(_tract_frames(20), _extensions(20))
        assert (tract[:, 14] == 0.0).all()
        assert (tract[:, 15] == 0.0).all()


class TestLegacyGlottis:
    def test_direct_e_mapping_and_silence(self):
        n = 4
        ext = {
            'glottis': np.zeros((n, 11)),
            'E': np.array([0.02, 1.0, 1.6, 0.10]),
            'V': np.zeros(n),
            'f0': np.array([100., 110., 120., 130.]),
        }
        g = AssembleTract._legacy_glottis(ext, n)
        # f0 column copied
        np.testing.assert_allclose(g[:, 0], ext['f0'])
        # E clamped to [0, 1.5]; E^1.2 mapping on phonatory frames
        from vtl_synth.core.constants import EFFORT_DEFAULTS
        p_min, p_max = EFFORT_DEFAULTS.P_min, EFFORT_DEFAULTS.P_max
        assert g[0, 1] == p_min                      # silence (E<=0.05)
        np.testing.assert_allclose(
            g[1, 1], p_min + 1.0 ** 1.2 * (p_max - p_min))
        np.testing.assert_allclose(
            g[2, 1], p_min + 1.5 ** 1.2 * (p_max - p_min))
        # rel_amp column: max(E_clamp, 0.25), 0 in silence
        np.testing.assert_allclose(g[1, 6], 1.0)
        np.testing.assert_allclose(g[2, 6], 1.5)
        np.testing.assert_allclose(g[3, 6], 0.25)
        assert g[0, 6] == 0.0

    def test_phonation_floor_with_voicing(self):
        n = 2
        ext = {
            'glottis': np.zeros((n, 11)),
            'E': np.array([0.0, 1.0]),
            'V': np.array([1.0, 1.0]),
        }
        g = AssembleTract._legacy_glottis(ext, n)
        # frame 0: E=0 -> silence pressure, but voiced -> floor 3000 dPa
        from vtl_synth.core.glottal_source import P_MIN_PHONATION
        assert g[0, 1] == P_MIN_PHONATION

    def test_assemble_uses_legacy_when_no_shape_events(self):
        n = 16
        ext = _extensions(n)
        ext['f0'] = np.full(n, 123.0)
        _, glottis = AssembleTract().assemble(_tract_frames(n), ext)
        np.testing.assert_allclose(glottis[:, 0], 123.0)

    def test_assemble_falls_back_on_glottis_error(self, monkeypatch):
        import vtl_synth.core.glottal_source as gs
        monkeypatch.setattr(
            gs, 'build_glottis_trajectory',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
        n = 16
        ext = _extensions(n, with_ev=True)
        ext['f0'] = np.full(n, 200.0)
        ext['shape_events'] = [('modal', 0)]
        _, glottis = AssembleTract().assemble(_tract_frames(n), ext)
        # legacy path: f0 column copied verbatim
        np.testing.assert_allclose(glottis[:, 0], 200.0)

    def test_assemble_classifies_segments_when_events_missing(self):
        from types import SimpleNamespace
        n = 16
        ext = _extensions(n)
        ext['segments'] = [
            SimpleNamespace(key='s', kind='C', t_start=0.0, t_end=50.0,
                            voice=False),
        ]
        _, glottis = AssembleTract().assemble(_tract_frames(n), ext)
        assert glottis.shape == (n * 4, 11)   # 100->400 Hz upsample


class TestDownstreamCorrections:
    @staticmethod
    def _full_tract(n=20, ld=-3.0, tby=-5.0, tcx=5.0, tcy=-5.0):
        tract = np.zeros((n, 19))
        tract[:, IDX_LD] = ld
        tract[:, IDX_TBY] = tby
        tract[:, IDX_TCX] = tcx
        tract[:, IDX_TCY] = tcy
        return tract

    def test_velar_clamps_apply_in_occlusion_window(self, monkeypatch):
        monkeypatch.setattr(at, 'clamp_tongue_params', True)
        tract = self._full_tract()
        # velar cluster frames 2..12 (n_cluster=10): center=7,
        # half_win = max(1, int(10*0.30/2)) = 1 -> window 6..8
        AssembleTract._apply_downstream_corrections(
            tract, 20, 100.0,
            {'consonant_frames': [
                {'keys': ['g'], 'frame_start': 2, 'frame_end': 12}]})
        assert tract[7, IDX_TBY] == pytest.approx(TBY_VELAR_OCCLUSION_MIN)
        assert tract[7, IDX_TCX] == pytest.approx(TCX_VELAR_OCCLUSION_MAX)
        assert tract[7, IDX_TCY] == pytest.approx(TCY_VELAR_OCCLUSION_MIN)
        # outside the occlusion window: untouched
        assert tract[2, IDX_TBY] == -5.0
        assert tract[12, IDX_TBY] == -5.0

    def test_palatal_velar_skipped(self, monkeypatch):
        monkeypatch.setattr(at, 'clamp_tongue_params', True)
        tract = self._full_tract()
        AssembleTract._apply_downstream_corrections(
            tract, 20, 100.0,
            {'consonant_frames': [
                {'keys': ['g'], 'frame_start': 2, 'frame_end': 12,
                 'is_palatal': True}]})
        assert (tract[:, IDX_TBY] == -5.0).all()

    def test_non_velar_cluster_untouched(self, monkeypatch):
        monkeypatch.setattr(at, 'clamp_tongue_params', True)
        tract = self._full_tract()
        AssembleTract._apply_downstream_corrections(
            tract, 20, 100.0,
            {'consonant_frames': [
                {'keys': ['b', 'd'], 'frame_start': 2, 'frame_end': 12}]})
        assert (tract[:, IDX_TBY] == -5.0).all()

    def test_empty_cluster_window_untouched(self, monkeypatch):
        monkeypatch.setattr(at, 'clamp_tongue_params', True)
        tract = self._full_tract()
        AssembleTract._apply_downstream_corrections(
            tract, 20, 100.0,
            {'consonant_frames': [
                {'keys': ['g'], 'frame_start': 5, 'frame_end': 5}]})
        assert (tract[:, IDX_TBY] == -5.0).all()

    def test_clamps_disabled_by_default(self):
        tract = self._full_tract()
        assert at.clamp_tongue_params is False
        AssembleTract._apply_downstream_corrections(
            tract, 20, 100.0,
            {'consonant_frames': [
                {'keys': ['g'], 'frame_start': 2, 'frame_end': 12}]})
        assert (tract[:, IDX_TBY] == -5.0).all()

    def test_ld_floor_clamps_negatives(self):
        tract = self._full_tract()
        AssembleTract._apply_downstream_corrections(tract, 20, 100.0, {})
        assert (tract[:, IDX_LD] == at.LD_FLOOR).all()

    def test_ld_floor_disabled_when_none(self, monkeypatch):
        monkeypatch.setattr(at, 'LD_FLOOR', None)
        tract = self._full_tract()
        AssembleTract._apply_downstream_corrections(tract, 20, 100.0, {})
        assert (tract[:, IDX_LD] == -3.0).all()


class TestWriters:
    def test_write_tract_file_header(self, tmp_path):
        from vtl_synth.core.constants import (
            GLOTTIS_PARAM_NAMES, TRACT_PARAM_NAMES,
        )
        tract, glottis = np.zeros((3, 19)), np.zeros((3, 11))
        out = tmp_path / 'x.tract'
        AssembleTract.write_tract_file(tract, glottis, str(out), sr=400)
        lines = out.read_text().splitlines()
        assert lines[0] == '# VTL tract sequence file'
        assert '# sample_rate: 400' in lines
        assert f"# n_frames: 3" in lines
        assert f"# tract_param_names: {' '.join(TRACT_PARAM_NAMES)}" in lines
        assert f"# glottis_param_names: {' '.join(GLOTTIS_PARAM_NAMES)}" in lines
        assert '# ---' in lines
        assert len([l for l in lines if not l.startswith('#')]) == 3

    def test_write_tract_file_vtl_native(self, tmp_path):
        tract, glottis = np.zeros((3, 19)), np.zeros((3, 11))
        tract[:, 0] = 0.5
        out = tmp_path / 'x_native.tract'
        AssembleTract.write_tract_file_vtl_native(
            tract, glottis, str(out), sr=400)
        lines = out.read_text().splitlines()
        assert len(lines) == 3                     # no header, one frame/line
        for line in lines:
            tokens = line.split()
            assert len(tokens) == 19 + 11          # 19 tract + 11 glottis
        assert lines[0].split()[0] == '0.500000'
