# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Single-path guard: production synthesis must run ONE trajectory
algorithm.

Default engine ('syl') computes trajectories with syltraj only; the
deprecated ``engine='legacy'`` alignment path (default OFF) uses
``trajectory.py`` exclusively.  The legacy superposition-graph engine
(``vtl_synth.core.trajectory_legacy``) was removed from the package —
these tests prove that:

1. the legacy engine module can no longer be imported;
2. no module under ``vtl_synth/`` imports it (AST-level scan, comments
   and docstrings excluded);
3. a DEFAULT synthesis never loads it, and does load the active
   syltraj engine;
4. the deprecated alignment path runs on ``trajectory.py`` (the
   refactored block builder), never on the legacy engine.
"""
import ast
import importlib
import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

from vtl_synth.core.build_phrase_tract import build_phrase_tract

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = REPO_ROOT / 'vtl_synth'

LEGACY_MOD = 'vtl_synth.core.trajectory_legacy'
MODERN_MOD = 'vtl_synth.core.trajectory'
SYLTRAJ_MOD = 'vtl_synth.core.syltraj'


def test_legacy_engine_module_is_gone():
    """The legacy superposition-graph engine must not be importable."""
    assert importlib.util.find_spec(LEGACY_MOD) is None, (
        f'{LEGACY_MOD} still exists: the dual-trajectory engine '
        'was supposed to be removed')
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(LEGACY_MOD)


def test_no_package_module_imports_legacy_engine():
    """No module under vtl_synth/ may import the legacy engine.

    AST-level scan of real import statements: comments and docstrings
    that merely *mention* the old module are not offenders.
    """
    offenders = []
    for py in sorted(PKG_ROOT.rglob('*.py')):
        if '__pycache__' in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            else:
                continue
            if any('trajectory_legacy' in name for name in names):
                offenders.append(
                    f'{py.relative_to(REPO_ROOT)}:{node.lineno}')
    assert not offenders, (
        'modules still importing the legacy trajectory engine:\n'
        + '\n'.join(offenders))


def test_default_synthesis_uses_syltraj_only():
    """Default build_phrase_tract() must run the syltraj engine, and
    must never load the legacy trajectory engine."""
    result = build_phrase_tract('ba', phrase_id=None, label='guard',
                                return_data=True, verbose=False)
    tract, glottis = result[0], result[1]
    assert tract is not None and getattr(tract, 'size', 0) > 0
    assert SYLTRAJ_MOD in sys.modules, (
        'default engine did not load syltraj — which path ran?')
    assert LEGACY_MOD not in sys.modules, (
        'default synthesis loaded the legacy trajectory engine')


def test_deprecated_alignment_path_uses_modern_trajectory():
    """engine='legacy' (deprecated, default OFF, alignment reference)
    must compute through trajectory.py — never the removed engine."""
    from vtl_synth.core.continuous import parse_to_tract_trajectory
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        tract, rho_theta, block_info = parse_to_tract_trajectory('ba')
    assert tract.ndim == 2 and tract.shape[0] > 0
    assert rho_theta.shape == (tract.shape[0], 2)
    assert len(block_info) > 0
    assert MODERN_MOD in sys.modules, (
        "deprecated engine='legacy' path did not load trajectory.py — "
        'which path ran?')
    assert LEGACY_MOD not in sys.modules, (
        "deprecated engine='legacy' path loaded the removed "
        'trajectory engine')
