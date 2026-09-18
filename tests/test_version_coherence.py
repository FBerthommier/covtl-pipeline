# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Blocks any drift between vtl_synth.__version__ and pyproject.toml."""
import re
from pathlib import Path

import vtl_synth

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, 'version= introuvable dans pyproject.toml'
    return m.group(1)


def test_version_coherence():
    assert vtl_synth.__version__ == _pyproject_version(), (
        f"vtl_synth.__version__ ({vtl_synth.__version__}) != "
        f"pyproject.toml ({_pyproject_version()})")
