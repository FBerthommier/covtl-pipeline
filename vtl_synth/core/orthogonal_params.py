# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
orthogonal_params.py
====================
Side branch: orthogonal (non-COVTL) and source (glottis) parameters.

This module implements the side branch of the Berthommier-VTL pipeline:

  Architecture:                    
    VTL(t) = B(t) + E_source(t) + E_ortho(t)

    - B(t)     : Berthommier core — (rho,theta) -> COVTL -> 15 tract params
    - E_source : glottal source branch — 11 glottal control params
    - E_ortho  : orthogonal branch   — VS, VO, TRX, TRY, contextual TS3

The orthogonal parameters are those NOT controlled by the polar
space (rho, theta) of the COVTL model: 
    - VS (velum shape)       : depends on nasal context
    - VO (velum opening)      : depends on nasal context  
    - TRX, TRY (tongue root)  : left to VTL auto-calculation
    - TS3 (tongue side 3)     : context-dependent (fricatives=1, laterals=-1)

The values are extracted from the JD3.speaker file and injected
into the trajectories at TARGET_SR, then upsampled to TRACT_SR by
AssembleTract.

Source: JD3.speaker (contextual tract shapes + glottal shapes)
"""

from __future__ import annotations

import re
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from vtl_synth.core.constants import (
    TARGET_SR,
    TRACT_SR,
    N_TRACT_PARAMS,
    IDX_VS,
    IDX_VO,
    TRACT_PARAM_NAMES,
    AUTO_PARAMS,
    VOWEL_TARGETS,
)
from vtl_synth.core.speaker_jd import (
    parse_speaker_file,
    get_orthogonal_targets,
    get_ts3_context_map,
    get_vowel_orthogonal_defaults,
    get_consonant_orthogonal_targets,
    DEFAULT_SPEAKER_FILE,
)


# ==========================================================================
# Contextual TS3 map
# ==========================================================================
# This map is built from the JD shapes:
#   fricatives -> TS3 = +1.0 (edge raising for constriction)
#   laterals   -> TS3 = -1.0 (lowering for lateral passage)
#   stops      -> TS3 = 0.0
#   vowels     -> TS3 = COVTL (core value, no override)

# --- Articular-to-articulation type mapping ---
# Each pipeline consonant is mapped to an articulatory type
# that determines TS3 behavior.

ARTIC_TYPE_TO_TS3: Dict[str, float] = {
    # Fricatives -> TS3 = 1.0
    'fricative': 1.0,
    'dental-fricative': 1.0,
    'alveolar-fricative': 1.0,
    'postalveolar-fricative': 1.0,
    'palatal-fricative': 1.0,
    'uvular-fricative': 1.0,
    # Laterals -> TS3 = -1.0
    'lateral': -1.0,
    'alveolar-lateral': -1.0,
    'postalveolar-lateral': -1.0,
    # Stops -> TS3 = 0.0 (handled by COVTL)
    'closure': 0.0,
    'labial-closure': 0.0,
    'alveolar-closure': 0.0,
    'postalveolar-closure': 0.0,
    'velar-closure': 0.0,
    'dental-fricative': 1.0,
}

# Articulatory type → JD shape prefix mapping (used in get_ts3/get_vs)
_JD_ARTIC_MAP: Dict[str, str] = {
    'labial-closure': 'll-labial-closure',
    'tt-dental-fricative': 'tt-dental-fricative',
    'll-dental-fricative': 'll-dental-fricative',
    'alveolar-closure': 'tt-alveolar-closure',
    'alveolar-fricative': 'tt-alveolar-fricative',
    'alveolar-lateral': 'tt-alveolar-lateral',
    'postalveolar-closure': 'tt-postalveolar-closure',
    'postalveolar-fricative': 'tt-postalveolar-fricative',
    'postalveolar-lateral': 'tt-postalveolar-lateral',
    'palatal-fricative': 'tb-palatal-fricative',
    'velar-closure': 'tb-velar-closure',
    'uvular-fricative': 'tb-uvular-fricative',
}

# Pipeline phonemes -> articulatory type mapping
PHONEME_TO_ARTIC_TYPE: Dict[str, str] = {
    # Labials
    'b': 'labial-closure', 'p': 'labial-closure',
    'f': 'dental-fricative', 'v': 'dental-fricative',
    # Dentals (T/D = dental fricatives, f/v = labiodental)
    'T': 'tt-dental-fricative', 'D': 'tt-dental-fricative',
    'f': 'll-dental-fricative', 'v': 'll-dental-fricative',
    # Alveolars
    's': 'alveolar-fricative', 'z': 'alveolar-fricative',
    'd': 'alveolar-closure', 't': 'alveolar-closure',
    'l': 'alveolar-lateral',
    # Postalveolars
    'S': 'postalveolar-fricative', 'Z': 'postalveolar-fricative',
    'tS': 'postalveolar-closure', 'dZ': 'postalveolar-closure',
    # Palatals
    'C': 'palatal-fricative', 'j': 'palatal-fricative',
    # Velars
    'g_vel': 'velar-closure', 'g_pal': 'velar-closure',
    'k': 'velar-closure', 'g': 'velar-closure',
    # Uvulars
    'X': 'uvular-fricative', 'R': 'uvular-fricative',
}


# ==========================================================================
# OrthogonalBranch class
# ==========================================================================

class OrthogonalBranch:
    """Side branch for orthogonal and source parameters.

    This class generates, for each time frame: 
      - VS(t) : velum shape (nasality)
      - VO(t) : velum opening (nasality)
      - TRX(t), TRY(t) : tongue root (auto)
      - TS3_ortho(t) : contextual TS3 override (fricatives/laterals)

    For the glottal source, parameters are generated by ProsodySource
    (already existing). This module focuses on the orthogonal tract
    parameters.

    Parameters
    ----------
    speaker_file : str
        Path to the JD .speaker file.
    """

    def __init__(self, speaker_file: str = DEFAULT_SPEAKER_FILE):
        self.speaker_file = speaker_file
        self._load_speaker_data()

    def _load_speaker_data(self) -> None:
        """Load and index the speaker data."""
        self.ortho_targets = get_orthogonal_targets(self.speaker_file)
        self.ts3_context_map = get_ts3_context_map(self.speaker_file)
        self.vowel_ortho = get_vowel_orthogonal_defaults(self.speaker_file)
        self.consonant_ortho = get_consonant_orthogonal_targets(self.speaker_file)

    # ------------------------------------------------------------------
    # Contextual TS3
    # ------------------------------------------------------------------

    def get_ts3_for_phoneme(self, phoneme: str, vowel_context: str = 'a') -> float:
        """Return the TS3 value for a phoneme in a context.

        For vowels, returns None (COVTL handles TS3).
        For consonants, derived from the JD contextual map.

        Parameters
        ----------
        phoneme : str
            Phoneme (e.g. 'b', 's', 'S', 'g').
        vowel_context : str
            Context vowel (e.g. 'a', 'i', 'u').

        Returns
        -------
        float or None
            TS3 value, or None if COVTL handles it.
        """
        # Vowels use the COVTL core TS3 (HARD-005: direct test
        # against VOWEL_TARGETS — the old literal list contained
        # phantom keys 'E:', 'I', 'U', 'Y')
        if phoneme in VOWEL_TARGETS:
            return None

        # Determine the articulatory type
        artic_type = PHONEME_TO_ARTIC_TYPE.get(phoneme, '')
        if not artic_type:
            return None  # No override

        # Look up the value in the contextual JD shapes
        # JD format: 'tt-alveolar-fricative(a)', 'tb-velar-closure(i)', etc.
        jd_artic_map = {
            'labial-closure': 'll-labial-closure',
            'tt-dental-fricative': 'tt-dental-fricative',
            'll-dental-fricative': 'll-dental-fricative',
            'alveolar-closure': 'tt-alveolar-closure',
            'alveolar-fricative': 'tt-alveolar-fricative',
            'alveolar-lateral': 'tt-alveolar-lateral',
            'postalveolar-closure': 'tt-postalveolar-closure',
            'postalveolar-fricative': 'tt-postalveolar-fricative',
            'postalveolar-lateral': 'tt-postalveolar-lateral',
            'palatal-fricative': 'tb-palatal-fricative',
            'velar-closure': 'tb-velar-closure',
            'uvular-fricative': 'tb-uvular-fricative',
        }
        jd_prefix = jd_artic_map.get(artic_type)
        if jd_prefix is None:
            return None
        # Vowel context: preference (vowel_context), fallback (a)
        key = f'{jd_prefix}({vowel_context})'
        if key in self.ts3_context_map:
            return float(self.ts3_context_map[key])
        key = f'{jd_prefix}(a)'
        return float(self.ts3_context_map.get(key, 0.0))

    # ------------------------------------------------------------------
    # VS (velum shape) from JD
    # ------------------------------------------------------------------

    def get_vs_for_vowel(self, vowel: str) -> float:
        """Return VS (velum shape) for a vowel from JD.

        Parameters
        ----------
        vowel : str
            Phonetic symbol of the vowel.

        Returns
        -------
        float
            VS value from JD, or 0.0 by default.
        """
        if vowel in self.vowel_ortho:
            return self.vowel_ortho[vowel].get('VS', 0.0)
        return 0.0

    def get_vs_for_consonant(self, phoneme: str, vowel_context: str = 'a') -> float:
        """Return VS for a consonantal context from JD.

        Parameters
        ----------
        phoneme : str
            Phoneme.
        vowel_context : str
            Context vowel.

        Returns
        -------
        float
        """
        artic_type = PHONEME_TO_ARTIC_TYPE.get(phoneme, '')
        jd_artic_map = {
            'labial-closure': 'll-labial-closure',
            'tt-dental-fricative': 'tt-dental-fricative',
            'll-dental-fricative': 'll-dental-fricative',
            'alveolar-closure': 'tt-alveolar-closure',
            'alveolar-fricative': 'tt-alveolar-fricative',
            'alveolar-lateral': 'tt-alveolar-lateral',
            'postalveolar-closure': 'tt-postalveolar-closure',
            'postalveolar-fricative': 'tt-postalveolar-fricative',
            'postalveolar-lateral': 'tt-postalveolar-lateral',
            'palatal-fricative': 'tb-palatal-fricative',
            'velar-closure': 'tb-velar-closure',
            'uvular-fricative': 'tb-uvular-fricative',
        }

        jd_name = jd_artic_map.get(artic_type, '')
        if jd_name:
            shape_key = f"{jd_name}({vowel_context})"
            for name, ortho in self.ortho_targets.items():
                if name == shape_key and 'VS' in ortho:
                    return ortho['VS']

        # Fallback: VS of the context vowel
        return self.get_vs_for_vowel(vowel_context)

    # ------------------------------------------------------------------
    # Time trajectories
    # ------------------------------------------------------------------

    def compute_ts3_trajectory(
        self,
        phoneme_sequence: List[str],
        vowel_contexts: List[Optional[str]],
        t_ms: np.ndarray,
        segment_boundaries: List[Tuple[float, float]],
        ramp_ms: float = 10.0,
    ) -> np.ndarray:
        """Compute the TS3_ortho(t) trajectory at TARGET_SR.

        For each consonantal segment, TS3 is overridden with the
        contextual JD value. For vowels, TS3 stays at 0 (COVTL
        handles it).

        Parameters
        ----------
        phoneme_sequence : list[str]
            Phoneme sequence.
        vowel_contexts : list[str|None]
            Context vowel for each phoneme.
        t_ms : np.ndarray
            Time vector (ms).
        segment_boundaries : list[tuple]
            [(t_start, t_end), ...] for each phoneme.
        ramp_ms : float
            Transition ramp duration (ms).

        Returns
        -------
        np.ndarray, shape (n_frames,)
            TS3_ortho(t) — override to add to the COVTL core TS3.
        """
        n_frames = len(t_ms)
        ts3 = np.zeros(n_frames, dtype=np.float64)
        ramp_frames = max(1, int(ramp_ms * TARGET_SR / 1000.0))

        for idx, (phoneme, ctx) in enumerate(zip(phoneme_sequence, vowel_contexts)):
            target_ts3 = self.get_ts3_for_phoneme(phoneme, ctx or 'a')

            if target_ts3 is None or abs(target_ts3) < 0.01:
                continue  # COVTL handles it, no override

            t_start, t_end = segment_boundaries[idx]
            i_start = int(t_start * TARGET_SR / 1000.0)
            i_end = int(t_end * TARGET_SR / 1000.0)
            i_start = np.clip(i_start, 0, n_frames - 1)
            i_end = min(i_end, n_frames)

            if i_end <= i_start:
                continue

            # Attack ramp
            ramp_end = min(i_start + ramp_frames, i_end)
            n_ramp = ramp_end - i_start
            if n_ramp > 0:
                prev_val = ts3[max(0, i_start - 1)]
                alpha = np.linspace(0, 1, n_ramp)
                ts3[i_start:ramp_end] = prev_val + alpha * (target_ts3 - prev_val)

            # Hold
            ts3[ramp_end:i_end] = target_ts3

            # Release ramp
            relax_end = min(i_end + ramp_frames, n_frames)
            n_relax = relax_end - i_end
            if n_relax > 0 and idx + 1 < len(phoneme_sequence):
                next_ts3 = self.get_ts3_for_phoneme(
                    phoneme_sequence[idx + 1],
                    vowel_contexts[idx + 1] or 'a'
                ) or 0.0
                alpha = np.linspace(0, 1, n_relax)
                ts3[i_end:relax_end] = target_ts3 + alpha * (next_ts3 - target_ts3)

        return ts3

    def compute_vs_trajectory(
        self,
        phoneme_sequence: List[str],
        vowel_contexts: List[Optional[str]],
        t_ms: np.ndarray,
        segment_boundaries: List[Tuple[float, float]],
        ramp_ms: float = 15.0,
    ) -> np.ndarray:
        """Compute the VS(t) trajectory at TARGET_SR from JD.

        Parameters
        ----------
        phoneme_sequence : list[str]
            Phoneme sequence.
        vowel_contexts : list[str|None]
            Context vowel for each phoneme.
        t_ms : np.ndarray
            Time vector (ms).
        segment_boundaries : list[tuple]
            [(t_start, t_end), ...] for each phoneme.
        ramp_ms : float
            Transition ramp duration (ms).

        Returns
        -------
        np.ndarray, shape (n_frames,)
            VS(t) — velum shape.
        """
        n_frames = len(t_ms)
        vs = np.zeros(n_frames, dtype=np.float64)
        ramp_frames = max(1, int(ramp_ms * TARGET_SR / 1000.0))

        for idx, (phoneme, ctx) in enumerate(zip(phoneme_sequence, vowel_contexts)):
            if phoneme in VOWEL_TARGETS:
                target_vs = self.get_vs_for_vowel(phoneme)
            else:
                target_vs = self.get_vs_for_consonant(phoneme, ctx or 'a')

            t_start, t_end = segment_boundaries[idx]
            i_start = int(t_start * TARGET_SR / 1000.0)
            i_end = int(t_end * TARGET_SR / 1000.0)
            i_start = np.clip(i_start, 0, n_frames - 1)
            i_end = min(i_end, n_frames)

            if i_end <= i_start:
                continue

            # Smooth transition
            ramp_start = min(i_start + ramp_frames, i_end)
            n_ramp = ramp_start - i_start
            if n_ramp > 0:
                prev_val = vs[max(0, i_start - 1)]
                alpha = np.linspace(0, 1, n_ramp)
                vs[i_start:ramp_start] = prev_val + alpha * (target_vs - prev_val)

            vs[ramp_start:i_end] = target_vs

        return vs

    # ------------------------------------------------------------------
    # Full interface
    # ------------------------------------------------------------------

    def get_orthogonal_trajectories(
        self,
        phoneme_sequence: List[str],
        vowel_contexts: List[Optional[str]],
        total_duration_ms: float,
        segment_durations_ms: List[float],
    ) -> Dict[str, np.ndarray]:
        """Compute all orthogonal trajectories.

        Parameters
        ----------
        phoneme_sequence : list[str]
            Phoneme sequence.
        vowel_contexts : list[str|None]
            Context vowel for each phoneme.
        total_duration_ms : float
            Total duration (ms).
        segment_durations_ms : list[float]
            Duration of each segment (ms).

        Returns
        -------
        dict[str, np.ndarray]
            - 'VS_ortho' : velum shape at TARGET_SR
            - 'TS3_ortho' : contextual TS3 override at TARGET_SR
        """
        n_frames = int(total_duration_ms * TARGET_SR / 1000.0) + 1
        t_ms = np.linspace(0, total_duration_ms, n_frames)

        # Compute segment boundaries
        boundaries = []
        t = 0.0
        for dur in segment_durations_ms:
            boundaries.append((t, t + dur))
            t += dur

        vs_traj = self.compute_vs_trajectory(
            phoneme_sequence, vowel_contexts, t_ms, boundaries
        )
        ts3_traj = self.compute_ts3_trajectory(
            phoneme_sequence, vowel_contexts, t_ms, boundaries
        )

        return {
            'VS_ortho': vs_traj,
            'TS3_ortho': ts3_traj,
        }


# ==========================================================================
# Utility functions
# ==========================================================================

def get_ts3_summary(speaker_file: str = DEFAULT_SPEAKER_FILE) -> Dict[str, float]:
    """Return the TS3 summary per articulatory type from JD.

    Returns
    -------
    dict[str, float]
        {artic_type: ts3_value} — mean value per type.
    """
    ts3_map = get_ts3_context_map(speaker_file)
    summary = {}
    
    # Group by articulatory type
    type_values = {}
    for shape_name, ts3_val in ts3_map.items():
        # Extract the type (part before the parenthesis)
        m = re.match(r'^[a-z]+(?:-[a-z]+)*', shape_name)
        if m:
            art_type = m.group(0)
            if art_type not in type_values:
                type_values[art_type] = []
            type_values[art_type].append(ts3_val)

    for art_type, values in type_values.items():
        summary[art_type] = float(np.mean(values))

    return summary


if __name__ == '__main__':
    ob = OrthogonalBranch()
    print("=== TS3 Summary ===")
    summary = get_ts3_summary()
    for k, v in sorted(summary.items()):
        print(f"  {k:40s} : TS3 = {v:+.4f}")
    print()
    print("=== Per-phoneme TS3 ===")
    for phoneme in ['b', 's', 'S', 'l', 'g', 'f', 't', 'd']:
        for ctx in ['a', 'i', 'u']:
            val = ob.get_ts3_for_phoneme(phoneme, ctx)
            if val is not None:
                print(f"  {phoneme}/{ctx}: TS3 = {val:+.4f}")
    print()
    print("=== Vowel VS ===")
    for v in ['a', 'e', 'i', 'o', 'u', 'y', '@']:
        print(f"  {v}: VS = {ob.get_vs_for_vowel(v):.4f}")
