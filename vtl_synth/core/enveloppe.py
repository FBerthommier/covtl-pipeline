# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
enveloppe.py
==============
Time envelopes indexed by the Berthommier anchor system.

This module replaces and extends `prosody_source.py` by relying
on gesture anchors (GestureAnchor) as the temporal backbone,
in accordance with the timit-ro-maeda reference model.

Overall architecture
---------------------
    VTL(t) = B(t) + E_source(t) + E_ortho(t)

    where:
      B(t)       Berthommier core — (rho,theta) -> COVTL -> 15 params tract
      E_source(t) glottal source branch — 11 control parameters
      E_ortho(t)  orthogonal branch — VS, VO, TS3

    E_source(t) and E_ortho(t) do NOT have their own timing.
    They are indexed by the events already produced by B(t).
    Coarticulation is inherited from the Berthommier envelope.

Anchor system
----------------
    For each syllable:  V_o → [C1 → C2 → …] → V → [C3 → …] → V_e
                            ^^^^              ^^^^                ^^^^
                         COEFCEN*rho       nominal rho          COEFCEN*rho

    Anchors define the key instants at which the extension
    parameters (voicing, nasality, effort, f0) are evaluated
    and interpolated.

FeatureTimer — temporal control by phonetic tags
--------------------------------------------------------
    A FeatureTimer is a timed event anchored on an anchor of
    the gesture chain.  It controls:
      - VOT  (Voice Onset Time)  : delay between the release
        of a voiceless stop and the onset of voicing.
      - Nasality              : velar opening/closure
        with calibrated ramps.
      - Aspiration           : duration and intensity of the
        post-release aspiration phase.
      - Breathy/Creaky       : continuous phonation mode
        over a defined duration.
      - Airstream            : subglottal pressure
        and relative amplitude.

    Each timer is defined by:
      - anchor_ref  : the reference anchor (e.g. C_b for VOT)
      - offset_ms   : offset relative to the anchor
      - duration_ms : activation duration
      - ramp_ms     : input/output transition duration
      - target_value: target value of the parameter

Source: Berthommier 2023 §3 (gestures, anchors, COEFCEN),
         rapport_vecteur_VTL_400Hz.pdf §4-6
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import (
    Dict, List, Optional, Tuple, Sequence, Any, Callable,
)
from enum import Enum

from vtl_synth.core.constants import (
    TARGET_SR,
    N_GLOTTIS_PARAMS,
    GLOTTIS_PRESETS,
    GLOTTIS_PARAM_NAMES,
    TAG_TO_VOICING,
    TAG_TO_VO_TARGET,
    TAG_TO_GLOTTIS_PRESET,
    DELTA_O,
    DELTA_E,
    SpeakerConfig,
    GlottisPreset,
    EffortBounds,
    EFFORT_DEFAULTS,
)
from vtl_synth.core.types import GestureAnchor, GestureSyllable, GestureNode
from vtl_synth.core.prosody_source import Segment, Syllable
from vtl_synth.core.tag_system import (
    TagInterpreter,
    DEFAULT_PHONEME_TAGS,
    _derive_glottal_tag,
    _derive_velum_tag,
    _derive_vot_ms,
)


# ======================================================================
# Default timing constants
# ======================================================================

# Envelope ramps (ms)
DEFAULT_ATTACK_RAMP_MS: float = 30.0
DEFAULT_RELEASE_RAMP_MS: float = 30.0

# Feature-specific ramps (ms)
VOICING_RAMP_MS: float = 40.0        # Voicing on/off transition (smoothed)
VELUM_RAMP_MS: float = 15.0         # Velum open/close transition
ASPIRATION_RAMP_MS: float = 8.0     # Aspiration transition
F0_RAMP_MS: float = 15.0            # f0 transition (micro-prosody)
EFFORT_RAMP_MS: float = 20.0        # Phonation effort transition

# VOT by place of articulation (ms) — calibrated values
# Source: Keating (1984), Lisker & Abramson (1964) averages
VOT_BY_PLACE: Dict[str, float] = {
    'labial': 20.0,
    'alveolar': 40.0,
    'velar': 50.0,
    'palatal': 35.0,
    'uvular': 45.0,
    'postalveolar': 40.0,
    'dental': 30.0,
    'labiodental': 25.0,
    'glottal': 60.0,       # ? (glottal stop)
}

# Nasality: additional velum hold duration (ms)
# After the end of a nasal segment, the velum stays
# open briefly (nasal coarticulation).
NASAL_CARRYOVER_MS: float = 20.0


# ======================================================================
# FeatureEvent — single temporal event
# ======================================================================

@dataclass
class FeatureEvent:
    """Activation event for an extension parameter.

    A FeatureEvent describes a temporal modification of a
    parameter (voicing, nasality, aspiration, etc.), anchored
    on a GestureAnchor of the gesture chain.

    Parameters
    ----------
    param_name : str
        Name of the controlled parameter
        (e.g. 'V' for voicing, 'VO' for velum opening,
         'aspiration_strength' for glottis).
    anchor_label : str
        Label of the reference anchor
        (e.g. 'C_p', 'V_o', 'V_e', 'V').
    t_anchor_ms : float
        Absolute time of the reference anchor (ms).
    offset_ms : float
        Offset relative to the anchor (ms).
        A positive offset = after the anchor.
        For VOT, offset = 0 (start of the release)
        and duration = vot_ms.
    duration_ms : float
        Activation duration (ms).
    ramp_in_ms : float
        Input ramp duration (ms).
    ramp_out_ms : float
        Output ramp duration (ms).
    target_value : float
        Target value of the parameter during activation.
    baseline_value : float
        Rest value before/after the event.
    phoneme_key : str
        IPA key of the associated phoneme (for traceability).
    priority : int
        Priority (high-priority events
        override lower ones in case of overlap).
    """
    param_name: str
    anchor_label: str
    t_anchor_ms: float
    offset_ms: float = 0.0
    duration_ms: float = 0.0
    ramp_in_ms: float = 10.0
    ramp_out_ms: float = 10.0
    target_value: float = 1.0
    baseline_value: float = 0.0
    phoneme_key: str = ''
    priority: int = 0

    @property
    def t_start_ms(self) -> float:
        """Absolute start time (ms)."""
        return self.t_anchor_ms + self.offset_ms

    @property
    def t_end_ms(self) -> float:
        """Absolute end time (ms)."""
        return self.t_start_ms + self.duration_ms

    def evaluate(self, t_ms: np.ndarray) -> np.ndarray:
        """Evaluate the event over a time vector.

        Produces a trajectory in [baseline_value, target_value]
        with cosine ramps at the boundaries.

        Parameters
        ----------
        t_ms : np.ndarray
            Time vector (ms).

        Returns
        -------
        np.ndarray
            Parameter values.
        """
        result = np.full_like(t_ms, self.baseline_value, dtype=np.float64)

        t_on = self.t_start_ms
        t_off = self.t_end_ms

        if t_off <= t_on:
            return result

        t_ramp_in_end = t_on + self.ramp_in_ms
        t_ramp_out_start = t_off - self.ramp_out_ms

        # Input ramp phase (cosine)
        mask_in = (t_ms >= t_on) & (t_ms < t_ramp_in_end)
        if np.any(mask_in) and self.ramp_in_ms > 0:
            alpha = (t_ms[mask_in] - t_on) / self.ramp_in_ms
            alpha = np.clip(alpha, 0, 1)
            result[mask_in] = self.baseline_value + \
                (self.target_value - self.baseline_value) * \
                0.5 * (1 - np.cos(np.pi * alpha))

        # Sustain (plateau) phase
        mask_sustain = (t_ms >= t_ramp_in_end) & (t_ms < t_ramp_out_start)
        result[mask_sustain] = self.target_value

        # Output ramp phase (cosine)
        mask_out = (t_ms >= t_ramp_out_start) & (t_ms <= t_off)
        if np.any(mask_out) and self.ramp_out_ms > 0:
            alpha = (t_ms[mask_out] - t_ramp_out_start) / self.ramp_out_ms
            alpha = np.clip(alpha, 0, 1)
            result[mask_out] = self.target_value + \
                (self.baseline_value - self.target_value) * \
                0.5 * (1 - np.cos(np.pi * alpha))

        return result


# ======================================================================
# FeatureTimer — event scheduler by tag
# ======================================================================

class FeatureTimer:
    """Scheduler of anchor-indexed temporal events.

    The FeatureTimer translates phonetic tags into concrete
    temporal events anchored on the gesture chain.  It is
    the bridge between the tag system (tag_system.py) and
    the time envelopes (this module).

    Workflow:
      1. schedule_from_anchors(anchors, segments) → creates the events
      2. evaluate_all(t_ms) → evaluates all the events → dict of trajectories
      3. Each trajectory is then merged into the final vector.

    Parameters
    ----------
    tag_interpreter : TagInterpreter, optional
        Phonetic tag interpreter.
        If None, uses the default derivations.
    """

    def __init__(
        self,
        tag_interpreter: Optional[TagInterpreter] = None,
    ):
        self.tag_interpreter = tag_interpreter or TagInterpreter()
        self._events: List[FeatureEvent] = []

    def clear(self) -> None:
        """Resets all events."""
        self._events.clear()

    @property
    def events(self) -> List[FeatureEvent]:
        """List of scheduled events."""
        return list(self._events)

    def add_event(self, event: FeatureEvent) -> None:
        """Adds an event manually."""
        self._events.append(event)

    # ------------------------------------------------------------------
    # Scheduling from anchors
    # ------------------------------------------------------------------

    def schedule_from_anchors(
        self,
        anchors: List[GestureAnchor],
        segments: List[Segment],
    ) -> None:
        """Schedules all events from the anchor chain.

        For each phonemic segment, derives the phonetic
        tags and creates the corresponding FeatureEvents:
          - Voicing/VOT   : control of V(t)
          - Nasality     : control of VO(t) and VS(t)
          - Aspiration    : control of aspiration_strength
          - Phonation mode : control of x_bottom, x_top, chink_area
          - Effort        : control of pressure and rel_amp

        Parameters
        ----------
        anchors : list[GestureAnchor]
            Anchors of the gesture chain.
        segments : list[Segment]
            Phonemic segments annotated by TagInterpreter.
        """
        self.clear()

        # Annotate the segments if not already done
        for seg in segments:
            self.tag_interpreter.apply(seg)

        # Build an index of anchors by label and phoneme
        anchor_index = self._build_anchor_index(anchors)

        for seg_idx, seg in enumerate(segments):
            seg_events = self._schedule_segment_events(
                seg, seg_idx, anchor_index, segments,
            )
            self._events.extend(seg_events)

        # Sort by decreasing priority, then by time
        self._events.sort(key=lambda e: (-e.priority, e.t_start_ms))

    def _build_anchor_index(
        self,
        anchors: List[GestureAnchor],
    ) -> Dict[str, GestureAnchor]:
        """Builds a fast index of anchors by label.

        Returns
        -------
        dict[str, GestureAnchor]
            Map: label → anchor. Duplicate labels
            are suffixed with the index.
        """
        index: Dict[str, GestureAnchor] = {}
        seen: Dict[str, int] = {}
        for a in anchors:
            label = a.label
            if label in seen:
                seen[label] += 1
                unique = f"{label}_{seen[label]}"
            else:
                seen[label] = 0
                unique = label
            index[unique] = a
            # Also index by plain label (last one wins)
            index[label] = a
        return index

    def _schedule_segment_events(
        self,
        seg: Segment,
        seg_idx: int,
        anchor_index: Dict[str, GestureAnchor],
        all_segments: List[Segment],
    ) -> List[FeatureEvent]:
        """Creates the FeatureEvents for a segment.

        Parameters
        ----------
        seg : Segment
            Phonemic segment.
        seg_idx : int
            Index of the segment in the sequence.
        anchor_index : dict
            Anchor index.
        all_segments : list[Segment]
            All segments (for neighbor context).

        Returns
        -------
        list[FeatureEvent]
        """
        events: List[FeatureEvent] = []
        tags = DEFAULT_PHONEME_TAGS.get(seg.key, {})
        phoneme = seg.key

        # --- Voicing / VOT ---
        events.extend(self._make_voicing_events(
            seg, seg_idx, anchor_index, all_segments, tags,
        ))

        # --- Nasality (VO, VS) ---
        events.extend(self._make_nasality_events(
            seg, seg_idx, anchor_index, all_segments, tags,
        ))

        # --- Aspiration ---
        events.extend(self._make_aspiration_events(
            seg, seg_idx, anchor_index, all_segments, tags,
        ))

        # --- Phonation mode (breathy, creaky, whisper) ---
        events.extend(self._make_phonation_mode_events(
            seg, seg_idx, anchor_index, all_segments, tags,
        ))

        return events

    # ------------------------------------------------------------------
    # VOT and Voicing
    # ------------------------------------------------------------------

    def _make_voicing_events(
        self,
        seg: Segment,
        seg_idx: int,
        anchor_index: Dict[str, GestureAnchor],
        all_segments: List[Segment],
        tags: Dict[str, Any],
    ) -> List[FeatureEvent]:
        """Handles voicing and VOT events.

        For a voiceless stop:
          - V(t) = 0 during the closure (from t_start to the release)
          - V(t) = 0 during the VOT (from the release to t_end + VOT)
          - Voicing onset ramp from VOT to VOT + 10ms

        VOT is derived from the place of articulation via VOT_BY_PLACE.
        """
        events: List[FeatureEvent] = []
        voicing = tags.get('voicing', 'voiced')
        manner = tags.get('manner', '')

        if voicing == 'voiceless' and manner == 'stop':
            # Voiceless stop: VOT controlled by place
            place = tags.get('place', 'alveolar')
            vot = VOT_BY_PLACE.get(place, 30.0)

            # Event 1: silence during the closure
            # The reference anchor is the segment start (C_{key})
            anchor_label = f'C_{seg.key}'
            anchor = anchor_index.get(anchor_label)
            t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

            # Closure duration = from start to release
            # The release is typically at 60-70% of the duration
            closure_ratio = 0.65
            closure_duration = seg.duration_ms * closure_ratio

            events.append(FeatureEvent(
                param_name='V',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                offset_ms=0.0,
                duration_ms=closure_duration,
                ramp_in_ms=5.0,
                ramp_out_ms=0.0,
                target_value=0.0,
                baseline_value=0.0,  # Already at 0
                phoneme_key=seg.key,
                priority=10,
            ))

            # Event 2: VOT after the release
            t_release = t_ref + closure_duration
            events.append(FeatureEvent(
                param_name='V',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                offset_ms=closure_duration,
                duration_ms=vot,
                ramp_in_ms=0.0,
                ramp_out_ms=VOICING_RAMP_MS,
                target_value=0.0,  # Still silent during VOT
                baseline_value=0.0,
                phoneme_key=seg.key,
                priority=10,
            ))

            # Event 3: voicing onset ramp (after VOT)
            events.append(FeatureEvent(
                param_name='V',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                offset_ms=closure_duration + vot,
                duration_ms=VOICING_RAMP_MS,
                ramp_in_ms=VOICING_RAMP_MS,
                ramp_out_ms=0.0,
                target_value=1.0,
                baseline_value=0.0,
                phoneme_key=seg.key,
                priority=5,
            ))

        elif voicing == 'voiceless' and manner in ('fricative', 'affricate'):
            # Voiceless fricative/affricate: V = 0 over the whole segment
            anchor_label = f'C_{seg.key}'
            anchor = anchor_index.get(anchor_label)
            t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

            events.append(FeatureEvent(
                param_name='V',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                offset_ms=0.0,
                duration_ms=seg.duration_ms,
                ramp_in_ms=VOICING_RAMP_MS,
                ramp_out_ms=VOICING_RAMP_MS,
                target_value=0.0,
                baseline_value=TAG_TO_VOICING.get(seg.glottal_tag, 1.0),
                phoneme_key=seg.key,
                priority=10,
            ))

        elif voicing in ('breathy', 'creaky', 'whisper'):
            # Special phonation modes
            target_v = TAG_TO_VOICING.get(voicing, 1.0)
            anchor_label = f'C_{seg.key}' if seg.kind == 'C' else 'V'
            anchor = anchor_index.get(anchor_label)
            t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

            events.append(FeatureEvent(
                param_name='V',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                offset_ms=0.0,
                duration_ms=seg.duration_ms,
                ramp_in_ms=VOICING_RAMP_MS,
                ramp_out_ms=VOICING_RAMP_MS,
                target_value=target_v,
                baseline_value=1.0,
                phoneme_key=seg.key,
                priority=8,
            ))

        return events

    # ------------------------------------------------------------------
    # Nasality
    # ------------------------------------------------------------------

    def _make_nasality_events(
        self,
        seg: Segment,
        seg_idx: int,
        anchor_index: Dict[str, GestureAnchor],
        all_segments: List[Segment],
        tags: Dict[str, Any],
    ) -> List[FeatureEvent]:
        """Handles nasality events (VO and VS).

        For nasal segments:
          - VO(t) → 1.0 (velum open)
          - VS(t) → 0.8 (active velum shape)
          - 15 ms input/output ramps
          - 20 ms nasal carryover after the end of the segment

        For nasal vowels (œ̃, ɛ̃, ø̃):
          - VO(t) → 0.5 (velum partially open)
          - VS(t) → 0.4
        """
        events: List[FeatureEvent] = []
        is_nasal = tags.get('nasal', False) or tags.get('manner') == 'nasal'

        if not is_nasal:
            return events

        anchor_label = f'C_{seg.key}' if seg.kind == 'C' else 'V'
        anchor = anchor_index.get(anchor_label)
        t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

        # Determine the degree of nasality
        is_nasal_vowel = (seg.kind == 'V' and is_nasal)
        vo_target = 0.5 if is_nasal_vowel else 1.0
        vs_target = 0.4 if is_nasal_vowel else 0.8

        # VO event (velum opening)
        total_vo_duration = seg.duration_ms + NASAL_CARRYOVER_MS
        events.append(FeatureEvent(
            param_name='VO',
            anchor_label=anchor_label,
            t_anchor_ms=t_ref,
            offset_ms=0.0,
            duration_ms=total_vo_duration,
            ramp_in_ms=VELUM_RAMP_MS,
            ramp_out_ms=VELUM_RAMP_MS,
            target_value=vo_target,
            baseline_value=0.0,
            phoneme_key=seg.key,
            priority=8,
        ))

        # VS event (velum shape)
        events.append(FeatureEvent(
            param_name='VS',
            anchor_label=anchor_label,
            t_anchor_ms=t_ref,
            offset_ms=0.0,
            duration_ms=seg.duration_ms,
            ramp_in_ms=VELUM_RAMP_MS,
            ramp_out_ms=VELUM_RAMP_MS,
            target_value=vs_target,
            baseline_value=0.0,
            phoneme_key=seg.key,
            priority=8,
        ))

        return events

    # ------------------------------------------------------------------
    # Aspiration
    # ------------------------------------------------------------------

    def _make_aspiration_events(
        self,
        seg: Segment,
        seg_idx: int,
        anchor_index: Dict[str, GestureAnchor],
        all_segments: List[Segment],
        tags: Dict[str, Any],
    ) -> List[FeatureEvent]:
        """Handles aspiration events.

        Aspiration is active for aspirated stops
        (p, t, k) and typically lasts 30-80 ms after the release.
        Intensity depends on the place of articulation.
        """
        events: List[FeatureEvent] = []
        voicing = tags.get('voicing', 'voiced')
        manner = tags.get('manner', '')
        aspiration = tags.get('aspiration', False)

        if not aspiration and voicing != 'voiceless':
            return events
        if manner not in ('stop', 'affricate'):
            return events

        place = tags.get('place', 'alveolar')

        # Aspiration duration and intensity by place
        aspiration_config = {
            'labial': (30.0, 8.0),
            'alveolar': (50.0, 12.0),
            'velar': (60.0, 15.0),
            'palatal': (40.0, 10.0),
            'uvular': (45.0, 10.0),
        }
        asp_duration, asp_intensity = aspiration_config.get(
            place, (40.0, 10.0),
        )

        anchor_label = f'C_{seg.key}'
        anchor = anchor_index.get(anchor_label)
        t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

        # Aspiration starts at the release (~65% of the duration)
        closure_ratio = 0.65
        t_release = t_ref + seg.duration_ms * closure_ratio

        events.append(FeatureEvent(
            param_name='aspiration_strength',
            anchor_label=anchor_label,
            t_anchor_ms=t_ref,
            offset_ms=seg.duration_ms * closure_ratio,
            duration_ms=asp_duration,
            ramp_in_ms=ASPIRATION_RAMP_MS,
            ramp_out_ms=ASPIRATION_RAMP_MS * 2,
            target_value=asp_intensity,
            baseline_value=0.0,
            phoneme_key=seg.key,
            priority=7,
        ))

        # rel_amp reduction during aspiration
        events.append(FeatureEvent(
            param_name='rel_amp',
            anchor_label=anchor_label,
            t_anchor_ms=t_ref,
            offset_ms=seg.duration_ms * closure_ratio,
            duration_ms=asp_duration,
            ramp_in_ms=ASPIRATION_RAMP_MS,
            ramp_out_ms=ASPIRATION_RAMP_MS * 2,
            target_value=0.2,  # reduced during aspiration
            baseline_value=1.0,
            phoneme_key=seg.key,
            priority=6,
        ))

        return events

    # ------------------------------------------------------------------
    # Phonation modes (breathy, creaky, whisper)
    # ------------------------------------------------------------------

    def _make_phonation_mode_events(
        self,
        seg: Segment,
        seg_idx: int,
        anchor_index: Dict[str, GestureAnchor],
        all_segments: List[Segment],
        tags: Dict[str, Any],
    ) -> List[FeatureEvent]:
        """Handles phonation mode events.

        Breathy  : chink_area ↑, x_bottom ↑, x_top ↑
        Creaky   : f0 ↓, double_pulsing ↑, pulse_skewness ↑
        Whisper  : chink_area ↑↑, x_bottom ↑↑, x_top ↑↑
        """
        events: List[FeatureEvent] = []
        voicing = tags.get('voicing', 'voiced')

        if voicing not in ('breathy', 'creaky', 'whisper'):
            return events

        anchor_label = f'C_{seg.key}' if seg.kind == 'C' else 'V'
        anchor = anchor_index.get(anchor_label)
        t_ref = seg.t_start if anchor is None else (anchor.t_ms or seg.t_start)

        ramp = VOICING_RAMP_MS

        if voicing == 'breathy':
            # chink_area: slightly open
            events.append(FeatureEvent(
                param_name='chink_area',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=15.0, baseline_value=0.0,
                phoneme_key=seg.key, priority=7,
            ))
            # x_bottom slightly open
            events.append(FeatureEvent(
                param_name='x_bottom',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=0.3, baseline_value=0.0,
                phoneme_key=seg.key, priority=7,
            ))

        elif voicing == 'creaky':
            # f0 reduced
            events.append(FeatureEvent(
                param_name='f0_offset',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=F0_RAMP_MS, ramp_out_ms=F0_RAMP_MS,
                target_value=-20.0, baseline_value=0.0,
                phoneme_key=seg.key, priority=6,
            ))
            # double_pulsing
            events.append(FeatureEvent(
                param_name='double_pulsing',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=0.3, baseline_value=0.05,
                phoneme_key=seg.key, priority=7,
            ))

        elif voicing == 'whisper':
            # chink_area wide open
            events.append(FeatureEvent(
                param_name='chink_area',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=40.0, baseline_value=0.0,
                phoneme_key=seg.key, priority=9,
            ))
            # x_bottom and x_top large (folds spread apart)
            events.append(FeatureEvent(
                param_name='x_bottom',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=0.8, baseline_value=0.0,
                phoneme_key=seg.key, priority=9,
            ))
            events.append(FeatureEvent(
                param_name='x_top',
                anchor_label=anchor_label,
                t_anchor_ms=t_ref,
                duration_ms=seg.duration_ms,
                ramp_in_ms=ramp, ramp_out_ms=ramp,
                target_value=1.0, baseline_value=0.0,
                phoneme_key=seg.key, priority=9,
            ))

        return events

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_all(
        self,
        t_ms: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Evaluates all events and returns the trajectories.

        For each parameter, merges the events by priority:
        the highest-priority event overrides the others.

        Parameters
        ----------
        t_ms : np.ndarray
            Time vector (ms).

        Returns
        -------
        dict[str, np.ndarray]
            Trajectories by parameter name.
        """
        # Group the events by parameter
        by_param: Dict[str, List[FeatureEvent]] = {}
        for ev in self._events:
            by_param.setdefault(ev.param_name, []).append(ev)

        results: Dict[str, np.ndarray] = {}
        for param_name, param_events in by_param.items():
            # Start with baseline = 0
            trajectory = np.zeros_like(t_ms, dtype=np.float64)

            # Apply the events by decreasing priority
            # (the highest priority overrides)
            sorted_events = sorted(param_events, key=lambda e: -e.priority)
            for ev in sorted_events:
                ev_trajectory = ev.evaluate(t_ms)
                # Apply the event where it is active
                active_mask = (
                    (t_ms >= ev.t_start_ms) &
                    (t_ms <= ev.t_end_ms)
                )
                trajectory[active_mask] = ev_trajectory[active_mask]

            results[param_name] = trajectory

        return results

    def evaluate_param(
        self,
        param_name: str,
        t_ms: np.ndarray,
    ) -> np.ndarray:
        """Evaluates a single parameter.

        Parameters
        ----------
        param_name : str
            Parameter name.
        t_ms : np.ndarray
            Time vector (ms).

        Returns
        -------
        np.ndarray
            Parameter trajectory.
        """
        all_results = self.evaluate_all(t_ms)
        return all_results.get(param_name, np.zeros_like(t_ms))


# ======================================================================
# Syllabic envelope — anchor-indexed envelope
# ======================================================================

def envelope_from_anchors(
    t_ms: np.ndarray,
    anchors: List[GestureAnchor],
    syllables: Optional[List[Syllable]] = None,
    chain_elements: Optional[List] = None,
    attack_ramp_ms: float = DEFAULT_ATTACK_RAMP_MS,
    release_ramp_ms: float = DEFAULT_RELEASE_RAMP_MS,
) -> np.ndarray:
    """Computes E(t) indexed by gesture anchors.

    The syllabic envelope is built using the V_o, V and V_e
    anchors of each syllable.  For each syllable:

      - Rise   : from V_o (E=COEFCEN) to V (E=1)
        cosine ramp over attack_ramp_ms
      - Plateau : E=1 between V_o and V_e
      - Fall   : from V (E=1) to V_e (E=COEFCEN)
        cosine ramp over release_ramp_ms

    If chain_elements is provided (from parsing.py), uses the
    transition information (concatenated/pause) to
    determine the behavior at junctions.

    Parameters
    ----------
    t_ms : np.ndarray
        Time vector (ms).
    anchors : list[GestureAnchor]
        Anchors of the gesture chain.
    syllables : list[Syllable], optional
        ProsodySource syllabic structure.
    chain_elements : list[ChainElement], optional
        Elements from parsing.py (for transitions).
    attack_ramp_ms : float
        Attack ramp duration (ms).
    release_ramp_ms : float
        Release ramp duration (ms).

    Returns
    -------
    np.ndarray
        Envelope E(t) in [0, ~1.5].
    """
    E = np.zeros_like(t_ms, dtype=np.float64)

    if not anchors:
        return E

    # Build the (V_o, V, V_e) pairs per syllable
    syllable_anchors = _group_anchors_by_syllable(anchors)

    for syl_group in syllable_anchors:
        vo = syl_group.get('V_o')
        v = syl_group.get('V')
        ve = syl_group.get('V_e')

        if v is None:
            continue

        t_v = v.t_ms
        if t_v is None:
            continue

        # Determine the syllable boundaries
        t_syl_start = vo.t_ms if vo is not None and vo.t_ms is not None else t_v
        t_syl_end = ve.t_ms if ve is not None and ve.t_ms is not None else t_v

        # Determine the stress factor (from syllables if provided)
        stress_factor = 1.0
        if syllables is not None:
            for syl in syllables:
                if syl.nucleus is not None:
                    nuc_start = syl.nucleus.t_start
                    nuc_end = syl.nucleus.t_end
                    if abs(nuc_start - t_syl_start) < 5.0:
                        stress_factor = 1.0 + 0.3 * syl.stress
                        break

        # Build the envelope for this syllable
        syl_env = _single_syllable_envelope(
            t_ms,
            t_vo=t_syl_start,
            t_v=t_v,
            t_ve=t_syl_end,
            attack_ramp_ms=attack_ramp_ms,
            release_ramp_ms=release_ramp_ms,
            rho_vo=vo.rho if vo else (v.rho * DELTA_O),
            rho_v=v.rho,
            rho_ve=ve.rho if ve else (v.rho * DELTA_E),
        )

        E = np.maximum(E, syl_env * stress_factor)

    return E


def _group_anchors_by_syllable(
    anchors: List[GestureAnchor],
) -> List[Dict[str, GestureAnchor]]:
    """Groups anchors by syllable.

    Walks the sequential list of anchors and groups them
    into (V_o, V, V_e) triplets based on labels.

    Returns
    -------
    list[dict[str, GestureAnchor]]
        List of groups, each group being a dict
        with keys 'V_o', 'V', 'V_e' (optional).
    """
    groups: List[Dict[str, GestureAnchor]] = []
    current: Dict[str, GestureAnchor] = {}

    for a in anchors:
        if a.label == 'V_o':
            # New syllable
            if current.get('V') is not None:
                groups.append(current)
            current = {'V_o': a}
        elif a.label == 'V':
            current['V'] = a
        elif a.label == 'V_e':
            current['V_e'] = a
            groups.append(current)
            current = {}
        elif a.label.startswith('C_'):
            # Consonants belong to the current group
            current[a.label] = a

    # Last unclosed group
    if current.get('V') is not None:
        groups.append(current)

    return groups


def _single_syllable_envelope(
    t_ms: np.ndarray,
    t_vo: float,
    t_v: float,
    t_ve: float,
    attack_ramp_ms: float = 30.0,
    release_ramp_ms: float = 30.0,
    rho_vo: float = 0.7,
    rho_v: float = 1.0,
    rho_ve: float = 0.7,
) -> np.ndarray:
    """Computes the envelope of a syllable indexed by its anchors.

    The envelope reflects the degree of vowel realization,
    measured by normalized rho:
      E(t) = rho(t) / rho_nominal

    At the V_o and V_e anchors, rho is reduced by COEFCEN,
    which yields a natural envelope < 1 at the boundaries.

    Parameters
    ----------
    t_ms : np.ndarray
        Time vector (ms).
    t_vo : float
        Time of the V_o anchor (ms).
    t_v : float
        Time of the V anchor (nucleus, ms).
    t_ve : float
        Time of the V_e anchor (ms).
    attack_ramp_ms : float
        Attack ramp duration (ms).
    release_ramp_ms : float
        Release ramp duration (ms).
    rho_vo : float
        Rho at the V_o anchor.
    rho_v : float
        Nominal rho (full target).
    rho_ve : float
        Rho at the V_e anchor.

    Returns
    -------
    np.ndarray
        Envelope E(t) in [0, 1+].
    """
    E = np.zeros_like(t_ms, dtype=np.float64)

    if rho_v <= 0:
        return E

    # Normalize by nominal rho
    e_vo = rho_vo / rho_v  # typically COEFCEN
    e_v = rho_v / rho_v    # 1.0
    e_ve = rho_ve / rho_v  # typically COEFCEN

    # Rise phase (V_o → V)
    # In the Berthommier model, V_o is purely articulatory.
    # The effort envelope does not rise during V_o.
    # The rise starts attack_ramp_ms before V.
    ramp_start = t_v - attack_ramp_ms
    in_attack = (t_ms >= ramp_start) & (t_ms < t_v)
    if np.any(in_attack) and attack_ramp_ms > 0:
        alpha = (t_ms[in_attack] - ramp_start) / max(1.0, t_v - ramp_start)
        alpha = np.clip(alpha, 0, 1)
        # Rise from 0 (no effort at V_o) to 1 (full effort at V)
        E[in_attack] = 0.0 + (e_v - 0.0) * 0.5 * (1 - np.cos(np.pi * alpha))

    # Plateau phase (around V)
    # The plateau extends from t_v to t_v (instantaneous at the nucleus)
    # In practice, E=1 is held over a window around t_v
    nucleus_half = max(5.0, (t_ve - t_vo) * 0.1)  # 10% of the syllable duration
    in_nucleus = (t_ms >= t_v - nucleus_half) & (t_ms <= t_v + nucleus_half)
    E[in_nucleus] = np.maximum(E[in_nucleus], e_v)

    # Release phase (V → V_e)
    ramp_end = min(t_ve, t_v + release_ramp_ms)
    in_release = (t_ms > t_v + nucleus_half) & (t_ms <= t_ve)
    if np.any(in_release):
        # Interpolation from e_v to e_ve
        alpha = (t_ms[in_release] - (t_v + nucleus_half)) / \
            max(1.0, t_ve - (t_v + nucleus_half))
        alpha = np.clip(alpha, 0, 1)
        # Cosine for a smooth transition
        E[in_release] = e_v + (e_ve - e_v) * 0.5 * (1 + np.cos(np.pi * (1 - alpha)))

    return np.clip(E, 0, None)


# ======================================================================
# EnvelopeAnchor — adapter from anchors → segments for FeatureTimer
# ======================================================================

def anchors_to_segments(
    anchors: List[GestureAnchor],
    default_vowel_duration_ms: float = 80.0,
    default_consonant_duration_ms: float = 60.0,
) -> List[Segment]:
    """Converts an anchor chain into ProsodySource segments.

    This function is a bridge between the anchor system
    (gesture.py) and the envelope system (this module).

    Parameters
    ----------
    anchors : list[GestureAnchor]
        Anchors in chronological order.
    default_vowel_duration_ms : float
        Default duration for vowels (ms).
    default_consonant_duration_ms : float
        Default duration for consonants (ms).

    Returns
    -------
    list[Segment]
        Segments with timing derived from the anchors.
    """
    segments: List[Segment] = []

    for i, a in enumerate(anchors):
        if a.label in ('V_o', 'V_e'):
            # Boundary anchors do not generate segments
            continue

        if a.label == 'V':
            key = a.node.key if a.node else '@'
            kind = 'V'
        elif a.label.startswith('C_'):
            key = a.label[2:]  # Strip the 'C_' prefix
            kind = 'C'
        else:
            continue

        # Determine the duration from adjacent anchors
        if i + 1 < len(anchors):
            t_next = anchors[i + 1].t_ms or 0
        else:
            t_next = (a.t_ms or 0) + \
                (default_vowel_duration_ms if kind == 'V'
                 else default_consonant_duration_ms)

        duration = max(10.0, (t_next or 0) - (a.t_ms or 0))
        t_start = a.t_ms or 0

        segments.append(Segment(
            key=key,
            kind=kind,
            t_start=t_start,
            t_end=t_start + duration,
            duration_ms=duration,
        ))

    return segments


# ======================================================================
# TimedEnvelope — main class
# ======================================================================

class TimedEnvelope:
    """Time envelopes indexed by the anchor system.

    This class unifies the computation of all extension variables
    (E, VO, VS, V, f0, glottis) by relying on:
      1. Gesture anchors (GestureAnchor) as the backbone
      2. The FeatureTimer for tag-based temporal control
      3. The syllabic envelope derived from the V_o/V/V_e anchors

    Architecture:

        GestureAnchor[] → anchors_to_segments() → Segment[]
                                                    ↓
        FeatureTimer.schedule_from_anchors() → FeatureEvent[]
                                                    ↓
        envelope_from_anchors() → E(t)
        FeatureTimer.evaluate_all() → VO(t), V(t), glottis_params(t)
                                                    ↓
        TimedEnvelope.assemble() → complete dict

    Parameters
    ----------
    anchors : list[GestureAnchor]
        Anchors of the gesture chain.
    syllables : list[Syllable], optional
        Syllabic structure (ProsodySource).
    speaker_config : SpeakerConfig, optional
        Speaker configuration.
    tag_interpreter : TagInterpreter, optional
        Tag interpreter.
    f0_contour : np.ndarray, optional
        Global F0 contour (Hz).
    """

    def __init__(
        self,
        anchors: List[GestureAnchor],
        syllables: Optional[List[Syllable]] = None,
        speaker_config: Optional[SpeakerConfig] = None,
        tag_interpreter: Optional[TagInterpreter] = None,
        f0_contour: Optional[np.ndarray] = None,
    ):
        self.anchors = anchors
        self.syllables = syllables
        self.speaker = speaker_config or SpeakerConfig()
        self.f0_contour = f0_contour

        # FeatureTimer
        self.timer = FeatureTimer(
            tag_interpreter=tag_interpreter,
        )

        # Compute the timing
        self._compute_timing()

        # Convert the anchors to segments
        self.segments = anchors_to_segments(anchors)

        # Schedule the events
        self.timer.schedule_from_anchors(anchors, self.segments)

    def _compute_timing(self) -> None:
        """Computes the total duration and the time vector."""
        t_max = 0.0
        for a in self.anchors:
            if a.t_ms is not None:
                t_max = max(t_max, a.t_ms)

        # Add a margin for the end ramps
        self.total_duration_ms = max(t_max + 50.0, 100.0)
        self.n_frames = int(self.total_duration_ms * TARGET_SR / 1000.0) + 1
        self.t_ms = np.linspace(
            0, self.total_duration_ms, self.n_frames,
        )

    # ------------------------------------------------------------------
    # Syllabic envelope E(t) indexed by anchors
    # ------------------------------------------------------------------

    def compute_effort(self) -> np.ndarray:
        """Computes E(t), the phonation effort, indexed by the anchors.

        Unlike ProsodySource.compute_effort(), this
        version uses the V_o/V/V_e anchors to determine
        the rise, plateau and fall instants.

        Returns
        -------
        np.ndarray, shape (n_frames,)
            E(t) in [0, ~1.5].
        """
        return envelope_from_anchors(
            self.t_ms,
            self.anchors,
            syllables=self.syllables,
        )

    # ------------------------------------------------------------------
    # Voicing V(t) with timer-controlled VOT
    # ------------------------------------------------------------------

    def compute_voicing(self) -> np.ndarray:
        """Computes V(t) with VOT controlled by FeatureTimer.

        In the Berthommier model, V_o is purely
        articulatory (silent). Voicing only starts
        at the voiced consonantal onset or at the
        vocalic nucleus.

        Logic:
          - Before the first phonation event: V = 0
          - V_o (anticipation): V = 0 (articulatory only)
          - From the first voiced onset / nucleus on: V = 1
          - V_e (end of syllable): V returns to 0
          - Voiceless FeatureEvents override V to 0 locally

        Returns
        -------
        np.ndarray, shape (n_frames,)
            V(t) in [0, 1].
        """
        from vtl_synth.core.tag_system import DEFAULT_PHONEME_TAGS

        # By default, everything is unvoiced (silence)
        V = np.zeros(self.n_frames, dtype=np.float64)

        # Build the voicing regions syllable by syllable
        # from the anchor triplets (V_o, V, V_e)
        syllable_groups = _group_anchors_by_syllable(self.anchors)

        for syl_group in syllable_groups:
            vo = syl_group.get('V_o')
            v = syl_group.get('V')
            ve = syl_group.get('V_e')

            if v is None or v.t_ms is None:
                continue

            t_v = v.t_ms
            t_ve = ve.t_ms if ve and ve.t_ms is not None else t_v + 30.0

            # Find the start of voicing:
            # the first voiced C of THE current syllable, or V if there is no voiced C.
            # The search is restricted to the consonants of this syllable
            # (between V_o and V) to avoid capturing the Cs of a
            # previous syllable.
            t_syl_start = vo.t_ms if (vo is not None
                             and vo.t_ms is not None) else 0.0
            t_voicing_start = None
            for a in self.anchors:
                if a.t_ms is None:
                    continue
                if a.label.startswith('C_') and a.t_ms <= t_v:
                    # Only consider the Cs of this syllable
                    if a.t_ms < t_syl_start:
                        continue
                    ck = a.label[2:]
                    tags = DEFAULT_PHONEME_TAGS.get(ck, {})
                    if tags.get('voicing', 'voiced') == 'voiced':
                        if t_voicing_start is None or a.t_ms < t_voicing_start:
                            t_voicing_start = a.t_ms

            if t_voicing_start is None:
                t_voicing_start = t_v

            # For CVC syllables with a stop coda:
            # voicing stops BEFORE the coda
            has_coda_stop = False
            t_coda_start = None
            for a in self.anchors:
                if a.t_ms is None:
                    continue
                if a.label.startswith('C_') and a.t_ms > t_v:
                    # Only consider the Cs of this syllable (before V_e)
                    if a.t_ms >= t_ve:
                        continue
                    ck = a.label[2:]
                    tags = DEFAULT_PHONEME_TAGS.get(ck, {})
                    manner = tags.get('manner', '')
                    if manner == 'stop':
                        has_coda_stop = True
                        if t_coda_start is None or a.t_ms < t_coda_start:
                            t_coda_start = a.t_ms

            if has_coda_stop and t_coda_start is not None:
                # Voicing stops 10ms before the stop coda
                t_voicing_end = t_coda_start - 10.0
            else:
                t_voicing_end = t_ve

            if t_voicing_end <= t_voicing_start:
                continue

            # Attack ramp (30ms) and release ramp (40ms)
            ramp_in = 30.0
            ramp_out = 40.0

            # Rise phase
            t_ramp_end = t_voicing_start + ramp_in
            mask_in = (self.t_ms >= t_voicing_start) & (self.t_ms < t_ramp_end)
            if np.any(mask_in):
                alpha = (self.t_ms[mask_in] - t_voicing_start) / ramp_in
                alpha = np.clip(alpha, 0, 1)
                V[mask_in] = np.maximum(V[mask_in],
                                       0.5 * (1 - np.cos(np.pi * alpha)))

            # Sustain phase
            t_rel_start = t_voicing_end - ramp_out
            mask_sustain = (self.t_ms >= t_ramp_end) & (self.t_ms < t_rel_start)
            V[mask_sustain] = np.maximum(V[mask_sustain], 1.0)

            # Release phase
            mask_out = (self.t_ms >= t_rel_start) & (self.t_ms <= t_voicing_end)
            if np.any(mask_out):
                alpha = (self.t_ms[mask_out] - t_rel_start) / ramp_out
                alpha = np.clip(alpha, 0, 1)
                V[mask_out] = np.maximum(
                    V[mask_out],
                    0.5 * (1 + np.cos(np.pi * alpha))
                )

        # Apply the voiceless FeatureEvents (high priority)
        voicing_events = [
            ev for ev in self.timer._events
            if ev.param_name == 'V'
        ]
        voicing_events.sort(key=lambda e: -e.priority)
        for ev in voicing_events:
            ev_traj = ev.evaluate(self.t_ms)
            active = (self.t_ms >= ev.t_start_ms) & \
                     (self.t_ms <= ev.t_end_ms)
            V[active] = ev_traj[active]

        return np.clip(V, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Nasality VO(t) and VS(t) with carryover
    # ------------------------------------------------------------------

    def compute_velum(self) -> np.ndarray:
        """Computes VO(t) with nasal carryover.

        The FeatureTimer automatically handles the nasal
        carryover (NASAL_CARRYOVER_MS) via the extended
        duration of the VO event.

        Returns
        -------
        np.ndarray, shape (n_frames,)
            VO(t) in [0, 1].
        """
        VO = self.timer.evaluate_param('VO', self.t_ms)
        return np.clip(VO, 0.0, 1.0)

    def compute_velum_shape(self) -> np.ndarray:
        """Computes VS(t) with nasal carryover.

        Returns
        -------
        np.ndarray, shape (n_frames,)
            VS(t).
        """
        VS = self.timer.evaluate_param('VS', self.t_ms)
        return np.clip(VS, 0.0, 1.0)

    # ------------------------------------------------------------------
    # f0(t) with phonation mode offsets
    # ------------------------------------------------------------------

    def compute_f0(self) -> np.ndarray:
        """Computes f0(t) with phonation mode offsets.

        The FeatureTimer can generate an 'f0_offset' for
        creaky (reduced f0) or breathy modes.

        Returns
        -------
        np.ndarray, shape (n_frames,)
            f0(t) in Hz. 0 outside voicing.
        """
        V = self.compute_voicing()
        f0 = np.zeros(self.n_frames, dtype=np.float64)

        if self.f0_contour is not None and \
           len(self.f0_contour) == self.n_frames:
            f0 = self.f0_contour.copy()
        else:
            f0 = np.full(
                self.n_frames, self.speaker.f0_default,
                dtype=np.float64,
            )
            # Micro-prosody (light jitter)
            jitter = np.random.normal(0, 0.5, self.n_frames)
            f0 += jitter

        # Apply the phonation mode offsets
        f0_offset = self.timer.evaluate_param('f0_offset', self.t_ms)
        f0 += f0_offset

        # Zero outside voicing
        f0[V < 0.1] = 0.0

        return f0

    # ------------------------------------------------------------------
    # Glottal presets with phonation modes
    # ------------------------------------------------------------------

    def compute_presets(self) -> np.ndarray:
        """Computes the 11 glottal parameters at TARGET_SR.

        This version extends ProsodySource.compute_presets() by
        applying phonation mode FeatureEvents (breathy,
        creaky, whisper) as temporal overrides.

        Returns
        -------
        np.ndarray, shape (n_frames, 11)
            Glottal parameters per frame.
        """
        E = self.compute_effort()
        V = self.compute_voicing()
        f0 = self.compute_f0()
        effort = self.speaker.effort

        glottis = np.zeros(
            (self.n_frames, N_GLOTTIS_PARAMS), dtype=np.float64,
        )

        # Parameters derived from the timers
        timer_params = self.timer.evaluate_all(self.t_ms)

        for i in range(self.n_frames):
            # Determine the base preset for this frame
            preset_name = 'modal'
            for seg in self.segments:
                if seg.t_start <= self.t_ms[i] < seg.t_end:
                    preset_name = TAG_TO_GLOTTIS_PRESET.get(
                        seg.glottal_tag, 'modal',
                    )
                    break

            preset = self.speaker.get_preset(preset_name)
            frame = preset.to_vector()

            # f0
            frame[0] = f0[i]

            # Voicing blend -- determine whether the frame is voiced
            voiceless = GLOTTIS_PRESETS["voiceless"].to_vector()
            v = V[i]
            frame[2] = voiceless[2] * (1 - v) + preset.x_bottom * v
            frame[3] = voiceless[3] * (1 - v) + preset.x_top * v
            frame[4] = voiceless[4] * (1 - v) + preset.chink_area * v
            # Pressure: for voiced segments (v > 0.5),
            # the subglottal pressure must be high to
            # maintain phonation. E(t) modulates it slightly.
            # For voiceless segments, pressure derives from effort.
            if v > 0.5:
                p_voiced = getattr(preset, "pressure", 8000.0)
                frame[1] = p_voiced * (0.9 + 0.1 * E[i])
            else:
                frame[1] = effort.P_min + E[i] * (effort.P_max - effort.P_min)
            # rel_amp: voiced -> high (~preset.rel_amp), voiceless -> 0
            if v > 0.5:
                frame[6] = getattr(preset, "rel_amp", 1.0)
            else:
                frame[6] = 0.0

            # Phonation mode overrides from the timers
            for param_idx, param_name in enumerate(GLOTTIS_PARAM_NAMES):
                if param_name in ('f0', 'pressure', 'rel_amp'):
                    continue  # Already handled
                if param_name in timer_params:
                    timer_val = timer_params[param_name][i]
                    # Apply only if significant
                    if abs(timer_val) > 0.001:
                        frame[param_idx] = timer_val

            glottis[i] = frame

        return glottis

    # ------------------------------------------------------------------
    # Aspiration
    # ------------------------------------------------------------------

    def compute_aspiration(self) -> np.ndarray:
        """Computes aspiration_strength(t) at TARGET_SR.

        Returns
        -------
        np.ndarray, shape (n_frames,)
            aspiration_strength(t).
        """
        asp = self.timer.evaluate_param('aspiration_strength', self.t_ms)
        return np.clip(asp, 0.0, 30.0)

    # ------------------------------------------------------------------
    # Complete interface
    # ------------------------------------------------------------------

    def get_all_extensions(self) -> Dict[str, np.ndarray]:
        """Returns all extension variables at TARGET_SR.

        Returns
        -------
        dict[str, np.ndarray]
            - 'E'              : effort (n_frames,)
            - 'VO'             : velum opening (n_frames,)
            - 'VS'             : velum shape (n_frames,)
            - 'V'              : voicing (n_frames,)
            - 'f0'             : fundamental frequency (n_frames,)
            - 'aspiration'     : aspiration strength (n_frames,)
            - 'glottis'        : full glottis vector (n_frames, 11)
            - 'timer_events'   : dict of all timer trajectories
        """
        return {
            'E': self.compute_effort(),
            'VO': self.compute_velum(),
            'VS': self.compute_velum_shape(),
            'V': self.compute_voicing(),
            'f0': self.compute_f0(),
            'aspiration': self.compute_aspiration(),
            'glottis': self.compute_presets(),
            'timer_events': self.timer.evaluate_all(self.t_ms),
        }

    # ------------------------------------------------------------------
    # Manual timer addition
    # ------------------------------------------------------------------

    def add_vot_override(
        self,
        phoneme_key: str,
        vot_ms: float,
        anchor_label: Optional[str] = None,
    ) -> None:
        """Adds a manual VOT override for a phoneme.

        Parameters
        ----------
        phoneme_key : str
            IPA key of the phoneme.
        vot_ms : float
            VOT in ms.
        anchor_label : str, optional
            Anchor label. If None, inferred
            automatically (C_{key}).
        """
        if anchor_label is None:
            anchor_label = f'C_{phoneme_key}'

        # Find the anchor
        t_anchor = 0.0
        for a in self.anchors:
            if a.label == anchor_label and a.t_ms is not None:
                t_anchor = a.t_ms
                break

        self.timer.add_event(FeatureEvent(
            param_name='V',
            anchor_label=anchor_label,
            t_anchor_ms=t_anchor,
            offset_ms=0.0,
            duration_ms=vot_ms,
            ramp_in_ms=0.0,
            ramp_out_ms=VOICING_RAMP_MS,
            target_value=0.0,
            baseline_value=0.0,
            phoneme_key=phoneme_key,
            priority=15,  # High priority = overrides the default VOT
        ))


# ======================================================================
# Compatibility utilities
# ======================================================================

def create_timed_envelope_from_segments(
    segments: List[Segment],
    syllables: Optional[List[Syllable]] = None,
    speaker_config: Optional[SpeakerConfig] = None,
    tag_interpreter: Optional[TagInterpreter] = None,
    f0_contour: Optional[np.ndarray] = None,
) -> TimedEnvelope:
    """Creates a TimedEnvelope from segments (compatibility).

    This function converts the segments into synthetic anchors
    to allow using TimedEnvelope even without the full
    anchor pipeline.

    Parameters
    ----------
    segments : list[Segment]
        Phonemic segments.
    syllables : list[Syllable], optional
        Syllabic structure.
    speaker_config : SpeakerConfig, optional
        Speaker configuration.
    tag_interpreter : TagInterpreter, optional
        Tag interpreter.
    f0_contour : np.ndarray, optional
        F0 contour.

    Returns
    -------
    TimedEnvelope
    """
    from vtl_synth.core.constants import VOWEL_TARGETS, DELTA_O, DELTA_E

    # Build synthetic anchors from the segments
    synthetic_anchors: List[GestureAnchor] = []
    syl_idx = 0
    in_syllable = False
    syl_nucleus_t = 0.0
    syl_start_t = 0.0
    prev_vowel_rho = 0.5
    prev_vowel_theta = np.pi

    for seg in segments:
        if seg.kind == 'V':
            rho_v, theta_v = VOWEL_TARGETS.get(
                seg.key, (0.5, np.pi),
            )

            if not in_syllable:
                # Syllable start
                syl_start_t = seg.t_start
                in_syllable = True

                # V_o: anticipation (DELTA_O * rho)
                if syl_idx > 0:
                    synthetic_anchors.append(GestureAnchor(
                        rho=DELTA_O * rho_v,
                        theta=theta_v,
                        label='V_o',
                        t_ms=seg.t_start,
                    ))

            # V: full vowel (middle of the nucleus)
            syl_nucleus_t = seg.t_start + seg.duration_ms * 0.5
            synthetic_anchors.append(GestureAnchor(
                rho=rho_v,
                theta=theta_v,
                label='V',
                t_ms=syl_nucleus_t,
            ))

            prev_vowel_rho = rho_v
            prev_vowel_theta = theta_v

        elif seg.kind == 'C':
            # Mark the syllable start if a consonant precedes the vowel
            if not in_syllable:
                syl_start_t = seg.t_start
                in_syllable = True

    # Close the last syllable
    if in_syllable and len(synthetic_anchors) > 0:
        last_seg = segments[-1]
        synthetic_anchors.append(GestureAnchor(
            rho=DELTA_E * prev_vowel_rho,
            theta=prev_vowel_theta,
            label='V_e',
            t_ms=last_seg.t_end,
        ))
        syl_idx += 1

    return TimedEnvelope(
        anchors=synthetic_anchors,
        syllables=syllables,
        speaker_config=speaker_config,
        tag_interpreter=tag_interpreter,
        f0_contour=f0_contour,
    )


# ======================================================================
# Bridge: parsing → anchors
# ======================================================================

def chain_elements_to_anchors(
    chain_elements: list,
    consonant_durations: Optional[Dict[str, float]] = None,
) -> List[GestureAnchor]:
    """Converts a chain of ChainElement into gesture anchors.

    For each syllable (non-pause ChainElement), generates:
      V_o → C1 → C2 → … → V → Cj → … → V_e

    Absolute times are computed from the cumulative
    durations of the elements.

    Parameters
    ----------
    chain_elements : list[ChainElement]
        Syllabic chain from parsing.syllabify_continuous().
    consonant_durations : dict, optional
        Specific durations per consonant (ms).
        If None, uses the default durations.

    Returns
    -------
    list[GestureAnchor]
        Anchors in chronological order.
    """
    from vtl_synth.core.continuous import CONSONANT_DURATIONS

    if consonant_durations is None:
        consonant_durations = CONSONANT_DURATIONS

    # Durations by phoneme type
    default_c_dur = 60.0
    default_v_dur = 80.0

    anchors: List[GestureAnchor] = []
    t = 0.0

    for elem in chain_elements:
        if elem.is_pause:
            # Pause: no gesture anchors, just advance the time
            t += elem.pause_duration_ms
            continue

        if not elem.has_nucleus:
            continue

        # --- Intra-syllable temporal distribution ---
        onset_keys = elem.onset_keys
        coda_keys = elem.coda_keys
        n_onset = len(onset_keys)
        n_coda = len(coda_keys)

        # Individual durations
        onset_durs = [consonant_durations.get(k, default_c_dur)
                       for k in onset_keys]
        coda_durs = [consonant_durations.get(k, default_c_dur)
                      for k in coda_keys]
        total_onset_dur = sum(onset_durs)
        total_coda_dur = sum(coda_durs)

        # Nucleus duration = the remainder of the syllable duration
        nucleus_dur = max(20.0, elem.duration_ms - total_onset_dur - total_coda_dur)

        # --- V_o ---
        t_syl_start = t
        # V_o is created for every syllable except the very first
        # (t > 0), regardless of the transition type.  Without V_o,
        # _group_anchors_by_syllable() cannot form proper (V_o,V,V_e)
        # triplets, and compute_voicing() will set V(t)=0.
        if t > 0:
            anchors.append(GestureAnchor(
                rho=elem.rho_vo,
                theta=elem.theta_vo,
                label='V_o',
                t_ms=t,
            ))

        # --- Onset consonants ---
        t_onset = t
        for k_idx, c_key in enumerate(onset_keys):
            c_dur = onset_durs[k_idx]
            # Consonantal target
            c_target = _get_consonant_target(c_key)
            if c_target is not None:
                rho_c, theta_c = c_target
            else:
                rho_c, theta_c = 1.0, 0.0

            anchors.append(GestureAnchor(
                rho=rho_c,
                theta=theta_c,
                label=f'C_{c_key}',
                t_ms=t_onset,
            ))
            t_onset += c_dur

        # --- V (nucleus) ---
        t_nucleus = t_onset + nucleus_dur * 0.5
        anchors.append(GestureAnchor(
            rho=elem.rho_v,
            theta=elem.theta_v,
            label='V',
            t_ms=t_nucleus,
        ))

        # --- Coda consonants ---
        t_coda = t_onset + nucleus_dur
        for k_idx, c_key in enumerate(coda_keys):
            c_dur = coda_durs[k_idx]
            c_target = _get_consonant_target(c_key)
            if c_target is not None:
                rho_c, theta_c = c_target
            else:
                rho_c, theta_c = 1.0, 0.0

            anchors.append(GestureAnchor(
                rho=rho_c,
                theta=theta_c,
                label=f'C_{c_key}',
                t_ms=t_coda,
            ))
            t_coda += c_dur

        # --- V_e ---
        t_syl_end = t_coda
        anchors.append(GestureAnchor(
            rho=elem.rho_ve,
            theta=elem.theta_ve,
            label='V_e',
            t_ms=t_syl_end,
        ))

        t = t_syl_end

    return anchors


def _get_consonant_target(key: str) -> Optional[Tuple[float, float]]:
    """Returns (rho, theta) for a consonant.

    Uses the centralized normalization from berthommier.py
    (voiced/voiceless pairs) then handles the special keys g_vel/g_pal.
    """
    from vtl_synth.core.constants import CONSONANT_TARGETS
    from vtl_synth.core.projection import normalize_consonant_key

    key = normalize_consonant_key(key)

    # g (and k after normalization): velar by default
    if key == 'g':
        key = 'g_vel'

    info = CONSONANT_TARGETS.get(key)
    if info is not None:
        return info[0], info[1]
    return None


def parse_to_anchors(
    ipa_str: str,
    pause_marker: str = '.',
    pause_duration_ms: float = 50.0,
    vowel_duration_ms: float = 80.0,
    consonant_durations: Optional[Dict[str, float]] = None,
) -> List[GestureAnchor]:
    """Parses an IPA string and returns the gesture anchors.

    Convenience entry point that combines parsing and anchor
    construction in a single call.

    Parameters
    ----------
    ipa_str : str
        IPA string with pause markers ('.').
    pause_marker : str
        Pause marker character.
    pause_duration_ms : float
        Default duration of a pause (ms).
    vowel_duration_ms : float
        Default duration of vowels (ms).
    consonant_durations : dict, optional
        Specific durations per consonant.

    Returns
    -------
    list[GestureAnchor]
        Anchors in chronological order.
    """
    from vtl_synth.core.continuous import (
    parse_ipa_with_markers,
    syllabify_continuous,
)

    tokens = parse_ipa_with_markers(
        ipa_str,
        pause_marker=pause_marker,
        pause_duration_ms=pause_duration_ms,
        vowel_duration_ms=vowel_duration_ms,
        consonant_durations=consonant_durations,
    )

    elements = syllabify_continuous(tokens)

    return chain_elements_to_anchors(
        elements,
        consonant_durations=consonant_durations,
    )


# ======================================================================
# CLI entry point for testing
# ======================================================================

if __name__ == '__main__':
    print("=== enveloppe.py — anchor system and timer test ===")
    print()

    from vtl_synth.core.constants import VOWEL_TARGETS, COEFCEN

    # Create synthetic anchors for "ba.ta.ka"
    anchors = [
        # Syllable 1: ba
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_o', t_ms=0.0,
        ),
        GestureAnchor(
            rho=1.06, theta=np.radians(50),
            label='C_b', t_ms=10.0,
        ),
        GestureAnchor(
            rho=1.0, theta=np.pi,
            label='V', t_ms=80.0,
        ),
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_e', t_ms=140.0,
        ),
        # Syllable 2: ta
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_o', t_ms=140.0,
        ),
        GestureAnchor(
            rho=1.10, theta=np.radians(7),
            label='C_t', t_ms=150.0,
        ),
        GestureAnchor(
            rho=1.0, theta=np.pi,
            label='V', t_ms=220.0,
        ),
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_e', t_ms=280.0,
        ),
        # Syllable 3: ka
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_o', t_ms=280.0,
        ),
        GestureAnchor(
            rho=1.20, theta=np.pi / 3,
            label='C_k', t_ms=290.0,
        ),
        GestureAnchor(
            rho=1.0, theta=np.pi,
            label='V', t_ms=360.0,
        ),
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_e', t_ms=420.0,
        ),
    ]

    # Create the TimedEnvelope
    te = TimedEnvelope(anchors)

    # Retrieve all the extensions
    ext = te.get_all_extensions()

    print(f"Total duration: {te.total_duration_ms:.1f} ms")
    print(f"Number of frames: {te.n_frames} ({TARGET_SR} Hz)")
    print(f"Number of timers: {len(te.timer.events)}")
    print()

    # Display the scheduled timers
    print("--- Scheduled timers ---")
    for ev in te.timer.events:
        print(f"  {ev.param_name:25s} | {ev.anchor_label:8s} | "
              f"t={ev.t_start_ms:6.1f}-{ev.t_end_ms:6.1f} ms | "
              f"target={ev.target_value:.2f} | prio={ev.priority}")
    print()

    # Display a summary of the trajectories
    print("--- Trajectories (summary) ---")
    for name, traj in ext.items():
        if name == 'timer_events' or name == 'glottis':
            continue
        if isinstance(traj, np.ndarray) and traj.ndim == 1:
            print(f"  {name:15s} : min={traj.min():.3f} "
                  f"max={traj.max():.3f} "
                  f"mean={traj.mean():.3f}")
    print()

    # VOT override test
    print("--- VOT override test for /t/: 60 ms ---")
    te2 = TimedEnvelope(anchors)
    te2.add_vot_override('t', 60.0)
    V2 = te2.compute_voicing()
    # Find the index of the /t/
    t_t = 150.0
    i_t = int(t_t * TARGET_SR / 1000.0)
    print(f"  V(t) around the /t/ (t={t_t}ms): "
          f"{V2[max(0,i_t-1):min(len(V2),i_t+8)]}")
    print()

    # Nasality test
    print("--- Nasality test for /m/ ---")
    # Add a nasal consonant
    nasal_anchors = [
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_o', t_ms=0.0,
        ),
        GestureAnchor(
            rho=0.9, theta=np.radians(200),
            label='C_m', t_ms=10.0,
        ),
        GestureAnchor(
            rho=1.0, theta=np.pi,
            label='V', t_ms=90.0,
        ),
        GestureAnchor(
            rho=COEFCEN * 1.0, theta=np.pi,
            label='V_e', t_ms=160.0,
        ),
    ]
    te3 = TimedEnvelope(nasal_anchors)
    VO3 = te3.compute_velum()
    print(f"  VO(t) for /ma/: min={VO3.min():.3f} "
          f"max={VO3.max():.3f}")

    print()
    print("=== Test completed ===")
