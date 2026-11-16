# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""The four phonation modes side by side (wave 5, P3.7).

    python examples/demo_phonation.py

Synthesizes "this is easy for us" four times — modal (default),
breathy, creaky, whisper — and reports the WAV paths with the RMS of
each, so the phonation modes are audible and comparable in one run.
The three modes are whole-phrase here (wildcard '*' entry); see
demo_phonation --help for the per-key form (a mode on selected
vowels only).
"""
import argparse
import wave
from pathlib import Path

import numpy as np

from vtl_synth import Pipeline, is_vtl_available

OUT = Path(__file__).resolve().parent.parent / 'out_demo_phonation'

MODES = ('normal', 'breathy', 'creaky', 'whisper')


def _rms(path: Path) -> float:
    with wave.open(str(path), 'rb') as w:
        x = np.frombuffer(w.readframes(w.getnframes()),
                          dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean((x / 32768.0) ** 2)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--keys', default='*',
                    help=" phoneme keys to override (default: '*' — the "
                         "whole phrase; e.g. '@i' for the final schwa "
                         "and the /i/s only)")
    ap.add_argument('--text', default='this is easy for us',
                    help="input text (English g2p)")
    args = ap.parse_args()

    if not is_vtl_available():
        raise SystemExit('vocaltractlab-cython is not installed')

    keys = args.keys if args.keys != '*' else '*'
    for mode in MODES:
        overrides = None if mode == 'normal' else {
            k: {'voicing': mode} for k in keys} if keys != '*' else \
            {'*': {'voicing': mode}}
        pipe = Pipeline(tag_overrides=overrides)
        result = pipe.run(args.text, output_dir=str(OUT),
                          label=f'demo-phonation-{mode}')
        print(f'{mode:8s}: {result.wav_path}  '
              f'({result.duration_s:.2f} s, RMS '
              f'{_rms(Path(result.wav_path)):.4f})')


if __name__ == '__main__':
    main()
