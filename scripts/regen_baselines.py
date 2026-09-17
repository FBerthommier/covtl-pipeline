# -*- coding: utf-8 -*-
"""Regenerates the regression baselines for the ACTIVE speaker.

The baselines are speaker-relative (install_speaker.py, 2026-09-11):
the tract/glottis signals depend on the installed constants.py and on
the registry .speaker of the orthogonal branch.

Usage (from the repository root, with the target speaker installed)::

    python scripts/regen_baselines.py            # active speaker
    python scripts/regen_baselines.py --list     # active + available files

Output:
  * active 'jd3'  -> regression_baselines.json        (reference file)
  * active s1/s2  -> regression_baselines_<name>.json (per-speaker file)

The phrase list and schema (schema 2) are taken from the reference
regression_baselines.json; only the signal statistics/hashes are
recomputed.  tests/test_regression_baselines.py automatically picks
the file matching the active speaker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from vtl_synth.core import speaker_registry
from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core.constants import TRACT_PARAM_NAMES, GLOTTIS_PARAM_NAMES

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / 'regression_baselines.json'
QUANT = 6


def _stats(vec) -> dict:
    v = np.asarray(vec, dtype=np.float64)
    return {'min': round(float(v.min()), QUANT),
            'max': round(float(v.max()), QUANT),
            'mean': round(float(v.mean()), QUANT)}


def _build(phrase):
    result = build_phrase_tract(phrase, phrase_id=None, label='regen',
                                return_data=True, verbose=False)
    return result[0], result[1]


def _column_stats(mat, names) -> dict:
    return {name: _stats(mat[:, j]) for j, name in enumerate(names)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--list', action='store_true',
                    help='show active speaker and baseline files, change nothing')
    args = ap.parse_args()

    active = speaker_registry.active_name()

    if args.list:
        print(f"speaker actif : {active}")
        for name in speaker_registry.list_speakers():
            f = REFERENCE if name == 'jd3' else REPO_ROOT / f'regression_baselines_{name}.json'
            print(f"  {name:4s} : {f.name:35s} {'present' if f.exists() else 'absent'}")
        return 0

    if not speaker_registry.constants_coherent():
        raise SystemExit(
            f"INCOHERENCE : le constants.py installe ne correspond pas au "
            f"speaker actif '{active}' — relancer install_speaker.py install "
            f"{active} avant de regenerer les baselines.")

    ref = json.loads(REFERENCE.read_text(encoding='utf-8'))

    phrases = {}
    for name in sorted(ref['phrases']):
        base = ref['phrases'][name]
        tract, glottis = _build(base['ipa'])
        q = np.round(tract, QUANT)
        digest = hashlib.sha256(q.tobytes()).hexdigest()
        phrases[name] = {
            'ipa': base['ipa'],
            'n_frames': int(tract.shape[0]),
            'tract_shape': list(tract.shape),
            'glottis_shape': list(glottis.shape),
            'tract_cols': _column_stats(tract, TRACT_PARAM_NAMES),
            'glottis_cols': _column_stats(glottis, GLOTTIS_PARAM_NAMES),
            'tract_sha256': digest,
        }
        print(f"  {name:12s} {base['ipa']:30s} sha256={digest[:16]}")

    out = {
        'meta': {
            'schema': 2,
            'date': datetime.now().date().isoformat(),
            'engine': ref.get('meta', {}).get('engine', 'syl'),
            'quant_decimals': QUANT,
            'speaker': active,
            'note': ("Baselines RELATIVES au speaker actif '%s' (see "
                     "install_speaker.py / scripts/regen_baselines.py). "
                     "Regenerer apres toute modification volontaire du signal."
                     % active),
        },
        'phrases': phrases,
    }
    dest = REFERENCE if active == 'jd3' \
        else REPO_ROOT / f'regression_baselines_{active}.json'
    dest.write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(f"baselines '{active}' -> {dest} ({len(phrases)} phrases)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
