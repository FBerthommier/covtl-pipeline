# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
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

# Canonical corpus (schema 3): the phrase list is defined HERE — the
# single source of truth for every speaker file — instead of being
# copied from the reference JSON.  Phrases are engine SAMPA (the syl
# engine notation: space = inter-word pause, '|' = long pause, '.' =
# no-pause chain join, '%' = breath pause).
CORPUS = {
    # historical schema-2 phrases — their tract_sha256 values are the
    # 2026-09-04 acoustically validated reference; regen_refuses to
    # overwrite them with a drifted signal (see the guard below)
    'aiu':      'a i u',
    'ba':       'ba',
    'ba_da_ga': 'ba da ga',
    # schema-3 additions (2026-11-13): nasals + nasalized vowels,
    # clusters, word-final obstruents, breath pause
    'nasals':       'ma na',
    'nasal_vowels': 'b9 d9',
    'clusters':     'pla stRi',
    'finals':       'bas Rab',
    'breath':       'ba % da',
}


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
    ap.add_argument('--force', action='store_true',
                    help='allow overwriting a drifted historical baseline '
                         '(schema-2 tract_sha256 of the 2026-09-04 '
                         'reference); default is to abort')
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

    dest = REFERENCE if active == 'jd3' \
        else REPO_ROOT / f'regression_baselines_{active}.json'
    previous = {}
    if dest.exists():
        previous = json.loads(dest.read_text(encoding='utf-8')).get(
            'phrases', {})

    phrases = {}
    drift = []
    for name in sorted(CORPUS):
        ipa = CORPUS[name]
        tract, glottis = _build(ipa)
        q_tract = np.round(tract, QUANT)
        tract_digest = hashlib.sha256(q_tract.tobytes()).hexdigest()
        q_glottis = np.round(glottis, QUANT)
        glottis_digest = hashlib.sha256(q_glottis.tobytes()).hexdigest()
        # non-regression guard: a historical tract_sha256 that changes
        # means the SIGNAL drifted — regenerating would launder a
        # regression into the new baselines. Refuse unless --force.
        old = previous.get(name, {}).get('tract_sha256')
        if old is not None and old != tract_digest:
            drift.append((name, old[:16], tract_digest[:16]))
        phrases[name] = {
            'ipa': ipa,
            'n_frames': int(tract.shape[0]),
            'tract_shape': list(tract.shape),
            'glottis_shape': list(glottis.shape),
            'tract_cols': _column_stats(tract, TRACT_PARAM_NAMES),
            'glottis_cols': _column_stats(glottis, GLOTTIS_PARAM_NAMES),
            'tract_sha256': tract_digest,
            'glottis_sha256': glottis_digest,
        }
        print(f"  {name:13s} {ipa:14s} tract={tract_digest[:16]} "
              f"glottis={glottis_digest[:16]}")

    if drift and not args.force:
        for name, old, new in drift:
            print(f"DRIFT {name}: {old} -> {new}")
        raise SystemExit(
            "ABORT: le signal a derive sur des phrases historiques "
            "(voir DRIFT ci-dessus). Une regen sans verification serait "
            "une regression blanchie. Verifier le changement de signal; "
            "s'il est volontaire: relancer avec --force.")

    out = {
        'meta': {
            'schema': 3,
            'date': datetime.now().date().isoformat(),
            'engine': 'syl',
            'quant_decimals': QUANT,
            'speaker': active,
            'corpus': 'scripts/regen_baselines.py CORPUS (schema 3): '
                      'vowels/plosives + nasals + nasalized vowels + '
                      'clusters + word finals + breath pause',
            'note': ("Baselines RELATIVES au speaker actif '%s' (see "
                     "install_speaker.py / scripts/regen_baselines.py). "
                     "Regenerer apres toute modification volontaire du signal."
                     % active),
        },
        'phrases': phrases,
    }
    dest.write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(f"baselines '{active}' -> {dest} ({len(phrases)} phrases)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
