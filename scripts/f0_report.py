# -*- coding: utf-8 -*-
"""Objective measurement of the F0 contour of a .tract file
(expressive prosody).

    python scripts/f0_report.py file.tract [file2.tract ...]

Prints: voiced fraction, mean F0, standard deviation of the contour
in semitones (expressive dynamics), max jump per sample @400 Hz
(smoothness), range.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vtl_synth.video.renderer import read_tract  # noqa: E402


def report(path: str) -> dict:
    data, sr = read_tract(path)
    glottis = data[:, 19:]
    f0 = glottis[:, 0]
    voiced = glottis[:, 6] > 0.1
    f0v = f0[voiced]
    st = 12.0 * np.log2(f0v / f0v.mean())
    # smoothness: jumps between consecutive VOICED frames (silence
    # regions carry default values with no meaning)
    vv = voiced[:-1] & voiced[1:]
    jumps = np.abs(np.diff(f0))[vv]
    # accent peaks: SUSTAINED bumps (>= 30 ms above +5 % of the 400 ms
    # moving local base) — removes the artefacts of a ragged contour
    # (one-frame jumps do not count)
    k = int(0.4 * sr)
    if k % 2 == 0:
        k += 1
    if k >= 3 and len(f0) > k:
        base = np.convolve(f0, np.ones(k) / k, mode='same')
        above = (f0 > 1.05 * base) & voiced
        win = max(3, int(0.03 * sr))
        sustained = np.convolve(above.astype(float), np.ones(win),
                                mode='same') >= win
        n_peaks = 0
        prev = False
        for s in sustained:
            if s and not prev:
                n_peaks += 1
            prev = s
    else:
        n_peaks = 0
    out = {
        'path': path,
        'voiced_pct': 100.0 * voiced.mean(),
        'f0_mean': float(f0v.mean()),
        'std_st': float(st.std()),
        'max_jump': float(jumps.max()) if len(jumps) else 0.0,
        'f0_min': float(f0v.min()),
        'f0_max': float(f0v.max()),
        'n_peaks': n_peaks,
    }
    return out


def main() -> None:
    for p in sys.argv[1:]:
        r = report(p)
        print(f"{Path(p).name:<28s} voiced={r['voiced_pct']:5.1f}%  "
              f"f0={r['f0_mean']:6.1f} Hz  dyn={r['std_st']:5.2f} ST  "
              f"span={r['f0_max'] - r['f0_min']:5.1f} Hz  "
              f"maxjump={r['max_jump']:5.2f} Hz/fr  "
              f"peaks>+5%={r['n_peaks']:3d}  "
              f"range={r['f0_min']:.1f}-{r['f0_max']:.1f} Hz")


if __name__ == '__main__':
    main()
