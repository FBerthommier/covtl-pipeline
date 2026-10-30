# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
calibrate_vowels.py
====================
Calibrage automatique des cibles vocaliques (rho, theta) pour un
locuteur VTL spécifique et une langue cible.

Principe
--------
Étant donnés :
  1. Un speaker VTL (fichier .speaker) — définit la géométrie du tract
  2. Une matrice COVTL (coefficients c0/c1/c2 des 15 paramètres VTL) —
     définie dans ``constants.CO_VTL``
  3. Un inventaire vocalique de langue (F1/F2 attendus + theta cardinal)
     — défini dans ``language_vowel_sets.VOWEL_SETS``

Le calibreur :
  - Mesure les extréma mécaniques /a/ /i/ /u/ du speaker en balayant
    rho ∈ [0.3, 1.2] et en mesurant les formants via la transfer function
    VTL + analyse LPC.
  - Pour chaque voyelle, trouve le rho optimal (theta fixe) qui
    minimise l'écart aux formants de référence de la langue.
  - Calcule le schwa comme centroïde du triangle a-i-u.
  - Retourne un dict ``{clé → (rho, theta)}`` prêt à être installé
    dans ``constants.VOWEL_TARGETS``.

Usage
-----
::

    from vtl_synth.utils.calibrate_vowels import calibrate_vowels
    from vtl_synth.core.constants import CO_VTL, COVTL_TO_FULL

    targets = calibrate_vowels(
        lang='fr',
        co_vtl=CO_VTL,
        covtl_to_full=COVTL_TO_FULL,
        speaker_path=None,  # utilise le speaker VTL par défaut
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

# Imports paresseux pour éviter les dépendances circulaires
def _import_vtl():
    """Import vocaltractlab_cython (lazy)."""
    import vocaltractlab_cython as vtl
    return vtl


def _import_constants():
    """Importe CO_VTL et COVTL_TO_FULL depuis constants (lazy)."""
    from vtl_synth.core.constants import CO_VTL, COVTL_TO_FULL
    return CO_VTL, COVTL_TO_FULL


# =====================================================================
# Mesure des formants par LPC
# =====================================================================

def compute_formants_lpc(tract19, sr_audio: int = 44100,
                          order: int = 12, window_ms: float = 30.0):
    """Mesure les formants d'un état du tract via analyse LPC.

    Parameters
    ----------
    tract19 : array-like (19,)
        Vecteur d'état du tract vocal (19 paramètres VTL).
    sr_audio : int
        Fréquence d'échantillonnage audio (Hz).
    order : int
        Ordre du modèle LPC (12 = 6 paires de pôles, suffisant pour
        4-5 formants).
    window_ms : float
        Durée de la fenêtre d'analyse (ms) sur l'impulse response.

    Returns
    -------
    list of float
        Liste des formants (F1, F2, F3, ...) triés par fréquence
        croissante. Liste vide si la mesure échoue.
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
    R = R + 1e-8 * np.max(np.abs(R))  # régularisation
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
# Construction du tract à partir d'une cible (rho, theta)
# =====================================================================

def build_tract(rho: float, theta: float, co_vtl: dict,
                covtl_to_full: dict) -> np.ndarray:
    """Construit le vecteur 19-paramètres pour une cible (rho, theta).

    Parameters
    ----------
    rho : float
        Rayon polaire (0.0 = neutre, 1.0 = cible nominale, >1.0 = occlusion).
    theta : float
        Angle polaire (radians).
    co_vtl : dict
        Matrice CO_VTL : {param_name → (c1, c0, c2)}.
    covtl_to_full : dict
        Mapping {param_name → index 0-18} dans le vecteur 19-paramètres.

    Returns
    -------
    np.ndarray (19,)
        Vecteur d'état du tract.
    """
    tract = np.zeros(19)
    for p, idx in covtl_to_full.items():
        c1, c0, c2 = co_vtl[p]
        tract[idx] = c1 + rho * c0 * np.cos(c2 - theta)
    return tract


# =====================================================================
# Mesure des formants pour une cible
# =====================================================================

def measure_formants(rho: float, theta: float, co_vtl: dict,
                     covtl_to_full: dict) -> Tuple[float, float]:
    """Mesure F1/F2 pour une cible (rho, theta) via VTL + LPC.

    Returns
    -------
    (F1, F2) en Hz, ou (0, 0) si la mesure échoue.
    """
    tract = build_tract(rho, theta, co_vtl, covtl_to_full)
    formants = compute_formants_lpc(tract)
    if len(formants) >= 2:
        return formants[0], formants[1]
    return 0.0, 0.0


# =====================================================================
# Recherche du rho optimal pour une voyelle
# =====================================================================

def find_best_rho(f1_att: float, f2_att: float, theta: float,
                  co_vtl: dict, covtl_to_full: dict,
                  rho_min: float = 0.3, rho_max: float = 1.2,
                  rho_step: float = 0.05,
                  verbose: bool = False) -> Tuple[float, float, float, float]:
    """Trouve le rho optimal pour une voyelle (theta fixe).

    Parameters
    ----------
    f1_att, f2_att : float
        Formants de référence (Hz) — cibles à atteindre.
    theta : float
        Angle polaire fixe (radians) — position cardinale de la voyelle.
    co_vtl, covtl_to_full : dict
        Matrice COVTL et mapping d'index (cf. build_tract).
    rho_min, rho_max, rho_step : float
        Plage de recherche pour rho.
    verbose : bool
        Si True, affiche chaque mesure.

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
# Calibrage complet d'une langue
# =====================================================================

def calibrate_vowels(lang: str,
                     co_vtl: Optional[dict] = None,
                     covtl_to_full: Optional[dict] = None,
                     speaker_path: Optional[str] = None,
                     rho_range_cardinal: Tuple[float, float, float] = (0.3, 1.2, 0.02),
                     rho_range_others: Tuple[float, float, float] = (0.3, 1.05, 0.05),
                     verbose: bool = False) -> Dict[str, Tuple[float, float]]:
    """Calibre les cibles vocaliques pour une langue et un speaker VTL.

    Parameters
    ----------
    lang : str
        Code langue ISO 639-1 (e.g. 'fr', 'en', 'es', 'de').
    co_vtl : dict, optional
        Matrice CO_VTL {param → (c1, c0, c2)}. Si None, utilise
        ``constants.CO_VTL`` du dépôt.
    covtl_to_full : dict, optional
        Mapping {param → index 0-18}. Si None, utilise
        ``constants.COVTL_TO_FULL``.
    speaker_path : str, optional
        Chemin vers le fichier .speaker VTL. Si None, utilise le
        speaker par défaut (JD3).
    rho_range_cardinal : tuple
        (rho_min, rho_max, rho_step) pour les extréma /a/ /i/ /u/.
    rho_range_others : tuple
        (rho_min, rho_max, rho_step) pour les autres voyelles.
    verbose : bool
        Si True, affiche chaque mesure de formants.

    Returns
    -------
    dict
        {clé_voyelle → (rho, theta)} prêt à installer dans VOWEL_TARGETS.
    """
    # Imports paresseux
    if co_vtl is None or covtl_to_full is None:
        CO_VTL, COVTL_TO_FULL = _import_constants()
        if co_vtl is None:
            co_vtl = CO_VTL
        if covtl_to_full is None:
            covtl_to_full = COVTL_TO_FULL

    # Charger le speaker si spécifié
    vtl = _import_vtl()
    if speaker_path is not None:
        if not os.path.exists(speaker_path):
            raise FileNotFoundError(f'speaker file not found: {speaker_path}')
        # Note : l'API VTL 0.0.17 ne permet pas de charger un speaker
        # personnalisé facilement ; le speaker par défaut (JD3) est
        # utilisé. Pour un autre speaker, il faudrait recompilier VTL.
        print(f'[!] Note: speaker_path={speaker_path!r} ignoré (VTL API '
              f'limitation) — utilisation du speaker par défaut',
              file=sys.stderr)

    # Inventaire de la langue
    from vtl_synth.utils.language_vowel_sets import get_vowel_targets, get_cardinal_corners, get_schwa_key
    vowel_targets_ref = get_vowel_targets(lang)
    cardinal_corners = get_cardinal_corners(lang)
    schwa_key = get_schwa_key(lang)

    print(f'[+] Calibrage automatique pour la langue : {lang!r}')
    print(f'    Extréma cardinaux : {cardinal_corners}')
    print(f'    Schwa : {schwa_key}')
    print()

    # Étape 1 : calibrer les extréma /a/ /i/ /u/ avec rho fin
    print('=== Étape 1 : extréma cardinaux (rho fin) ===')
    print(f'{"voy":>4} {"θ°":>5} {"F1_att":>7} {"F2_att":>7} '
          f'{"rho_opt":>7} {"F1_pred":>7} {"F2_pred":>7} {"erreur":>7}')
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

    # Étape 2 : calibrer les autres voyelles
    print()
    print('=== Étape 2 : autres voyelles ===')
    print(f'{"voy":>4} {"θ°":>5} {"F1_att":>7} {"F2_att":>7} '
          f'{"rho_opt":>7} {"F1_pred":>7} {"F2_pred":>7} {"erreur":>7}')
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

    # Étape 3 : schwa = centroïde du triangle a-i-u
    if schwa_key is not None:
        rho_mean = np.mean(list(cardinal_rhos.values()))
        theta_schwa = vowel_targets_ref[schwa_key][2]
        targets[schwa_key] = (rho_mean, theta_schwa)
        print()
        print(f'=== Étape 3 : schwa /{schwa_key}/ ===')
        print(f'  rho = moyenne des cardinaux = ({cardinal_rhos}) = {rho_mean:.3f}')
        print(f'  theta = {np.degrees(theta_schwa):.0f}°')

    print()
    print('=== Cibles finales calibrées ===')
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
        description='Calibre automatiquement les cibles vocaliques pour '
                    'une langue et un speaker VTL.',
    )
    parser.add_argument('--lang', default='fr',
                        choices=['fr', 'en', 'es', 'de'],
                        help='code langue (default: fr)')
    parser.add_argument('--speaker', default=None,
                        help='chemin vers le fichier .speaker VTL')
    parser.add_argument('--output', '-o', default=None,
                        help='fichier JSON de sortie (calibrated_vowels.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='affiche chaque mesure de formants')
    args = parser.parse_args()

    targets = calibrate_vowels(
        lang=args.lang,
        speaker_path=args.speaker,
        verbose=args.verbose,
    )

    # Sauvegarder en JSON
    if args.output is None:
        args.output = f'/home/z/my-project/download/calibrated_vowels_{args.lang}.json'
    data = {v: {'rho': r, 'theta_deg': np.degrees(t), 'theta_rad': t}
            for v, (r, t) in targets.items()}
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'\n[+] Calibration sauvegardée : {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
