# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Smoke tests for the legacy V1 public API (kept for compatibility).

The production engine is the syllabic trajectory (build_phrase_tract /
Pipeline, engine='syl'), but the V1 chain remains a documented public
entry point (``from vtl_synth import text_to_tract``, the synth module
and the ``vtl_synth.vtl.api`` facade).  These tests only lock the
ENTRY-POINT CONTRACT (imports resolve, shapes/dtypes/types are sane) —
the V1 signal itself is intentionally NOT pinned here (see LEGACY.md
for the coverage policy).
"""
import numpy as np
import pytest

import vtl_synth
from vtl_synth import (
    build_phrase_tract,
    text_to_tract,
    is_vtl_available,
    get_vtl_info,
    synthesize_to_wav,
)


class TestPublicExports:
    def test_all_exports_resolve(self):
        for name in vtl_synth.__all__:
            assert hasattr(vtl_synth, name), name

    def test_vtl_api_facade_reexports(self):
        # mirrors the vtl-pipeline reference repository layout
        import vtl_synth.vtl.api as api
        import vtl_synth.core.synth as synth
        for name in api.__all__:
            assert getattr(api, name) is getattr(synth, name), name


class TestTextToTractV1:
    def test_smoke_ba_shapes(self):
        tract, glottis = text_to_tract('ba', return_data=True, verbose=False)
        assert tract.ndim == 2 and tract.shape[1] == 19
        assert glottis.ndim == 2 and glottis.shape[0] == tract.shape[0]
        assert glottis.shape[1] == 11
        assert np.isfinite(tract).all() and np.isfinite(glottis).all()

    def test_smoke_docstring_example(self):
        data = text_to_tract('a i u', return_data=True, verbose=False)
        assert data[0].shape[1] == 19
        assert data[1].shape[1] == 11

    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            text_to_tract('...', return_data=True, verbose=False)


class TestSynthFacade:
    def test_vtl_available_and_info(self):
        assert is_vtl_available() is True
        info = get_vtl_info()
        assert isinstance(info, dict)
        for key in ('available', 'version', 'sr_audio',
                    'n_tract_params', 'n_glottis_params'):
            assert key in info, key
        assert info['sr_audio'] == 44100
        assert info['n_tract_params'] == 19
        assert info['n_glottis_params'] == 11

    def test_param_info_tables(self):
        from vtl_synth.core.synth import (
            get_tract_param_info, get_glottis_param_info,
        )
        tract = get_tract_param_info()
        glottis = get_glottis_param_info()
        assert len(tract) == 19 and len(glottis) == 11
        assert {'name', 'min', 'max'} <= set(tract[0])

    def test_synthesize_to_wav_smoke(self, tmp_path):
        # synthesize_to_wav takes a native .tract FILE (19+11 columns)
        tract = np.tile(
            np.array([0.0, -4.0, 0.0, -3.0, 0.5, 0.5, 0.0, -0.1, 0.5, -1.0,
                      4.0, -1.0, 3.0, -0.3, 0.0, 0.0, 0.0, 0.2, 0.2]),
            (100, 1))
        glottis = np.tile(
            np.array([120.0, 4000.0, 0.01, 0.02, 0.05, 1.2, 1.0, 0.05,
                      0.0, 0.0, 0.0]), (100, 1))
        tract_file = tmp_path / 'v1.tract'
        np.savetxt(tract_file, np.hstack([tract, glottis]))
        wav = tmp_path / 'v1.wav'
        synthesize_to_wav(str(tract_file), str(wav))
        assert wav.stat().st_size > 44          # RIFF header + samples

    def test_syl_engine_still_the_production_path(self):
        # guard the coexistence: the default engine of the orchestrator
        # must remain the syllabic one, not the V1 chain
        import inspect
        from vtl_synth.core.pipeline import Pipeline
        sig = inspect.signature(Pipeline.__init__)
        assert sig.parameters['engine'].default == 'syl'

    def test_v1_call_does_not_leak_into_next_syl_build(self):
        # 2026-11-13: text_to_tract left a stale
        # continuous._LAST_PVAL_STATE that the next build_phrase_tract
        # consumed (envelope/timer channel) — f0 max of 'a i u' shifted
        # from 116.560262 to 112.097452. build_phrase_tract now clears
        # the channel before dispatching the engine.
        from vtl_synth.core.build_phrase_tract import build_phrase_tract

        def _build():
            _, glottis = build_phrase_tract(
                'a i u', phrase_id=None, label='iso', return_data=True,
                verbose=False)
            return glottis[:, 0].copy()

        pristine_f0 = _build()
        text_to_tract('a i u', return_data=True, verbose=False)
        after_f0 = _build()
        np.testing.assert_array_equal(after_f0, pristine_f0)
