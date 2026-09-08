# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
build_phrase_tract.py
====================
Complete orchestrator: assembles the 400 Hz VTL vectors from the three
pipeline branches (rapport_vecteur_VTL_400Hz.pdf, §5, §7).

    VTL(t) = B(t) + E_source(t) + E_ortho(t)

    B(t)       : Berthommier core — COVTL(rho, theta) + selectors → 15 params
    E_source   : TimedEnvelope — E(t), VO(t), V(t), f0(t), preset(t) → 11 glottis + VS + VO
                 indexed by gesture anchors
    E_ortho    : OrthogonalBranch — contextual TS3, VS from JD

This module implements the complete assembly procedure described in
the documentation, section §5 (Frame assembly) and §7 (Module layout):

  1. Text/IPA → annotated phonemic segments
  2. Berthommier core: (rho,theta) → tract trajectory B(t) at 100 Hz
  3. TimedEnvelope: anchors+timers → E(t), VO(t), VS(t), V(t), f0(t), glottis(t)
  4. OrthogonalBranch: phonemes+contexts → TS3_ortho(t), VS_ortho(t) at 100 Hz
  5. AssembleTract: merge B+E+E_ortho → upsample 100→400 Hz
  6. Write the per-phrase .tract file into output/phrases/

Directory layout (aligned with the berthommier github):

    berthommier_vtl_pipeline/
    ├── output/
    │   └── phrases/                ← per-phrase .tract files
    │       ├── 001_bonjour.tract
    │       ├── 002_au_revoir.tract
    │       └── ...
    ├── pipeline/
    │   ├── constants.py
    │   ├── berthommier.py
    │   ├── orthogonal_params.py
    │   ├── assemble_tract.py
    │   └── build_phrase_tract.py   ← this module
    └── vocaltractlab/
        ├── speaker/
        │   └── JD3.speaker
        └── synth/                   ← ready for synth_block()

Usage:
-------
    from vtl_synth.core.build_phrase_tract import build_phrase_tract

    # Single phrase
    build_phrase_tract('b o Z u R', phrase_id=1, label='bonjour')

    # Several phrases
    phrases = [
        ('b o Z u R', 'bonjour'),
        ('a v w a R', 'au_revoir'),
    ]
    for i, (ipa, label) in enumerate(phrases, 1):
        build_phrase_tract(ipa, phrase_id=i, label=label)

    # With a custom output path
    build_phrase_tract('a i u', output_dir='/custom/path')

    # Return the data instead of writing
    tract, glottis = build_phrase_tract('a i u', return_data=True)
"""

from __future__ import annotations

import os
import re
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from vtl_synth.core.constants import (
    TRACT_SR,
    TARGET_SR,
    VOWEL_TARGETS,
    CONSONANT_TARGETS,
    SpeakerConfig,
    CO_VTL,
    N_TRACT_PARAMS,
    N_GLOTTIS_PARAMS,
)
from vtl_synth.core.prosody_source import Segment, Syllable
from vtl_synth.core.enveloppe import (
    TimedEnvelope,
    chain_elements_to_anchors,
    FeatureTimer,
)
from vtl_synth.core.amplitude_envelope import build_envelope_from_blocks
from vtl_synth.core.tag_system import TagInterpreter
from vtl_synth.core.projection import (
    get_consonant_info,
    get_consonant_target,
)
from vtl_synth.core.assemble_tract import AssembleTract
from vtl_synth.core.orthogonal_params import OrthogonalBranch
from vtl_synth.core.text_to_tract import (
    _normalize_ipa,
)
from vtl_synth.core.continuous import (
    parse_to_tract_trajectory,
    parse_to_segments,
)
from vtl_synth.core.constants import FS, T_S
from vtl_synth.core.types import PolarTarget


# ==========================================================================
# Default paths
# ==========================================================================

# Package root (vtl_synth/)
_PKG_ROOT = Path(__file__).resolve().parent.parent

# Speaker file shipped as package data (vtl_synth/data/vtl_binaries/)
DEFAULT_SPEAKER_FILE = _PKG_ROOT / 'data' / 'vtl_binaries' / 'JD3.speaker'

# Default output directory (cwd-based: the package may be installed
# read-only in site-packages)
DEFAULT_OUTPUT_DIR = Path.cwd() / 'out' / 'phrases'


# ==========================================================================
# Utilities
# ==========================================================================

def _sanitize_label(label: str) -> str:
    """Sanitize a label for use as a file name.

    Replaces spaces and special characters with underscores.
    """
    label = re.sub(r'[^\w\-]', '_', label)
    label = re.sub(r'_+', '_', label).strip('_')
    return label


def _ensure_output_dir(output_dir: Union[str, Path]) -> Path:
    """Create the output directory if it does not exist.

    Parameters
    ----------
    output_dir : str or Path
        Directory path.

    Returns
    -------
    Path
        Absolute path of the directory (existing).
    """
    p = Path(output_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_vowel_contexts(
    segments: List[Segment],
) -> List[Optional[str]]:
    """Determine the vowel context for each phoneme.

    For each segment, the context vowel is the nearest vowel
    (previous or next).

    Parameters
    ----------
    segments : list[Segment]
        List of phonemic segments.

    Returns
    -------
    list[str|None]
        Context vowel for each segment.
    """
    contexts = []
    current_vowel = None

    for seg in segments:
        if seg.kind == 'V':
            current_vowel = seg.key
            contexts.append(current_vowel)
        else:
            # Consonant: use the current or next vowel
            if current_vowel is not None:
                contexts.append(current_vowel)
            else:
                # Find the next vowel
                next_vowel = None
                for s2 in segments:
                    if s2.kind == 'V':
                        next_vowel = s2.key
                        break
                contexts.append(next_vowel)

    return contexts


def _align_trajectories(
    tract_100: np.ndarray,
    extensions: Dict[str, np.ndarray],
    ortho: Dict[str, np.ndarray],
    n_target: int,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Realign all trajectories to the same length.

    The three branches (Berthommier, TimedEnvelope, OrthogonalBranch)
    may produce slightly different lengths due to duration rounding.
    This function truncates or pads them to n_target frames.

    Parameters
    ----------
    tract_100 : np.ndarray, shape (T1, 15)
        Berthommier trajectory.
    extensions : dict
        TimedEnvelope extensions.
    ortho : dict
        Orthogonal trajectories.
    n_target : int
        Target number of frames.

    Returns
    -------
    tuple
        (tract_aligned, extensions_aligned, ortho_aligned)
    """
    # Truncate or pad the tract
    if len(tract_100) >= n_target:
        tract_aligned = tract_100[:n_target]
    else:
        pad = np.zeros((n_target - len(tract_100), tract_100.shape[1]))
        tract_aligned = np.vstack([tract_100, pad])

    # Align the 1D extensions
    ext_aligned = {}
    for k, v in extensions.items():
        if isinstance(v, np.ndarray) and v.ndim == 1:
            if len(v) >= n_target:
                ext_aligned[k] = v[:n_target]
            else:
                pad = np.zeros(n_target - len(v))
                ext_aligned[k] = np.concatenate([v, pad])
        elif isinstance(v, np.ndarray) and v.ndim == 2:
            if len(v) >= n_target:
                ext_aligned[k] = v[:n_target]
            else:
                pad = np.zeros((n_target - len(v), v.shape[1]))
                ext_aligned[k] = np.vstack([v, pad])
        else:
            ext_aligned[k] = v

    # Align the orthogonals
    ortho_aligned = {}
    for k, v in ortho.items():
        if isinstance(v, np.ndarray) and v.ndim == 1:
            if len(v) >= n_target:
                ortho_aligned[k] = v[:n_target]
            else:
                pad = np.zeros(n_target - len(v))
                ortho_aligned[k] = np.concatenate([v, pad])
        else:
            ortho_aligned[k] = v

    return tract_aligned, ext_aligned, ortho_aligned


# ==========================================================================
# VV arc closure probe (schwa routing in syltraj)
# ==========================================================================

def _make_vv_closure_probe():
    """Probe: minimum LINGUAL cross-sectional area (cm²) in the central half of a block.

    Only a median lingual constriction is a polar-arc artifact
    (transient occlusion); a median labial closure between rounded
    vowels (o→u) is natural rounding continuity —
    it does not trigger schwa routing.

    Rebuilds the 19-param VTL state from the (n,15) COVTL block with
    VS/VO at rest (baseline VO = -0.1).  Hooked onto
    syltraj.VV_CLOSURE_PROBE by build_phrase_tract (the syltraj engine
    stays free of any VTL dependency).
    """
    import numpy as _np
    from vocaltractlab_cython import (
        tract_state_to_tube_state as _tt,
        tract_state_to_limited_tract_state as _tl,
    )
    from vtl_synth.core.constants import CO_VTL as _COVTL, COVTL_TO_FULL
    covtl_to_full = COVTL_TO_FULL
    order = list(_COVTL.keys())

    def probe(block: np.ndarray) -> float:
        n = len(block)
        full = np.zeros((n, 19))
        for j, key in enumerate(order):
            if key in covtl_to_full:
                full[:, covtl_to_full[key]] = block[:, j]
        full[:, 6] = 0.0     # VS (velum) at rest
        full[:, 7] = -0.1    # VO baseline (oral)
        best = 9.9
        for t in _np.linspace(n // 4, max(3 * n // 4 - 1, n // 4),
                              7).astype(int):
            ts = _tt(_tl(full[t]))
            area, art = ts['tube_area'], ts['tube_articulator']
            ln = ts['tube_length']
            cum = _np.concatenate([[0.0], _np.cumsum(ln)])
            mid = 0.5 * (cum[:-1] + cum[1:])
            vals = _np.where((art == 1) & (mid >= 8.0) & (mid < 16.0),
                             area, _np.inf)
            if _np.isfinite(vals).any():
                best = min(best, float(vals.min()))
        return best

    return probe


# ==========================================================================
# Main function
# ==========================================================================

def build_phrase_tract(
    text_or_ipa: str,
    phrase_id: Optional[int] = None,
    label: Optional[str] = None,
    output_dir: Optional[Union[str, Path]] = None,
    f0_hz: float = 102.216,
    speaker: str = 'JD3',
    speaker_config: Optional[SpeakerConfig] = None,
    speaker_file: Optional[str] = None,
    f0_contour: Optional[np.ndarray] = None,
    sr_out: float = TRACT_SR,
    tag_overrides: Optional[Dict[str, Dict]] = None,
    use_orthogonal: bool = True,
    return_data: bool = False,
    verbose: bool = True,
    add_phrase_anchors: bool = True,
    engine: str = 'syl',
    t_cons: Optional[int] = None,
    t_voy: Optional[int] = None,
    pause_short_ms: Optional[float] = None,
    pause_long_ms: Optional[float] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Assemble the complete 400 Hz VTL vector for a phrase.

    Complete pipeline (rapport_vecteur_VTL_400Hz.pdf, §5 and §7):

      1. Text/IPA → annotated phonemic segments
      2. Berthommier core: coarticulation (rho,theta) → B(t) at 100 Hz (15 params)
      3. TimedEnvelope: anchors + FeatureTimer → E(t), VO(t), VS(t), V(t), f0(t) → glottis(t) at 100 Hz
      4. OrthogonalBranch: TS3_ortho(t), VS_ortho(t) at 100 Hz from JD
      5. AssembleTract: merge B+E+E_ortho, upsample 100→400 Hz
      6. Write the .tract file

    Parameters
    ----------
    text_or_ipa : str
        Plain text or IPA sequence.
        If all characters are in VOWEL_TARGETS or
        CONSONANT_TARGETS, treated as IPA directly.
    phrase_id : int, optional
        Numeric phrase identifier. Used for naming.
        If None, a timestamp is used.
    label : str, optional
        Descriptive label for the file (e.g. 'bonjour').
        If None, derived from the IPA.
    output_dir : str or Path, optional
        Output directory. Default: <project_root>/output/phrases/
    f0_hz : float
        Default fundamental frequency (Hz). Default: 102.216 (JD3).
    speaker : str
        Speaker name.
    speaker_config : SpeakerConfig, optional
        Custom speaker configuration.
    speaker_file : str, optional
        Path to the JD .speaker file.
    f0_contour : np.ndarray, optional
        Global F0 contour.
    sr_out : float
        Output sampling rate (Hz). Default: 400.
    tag_overrides : dict, optional
        Per-phoneme tag overrides.
    use_orthogonal : bool
        Enable the orthogonal branch (TS3, VS from JD). Default: True.
    return_data : bool
        If True, return (tract, glottis) in addition to writing the file.
    add_phrase_anchors : bool
        If True (default), add phrase start/end
        anchors. Spaces are always treated as
        inter-word pauses.
    engine : str, optional
        Trajectory engine for B(t): 'syl' (default) selects the
        syltraj syllabic engine (COVTL specification: vowel
        anchors + consonant targets at the arc endpoints); 'legacy'
        selects the former parse_to_tract_trajectory path
        (deprecated alignment reference, RISK-002 — no
        parameterizable t_cons/t_voy).
    t_cons : int, optional
        Consonantal arc duration (ms) for engine='syl'.
        None → engine default. Validated setting: 160 (T160).
    t_voy : int, optional
        Vocalic arc duration (ms) for engine='syl'.
        None → engine default.
    pause_short_ms : float, optional
        Short-pause duration (ms), engine='syl' only.
        None → 200 ms.
    pause_long_ms : float, optional
        Long (inter-word) pause duration (ms), engine='syl' only.
        None → 320 ms.
    verbose : bool
        Display progress information.

    Returns
    -------
    tuple[np.ndarray, np.ndarray] or None
        (tract_400, glottis_400) if return_data=True, otherwise None.

    Examples
    --------
    >>> build_phrase_tract('b o Z u R', phrase_id=1, label='bonjour')
    >>> data = build_phrase_tract('a i u', return_data=True)
    >>> data[0].shape  # (T, 19)
    >>> data[1].shape  # (T, 11)
    """
    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    if speaker_config is None:
        speaker_config = SpeakerConfig(name=speaker, f0_default=f0_hz)

    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    if speaker_file is None:
        speaker_file = str(DEFAULT_SPEAKER_FILE)

    # ------------------------------------------------------------------
    # Step 1: Text/IPA → annotated segments
    # ------------------------------------------------------------------
    ipa = text_or_ipa
    # syltraj normalization BEFORE _normalize_ipa: nasal vowel
    # sequences (ɔ+̃ → 'O~', ã → 'a~' …) must become stable keys
    # before the continuous table (which maps ɔ→9, losing the
    # tilde — loss of nasality). See CDC_passerelle_IPA_SAMPA.
    from vtl_synth.core.syltraj import _normalize_word as _syl_normalize_word
    ipa = _syl_normalize_word(ipa)
    ipa = _normalize_ipa(ipa)
    # Spaces are kept: they are treated as inter-word
    # pauses by parse_to_segments() / parse_to_tract_trajectory()

    if verbose:
        print(f'[build_phrase_tract] IPA: {ipa}')

    # Use the continuous parsing pipeline
    segments, chain_elements = parse_to_segments(ipa, add_phrase_anchors=add_phrase_anchors)

    if not segments:
        raise ValueError(f"No phonemic segments found in '{text_or_ipa}'")

    # Annotation with phonetic tags
    tag_interpreter = TagInterpreter(tag_overrides=tag_overrides)
    segments = tag_interpreter.apply_all(segments)

    if verbose:
        print(f'[build_phrase_tract] Segments: '
              f'{[(s.key, s.kind, s.duration_ms, s.glottal_tag, s.velum_tag) for s in segments]}')

    # ------------------------------------------------------------------
    # Step 2: Berthommier core → B(t) at 100 Hz
    # ------------------------------------------------------------------
    # The trajectory is computed by the continuous pipeline
    # (CV, CVC, CCV, CCCV graphs with superposition, inter-syllabic
    # transition arcs, and pauses). The length in frames is
    # determined by the segment durations.

    # ------------------------------------------------------------------
    # Step 2: Trajectory — syltraj syllabic engine (COVTL
    # specification: vocal anchors + consonant targets at arc
    # endpoints, no consonant interpolation).
    # engine='legacy' → former parse_to_tract_trajectory path
    # (continuous + trajectory, COVTL reference). DEPRECATED
    # (RISK-002/syltraj↔trajectory merge, 2026-09-04): kept as an
    # alignment reference only; timing differs from the active
    # engine (no parameterizable T_cons/T_voy).
    # ------------------------------------------------------------------
    if engine == 'syl':
        import vtl_synth.core.syltraj as _syltraj
        from vtl_synth.core.syltraj import build_phrase_pval
        # VV closure probe: schwa routing for background arcs that
        # close mid-way (defect of large-Δθ polar arcs)
        _syltraj.VV_CLOSURE_PROBE = _make_vv_closure_probe()
        cons_ms = 60.0
        vowel_ms = 60.0
        tract_100 = None
        rho_theta = np.zeros((0, 2))
        Pval, block_info, _nodes_syl, _anchors_syl = build_phrase_pval(
            ipa, t_cons=t_cons, t_voy=t_voy,
            pause_short_ms=pause_short_ms or 200.0,
            pause_long_ms=pause_long_ms or 320.0)
        _syltraj.VV_CLOSURE_PROBE = None
        tract_100 = Pval
        n_steps = tract_100.shape[0]
        if verbose:
            print(f'[build_phrase_tract] syltraj B(t): {tract_100.shape} '
                  f'at {TARGET_SR} Hz ({len(block_info)} blocks)')
    else:
        import warnings
        warnings.warn(
            "engine='legacy' is deprecated: COVTL reference "
            "engine kept for alignment only; "
            "use engine='syl' (default). See RISK-002 "
            "(KNOWN_ISSUES.md).", DeprecationWarning, stacklevel=2)
        tract_100, rho_theta, block_info = parse_to_tract_trajectory(
            ipa, sr=TARGET_SR, add_phrase_anchors=add_phrase_anchors)
        n_steps = tract_100.shape[0]
        if verbose:
            print(f'[build_phrase_tract] Berthommier B(t): {tract_100.shape}')
            print(f'[build_phrase_tract] block_info: {len(block_info)} '
                  f'blocks, kind={[b.kind for b in block_info]}')

    # ------------------------------------------------------------------
    # Step 2b: Amplitude envelope E(t) from block_info
    # ------------------------------------------------------------------
    # The COVTL token-based envelope is built from
    # the BlockInfo produced by build_global_pval(). It is
    # synchronized with the trajectory because it shares the same
    # temporal structure.
    #
    # E(t) is first computed at FS=10000 Hz, then downsampled
    # to n_steps (100 Hz) by per-block averaging of sps samples.

    # Build the flat list of phonemes and the polar targets
    flat = []
    all_polars = []
    for elem in chain_elements:
        if elem.is_pause:
            continue
        # Onset consonants
        for ck in elem.onset_keys:
            ct = get_consonant_target(ck, elem.theta_vo)
            is_v = False
            if ct is not None:
                flat.append(ck)
                all_polars.append(PolarTarget(ct[0], ct[1], f'C_{ck}', is_vowel=is_v))
            else:
                flat.append(ck)
                all_polars.append(PolarTarget(0, 0, f'C_{ck}', is_vowel=is_v))
        # Vowel nucleus
        if elem.nucleus_key in VOWEL_TARGETS:
            rv, tv = VOWEL_TARGETS[elem.nucleus_key]
            flat.append(elem.nucleus_key)
            all_polars.append(PolarTarget(rv, tv, f'V_{elem.nucleus_key}', is_vowel=True))
        # Coda consonants
        for ck in elem.coda_keys:
            ct = get_consonant_target(ck, elem.theta_ve)
            is_v = False
            if ct is not None:
                flat.append(ck)
                all_polars.append(PolarTarget(ct[0], ct[1], f'C_{ck}', is_vowel=is_v))
            else:
                flat.append(ck)
                all_polars.append(PolarTarget(0, 0, f'C_{ck}', is_vowel=is_v))

    # Build the syllable boundaries (indices into flat)
    flat_idx = 0
    syl_boundaries = set()
    for elem in chain_elements:
        if elem.is_pause:
            continue
        syl_boundaries.add(flat_idx)
        flat_idx += len(elem.onset_keys) + 1 + len(elem.coda_keys)

    # High-resolution envelope then downsampling
    sps = int(T_S * FS)  # 100
    from vtl_synth.core.continuous import get_last_pval_state
    nodes_for_env, anchors_for_env = get_last_pval_state()

    env_highres = build_envelope_from_blocks(
        block_info=block_info,
        nodes=nodes_for_env,
        anchors=anchors_for_env,
        all_polars=all_polars,
        flat=flat,
        syl_boundaries=syl_boundaries,
        sps=sps,
        cexp=1.0,
        cdec=3.0,
    )

    # Downsample from FS to n_steps by averaging
    if len(env_highres) >= n_steps * sps:
        # Reshape and average
        n_full = (len(env_highres) // sps) * sps
        E_100 = env_highres[:n_full].reshape(-1, sps).mean(axis=1)
        E_100 = E_100[:n_steps]
    else:
        # Linear interpolation
        t_env = np.linspace(0, 1, len(env_highres))
        t_target = np.linspace(0, 1, n_steps)
        E_100 = np.interp(t_target, t_env, env_highres)

    # ------------------------------------------------------------------
    # Step 2c: silence the inter-word backgrounds (spurious energy
    # packets). The envelope assigns E=1 to background blocks (vocalic
    # transition arcs): after an inter-word pause, this creates an
    # extra energy packet BEFORE each logatome (17 packets instead
    # of 9 on bx_dx_gx — the first one, with no preceding background,
    # is not doubled). A background preceded by a pause is a silent
    # glide: E=0 (energy resumes at the vocalic approach in the
    # following cluster).
    # ------------------------------------------------------------------
    _off = 0
    _prev_kind = None
    for _bi in block_info:
        if _bi.kind == 'background' and _prev_kind == 'pause':
            E_100[_off:_off + _bi.n_steps] = 0.0
        _prev_kind = _bi.kind
        _off += _bi.n_steps

    # ------------------------------------------------------------------
    # Step 2d: per-vowel effort gain (relative intensity).
    # /i/,/u/ come out ~10-11 dB below /a/ (intrinsic F1 + fine
    # constrictions of the rho compensations): VOWEL_EFFORT_GAIN
    # raises E on their plateaus (clamped to 1.5 downstream:
    # pressure ~12700 dPa, rel_amp 1.5, i.e. ~+3 dB).
    # ------------------------------------------------------------------
    from vtl_synth.core.constants import VOWEL_EFFORT_GAIN
    if VOWEL_EFFORT_GAIN:
        _off = 0
        for _bi in block_info:
            if _bi.kind == 'plateau':
                # robust pairing: key carried by the block (syltraj);
                # parser-order fallback for the old engine
                _key = getattr(_bi, 'vowel_key', '') or (
                    _vow_keys_all[0] if False else '')
                _gain = VOWEL_EFFORT_GAIN.get(_key, 1.0)
                if _gain != 1.0:
                    E_100[_off:_off + _bi.n_steps] = np.clip(
                        E_100[_off:_off + _bi.n_steps] * _gain, 0.0, 1.5)
            _off += _bi.n_steps

    if verbose:
        print(f'[build_phrase_tract] Envelope E(t): {E_100.shape}, '
              f'min={E_100.min():.3f}, max={E_100.max():.3f}, '
              f'mean={E_100.mean():.3f}')

    # ------------------------------------------------------------------
    # Step 3: Glottal source → VO, VS, V, f0, glottis
    # ------------------------------------------------------------------
    # TimedEnvelope handles V(t), VO(t), VS(t), f0(t), glottis(t).
    # These parameters are resampled to n_steps to
    # exactly match the tract trajectory.

    # Build the anchors from the chain elements
    anchors = chain_elements_to_anchors(chain_elements)

    if verbose:
        print(f'[build_phrase_tract] Anchors built: {len(anchors)}')

    timed_env = TimedEnvelope(
        anchors=anchors,
        speaker_config=speaker_config,
        tag_interpreter=tag_interpreter,
        f0_contour=f0_contour,
    )
    extensions = timed_env.get_all_extensions()

    # Resample the TimedEnvelope extensions to n_steps
    for key in list(extensions.keys()):
        val = extensions[key]
        if not isinstance(val, np.ndarray):
            continue
        if key == 'timer_events':
            continue
        if len(val) != n_steps:
            if len(val) > 0:
                t_ext = np.linspace(0, 1, len(val))
                t_target = np.linspace(0, 1, n_steps)
                if val.ndim == 1:
                    extensions[key] = np.interp(t_target, t_ext, val)
                else:
                    # 2D: interpolate each column
                    interp_2d = np.zeros((n_steps, val.shape[1]), dtype=val.dtype)
                    for col in range(val.shape[1]):
                        interp_2d[:, col] = np.interp(t_target, t_ext, val[:, col])
                    extensions[key] = interp_2d
            else:
                shape = (n_steps,) + val.shape[1:]
                extensions[key] = np.zeros(shape, dtype=val.dtype)

    # Replace the effort envelope with E(t) from block_info
    extensions['E'] = E_100

    # ------------------------------------------------------------------
    # Step 3b-NEW: Pulmonary effort synthesis
    # ------------------------------------------------------------------
    # The pulmonary effort E_pulm(t) is a synthesis of three
    # components: E(t) (envelope), V(t) (voicing from timers),
    # and VO(t) (nasality from timers).
    #
    # For voiced stops, E(t) may be zeroed before the
    # occlusion, but pre-voicing requires airflow.
    # For nasal segments, E(t) may be low, but
    # nasality requires continuous airflow.
    #
    # We retrieve the TimerData from parsing and adjust E(t).
    # ------------------------------------------------------------------
    from vtl_synth.core.glottal_source import compute_pulmonary_effort_from_timers
    # parse_to_tract_trajectory: module-level import (a local import here
    # would shadow the name for the whole function → UnboundLocalError in step 2).

    from vtl_synth.core.continuous import get_last_timer_data
    timer_data = get_last_timer_data()

    if timer_data is not None and timer_data.total_duration_ms > 0:
        # Adjust the timer duration if needed
        actual_duration = n_steps / TARGET_SR * 1000.0
        if abs(timer_data.total_duration_ms - actual_duration) > 10.0:
            timer_data.total_duration_ms = actual_duration

        # Do NOT apply the pulmonary adjustment if the timer marks
        # are not aligned with the real trajectory: in a multi-word
        # phrase, the timer runs ~2-3x too fast (parser marks),
        # and the pre-voicing injections fall into decays/pauses
        # (spurious packets). Pre-voicing is already ensured by V(t)
        # via phoneme identity (C1) + step 4e of glottal_source (C2-C3).
        voicing_marks = list(getattr(timer_data, 'voicing_marks', []) or [])
        marks_end_ms = max((m.t_end_ms for m in voicing_marks),
                           default=timer_data.total_duration_ms)
        timer_aligned = abs(marks_end_ms - actual_duration) <= \
            0.15 * actual_duration

        if timer_aligned:
            E_pulmonary = compute_pulmonary_effort_from_timers(
                E_100, timer_data, sr=TARGET_SR)
            extensions['E'] = E_pulmonary

            if verbose:
                n_prevoiced = int(np.sum(E_pulmonary > E_100 + 0.05))
                print(f'[build_phrase_tract] Pulmonary effort synthesized: '
                      f'{n_prevoiced} frames adjusted '
                      f'(pre-voicing + nasality)')
        elif verbose:
            print(f'[build_phrase_tract] Misaligned timer '
                  f'({marks_end_ms:.0f} ms of marks vs '
                  f'{actual_duration:.0f} ms actual) — pulmonary adjustment '
                  f'ignored (pre-voicing covered by V(t) + step 4e)')
    elif verbose:
        print(f'[build_phrase_tract] No TimerData — effort not adjusted')

    # ------------------------------------------------------------------
    # Step 3b: V(t) from block_info (synchronized timing)
    # ------------------------------------------------------------------
    # C1 (pre-voicing): V(t) of cluster blocks is derived from
    # the IDENTITY of the consonants (VOICED_CONSONANT_KEYS), not from E(t).
    # E(t) is an amplitude envelope, zero during the occlusion:
    # clip(E,0,1) was switching off the voicing of /b,d,g/ → rel_amp=0 and
    # pressure ≈ 140 dPa at the occlusion centers (stops realized
    # voiceless). With V=1, compute_pressure floors at P_MIN_PHONATION
    # (3000 dPa, C2) and rel_amp follows the E_GATE_FLOOR≈0.35 floor
    # bounded to [0.2, 0.4] in glottal_source (C3, voicing bar).
    # ------------------------------------------------------------------
    from vtl_synth.core.constants import VOICED_CONSONANT_KEYS, \
        NASAL_CONSONANT_KEYS, VO_NASALIZED_VOWEL
    cons_segments_all = [s for s in segments if s.kind == 'C']
    V_from_blocks = np.zeros(n_steps, dtype=np.float64)
    # closed velar baseline VTL = -0.1 (VO=0 = slightly open!)
    VO_from_blocks = np.full(n_steps, -0.1, dtype=np.float64)
    _f = 0
    _ci = 0
    for _bi in block_info:
        if _bi.kind == 'cluster':
            n_cons = _bi.n_cons if _bi.n_cons > 0 else len(_bi.cons_tokens)
            # exact keys carried by the block (syltraj); sequential
            # parser fallback for the old engine
            _ck = list(getattr(_bi, 'cons_keys', []) or [])
            if _ck:
                keys = _ck
                _ci += n_cons
            else:
                keys = [cons_segments_all[_ci + k].key
                        for k in range(n_cons)
                        if _ci + k < len(cons_segments_all)]
                _ci += n_cons
            # fair split of the block between the consonants of the cluster
            n_blk = _bi.n_steps
            for _k, _key in enumerate(keys):
                _s0 = _f + int(round(_k * n_blk / max(len(keys), 1)))
                _s1 = _f + int(round((_k + 1) * n_blk / max(len(keys), 1)))
                V_from_blocks[_s0:_s1] = \
                    1.0 if _key in VOICED_CONSONANT_KEYS else 0.0
                if _key in NASAL_CONSONANT_KEYS:
                    # nasality: velar opening over the sub-slice
                    # (rise/fall bounded to 20% of the slice,
                    # max 40 ms — avoids spilling onto neighboring plateaus)
                    _ramp = min(max(2, int(0.04 * TARGET_SR)),
                                (_s1 - _s0) // 4)
                    _seg = np.ones(_s1 - _s0)
                    _seg[:_ramp] = np.linspace(0, 1, _ramp)
                    _seg[-_ramp:] = np.linspace(1, 0, _ramp)
                    VO_from_blocks[_s0:_s1] = np.maximum(
                        VO_from_blocks[_s0:_s1], _seg)
        elif _bi.kind in ('background', 'plateau'):
            # Vocalic phonation zones: V follows E(t)
            _e_slice = E_100[_f:_f + _bi.n_steps]
            V_from_blocks[_f:_f + _bi.n_steps] = np.clip(_e_slice, 0.0, 1.0)
            # Nasal vowel (ã ẽ ɛ̃ ɔ̃ …): velum PARTIALLY open
            # (VO = TAG_TO_VO_TARGET['nasalized'] = 0.5), 20% ramps.
            if _bi.kind == 'plateau' and getattr(_bi, 'nasal', False):
                _w0, _w1 = _f, _f + _bi.n_steps
                _ramp = min(max(2, int(0.04 * TARGET_SR)),
                            max(1, (_w1 - _w0) // 4))
                _seg = np.full(_w1 - _w0, VO_NASALIZED_VOWEL)
                _seg[:_ramp] = np.linspace(-0.1, VO_NASALIZED_VOWEL, _ramp)
                _seg[-_ramp:] = np.linspace(VO_NASALIZED_VOWEL, -0.1,
                                            _ramp)
                VO_from_blocks[_w0:_w1] = np.maximum(
                    VO_from_blocks[_w0:_w1], _seg)
        # pause / terminal / initial / decay / attack: V = 0 (already 0)
        _f += _bi.n_steps
    extensions['V'] = V_from_blocks
    # Synchronized nasality (consonantal nasals): replaces the VO of
    # TimedEnvelope (misaligned in multi-word — VO spans of only ~25 ms).
    #
    # Anti-click: VO smoothing with the VTL gesture time constant
    # (τ = 12 ms, first order). Without smoothing, −0.1↔1.0
    # transitions over 22-32 ms produce audible clicks (VTL's internal
    # velar dynamics does not anticipate jumps coming from the .tract).
    # The smoothing applies to the full VO trajectory (including the
    # −0.1 baseline), to guarantee the absence of discontinuities.
    _vo_tau_ms = 20.0   # τ longer than 12 ms: anti-click margin
    _vo_alpha = 1.0 - np.exp(-1.0 / (_vo_tau_ms / 1000.0 * TARGET_SR))
    _vo_smooth = np.copy(VO_from_blocks)
    for _t in range(1, n_steps):
        _vo_smooth[_t] = _vo_alpha * VO_from_blocks[_t] + \
            (1 - _vo_alpha) * _vo_smooth[_t - 1]
    extensions['VO'] = _vo_smooth

    if verbose:
        ext_shapes = {k: v.shape for k, v in extensions.items()
                      if isinstance(v, np.ndarray)}
        print(f'[build_phrase_tract] Aligned extensions: {ext_shapes}')
        print(f'[build_phrase_tract] FeatureTimer: '
              f'{len(timed_env.timer.events)} events')

    # ------------------------------------------------------------------
    # Step 4: OrthogonalBranch → TS3_ortho(t), VS_ortho(t) at 100 Hz
    # ------------------------------------------------------------------
    # The orthogonal parameters are derived from the JD3.speaker file:
    #   - TS3: context-dependent (fricatives → +1, laterals → -1)
    #   - VS : velum shape from the JD shapes

    ts3_ortho = None
    vs_ortho = None

    if use_orthogonal and os.path.exists(speaker_file):
        try:
            ortho_branch = OrthogonalBranch(speaker_file=speaker_file)

            phoneme_seq = [s.key for s in segments]
            vowel_contexts = _get_vowel_contexts(segments)
            segment_durations = [s.duration_ms for s in segments]
            total_duration = sum(segment_durations)

            ortho_data = ortho_branch.get_orthogonal_trajectories(
                phoneme_sequence=phoneme_seq,
                vowel_contexts=vowel_contexts,
                total_duration_ms=total_duration,
                segment_durations_ms=segment_durations,
            )

            ts3_ortho = ortho_data.get('TS3_ortho')
            vs_ortho = ortho_data.get('VS_ortho')

            if verbose:
                print(f'[build_phrase_tract] OrthogonalBranch: '
                      f'TS3_ortho={ts3_ortho.shape if ts3_ortho is not None else None}, '
                      f'VS_ortho={vs_ortho.shape if vs_ortho is not None else None}')
        except Exception as e:
            if verbose:
                print(f'[build_phrase_tract] OrthogonalBranch aborted: {e}')
    elif use_orthogonal and verbose:
        print(f'[build_phrase_tract] OrthogonalBranch: file not found ({speaker_file})')

    # ------------------------------------------------------------------
    # Step 5: Trajectory alignment
    # ------------------------------------------------------------------
    # The three branches may have slightly different lengths.
    # We realign them to the length of B(t).

    # Remove 'timer_events' from the extensions before alignment
    # (it is an internal dict, not a trajectory)
    ext_for_align = {
        k: v for k, v in extensions.items()
        if k != 'timer_events' and isinstance(v, np.ndarray)
    }

    n_target = len(tract_100)
    tract_aligned, ext_aligned, ortho_aligned = _align_trajectories(
        tract_100, ext_for_align,
        {'TS3_ortho': ts3_ortho, 'VS_ortho': vs_ortho}
        if ts3_ortho is not None or vs_ortho is not None
        else {},
        n_target,
    )

    ts3_ortho_aligned = ortho_aligned.get('TS3_ortho')
    vs_ortho_aligned = ortho_aligned.get('VS_ortho')

    # ------------------------------------------------------------------
    # Step 6: Assembly — merge B(t) + E(t) + E_ortho(t) → 400 Hz
    # ------------------------------------------------------------------
    # Procedure (§5 of the report):
    #   for each frame t:
    #     art = CO_VTL(rho(t), theta(t))        [B(t) — already done]
    #     art[VS], art[VO] = VS(t), VO(t)        [E_source]
    #     art[TS3] += TS3_ortho(t)               [E_ortho]
    #     glottis = preset(t); glottis[f0] = f0(t)
    #     glottis[pressure] = from E(t)
    #     glottis[rel_amp] = from E(t)
    #   upsample 100 → 400 Hz

    # Remove 'timer_events' if it remains in ext_aligned
    ext_aligned.pop('timer_events', None)
    ext_aligned.pop('aspiration', None)

    # Pass the segments for the glottal source rule engine
    ext_aligned['segments'] = segments

    # Shape events aligned to the REAL trajectory timing (blocks),
    # not to the parser t_start values (~2.3x too fast —
    # they caused x_top/chink oscillations at sequence start, then
    # freezing of the glottal shape on 'modal').
    from vtl_synth.core.glottal_source import classify_block_events
    from vtl_synth.core.constants import TARGET_SR as _TSR
    ext_aligned['shape_events'] = classify_block_events(
        block_info, [s.key for s in cons_segments_all], sr=_TSR)

    # Extract the consonant timing from block_info for the downstream
    # corrections in assemble_tract.py (velar TBY clamping, etc.)
    # cons_tokens holds envelope tokens ('C'), not IPA keys.
    # We use the (chronological) segments to recover the real keys.
    cons_segments = [s for s in segments if s.kind == 'C']
    consonant_frames = []
    _frame_offset = 0
    _cons_seg_idx = 0
    for _bi in block_info:
        if _bi.kind == 'cluster' and _bi.cons_tokens:
            n_cons = _bi.n_cons if _bi.n_cons > 0 else len(_bi.cons_tokens)
            raw_keys = []
            for _ in range(n_cons):
                if _cons_seg_idx < len(cons_segments):
                    raw_keys.append(cons_segments[_cons_seg_idx].key)
                    _cons_seg_idx += 1
            consonant_frames.append({
                'keys': raw_keys,
                'frame_start': _frame_offset,
                'frame_end': _frame_offset + _bi.n_steps,
            })
        _frame_offset += _bi.n_steps
    ext_aligned['consonant_frames'] = consonant_frames

    assembler = AssembleTract(speaker_config=speaker_config)
    tract_400, glottis_400 = assembler.assemble(
        tract_frames=tract_aligned,
        extension_data=ext_aligned,
        sr_in=TARGET_SR,
        sr_out=sr_out,
        ts3_ortho=ts3_ortho_aligned,
        vs_ortho=vs_ortho_aligned,
    )

    if verbose:
        print(f'[build_phrase_tract] Output: tract {tract_400.shape}, glottis {glottis_400.shape}')
        print(f'[build_phrase_tract] SR: {sr_out} Hz, '
              f'Duration: {len(tract_400) / sr_out * 1000:.1f} ms')

    # ------------------------------------------------------------------
    # Step 7: Write the .tract file
    # ------------------------------------------------------------------
    if phrase_id is not None:
        prefix = f'{phrase_id:03d}_'
    else:
        import time
        prefix = f'{int(time.time())}_'

    if label is None:
        label = ipa[:20]  # Truncate if too long
    safe_label = _sanitize_label(label)
    filename = f'{prefix}{safe_label}.tract'

    output_path = _ensure_output_dir(output_dir) / filename
    AssembleTract.write_tract_file(
        tract_400, glottis_400, str(output_path), sr=int(sr_out)
    )

    if verbose:
        print(f'[build_phrase_tract] File written: {output_path}')

    if return_data:
        return tract_400, glottis_400
    return None


# ==========================================================================
# Batch pipeline (several phrases)
# ==========================================================================

def build_batch_tract(
    phrases: List[Union[str, Tuple[str, str]]],
    output_dir: Optional[Union[str, Path]] = None,
    **kwargs,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Generate the .tract files for a batch of phrases.

    Parameters
    ----------
    phrases : list
        List of phrases. Each element is either:
          - an IPA string (auto label)
          - a tuple (ipa, label)
    output_dir : str or Path, optional
        Output directory.
    **kwargs
        Additional parameters passed to build_phrase_tract().

    Returns
    -------
    dict[str, tuple]
        {label: (tract_400, glottis_400)} for each phrase.
    """
    results = {}

    for i, phrase in enumerate(phrases, 1):
        if isinstance(phrase, tuple):
            ipa, label = phrase
        else:
            ipa = phrase
            label = None

        data = build_phrase_tract(
            ipa,
            phrase_id=i,
            label=label,
            output_dir=output_dir,
            return_data=True,
            **kwargs,
        )

        safe_label = _sanitize_label(label or ipa[:20])
        results[safe_label] = data

    return results


# ==========================================================================
# CLI entry point
# ==========================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate a 400 Hz VTL .tract file from IPA.'
    )
    parser.add_argument('ipa', help='IPA sequence (e.g. "b o Z u R")')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('-f0', '--f0', type=float, default=102.216, help='F0 (Hz)')
    parser.add_argument('-s', '--speaker', default='JD3', help='Speaker name')
    parser.add_argument('-n', '--no-ortho', action='store_true',
                        help='Disable the orthogonal branch')

    args = parser.parse_args()

    build_phrase_tract(
        args.ipa,
        f0_hz=args.f0,
        speaker=args.speaker,
        output_dir=args.output,
        use_orthogonal=not args.no_ortho,
    )
