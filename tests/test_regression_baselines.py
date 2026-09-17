# -*- coding: utf-8 -*-
"""E2E non-regression test against regression_baselines.json (schema 2).

The baselines are the acoustically validated state (2026-09-04, TS3
override included). After an INTENTIONAL change to the signal:
    python scripts/regen_baselines.py
then rerun the tests.

Speaker-relative baselines (install_speaker.py, 2026-09-11): the tract
and glottis signals depend on the ACTIVE speaker (constants.py +
registry .speaker).  For 'jd3' the reference file
regression_baselines.json is used; for any other active speaker the
per-speaker file regression_baselines_<name>.json is required
(generate it with:  python scripts/regen_baselines.py  while the
speaker is installed).
"""
import json
from pathlib import Path

import numpy as np
import pytest

from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core import speaker_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTIVE = speaker_registry.active_name()
if ACTIVE in ('', 'jd3'):
    BASELINES_PATH = REPO_ROOT / 'regression_baselines.json'
else:
    BASELINES_PATH = REPO_ROOT / f'regression_baselines_{ACTIVE}.json'

QUANT = 6

if BASELINES_PATH.exists():
    BASELINES = json.loads(BASELINES_PATH.read_text(encoding='utf-8'))
else:
    BASELINES = {'phrases': {}}
PHRASES = BASELINES['phrases']


def test_baselines_available_for_active_speaker():
    """Per-speaker baselines must exist before the signal tests run."""
    if not BASELINES_PATH.exists():
        pytest.fail(
            f"baselines absentes pour le speaker actif '{ACTIVE}' : "
            f"{BASELINES_PATH.name}\n"
            f"generer avec : python scripts/regen_baselines.py "
            f"(depuis la racine du depot, speaker '{ACTIVE}' installe)")


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
