# -*- coding: utf-8 -*-
"""E2E non-regression test against regression_baselines.json (schema 2).

The baselines are the acoustically validated state (2026-09-04, TS3
override included). After an INTENTIONAL change to the signal:
    python scripts/regen_baselines.py
then rerun the tests.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from vtl_synth.core.build_phrase_tract import build_phrase_tract

BASELINES_PATH = Path(__file__).resolve().parent.parent / 'regression_baselines.json'
QUANT = 6

BASELINES = json.loads(BASELINES_PATH.read_text(encoding='utf-8'))
PHRASES = BASELINES['phrases']


def _build(phrase):
    result = build_phrase_tract(phrase, phrase_id=None, label='pytest',
                                return_data=True, verbose=False)
    return result[0], result[1]


def _stats(vec):
    v = np.asarray(vec, dtype=np.float64)
    return {'min': round(float(v.min()), QUANT),
            'max': round(float(v.max()), QUANT),
            'mean': round(float(v.mean()), QUANT)}


@pytest.mark.parametrize('name', sorted(PHRASES))
class TestRegressionBaselines:
    def test_shapes(self, name):
        base = PHRASES[name]
        tract, glottis = _build(base['ipa'])
        assert list(tract.shape) == base['tract_shape']
        assert list(glottis.shape) == base['glottis_shape']

    def test_finite(self, name):
        base = PHRASES[name]
        tract, glottis = _build(base['ipa'])
        assert np.isfinite(tract).all()
        assert np.isfinite(glottis).all()

    def test_tract_column_stats(self, name):
        base = PHRASES[name]
        tract, _ = _build(base['ipa'])
        for j, (col, ref) in enumerate(base['tract_cols'].items()):
            got = _stats(tract[:, j])
            assert got == ref, f'{name} column {col}: {got} != {ref}'

    def test_glottis_column_stats(self, name):
        base = PHRASES[name]
        _, glottis = _build(base['ipa'])
        for j, (col, ref) in enumerate(base['glottis_cols'].items()):
            got = _stats(glottis[:, j])
            assert got == ref, f'{name} glottis column {col}: {got} != {ref}'

    def test_tract_sha256(self, name):
        base = PHRASES[name]
        tract, _ = _build(base['ipa'])
        q = np.round(tract, QUANT)
        import hashlib
        digest = hashlib.sha256(q.tobytes()).hexdigest()
        assert digest == base['tract_sha256'], (
            f'{name}: signal changed. If intentional, regenerate via '
            f'scripts/regen_baselines.py')
