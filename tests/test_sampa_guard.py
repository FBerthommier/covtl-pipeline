# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""SAMPA input guard (CORRECTIONS v2.1 s.2) — engine regression tests.

Covers:
  * the detection walk (unknown_symbols) against the reference parser
    behaviour (symbols silently dropped before the fix);
  * the three policies (warn / error / off) and their resolution
    (argument > VTL_SAMPA_GUARD > default 'warn');
  * the public engine boundaries: parse_input, parse_to_segments,
    build_phrase_pval, build_phrase_tract, Pipeline.run;
  * single diagnostic per synthesis (inner calls carry 'off');
  * BIT-IDENTICAL outputs between policies (the guard never alters a
    trajectory) and versus the pre-fix token sequences.
"""

import warnings

import numpy as np
import pytest

from vtl_synth import Pipeline, SampaGuardError, UnknownSegmentWarning
from vtl_synth.core.continuous import parse_to_segments
from vtl_synth.core.parsing import parse_input
from vtl_synth.core.sampa_guard import (
    guard_input,
    resolve_policy,
    unknown_symbols,
)
from vtl_synth.core.syltraj import build_phrase_pval
from vtl_synth.core.build_phrase_tract import build_phrase_tract


# ======================================================================
# Detection walk
# ======================================================================

@pytest.mark.parametrize('text,expected', [
    ('klincan', [('c', 4)]),          # the CORRECTIONS v2.1 s.2 incident
    ('traNd', [('r', 1)]),            # pinned by test_parsing_equivalence
    ('kliN. pan', []),                # kit P1 carrier
    ('ba.bi.bu', []),
    ('b o Z u R', []),
    ('aU', []),                       # diphthong key
    ('ta.jm', []),                    # glide sequence (kit convention)
    ('a~ O~', []),                    # nasal marker tolerated (syl engine)
    ('| % , . -', []),                # engine markers tolerated
    ('qq', [('q', 0), ('q', 1)]),     # grouped positions
])
def test_unknown_symbols(text, expected):
    assert unknown_symbols(text) == expected


def test_walk_mirrors_reference_parser_drops():
    """Every symbol flagged by the walk must be absent from the
    continuous parser output, and vice versa (post-normalization)."""
    from vtl_synth.core.continuous import _normalize_ipa
    for text in ('klincan', 'traNd', 'kliN. pan'):
        normalized = _normalize_ipa(text)
        segs, _ = parse_to_segments(normalized, sampa_guard='off')
        keys = [s.key for s in segs]
        dropped = {ch for ch, _ in unknown_symbols(normalized)}
        for ch in dropped:
            assert ch not in ''.join(keys)
        # no unknown -> full coverage of the remaining chars
        if not dropped:
            assert ''.join(keys) == normalized.replace(' ', '') \
                .replace('.', '').replace('-', '')


# ======================================================================
# Policies
# ======================================================================

def test_default_policy_is_warn():
    assert resolve_policy(None) == 'warn'
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        unknowns = guard_input('klincan', source='unit')
    assert unknowns == [('c', 4)]
    assert len(w) == 1
    assert w[0].category is UnknownSegmentWarning
    msg = str(w[0].message)
    assert "'c' at position 4" in msg
    assert 'klincan' in msg


def test_error_policy_raises():
    with pytest.raises(SampaGuardError, match="'c' at position 4"):
        guard_input('klincan', source='unit', policy='error')


def test_off_policy_silent():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        assert guard_input('klincan', source='unit', policy='off') == []
    assert len(w) == 0


def test_env_var_resolution(monkeypatch):
    monkeypatch.setenv('VTL_SAMPA_GUARD', 'error')
    assert resolve_policy(None) == 'error'
    # explicit argument wins over the environment
    assert resolve_policy('off') == 'off'
    monkeypatch.setenv('VTL_SAMPA_GUARD', 'off')
    assert resolve_policy(None) == 'off'
    # invalid value falls back to the default, with a notice
    monkeypatch.setenv('VTL_SAMPA_GUARD', 'bogus')
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        assert resolve_policy(None) == 'warn'
    assert any('VTL_SAMPA_GUARD' in str(x.message) for x in w)


def test_env_var_drives_parser(monkeypatch):
    monkeypatch.setenv('VTL_SAMPA_GUARD', 'error')
    with pytest.raises(SampaGuardError):
        parse_to_segments('klincan')


# ======================================================================
# Public engine boundaries
# ======================================================================

def test_parse_input_warns_and_keeps_tokens():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        pr = parse_input('trand')
    flat = [t for t in pr.flat if t not in ('GAP',)]
    assert flat == ['t', 'a', 'n', 'd']      # pre-fix sequence, unchanged
    assert len(w) == 1
    assert w[0].category is UnknownSegmentWarning
    assert "'r' at position 1" in str(w[0].message)


def test_parse_input_clean_is_silent():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        parse_input('ba.da abda')
    assert len(w) == 0


def test_parse_to_segments_error_policy():
    with pytest.raises(SampaGuardError):
        parse_to_segments('klincan', sampa_guard='error')


def test_build_phrase_pval_warns():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        build_phrase_pval('klincan')
    assert len(w) == 1
    assert w[0].category is UnknownSegmentWarning


def test_build_phrase_pval_error_policy():
    with pytest.raises(SampaGuardError):
        build_phrase_pval('klincan', sampa_guard='error')


def test_build_phrase_tract_single_diagnostic(tmp_path):
    """One synthesis -> exactly ONE warning (inner calls carry 'off')."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        build_phrase_tract('klincan', return_data=True,
                           output_dir=str(tmp_path), verbose=False)
    sampa = [x for x in w if x.category is UnknownSegmentWarning]
    assert len(sampa) == 1
    assert '[build_phrase_tract]' in str(sampa[0].message)


def test_build_phrase_tract_error_before_synthesis(tmp_path):
    with pytest.raises(SampaGuardError):
        build_phrase_tract('klincan', return_data=True,
                           output_dir=str(tmp_path), verbose=False,
                           sampa_guard='error')


def test_uppercase_nonphonemic_normalized_before_guard(tmp_path):
    """'K' is lowercased by _normalize_ipa BEFORE the guard fires:
    'KliN. pan' must NOT warn (regression test for the guard's
    placement after normalization)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        build_phrase_tract('KliN. pan', return_data=True,
                           output_dir=str(tmp_path), verbose=False)
    assert not any(x.category is UnknownSegmentWarning for x in w)


# ======================================================================
# Bit-identical outputs (the guard never alters a trajectory)
# ======================================================================

def test_policy_does_not_change_outputs(tmp_path):
    a = build_phrase_tract('klincan', return_data=True,
                           output_dir=str(tmp_path), verbose=False,
                           sampa_guard='off')
    with warnings.catch_warnings(record=True):
        warnings.simplefilter('always')
        b = build_phrase_tract('klincan', return_data=True,
                               output_dir=str(tmp_path), verbose=False,
                               sampa_guard='warn')
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def test_clean_phrase_outputs_unchanged(tmp_path):
    """The tokens and trajectory of a clean input keep their pre-fix
    values (regression anchors from the 2026-10 baseline)."""
    segs, _ = parse_to_segments('kliN. pan', sampa_guard='off')
    assert [s.key for s in segs] == ['k', 'l', 'i', 'N', 'p', 'a', 'n']
    pval, _, _, _ = build_phrase_pval('kliN. pan', sampa_guard='off')
    assert pval.shape[1] == 15          # B(t) @100 Hz, 15 params
    tract, glott = build_phrase_tract(
        'kliN. pan', return_data=True, output_dir=str(tmp_path),
        verbose=False, sampa_guard='off')
    assert tract.shape[1] == 19 and glott.shape[1] == 11
    assert tract.shape[0] == 4 * pval.shape[0]   # 400 Hz vs 100 Hz


def test_pipeline_run_guard(tmp_path):
    pipe = Pipeline()
    with pytest.raises(SampaGuardError):
        pipe.run('klincan', output_dir=str(tmp_path), use_g2p=False,
                 video=False, sampa_guard='error')
    # clean input: no warning, synthesis succeeds
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        pipe.run('kliN. pan', output_dir=str(tmp_path), use_g2p=False,
                 video=False)
    assert not any(x.category is UnknownSegmentWarning for x in w)


# ======================================================================
# CLI end-to-end
# ======================================================================

def test_cli_sampa_guard_error():
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, '-m', 'vtl_synth.cli.main', 'run',
         '--phonetic', '--no-video', '--sampa-guard', 'error',
         '-o', '/tmp/vtl_sampa_guard_cli_test', 'klincan'],
        capture_output=True, text=True, timeout=300)
    assert r.returncode != 0
    assert 'SambaGuardError' in r.stderr or 'unknown symbol' in r.stderr


def test_cli_sampa_guard_warn_shows_message():
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, '-m', 'vtl_synth.cli.main', 'run',
         '--phonetic', '--no-video',
         '-o', '/tmp/vtl_sampa_guard_cli_test', 'klincan'],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0
    assert 'unknown symbol' in r.stderr
    assert "'c' at position 4" in r.stderr
