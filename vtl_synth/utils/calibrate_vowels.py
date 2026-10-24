# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
calibrate_vowels.py
====================
Automatic calibration of the vowel targets (rho, theta) for a
specific VTL speaker and a target language.

Principle
---------
Given:
  1. A VTL speaker (.speaker file) — defines the tract geometry
  2. A COVTL matrix (c0/c1/c2 coefficients of the 15 VTL parameters) —
     defined in ``constants.CO_VTL``
  3. A language vowel inventory (expected F1/F2 + cardinal theta) —
     defined in ``language_vowel_sets.VOWEL_SETS``

The calibrator:
  - Measures the speaker's mechanical extremes /a/ /i/ /u/ by sweeping
    rho ∈ [0.3, 1.2] and measuring the formants via the VTL transfer
    function + LPC analysis.
  - For each vowel, finds the optimal rho (fixed theta) that
    minimizes the deviation from the language's reference formants.
  - Computes the schwa as the centroid of the a-i-u triangle.
  - Returns a ``{key → (rho, theta)}`` dict ready to be installed in
    ``constants.VOWEL_TARGETS``.

Usage
-----
::

    from vtl_synth.utils.calibrate_vowels import calibrate_vowels
    from vtl_synth.core.constants import CO_VTL, COVTL_TO_FULL

    targets = calibrate_vowels(
        lang='fr',
        co_vtl=CO_VTL,
        covtl_to_full=COVTL_TO_FULL,
        speaker_path=None,  # use the default VTL speaker
    )
    # targets = {'i': (0.34, 5.236), 'e': (0.85, 4.712), ...}

CLI
---
::

    python -m vtl_synth.utils.calibrate_vowels --lang fr --output calibrated.json
    python -m vtl_synth.utils.calibrate_vowels --lang en --speaker /path/to/JD3.speaker
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from typing import Dict, Tuple, Optional

import numpy as np

# Lazy imports to avoid circular dependencies
def _import_vtl():
    """Import vocaltractlab_cython (lazy)."""
    import vocaltractlab_cython as vtl
    return vtl


def _import_constants():
    """Imports CO_VTL and COVTL_TO_FULL from constants (lazy)."""
    from vtl_synth.core.constants import CO_VTL, COVTL_TO_FULL
    return CO_VTL, COVTL_TO_FULL


# =====================================================================
# Formant measurement via LPC
# =====================================================================

def compute_formants_lpc(tract19, sr_audio: int = 44100,
                          order: int = 12, window_ms: float = 30.0):
    """Measures the formants of a tract state via LPC analysis.

    Parameters
    ----------
    tract19 : array-like (19,)
        Vocal tract state vector (19 VTL parameters).
    sr_audio : int
        Audio sampling rate (Hz).
    order : int
        LPC model order (12 = 6 pole pairs, enough for
        4-5 formants).
    window_ms : float
        Analysis window duration (ms) on the impulse response.

    Returns
    -------
    list of float
        List of formants (F1, F2, F3, ...) sorted by
        increasing frequency. Empty list if the measurement fails.
    """
    vtl = _import_vtl()
    from scipy.linalg import toeplitz

    # Transfer function (magnitude + phase)
    result = vtl.tract_state_to_transfer_function(tract19.astype(np.float64))
    mag = np.array(result['magnitude_spectrum']).flatten()
    phase = np.array(result.get('phase_spectrum',
                                  np.zeros_like(mag))).flatten()
    # Reconstruct complex TF and impulse response
    H = mag * np.exp(1j * phase)
    h = np.fft.irfft(H, n=2 * len(H) - 1)
    # Window the impulse response
    n_win = int(window_ms * 1e-3 * sr_audio)
    h = h[:n_win]
    if len(h) < n_win:
        h = np.pad(h, (0, n_win - len(h)))
    h = h * np.hamming(len(h))
    # Autocorrelation LPC
    n = len(h)
    if n < order + 2:
        return []
    R = np.correlate(h, h, mode='full')[n - 1:n + order]
    R = R + 1e-8 * np.max(np.abs(R))  # regularization
    try:
        A = np.linalg.solve(toeplitz(R[:-1]), R[1:])
        A = np.concatenate([[1.0], -A])
        roots = np.roots(A)
        formants = []
        for r in roots:
            if np.imag(r) > 0.01:
                f = np.angle(r) * sr_audio / (2 * np.pi)
                bw = -2 * np.log(np.abs(r)) * sr_audio / (2 * np.pi)
                if 90 < f < 5000 and bw < 800:
                    formants.append((f, bw))
        formants.sort()
        return [f for f, _ in formants[:5]]
    except Exception:
        return []


# =====================================================================
# Tract construction from a (rho, theta) target
# =====================================================================

def build_tract(rho: float, theta: float, co_vtl: dict,
                covtl_to_full: dict) -> np.ndarray:
    """Builds the 19-parameter vector for a (rho, theta) target.

    Parameters
    ----------
    rho : float
        Polar radius (0.0 = neutral, 1.0 = nominal target, >1.0 = occlusion).
    theta : float
        Polar angle (radians).
    co_vtl : dict
        CO_VTL matrix: {param_name → (c1, c0, c2)}.
    covtl_to_full : dict
        Mapping {param_name → index 0-18} in the 19-parameter vector.

    Returns
    -------
    np.ndarray (19,)
        Tract state vector.
    """
    tract = np.zeros(19)
    for p, idx in covtl_to_full.items():
        c1, c0, c2 = co_vtl[p]
        tract[idx] = c1 + rho * c0 * np.cos(c2 - theta)
    return tract


# =====================================================================
# Formant measurement for a target
# =====================================================================

def measure_formants(rho: float, theta: float, co_vtl: dict,
                     covtl_to_full: dict) -> Tuple[float, float]:
    """Measures F1/F2 for a (rho, theta) target via VTL + LPC.

    Returns
    -------
    (F1, F2) in Hz, or (0, 0) if the measurement fails.
    """
    tract = build_tract(rho, theta, co_vtl, covtl_to_full)
    formants = compute_formants_lpc(tract)
    if len(formants) >= 2:
        return formants[0], formants[1]
    return 0.0, 0.0


# =====================================================================
# Optimal rho search for a vowel
# =====================================================================

def find_best_rho(f1_att: float, f2_att: float, theta: float,
                  co_vtl: dict, covtl_to_full: dict,
                  rho_min: float = 0.3, rho_max: float = 1.2,
                  rho_step: float = 0.05,
                  verbose: bool = False) -> Tuple[float, float, float, float]:
    """Finds the optimal rho for a vowel (fixed theta).

    Parameters
    ----------
    f1_att, f2_att : float
        Reference formants (Hz) — targets to reach.
    theta : float
        Fixed polar angle (radians) — cardinal position of the vowel.
    co_vtl, covtl_to_full : dict
        COVTL matrix and index mapping (cf. build_tract).
    rho_min, rho_max, rho_step : float
        Search range for rho.
    verbose : bool
        If True, prints each measurement.

    Returns
    -------
    (best_rho, best_f1, best_f2, best_err) : tuple
        best_err = |F1_pred - F1_att| + |F2_pred - F2_att| (Hz).
    """
    best_err = float('inf')
    best_rho = 0.5
    best_f1, best_f2 = 0.0, 0.0
    for rho in np.arange(rho_min, rho_max + 0.001, rho_step):
        f1, f2 = measure_formants(rho, theta, co_vtl, covtl_to_full)
        if f1 == 0 or f2 == 0:
            if verbose:
                print(f'    rho={rho:.3f} θ={np.degrees(theta):.0f}° : no formants')
            continue
        err = abs(f1 - f1_att) + abs(f2 - f2_att)
        if verbose:
            print(f'    rho={rho:.3f} θ={np.degrees(theta):.0f}° : F1={f1:.0f} F2={f2:.0f} err={err:.0f}')
        if err < best_err:
            best_err = err
            best_rho = float(rho)
            best_f1, best_f2 = float(f1), float(f2)
    return best_rho, best_f1, best_f2, best_err


# =====================================================================
# Full calibration of a language
# =====================================================================

def calibrate_vowels(lang: str,
                     co_vtl: Optional[dict] = None,
                     covtl_to_full: Optional[dict] = None,
                     speaker_path: Optional[str] = None,
                     rho_range_cardinal: Tuple[float, float, float] = (0.3, 1.2, 0.02),
                     rho_range_others: Tuple[float, float, float] = (0.3, 1.05, 0.05),
                     verbose: bool = False) -> Dict[str, Tuple[float, float]]:
    """Calibrates the vowel targets for a language and a VTL speaker.

    Parameters
    ----------
    lang : str
        ISO 639-1 language code (e.g. 'fr', 'en', 'es', 'de').
    co_vtl : dict, optional
        CO_VTL matrix {param → (c1, c0, c2)}. If None, uses
        the repository's ``constants.CO_VTL``.
    covtl_to_full : dict, optional
        Mapping {param → index 0-18}. If None, uses
        ``constants.COVTL_TO_FULL``.
    speaker_path : str, optional
        Path to the VTL .speaker file. If None, uses the
        default speaker (JD3).
    rho_range_cardinal : tuple
        (rho_min, rho_max, rho_step) for the /a/ /i/ /u/ extremes.
    rho_range_others : tuple
        (rho_min, rho_max, rho_step) for the other vowels.
    verbose : bool
        If True, prints each formant measurement.

    Returns
    -------
    dict
        {vowel_key → (rho, theta)} ready to install in VOWEL_TARGETS.
    """
    # Lazy imports
    if co_vtl is None or covtl_to_full is None:
        CO_VTL, COVTL_TO_FULL = _import_constants()
        if co_vtl is None:
            co_vtl = CO_VTL
        if covtl_to_full is None:
            covtl_to_full = COVTL_TO_FULL

    # Load the speaker if specified
    vtl = _import_vtl()
    if speaker_path is not None:
        if not os.path.exists(speaker_path):
            raise FileNotFoundError(f'speaker file not found: {speaker_path}')
        # Note: the VTL 0.0.17 API does not make it easy to load a
        # custom speaker; the default speaker (JD3) is used. For
        # another speaker, VTL would have to be recompiled.
        print(f'[!] Note: speaker_path={speaker_path!r} ignored (VTL API '
              f'limitation) — using the default speaker',
              file=sys.stderr)

    # Language inventory
    from vtl_synth.utils.language_vowel_sets import get_vowel_targets, get_cardinal_corners, get_schwa_key
    vowel_targets_ref = get_vowel_targets(lang)
    cardinal_corners = get_cardinal_corners(lang)
    schwa_key = get_schwa_key(lang)

    print(f'[+] Automatic calibration for language: {lang!r}')
    print(f'    Cardinal extremes: {cardinal_corners}')
    print(f'    Schwa: {schwa_key}')
    print()

    # Step 1: calibrate the /a/ /i/ /u/ extremes with a fine rho
    print('=== Step 1: cardinal extremes (fine rho) ===')
    print(f'{"vow":>4} {"θ°":>5} {"F1_tgt":>7} {"F2_tgt":>7} '
          f'{"rho_opt":>7} {"F1_pred":>7} {"F2_pred":>7} {"error":>7}')
    targets = {}
    cardinal_rhos = {}
    for v in cardinal_corners:
        f1_att, f2_att, theta, desc = vowel_targets_ref[v]
        rho, f1, f2, err = find_best_rho(
            f1_att, f2_att, theta, co_vtl, covtl_to_full,
            rho_min=rho_range_cardinal[0],
            rho_max=rho_range_cardinal[1],
            rho_step=rho_range_cardinal[2],
            verbose=verbose,
        )
        targets[v] = (rho, theta)
        cardinal_rhos[v] = rho
        print(f'  /{v}/ {int(np.degrees(theta)):>5} {f1_att:>7.0f} {f2_att:>7.0f} '
              f'{rho:>7.3f} {f1:>7.0f} {f2:>7.0f} {err:>7.0f}  {desc}')

    # Step 2: calibrate the other vowels
    print()
    print('=== Step 2: other vowels ===')
    print(f'{"vow":>4} {"θ°":>5} {"F1_tgt":>7} {"F2_tgt":>7} '
          f'{"rho_opt":>7} {"F1_pred":>7} {"F2_pred":>7} {"error":>7}')
    for v, (f1_att, f2_att, theta, desc) in vowel_targets_ref.items():
        if v in cardinal_corners or v == schwa_key:
            continue
        rho, f1, f2, err = find_best_rho(
            f1_att, f2_att, theta, co_vtl, covtl_to_full,
            rho_min=rho_range_others[0],
            rho_max=rho_range_others[1],
            rho_step=rho_range_others[2],
            verbose=verbose,
        )
        targets[v] = (rho, theta)
        print(f'  /{v}/ {int(np.degrees(theta)):>5} {f1_att:>7.0f} {f2_att:>7.0f} '
              f'{rho:>7.3f} {f1:>7.0f} {f2:>7.0f} {err:>7.0f}  {desc}')

    # Step 3: schwa = centroid of the a-i-u triangle
    if schwa_key is not None:
        rho_mean = np.mean(list(cardinal_rhos.values()))
        theta_schwa = vowel_targets_ref[schwa_key][2]
        targets[schwa_key] = (rho_mean, theta_schwa)
        print()
        print(f'=== Step 3: schwa /{schwa_key}/ ===')
        print(f'  rho = mean of the cardinals = ({cardinal_rhos}) = {rho_mean:.3f}')
        print(f'  theta = {np.degrees(theta_schwa):.0f}°')

    print()
    print('=== Final calibrated targets ===')
    print('VOWEL_TARGETS = {')
    for v, (rho, theta) in targets.items():
        print(f"    '{v}': ({rho:.3f}, {theta:.6f}),  # {int(np.degrees(theta))}°")
    print('}')

    return targets


# =====================================================================
# CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Automatically calibrates the vowel targets for '
                    'a language and a VTL speaker.',
    )
    parser.add_argument('--lang', default='fr',
                        choices=['fr', 'en', 'es', 'de'],
                        help='language code (default: fr)')
    parser.add_argument('--speaker', default=None,
                        help='path to the VTL .speaker file')
    parser.add_argument('--output', '-o', default=None,
                        help='output JSON file (calibrated_vowels.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='print each formant measurement')
    args = parser.parse_args()

    targets = calibrate_vowels(
        lang=args.lang,
        speaker_path=args.speaker,
        verbose=args.verbose,
    )

    # Save to JSON
    if args.output is None:
        args.output = f'/home/z/my-project/download/calibrated_vowels_{args.lang}.json'
    data = {v: {'rho': r, 'theta_deg': np.degrees(t), 'theta_rad': t}
            for v, (r, t) in targets.items()}
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'\n[+] Calibration saved: {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
