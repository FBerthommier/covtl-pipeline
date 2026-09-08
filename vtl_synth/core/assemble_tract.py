# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
assemble_tract.py
=================
Merges B(t) + E(t) + E_ortho(t) and assembles the 400 Hz VTL .tract file.

This module is the final assembler. It takes:
  1. The Berthommier core tract trajectory B(t) at TARGET_SR (100 Hz)
  2. The extension variables E(t) at TARGET_SR  (source: TimedEnvelope)
  3. The orthogonal parameters E_ortho(t) at TARGET_SR (source: OrthogonalBranch)
  4. Upsamples them to TRACT_SR (400 Hz)
  5. Writes the .tract file in VTL 2.3 format

Architecture (rapport_vecteur_VTL_400Hz.pdf, §5):

    VTL(t) = B(t) + E_source(t) + E_ortho(t)

    - B(t)       : Berthommier core — 15 COVTL tract params
    - E_source   : source branch — 11 glottal params + VS/VO
    - E_ortho    : orthogonal branch — contextual TS3 (fricatives/laterals)

.tract file format:
  - Header line: version, n_frames, sr, n_tract, n_glottis
  - Data lines: tract_params(19) glottis_params(11)
  - All values separated by spaces

Source: rapport_vecteur_VTL_400Hz.pdf, §5
"""

from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple, Union

from vtl_synth.core.constants import (
    TRACT_PARAM_NAMES,
    GLOTTIS_PARAM_NAMES,
    TRACT_SR,
    TARGET_SR,
    N_TRACT_PARAMS,
    N_GLOTTIS_PARAMS,
    AUTO_PARAMS,
    COVTL_PARAMS,
    COVTL_TO_FULL,
    IDX_VS,
    IDX_VO,
    IDX_TS3,
    TBY_VELAR_OCCLUSION_MIN,
    TCX_VELAR_OCCLUSION_MAX,
    TCY_VELAR_OCCLUSION_MIN,
    PLOSIVE_VIRTUAL_TARGETS,
)


# ==========================================================================
# Hard downstream rectifications (post-COVTL projection)
# ==========================================================================
# These corrections are applied AFTER the COVTL projection and BEFORE
# the 100→400 Hz upsample, in full_tract_100.
#
# Principle: the Berthommier model (COVTL) produces trajectories
# that may not reach the physiological occlusion thresholds.
# Rather than biasing the model upstream (in build_cluster_pval),
# targeted corrections are applied downstream on the tract parameters.
#
# These corrections are "hard" (direct clamping). A soft rectification
# (sigmoid, smoothed window) may be added later for
# consonant fine-tuning.
# ==========================================================================

# Indices of parameters in the full tract vector (19 VTL params)
IDX_LD = 5    # Lip Distance
IDX_TCX = 8   # Tongue Center X
IDX_TCY = 9   # Tongue Center Y
IDX_TBY = 13  # Tongue Body Y

# LD floor: prevents LD from going below this value.
# LD < 0 is physiologically impossible (lips cannot overlap
# negatively in VTL). A floor > 0 also prevents an
# unwanted labial closure at the end of a vowel.
# Set to None to disable.
LD_FLOOR: Optional[float] = 0.0

# Velar plosives: IPA keys identifying the g/k segments
VELAR_PLOSIVE_KEYS: frozenset = frozenset({'g', 'k'})

# Enable the tongue parameter clamps (TBY, TCX, TCY) for
# velar occlusion (g/k). These clamps fix the shortcomings
# of the linear COVTL model in reaching the contact thresholds.
# Disabled by default: the pure COVTL model is preferred.
clamp_tongue_params: bool = False


# ==========================================================================
# Upsampling
# ==========================================================================

def _upsample(data: np.ndarray, sr_in: float, sr_out: float) -> np.ndarray:
    """Resamples by linear interpolation.

    Parameters
    ----------
    data : np.ndarray, shape (N_in, ...)
        Input data.
    sr_in : float
        Input sampling frequency (Hz).
    sr_out : float
        Output sampling frequency (Hz).

    Returns
    -------
    np.ndarray, shape (N_out, ...)
        Resampled data.
    """
    if sr_in == sr_out:
        return data.copy()

    n_in = len(data)
    duration = n_in / sr_in  # in seconds
    n_out = int(np.ceil(duration * sr_out))

    # Input indices for each output frame
    t_in = np.arange(n_in) / sr_in
    t_out = np.arange(n_out) / sr_out

    # Linear interpolation
    indices = t_out * sr_in
    indices = np.clip(indices, 0, n_in - 1.001)

    i_low = np.floor(indices).astype(int)
    frac = indices - i_low
    i_high = np.minimum(i_low + 1, n_in - 1)

    # Broadcasting for multi-dimensional data
    if data.ndim == 1:
        return data[i_low] * (1 - frac) + data[i_high] * frac
    elif data.ndim == 2:
        return (data[i_low] * (1 - frac)[:, np.newaxis]
                + data[i_high] * frac[:, np.newaxis])
    else:
        # General case: interp frame by frame
        out = np.zeros((n_out,) + data.shape[1:], dtype=data.dtype)
        for d in range(data.shape[1] if data.ndim > 1 else 1):
            if data.ndim == 2:
                out[:, d] = data[i_low, d] * (1 - frac) + data[i_high, d] * frac
        return out


# ==========================================================================
# Frame assembler
# ==========================================================================

class AssembleTract:
    """Final assembler: B(t) + E(t) → .tract file at 400 Hz.

    Parameters
    ----------
    speaker_config : SpeakerConfig, optional
        Speaker configuration.
    """

    def __init__(self, speaker_config=None):
        from vtl_synth.core.constants import SpeakerConfig
        self.speaker = speaker_config or SpeakerConfig()

    def assemble(
        self,
        tract_frames: np.ndarray,
        extension_data: Dict[str, np.ndarray],
        sr_in: float = TARGET_SR,
        sr_out: float = TRACT_SR,
        ts3_ortho: Optional[np.ndarray] = None,
        vs_ortho: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Merges B(t), E(t), and E_ortho(t) and upsamples to sr_out.

        Assembly procedure (rapport_vecteur_VTL_400Hz.pdf, §5):

        For each frame t at TARGET_SR:
          1. art = B(t)                                    [Berthommier core]
          2. art[VS], art[VO] = VS(t), VO(t)              [nasality extension]
          3. art[TS3] += TS3_ortho(t)                     [orthogonal branch]
          4. glottis = preset(t)                          [source]
          5. glottis[f0] = f0(t)
          6. glottis[pressure] = from E(t)
          7. glottis[rel_amp] = from E(t)
        Then upsample from sr_in → sr_out (100 → 400 Hz).

        Parameters
        ----------
        tract_frames : np.ndarray, shape (T_in, N_covtl)
            Berthommier tract trajectory (COVTL params only).
        extension_data : dict
            Dictionary returned by TimedEnvelope.get_all_extensions():
              - 'VO': (T_in,), velum opening
              - 'VS': (T_in,), velum shape
              - 'glottis': (T_in, 11), full glottal parameters
              - 'E': (T_in,), effort (optional)
              - 'V': (T_in,), voicing (optional)
              - 'f0': (T_in,), fundamental frequency (optional)
        sr_in : float
            Input frequency (Hz). Default: 100.
        sr_out : float
            Output frequency (Hz). Default: 400.
        ts3_ortho : np.ndarray, shape (T_in,), optional
            Contextual TS3 override from OrthogonalBranch.
            Non-zero values replace the COVTL core TS3.
        vs_ortho : np.ndarray, shape (T_in,), optional
            VS (velum shape) override from OrthogonalBranch.
            If provided, takes priority over extension_data['VS'].

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (full_tract, full_glottis) at sr_out Hz.
            full_tract : (T_out, 19)
            full_glottis : (T_out, 11)
        """
        n_in = len(tract_frames)

        # --- Align the extensions to the tract length ---
        # The extensions (TimedEnvelope) may have a length
        # slightly different from the tract (duration rounding).
        # Truncate to the common minimum.
        for key in list(extension_data.keys()):
            val = extension_data[key]
            if isinstance(val, np.ndarray) and len(val) != n_in:
                if len(val) > n_in:
                    extension_data[key] = val[:n_in]
                else:
                    # Pad with zeros
                    pad = np.zeros((n_in - len(val),) + val.shape[1:],
                                   dtype=val.dtype) if val.ndim > 1 else np.zeros(n_in - len(val), dtype=val.dtype)
                    extension_data[key] = np.concatenate([val, pad])
        if ts3_ortho is not None and len(ts3_ortho) != n_in:
            if len(ts3_ortho) > n_in:
                ts3_ortho = ts3_ortho[:n_in]
            else:
                ts3_ortho = np.concatenate([ts3_ortho, np.zeros(n_in - len(ts3_ortho))])
        if vs_ortho is not None and len(vs_ortho) != n_in:
            if len(vs_ortho) > n_in:
                vs_ortho = vs_ortho[:n_in]
            else:
                vs_ortho = np.concatenate([vs_ortho, np.zeros(n_in - len(vs_ortho))])

        # --- Build the full tract vector (19 params) ---
        # Native VTL order (confirmed JD3.speaker index 14-18):
        #   HX HY JX JA LP LD VS VO TCX TCY TTX TTY TBX TBY TRX TRY TS1 TS2 TS3
        # COVTL gives us (in dictionary order):
        #   HX HY JX JA LP LD TCX TCY TTX TTY TBX TBY TS1 TS2 TS3
        # VS and VO must be inserted, and TRX, TRY moved before TS1-3.

        full_tract_100 = np.zeros((n_in, N_TRACT_PARAMS), dtype=np.float64)

        # Mapping: index in tract_frames → index in full_tract (19)
        # Single source: constants.COVTL_TO_FULL
        covtl_to_full = COVTL_TO_FULL

        # Names in COVTL dictionary order (stable iteration Python 3.7+)
        covtl_keys = list(tract_frames.dtype.names) if tract_frames.dtype.names else None

        if covtl_keys is None:
            # Assume the CO_VTL dictionary order
            from vtl_synth.core.constants import CO_VTL
            covtl_keys = list(CO_VTL.keys())

        for j, key in enumerate(covtl_keys):
            if key in covtl_to_full:
                full_tract_100[:, covtl_to_full[key]] = tract_frames[:, j]

        # --- Insert the extension parameters: VS, VO ---
        # VS: priority vs_ortho (JD) > extension_data['VS'] (TimedEnvelope)
        if vs_ortho is not None and len(vs_ortho) == n_in:
            full_tract_100[:, IDX_VS] = vs_ortho
        else:
            full_tract_100[:, IDX_VS] = extension_data.get('VS', np.zeros(n_in))

        # VO (velum opening = nasality): comes from extension_data['VO'].
        # Caution: extension_data['V'] is VOISING (glottal control),
        # NOT the velum opening.  The velum opening (nasality) is in 'VO'.
        # Voicing is handled via the glottal parameters (rel_amp, f0, etc.)
        # and does NOT belong in the tract vector.
        full_tract_100[:, IDX_VO] = extension_data.get('VO', np.zeros(n_in))

        # --- Apply the orthogonal TS3 override ---
        # The COVTL core TS3 is already at index 18.
        # The orthogonal branch adds a contextual override
        # (fricatives → +1.0, laterals → -1.0, vowels/stops → 0).
        if ts3_ortho is not None and len(ts3_ortho) == n_in:
            # Additive override: TS3_final = TS3_covtl + TS3_ortho
            full_tract_100[:, IDX_TS3] += ts3_ortho

        # TRX(14), TRY(15): leave at 0 (VTL auto)
        full_tract_100[:, 14] = 0.0
        full_tract_100[:, 15] = 0.0

        # --- Glottis ---
        # New approach: glottal_source rule engine (Steps 2–4)
        # Builds the glottal trajectory from the per-segment
        # classification + VTL smoothing (12ms) + F0 with micro-prosody + pressure.
        E = extension_data.get('E', None)
        V = extension_data.get('V', None)
        segments = extension_data.get('segments', None)
        # Shape events precomputed on the real trajectory timing
        # (classify_block_events) — takes priority over the classification by
        # parser t_start, which scrolls ~2.3× too fast (x_top/chink
        # oscillations at the start of the sequence, then shape freeze).
        shape_events = extension_data.get('shape_events', None)

        if shape_events is None and segments is not None:
            from vtl_synth.core.glottal_source import classify_segment_events
            shape_events = classify_segment_events(segments, sr_in)

        if shape_events is not None and E is not None and V is not None:
            try:
                from vtl_synth.core.glottal_source import (
                    build_glottis_trajectory,
                )
                f0_base = self.speaker.f0_default
                glottis_100 = build_glottis_trajectory(
                    shape_events, n_in, E, V,
                    f0_base=f0_base, sr=sr_in,
                )
            except Exception:
                # Fallback: old method
                glottis_100 = self._legacy_glottis(
                    extension_data, n_in)
        else:
            glottis_100 = self._legacy_glottis(extension_data, n_in)

        # --- Hard downstream rectifications ---
        # Post-COVTL-projection corrections, before upsample.
        # Cf. documentation at the top of the module.
        self._apply_downstream_corrections(full_tract_100, n_in, sr_in,
                                           extension_data)

        # --- Upsample from sr_in to sr_out (100 → 400 Hz) ---
        full_tract_400 = _upsample(full_tract_100, sr_in, sr_out)
        full_glottis_400 = _upsample(glottis_100, sr_in, sr_out)

        # Check that the lengths match
        min_len = min(len(full_tract_400), len(full_glottis_400))
        full_tract_400 = full_tract_400[:min_len]
        full_glottis_400 = full_glottis_400[:min_len]

        return full_tract_400, full_glottis_400

    @staticmethod
    def _apply_downstream_corrections(
        full_tract: np.ndarray,
        n_frames: int,
        sr: float,
        extension_data: dict,
    ) -> None:
        """Applies the hard downstream rectifications to full_tract_100.

        Corrections applied BEFORE the 100 → 400 Hz upsample:
          1. TBY velar occlusion clamp: for velar plosives (g/k),
             clamp TBY to TBY_VELAR_OCCLUSION_MIN (= c1+c0) over the
             central occlusion zone of each velar cluster.
          2. LD floor: prevents LD from going below LD_FLOOR.

        The consonant timing comes from extension_data['consonant_frames'],
        extracted from block_info in build_phrase_tract.py. This timing is
        synchronized with the tract trajectory (same time base as
        full_tract_100), unlike the parser segment timing
        which ignores pauses and transitions.

        Modifies full_tract in place.
        """
        # --- 1. TBY/TCX/TCY velar occlusion clamp (optional) ---
        # g_pal (palatal context, theta > pi)
        # is excluded: its occlusion is palatal (anterior TCX), not velar.
        # The velar TCX/TCY clamp only applies to g_vel.
        if clamp_tongue_params:
            consonant_frames = extension_data.get('consonant_frames', None)
            if consonant_frames is not None:
                for cf in consonant_frames:
                    keys = cf.get('keys', [])
                    f_start = cf.get('frame_start', 0)
                    f_end = cf.get('frame_end', 0)

                    # Skip g_pal: palatal occlusion, not velar
                    if cf.get('is_palatal', False):
                        continue

                    # Check whether this cluster contains a velar
                    has_velar = any(k in VELAR_PLOSIVE_KEYS for k in keys)
                    if not has_velar:
                        continue

                    # Central occlusion zone of the cluster
                    n_cluster = f_end - f_start
                    if n_cluster <= 0:
                        continue

                    vt = PLOSIVE_VIRTUAL_TARGETS.get('g', {})
                    occl_factor = vt.get('occlusion_duration_factor', 0.30)
                    center = (f_start + f_end) // 2
                    half_win = max(1, int(n_cluster * occl_factor / 2))
                    win_start = max(center - half_win, 0)
                    win_end = min(center + half_win + 1, n_frames)

                    # Apply the TBY clamp
                    full_tract[win_start:win_end, IDX_TBY] = np.maximum(
                        full_tract[win_start:win_end, IDX_TBY],
                        TBY_VELAR_OCCLUSION_MIN,
                    )

                    # Apply the TCX clamp (max: tongue center pulled back)
                    full_tract[win_start:win_end, IDX_TCX] = np.minimum(
                        full_tract[win_start:win_end, IDX_TCX],
                        TCX_VELAR_OCCLUSION_MAX,
                    )

                    # Apply the TCY clamp (min: tongue center raised)
                    full_tract[win_start:win_end, IDX_TCY] = np.maximum(
                        full_tract[win_start:win_end, IDX_TCY],
                        TCY_VELAR_OCCLUSION_MIN,
                    )

        # --- 2. Global LD floor ---
        if LD_FLOOR is not None:
            full_tract[:, IDX_LD] = np.maximum(
                full_tract[:, IDX_LD], LD_FLOOR)

    @staticmethod
    def _legacy_glottis(
        extension_data: Dict[str, np.ndarray],
        n_in: int,
    ) -> np.ndarray:
        """Old glottis method (fallback if segments are unavailable)."""
        glottis_100 = extension_data.get(
            'glottis', np.zeros((n_in, N_GLOTTIS_PARAMS))
        )
        f0_data = extension_data.get('f0', None)
        if f0_data is not None and isinstance(f0_data, np.ndarray) and len(f0_data) == n_in:
            glottis_100[:, 0] = f0_data
        E = extension_data.get('E', None)
        V = extension_data.get('V', None)
        if E is not None and isinstance(E, np.ndarray) and len(E) == n_in:
            E_clamp = np.clip(E, 0.0, 1.5)
            phonatory = E_clamp > 0.05
            # Centralized bounds (single source: constants.EffortBounds +
            # glottal_source.P_MIN_PHONATION) — cf. HARD-001
            from vtl_synth.core.constants import EFFORT_DEFAULTS as _effort
            from vtl_synth.core.glottal_source import P_MIN_PHONATION as P_min_phonation
            P_min, P_max = _effort.P_min, _effort.P_max
            # E^1.2 mapping + phonation floor (consistent with glottal_source)
            glottis_100[phonatory, 1] = P_min + (E_clamp[phonatory] ** 1.2) * (P_max - P_min)
            glottis_100[phonatory, 6] = np.maximum(E_clamp[phonatory], 0.25)
            silence = ~phonatory
            glottis_100[silence, 1] = P_min
            glottis_100[silence, 6] = 0.0
            # Phonation floor on P if V(t) is available
            if V is not None and isinstance(V, np.ndarray) and len(V) == n_in:
                voiced_mask = V > 0.5
                glottis_100[voiced_mask, 1] = np.maximum(
                    glottis_100[voiced_mask, 1], P_min_phonation)
        return glottis_100

    @staticmethod
    def write_tract_file(
        tract: np.ndarray,
        glottis: np.ndarray,
        file_path: str,
        sr: int = TRACT_SR,
    ) -> None:
        """Writes a .tract file in VTL format.

        Format:
          # VTL tract sequence file
          # version: 1
          # sample_rate: {sr}
          # n_tract_params: {tract.shape[1]}
          # n_glottis_params: {glottis.shape[1]}
          # n_frames: {tract.shape[0]}
          # tract_param_names: {names...}
          # glottis_param_names: {names...}
          # ---
          {values per frame}

        Parameters
        ----------
        tract : np.ndarray, shape (T, 19)
        glottis : np.ndarray, shape (T, 11)
        file_path : str
            Path of the output file.
        sr : int
            Sampling frequency.
        """
        n_frames = tract.shape[0]
        n_tract = tract.shape[1]
        n_glottis = glottis.shape[1]

        with open(file_path, 'w') as f:
            # Header
            f.write('# VTL tract sequence file\n')
            f.write('# version: 1\n')
            f.write(f'# sample_rate: {sr}\n')
            f.write(f'# n_tract_params: {n_tract}\n')
            f.write(f'# n_glottis_params: {n_glottis}\n')
            f.write(f'# n_frames: {n_frames}\n')
            f.write(f'# tract_param_names: {" ".join(TRACT_PARAM_NAMES)}\n')
            f.write(f'# glottis_param_names: {" ".join(GLOTTIS_PARAM_NAMES)}\n')
            f.write('# ---\n')

            # Data: one frame per line
            for i in range(n_frames):
                tract_vals = ' '.join(f'{v:.6f}' for v in tract[i])
                glottis_vals = ' '.join(f'{v:.6f}' for v in glottis[i])
                f.write(f'{tract_vals} {glottis_vals}\n')

    @staticmethod
    def write_tract_file_vtl_native(
        tract: np.ndarray,
        glottis: np.ndarray,
        file_path: str,
        sr: int = TRACT_SR,
    ) -> None:
        """Writes a .tract file compatible with VTL synth_block().

        This format is directly readable by vocaltractlab_cython.synth_block().
        The file contains:
          - Line 1: n_tract_params n_glottis_params state_samples sr_audio
          - Following lines: tract_params... glottis_params...

        Parameters
        ----------
        tract : np.ndarray, shape (T, 19)
        glottis : np.ndarray, shape (T, 11)
        file_path : str
            Path of the output file.
        sr : int
            Tract sampling frequency.
        """
        from vtl_synth.core.constants import AUDIO_SR

        n_tract = tract.shape[1]
        n_glottis = glottis.shape[1]
        n_frames = tract.shape[0]
        state_samples = int(AUDIO_SR / sr)

        with open(file_path, 'w') as f:
            for i in range(n_frames):
                tract_vals = ' '.join(f'{v:.6f}' for v in tract[i])
                glottis_vals = ' '.join(f'{v:.6f}' for v in glottis[i])
                f.write(f'{tract_vals} {glottis_vals}\n')
