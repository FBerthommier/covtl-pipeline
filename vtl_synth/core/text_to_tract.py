# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
text_to_tract.py
================
High-level interface: Text → VTL .tract file at 400 Hz.

This is the main entry point of the pipeline.

Full pipeline:
  1. Text → phonemic segments (with default durations)
  2. Segments → syllables
  3. TagInterpreter: annotate the segments with tags
  4. Berthommier core: (ρ,θ) → tract trajectory B(t)
  5. TimedEnvelope: anchors+FeatureTimer → E(t), VO(t), V(t), f0(t), glottis(t)
  6. AssembleTract: B(t) + E(t) → upsample → .tract file

Usage:
-------
    from vtl_synth.core.text_to_tract import text_to_tract

    # Simple API
    text_to_tract('bonjour', output_path='bonjour.tract')

    # Advanced API
    text_to_tract(
        'bonjour',
        output_path='bonjour.tract',
        f0_hz=120,
        speaker='JD2',
    )
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Optional, Tuple

from vtl_synth.core.constants import (
    TRACT_SR,
    TARGET_SR,
    VOWEL_TARGETS,
    SpeakerConfig,
    FS,
    T_S,
)
from vtl_synth.core.enveloppe import TimedEnvelope, chain_elements_to_anchors
from vtl_synth.core.amplitude_envelope import build_envelope_from_blocks
from vtl_synth.core.tag_system import TagInterpreter
from vtl_synth.core.projection import get_consonant_target
from vtl_synth.core.continuous import (
    parse_to_tract_trajectory,
    parse_to_segments,
)
from vtl_synth.core.assemble_tract import AssembleTract
from vtl_synth.core.types import PolarTarget
from vtl_synth.core.timers import build_all_timers, build_extension_curves, rescale_timer_data


# ==========================================================================
# IPA normalization
# ==========================================================================
# NOTE: The default consonant durations (CONSONANT_DURATIONS in
# parsing.py) are only used for the initial computation of
# ChainElement.duration_ms.  The effective timing of the articulatory
# trajectory is entirely controlled by T_cons / T_voy in
# _chain_elements_to_pval() (parsing.py:l.2865-2866) and by
# build_global_pval() (trajectory.py).  The E(t) envelope is
# computed from block_info, which shares this same timing.  V(t) is
# computed from block_info (l.401-415 below) to stay synchronized.
# ==========================================================================

# SAMPA phonemic uppercase letters (same definition as parsing.py)
_PHONEMIC_UPPER: frozenset = frozenset('SETDZLRNCJXOEIUY')
_CASE_NORM_TABLE = str.maketrans({
    c: c.lower()
    for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if c not in _PHONEMIC_UPPER
})


def _normalize_ipa(ipa_str: str) -> str:
    """Normalizes an IPA string.

    Handles two steps:
      0. Case normalization: non-phonemic uppercase letters (A, B, F,
         G, H, K, M, P, V, W) are converted to lowercase.
      1. Multi-character symbols (e.g. 'tS' for /tʃ/).
    """
    # 0. Case normalization
    ipa_str = ipa_str.translate(_CASE_NORM_TABLE)

    # 1. Mapping of common multi-character symbols
    multi_char = {
        'ʃ': 'S', 'ʒ': 'Z', 'tʃ': 'tS', 'dʒ': 'dZ',
        'ŋ': 'N', 'ɲ': 'J', 'ʁ': 'R', 'œ': '6',
        'ɛ': 'E', 'ɔ': 'O', 'ø': '2', 'y': 'y',
        'ə': '@', 'ɛ̃': '9', 'œ̃': '6', 'ɑ̃': '6',
        'ɔ̃': '9', 'β': 'v', 'ð': 'D', 'θ': 'T',
        'χ': 'X', 'ç': 'C', 'ʝ': 'j', 'ʍ': 'w',
        'ɥ': 'w',  # approximation
    }
    # Replace multi-char Unicode symbols with the keys
    result = ipa_str
    for uni, key in sorted(multi_char.items(), key=lambda x: -len(x[0])):
        result = result.replace(uni, key)
    return result


def text_to_tract(
        text_or_ipa: str,
        output_path: Optional[str] = None,
        f0_hz: float = 120.0,
        speaker: str = 'JD2',
        speaker_config: Optional[SpeakerConfig] = None,
        f0_contour: Optional[np.ndarray] = None,
        return_data: bool = False,
        sr_out: float = TRACT_SR,
        tag_overrides: Optional[Dict[str, Dict]] = None,
        verbose: bool = True,
        add_phrase_anchors: bool = True,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Full pipeline: Text/IPA → VTL .tract file at 400 Hz.

    Parameters
    ----------
    text_or_ipa : str
        Plain text or IPA sequence.
        If all characters are in VOWEL_TARGETS or
        CONSONANT_TARGETS, treated directly as IPA.
    output_path : str, optional
        Path of the output .tract file.
    f0_hz : float
        Default fundamental frequency (Hz).
    speaker : str
        Name of the speaker (used for configuration).
    speaker_config : SpeakerConfig, optional
        Custom speaker configuration.
    f0_contour : np.ndarray, optional
        Global F0 contour.
    return_data : bool
        If True, returns (tract, glottis) in addition to writing the file.
    sr_out : float
        Output sample rate (Hz). Default: 400.
    tag_overrides : dict, optional
        Per-phoneme tag overrides.
    verbose : bool
        Print progress information.
    add_phrase_anchors : bool
        If True (default), wrap the utterance with phrase start/end
        anchors; spaces are always treated as inter-word pauses.

    Returns
    -------
    tuple[np.ndarray, np.ndarray] or None
        (tract_400, glottis_400) if return_data=True, else None.

    Examples
    --------
    >>> text_to_tract('b o Z u R', output_path='bonjour.tract')
    >>> data = text_to_tract('a i u', return_data=True)
    >>> data[0].shape  # (T, 19)
    >>> data[1].shape  # (T, 11)
    """
    # --- Speaker configuration ---
    if speaker_config is None:
        speaker_config = SpeakerConfig(name=speaker, f0_default=f0_hz)

    # --- Step 1: Text → Segments ---
    ipa = _normalize_ipa(text_or_ipa)
    # Spaces are preserved: they are treated as inter-word pauses
    # by parse_to_segments() / parse_to_tract_trajectory()

    if verbose:
        print(f'IPA: {ipa}')

    # Use the continuous parsing pipeline
    # parse_to_segments returns (segments_without_pauses, chain_elements)
    segments, chain_elements = parse_to_segments(ipa, add_phrase_anchors=add_phrase_anchors)

    if not segments:
        raise ValueError(f"No phonemic segments found in '{text_or_ipa}'")

    if verbose:
        print(f'Segments: {[(s.key, s.kind, s.duration_ms) for s in segments]}')

    # --- Step 2: Tag annotation ---
    tag_interpreter = TagInterpreter(tag_overrides=tag_overrides)
    segments = tag_interpreter.apply_all(segments)

    if verbose:
        print(f'Tags applied: {[(s.key, s.glottal_tag, s.velum_tag, s.vot_ms) for s in segments]}')

    # --- Step 3: Berthommier tract trajectory B(t) + block_info ---
    
    tract_100, _, block_info = parse_to_tract_trajectory(ipa, sr=TARGET_SR,
                                                        add_phrase_anchors=add_phrase_anchors)
    n_steps = tract_100.shape[0]

    if verbose:
        print(f'Berthommier tract: {tract_100.shape} ({len(block_info)} blocks)')

    # --- Step 3b: Amplitude envelope E(t) from block_info ---
    flat = []
    all_polars = []
    for elem in chain_elements:
        if elem.is_pause:
            continue
        for ck in elem.onset_keys:
            ct = get_consonant_target(ck, elem.theta_vo)
            flat.append(ck)
            if ct is not None:
                all_polars.append(PolarTarget(ct[0], ct[1], f'C_{ck}', is_vowel=False))
            else:
                all_polars.append(PolarTarget(0, 0, f'C_{ck}', is_vowel=False))
        if elem.nucleus_key in VOWEL_TARGETS:
            rv, tv = VOWEL_TARGETS[elem.nucleus_key]
            flat.append(elem.nucleus_key)
            all_polars.append(PolarTarget(rv, tv, f'V_{elem.nucleus_key}', is_vowel=True))
        for ck in elem.coda_keys:
            ct = get_consonant_target(ck, elem.theta_ve)
            flat.append(ck)
            if ct is not None:
                all_polars.append(PolarTarget(ct[0], ct[1], f'C_{ck}', is_vowel=False))
            else:
                all_polars.append(PolarTarget(0, 0, f'C_{ck}', is_vowel=False))

    flat_idx = 0
    syl_boundaries = set()
    for elem in chain_elements:
        if elem.is_pause:
            continue
        syl_boundaries.add(flat_idx)
        flat_idx += len(elem.onset_keys) + 1 + len(elem.coda_keys)

    sps = int(T_S * FS)
    from vtl_synth.core.continuous import get_last_pval_state
    nodes_for_env, anchors_for_env = get_last_pval_state()

    env_highres = build_envelope_from_blocks(
        block_info=block_info, nodes=nodes_for_env, anchors=anchors_for_env,
        all_polars=all_polars, flat=flat, syl_boundaries=syl_boundaries,
        sps=sps, cexp=1.0, cdec=1.5)

    if len(env_highres) >= n_steps * sps:
        n_full = (len(env_highres) // sps) * sps
        E_100 = env_highres[:n_full].reshape(-1, sps).mean(axis=1)[:n_steps]
    else:
        t_env = np.linspace(0, 1, len(env_highres))
        t_target = np.linspace(0, 1, n_steps)
        E_100 = np.interp(t_target, t_env, env_highres)

    # --- Step 4: Glottal source (V, VO, VS, f0, glottis) ---
    anchors = chain_elements_to_anchors(chain_elements)
    timed_env = TimedEnvelope(
        anchors=anchors, speaker_config=speaker_config,
        tag_interpreter=tag_interpreter, f0_contour=f0_contour)
    extensions = timed_env.get_all_extensions()

    # Resample the extensions to n_steps
    for key in list(extensions.keys()):
        val = extensions[key]
        if not isinstance(val, np.ndarray) or key == 'timer_events':
            continue
        if len(val) != n_steps:
            if len(val) > 0:
                t_ext = np.linspace(0, 1, len(val))
                t_tgt = np.linspace(0, 1, n_steps)
                if val.ndim == 1:
                    extensions[key] = np.interp(t_tgt, t_ext, val)
                else:
                    interp_2d = np.zeros((n_steps, val.shape[1]), dtype=val.dtype)
                    for col in range(val.shape[1]):
                        interp_2d[:, col] = np.interp(t_tgt, t_ext, val[:, col])
                    extensions[key] = interp_2d
            else:
                shape = (n_steps,) + val.shape[1:]
                extensions[key] = np.zeros(shape, dtype=val.dtype)
    extensions['E'] = E_100

    # --- Step 3.5: Parsing timers (voicing, nasality, laterality) ---
    # The three timers are built at the parsing level from the
    # ChainElements. They produce VO (nasality) and TS3_ortho
    # (laterality) curves that are injected into extension_data.
    #
    # Nasality timer: VO curve with a 12 ms time constant
    # Laterality timer: TS3 curve with a fast time constant
    # Voicing timer: glottal shape events (pre-voicing)
    timer_data = None  # initialization for scope
    try:
        timer_data = build_all_timers(chain_elements, sr=TARGET_SR)

        # --- Temporal rescaling ---
        # The timers are built from ChainElement.duration_ms
        # (CONSONANT_DURATIONS + DEFAULT_VOWEL_DURATION_MS), while the
        # trajectory uses T_cons/T_voy in frames (build_global_pval).
        # A rescaling is applied to align the two clocks.
        trajectory_duration_ms = n_steps * 1000.0 / TARGET_SR
        timer_data = rescale_timer_data(timer_data, trajectory_duration_ms)

        timer_curves = build_extension_curves(timer_data, n_steps)

        # Inject the VO curve from the timer (nasality) — overrides
        # the TimedEnvelope VO if the timer produces data
        if timer_data.nasality_marks:
            extensions['VO'] = timer_curves['VO']

        # Inject the TS3_ortho curve from the timer (laterality)
        # Non-zero values only for lateral consonants.
        # TS3 = -1 → the model automatically adjusts the occlusion to 25 mm².
        if timer_data.lateral_marks:
            extensions['TS3_ortho'] = timer_curves['TS3_ortho']

        # Inject the glottal events from the voicing timer
        # (pre-voicing: supraglottal occlusion + modal coordination)
        if timer_data.voicing_marks:
            extensions['glottal_events'] = timer_curves['glottal_events']

        # Inject the pulmonary Pexp curve (bursts and frication)
        # ADDITIVE: added to the pressure in pulmonary_effort.py
        # Does NOT replace and does NOT interact with the kinematic Pexp.
        if timer_data.pexp_marks:
            extensions['Pexp_pulmonary'] = timer_curves['Pexp_pulmonary']

    except Exception as e:
        if verbose:
            print(f'Timers error: {e}')

    # --- Step 4b: V(t) from timer voicing ---
    try:
        from vtl_synth.core.timers import build_voicing_curve
        if timer_data is not None:
            V_from_timers = build_voicing_curve(timer_data, n_steps)
            if V_from_timers is not None and len(V_from_timers) == n_steps:
                extensions['V'] = V_from_timers
                if verbose:
                    print(f'V(t) timers: min={V_from_timers.min():.3f}, max={V_from_timers.max():.3f}')
            else:
                raise ValueError('V_from_timers empty or wrong length')
        else:
            raise ValueError('timer_data not available')
    except Exception as e:
        if verbose:
            print(f'V(t) timers error: {e} — fallback block_info')
        V_from_blocks = np.zeros(n_steps, dtype=np.float64)
        _f = 0
        for _bi in block_info:
            if _bi.kind in ('pause', 'terminal', 'initial'):
                pass
            elif _bi.kind in ('plateau', 'background'):
                V_from_blocks[_f:_f + _bi.n_steps] = 1.0
            elif _bi.kind in ('cluster', 'decay', 'attack'):
                V_from_blocks[_f:_f + _bi.n_steps] = 0.7
            _f += _bi.n_steps
        extensions['V'] = V_from_blocks

    if verbose:
        print(f'Envelope E(t): {E_100.shape}, min={E_100.min():.3f}, max={E_100.max():.3f}')
        print(f'FeatureTimer: {len(timed_env.timer.events)} events')
        for k, v in extensions.items():
            if hasattr(v, 'shape'):
                print(f'  Extension {k}: {v.shape}')

    # --- Step 5: Assembly B(t) + E(t) → 400 Hz ---
    ext_clean = {
        k: v for k, v in extensions.items()
        if k not in ('timer_events', 'aspiration') and isinstance(v, np.ndarray)
    }
    # Pass the segments for the glottal source rule engine
    ext_clean['segments'] = segments

    # Extract consonant timing from block_info for downstream
    # corrections in assemble_tract.py (TBY velar clamping, etc.)
    # cons_tokens contains envelope tokens ('C'), not IPA keys.
    # The (chronological) segments are used to recover the real keys.
    # is_palatal is added for velars in a palatal context
    # (theta > pi → palatal), so that the TCX/TCY velar
    # clamping is skipped in assemble_tract.py.
    cons_segments = [s for s in segments if s.kind == 'C']

    # Build the vowel context for each segment
    _vowel_contexts = []
    _current_vowel_key = None
    for _s in segments:
        if _s.kind == 'V':
            _current_vowel_key = _s.key
            _vowel_contexts.append(_current_vowel_key)
        else:
            if _current_vowel_key is not None:
                _vowel_contexts.append(_current_vowel_key)
            else:
                _next_v = None
                for _s2 in segments:
                    if _s2.kind == 'V':
                        _next_v = _s2.key
                        break
                _vowel_contexts.append(_next_v)

    # Normalize consonant keys (k→g, p→b, etc.)
    def _norm_key(k):
        _m = {'p': 'b', 't': 'd', 'f': 'v', 's': 'z', 'S': 'Z',
              'T': 'D', 'tS': 'dZ', 'k': 'g'}
        return _m.get(k, k)

    consonant_frames = []
    _frame_offset = 0
    _cons_seg_idx = 0
    for _bi in block_info:
        if _bi.kind == 'cluster' and _bi.cons_tokens:
            n_cons = _bi.n_cons if _bi.n_cons > 0 else len(_bi.cons_tokens)
            raw_keys = []
            pal_flags = []
            for _ in range(n_cons):
                if _cons_seg_idx < len(cons_segments):
                    ck = cons_segments[_cons_seg_idx].key
                    raw_keys.append(ck)
                    # Detect g_pal: g/k key with a front vowel
                    # (theta > π → palatal; /a/ at exactly π → velar)
                    nk = _norm_key(ck)
                    vk = _vowel_contexts[_cons_seg_idx] if _cons_seg_idx < len(_vowel_contexts) else None
                    is_pal = False
                    if nk == 'g' and vk is not None and vk in VOWEL_TARGETS:
                        is_pal = VOWEL_TARGETS[vk][1] > np.pi
                    pal_flags.append(is_pal)
                    _cons_seg_idx += 1
            consonant_frames.append({
                'keys': raw_keys,
                'frame_start': _frame_offset,
                'frame_end': _frame_offset + _bi.n_steps,
                'is_palatal': any(pal_flags),
            })
        _frame_offset += _bi.n_steps
    ext_clean['consonant_frames'] = consonant_frames

    # Extract TS3_ortho from the extensions to pass it to the assembler
    ts3_ortho = ext_clean.pop('TS3_ortho', None)

    assembler = AssembleTract(speaker_config=speaker_config)
    tract_400, glottis_400 = assembler.assemble(
        tract_frames=tract_100,
        extension_data=ext_clean,
        sr_in=TARGET_SR,
        sr_out=sr_out,
        ts3_ortho=ts3_ortho,
    )

    if verbose:
        print(f'Output: tract {tract_400.shape}, glottis {glottis_400.shape}')
        print(f'SR: {sr_out} Hz')
        print(f'Duration: {len(tract_400) / sr_out * 1000:.1f} ms')

    # --- Step 7: Writing the .tract file ---
    if output_path is not None:
        AssembleTract.write_tract_file(
            tract_400, glottis_400, output_path, sr=int(sr_out)
        )
        if verbose:
            print(f'File written: {output_path}')

    if return_data:
        return tract_400, glottis_400
    return None


def text_to_audio_vtl(
        text_or_ipa: str,
        output_audio: Optional[str] = None,
        **kwargs,
) -> np.ndarray:
    """Full pipeline with audio synthesis via VTL.

    Generates the .tract file then calls synth_block() to
    produce the audio.

    Parameters
    ----------
    text_or_ipa : str
        Text or IPA sequence.
    output_audio : str, optional
        Path of the output WAV file.
    **kwargs
        Additional parameters passed to text_to_tract().

    Returns
    -------
    np.ndarray
        Audio signal (float64 samples).

    Raises
    ------
    ImportError
        If vocaltractlab-cython is not installed.
    """
    from vtl_synth.core.synth import synthesize_audio
    from vtl_synth.core.constants import AUDIO_SR, TRACT_SR

    # Generate the tract vector
    tract, glottis = text_to_tract(
        text_or_ipa, return_data=True, **kwargs
    )

    state_samples = int(AUDIO_SR / TRACT_SR)

    # Synthesis via synth.py (wraps synth_block)
    audio = synthesize_audio(
        tract_parameters=tract,
        glottis_parameters=glottis,
        output_wav=output_audio,
        state_samples=state_samples,
        sample_rate=AUDIO_SR,
    )

    return audio
