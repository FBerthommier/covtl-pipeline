# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Full-path phonation tests (wave 4 §7.4 redo + wave 5 P1.2).

Pytest-collected port of ``tests/check_phonation_full_path.py`` (which
stays as the standalone, print-oriented checker). Locks the COMPLETE
path of the phonation modes:

  1. ``classify_block_events`` relabels the phonation spans,
  2. ``phonation_schedule_from_segments`` converts the level-C
     glottal_tag into frame spans,
  3. ``_lookup_preset_vector`` resolves 'creaky' (no JD3 entry)
     through the generic presets,
  4. ``build_phrase_tract(tag_overrides=...)`` produces DIFFERENT
     glott400 matrices per mode (the read hole of the first fix),
  5. ``Pipeline(tag_overrides=...)`` forwards the overrides down to
     ``build_phrase_tract``,
  6. (wave 5) the wildcard ``'*'`` entry drives the whole phrase.

The vv-closure probe is stubbed at module scope: the REAL probe
rebuilds a 19-param VTL state through ``vocaltractlab_cython`` — a
tract-geometry concern orthogonal to the glottal layer under test
here (same stub as the standalone checker).
"""
from __future__ import annotations

import importlib

import numpy as np
import pytest

from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core.constants import CO_VTL as _COVTL
from vtl_synth.core.constants import GLOTTIS_PARAM_NAMES
from vtl_synth.core.glottal_source import (_lookup_preset_vector,
                                           classify_block_events,
                                           phonation_schedule_from_segments)
from vtl_synth.core.pipeline import Pipeline
from vtl_synth.core.prosody_source import Segment
from vtl_synth.core.tag_system import TagInterpreter

PHRASE = 'Dis.iz.i.zi.fOR.@s'   # « this is easy for us » (engine g2p)

# columns of the glottis matrix that each mode is expected to move
EXPECT_COLS = {
    # NB breathy: JD3 chink_area (0.100) equals the voiceless-fricative
    # preset (0.100) — near a final /s/ the two are indistinguishable,
    # so only the fold-spacing columns are asserted.
    'breathy': {'x_bottom', 'x_top'},
    'creaky':  {'double_pulsing', 'pulse_skewness'},
    'whisper': {'chink_area', 'x_bottom', 'x_top'},
}


def _sandbox_probe(block):
    """Stub of _make_vv_closure_probe (no vocaltractlab dependency)."""
    n = len(block)
    if n == 0:
        return 1e9
    order = list(_COVTL.keys())
    idx = [order.index(k) for k in order
           if any(t in k.lower() for t in ('tongue', 'body', 'tip'))]
    if not idx:
        idx = list(range(min(8, block.shape[1])))
    sub = block[:, idx]
    return float(40.0 + 200.0 * np.linalg.norm(sub[n // 2] - sub[-1]))


@pytest.fixture(scope='module', autouse=True)
def _stub_probe():
    _bpt = importlib.import_module('vtl_synth.core.build_phrase_tract')
    original = _bpt._make_vv_closure_probe
    _bpt._make_vv_closure_probe = lambda: _sandbox_probe
    yield
    _bpt._make_vv_closure_probe = original


def _run(ov):
    _, glottis = build_phrase_tract(PHRASE, output_dir=None,
                                    return_data=True, verbose=False,
                                    tag_overrides=ov, sampa_guard='off')
    return np.asarray(glottis)


# ── 1. preset resolution ────────────────────────────────────────────

def test_preset_creaky_resolves_generic():
    v = _lookup_preset_vector('creaky')
    assert v[7] == 0.3 and v[8] == 0.5          # dp / skew


def test_preset_breathy_is_jd3():
    v = _lookup_preset_vector('breathy')
    assert abs(v[4] - 0.100) < 1e-9             # chink


def test_preset_unknown_label_falls_back_modal():
    v = _lookup_preset_vector('label-inconnu')
    assert v[4] == 0.050                        # chink


# ── 2. schedule conversion ─────────────────────────────────────────

def _four_segments():
    return [
        Segment(key='D', kind='C', t_start=0, t_end=60),
        Segment(key='i', kind='V', t_start=60, t_end=150),
        Segment(key='s', kind='C', t_start=150, t_end=210),
        Segment(key='i', kind='V', t_start=210, t_end=300),
    ]


def test_schedule_two_whisper_spans():
    ti = TagInterpreter(tag_overrides={'i': {'voicing': 'whisper'}})
    spans = phonation_schedule_from_segments(ti.apply_all(_four_segments()),
                                             n_steps=100)
    assert len(spans) == 2 and all(m == 'whisper' for m, _, _ in spans)
    assert spans[0][1] < spans[1][1] and spans[0][2] <= spans[1][1]
    f0, f1 = spans[0][1], spans[0][2]
    assert f0 == 20 and f1 == 50                 # proportional (60/300)


def test_schedule_empty_without_override():
    spans = phonation_schedule_from_segments(
        TagInterpreter().apply_all(_four_segments()), 100)
    assert spans == []


def test_schedule_consonant_override_yields_span():
    segs = [Segment(key='D', kind='C', t_start=0, t_end=60),
            Segment(key='i', kind='V', t_start=60, t_end=150)]
    ti = TagInterpreter(tag_overrides={'D': {'voicing': 'breathy'}})
    spans = phonation_schedule_from_segments(ti.apply_all(segs), 100)
    assert len(spans) == 1 and spans[0][0] == 'breathy'


# ── 3. block-event relabelling ──────────────────────────────────────

class _Blk:
    def __init__(self, kind, n_steps, cons_tokens=()):
        self.kind, self.n_steps = kind, n_steps
        self.cons_tokens = list(cons_tokens)
        self.n_cons = len(self.cons_tokens)


def test_classify_relabels_inside_span():
    blocks = [_Blk('cluster', 20, ['D']), _Blk('plateau', 40),
              _Blk('cluster', 20, ['s']), _Blk('plateau', 40)]
    sched = [('whisper', 20, 60)]
    ev = classify_block_events(blocks, ['D', 's'],
                               phonation_schedule=sched)
    labels = dict(ev)
    inside = [l for l, f in ev if 20 <= f < 60]
    assert all(l == 'whisper' for l in inside)
    assert any(f == 60 and l != 'whisper' for l, f in ev)   # restored


def test_classify_no_schedule_no_phonation_labels():
    blocks = [_Blk('cluster', 20, ['D']), _Blk('plateau', 40)]
    ev = classify_block_events(blocks, ['D'])
    assert not any(l in ('breathy', 'creaky', 'whisper') for l, _ in ev)


# ── 4. build_phrase_tract full chain (glott400) ─────────────────────

def test_baseline_finite():
    base = _run(None)
    assert np.isfinite(base).all() and base.shape[1] == 11


@pytest.mark.parametrize('mode', sorted(EXPECT_COLS))
def test_mode_moves_expected_glottal_columns(mode):
    base = _run(None)
    g = _run({'@': {'voicing': mode}, 'i': {'voicing': mode}})
    assert g.shape == base.shape
    d = np.abs(g - base).max(axis=0)
    mods = {GLOTTIS_PARAM_NAMES[j] for j in range(11) if d[j] > 1e-6}
    assert EXPECT_COLS[mode].issubset(mods), (
        f'{mode}: modified columns {sorted(mods)}')


def test_empty_override_bit_identical_to_baseline():
    base = _run(None)
    g = _run({})
    assert g.shape == base.shape and np.array_equal(g, base)


def test_wildcard_whisper_moves_chink_on_final_schwa():
    """Wave 5: one '*' entry ≡ the same mode on every key (the whole
    phrase), chink_area must OPEN on the final schwa span."""
    base = _run(None)
    g = _run({'*': {'voicing': 'whisper'}})
    assert g.shape == base.shape
    i_ch = GLOTTIS_PARAM_NAMES.index('chink_area')
    n = min(len(base), len(g))
    span = slice(int(n * 0.80), int(n * 0.98))   # end of phrase: final /@/
    assert bool((g[span, i_ch] - base[span, i_ch] > 0.02).any())


def test_wildcard_creaky_double_pulsing_above_modal():
    base = _run(None)
    g = _run({'*': {'voicing': 'creaky'}})
    assert g.shape == base.shape
    i_dp = GLOTTIS_PARAM_NAMES.index('double_pulsing')
    assert bool((g[:, i_dp] > base[:, i_dp] + 0.05).any())


def test_wildcard_equal_to_explicit_per_key():
    """'*' with mode M ≡ the same override on EVERY key of the phrase
    (vowels AND consonants) — the one-entry contract of the UI
    selector. Overriding only the vowels is NOT equivalent (the
    consonant spans keep their default glottal behaviour)."""
    g_star = _run({'*': {'voicing': 'whisper'}})
    keys = set(PHRASE) - set('.|% ')
    g_keys = _run({k: {'voicing': 'whisper'} for k in keys})
    assert np.array_equal(g_star, g_keys)
    g_vowels_only = _run({k: {'voicing': 'whisper'} for k in '@i'})
    assert not np.array_equal(g_star, g_vowels_only)


# ── 5. Pipeline exposure ────────────────────────────────────────────

def test_pipeline_exposes_tag_overrides():
    p = Pipeline(tag_overrides={'@': {'voicing': 'breathy'}})
    assert p.tag_overrides == {'@': {'voicing': 'breathy'}}
    assert Pipeline().tag_overrides is None
