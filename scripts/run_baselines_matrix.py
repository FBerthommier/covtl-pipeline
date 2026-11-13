# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Runs (or regenerates) the regression baselines for every speaker.

The tract/glottis baselines depend on exactly two repository layers:

  * ``vtl_synth/core/constants.py``  (geometry/glottis/f0 calibration),
  * ``vtl_synth/data/speakers/ACTIVE_SPEAKER`` + the registry
    ``.speaker`` file (orthogonal branch, VS/VO/TRX/TRY/TS3).

The audio wheel (``vocaltractlab_cython``'s JD3.speaker resource) is
NOT involved — the baselines stop at the tract/glottis matrices — so
this script swaps the two repo layers directly instead of calling
``install_speaker.py`` (which is tied to machine-specific backup paths
and also swaps the shared wheel resource).

Each speaker runs in a FRESH subprocess: ``constants`` is imported at
module load all over the engine, so an in-process swap would be
poisoned by ``sys.modules`` caching.

Usage (from the repository root)::

    python scripts/run_baselines_matrix.py --list
    python scripts/run_baselines_matrix.py                 # test all 5
    python scripts/run_baselines_matrix.py --speaker s1    # test one
    python scripts/run_baselines_matrix.py --regen         # regen all 5
    python scripts/run_baselines_matrix.py --regen --speaker s2

On exit the repository state is restored bit-exactly (original
constants.py + original ACTIVE_SPEAKER marker), whatever happened.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from vtl_synth.core import speaker_registry as sr  # noqa: E402

CONSTANTS = REPO_ROOT / 'vtl_synth' / 'core' / 'constants.py'
BACKUP = REPO_ROOT / '.constants_baseline_backup.py'


def _swap(speaker: str) -> None:
    """Installs ``speaker``'s constants + marker over the repo layers."""
    src = sr.constants_source_path(speaker)
    CONSTANTS.write_bytes(src.read_bytes())
    sr.set_active(speaker)


def _restore(original_constants: bytes,
             original_marker: str | None) -> None:
    CONSTANTS.write_bytes(original_constants)
    if original_marker is None:
        sr.ACTIVE_MARKER.unlink(missing_ok=True)
    else:
        sr.ACTIVE_MARKER.write_text(original_marker, encoding='ascii')


def _run_for(speaker: str, regen: bool) -> int:
    """One speaker: swap → subprocess (pytest or regen) → restore."""
    original_constants = CONSTANTS.read_bytes()
    original_marker = (sr.ACTIVE_MARKER.read_text(encoding='ascii').strip()
                       if sr.ACTIVE_MARKER.is_file() else None)
    try:
        _swap(speaker)
        if regen:
            cmd = [sys.executable,
                   str(REPO_ROOT / 'scripts' / 'regen_baselines.py')]
        else:
            cmd = [sys.executable, '-m', 'pytest', '-q', '--no-header',
                   str(REPO_ROOT / 'tests' / 'test_regression_baselines.py')]
        print(f'--- {speaker}: {"regen" if regen else "test"} '
              f'(subprocess) ---', flush=True)
        rc = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
        print(f'--- {speaker}: {"OK" if rc == 0 else "FAILED"} ---',
              flush=True)
        return rc
    finally:
        _restore(original_constants, original_marker)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--speaker', default=None,
                    help='restrict to one speaker (default: all)')
    ap.add_argument('--regen', action='store_true',
                    help='regenerate the baselines instead of testing')
    ap.add_argument('--list', action='store_true',
                    help='show registered speakers and baseline files')
    args = ap.parse_args()

    if args.list:
        for name in sr.list_speakers():
            f = 'regression_baselines.json' if name == 'jd3' \
                else f'regression_baselines_{name}.json'
            print(f'  {name:4s} : {f}')
        return 0

    speakers = sr.list_speakers()
    if args.speaker:
        if args.speaker not in speakers:
            ap.error(f'unknown speaker {args.speaker!r}: {speakers}')
        speakers = [args.speaker]

    failures = [s for s in speakers if _run_for(s, args.regen) != 0]
    if failures:
        print(f'FAILED speakers: {failures}')
        return 1
    print(f'all {len(speakers)} speakers '
          f'{"regenerated" if args.regen else "green"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
