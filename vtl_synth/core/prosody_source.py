# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
prosody_source.py
=================
Derivation of the complementary variables from the segmental
and syllabic structure.

This module generates the time functions E(t), VO(t), V(t), f0(t)
that complement the Berthommier core output.  It implements
the syllabic envelope, nasality, voicing/VOT, and the F0 contour.

Fundamental principle (architecture specification):
  E(t) has no timing of its own.
  It is indexed by the events already produced by B(t).
  Coarticulation is inherited from the Berthommier envelope.

Source: rapport_vecteur_VTL_400Hz.pdf, §4
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Sequence

from vtl_synth.core.constants import (
    GLOTTIS_PRESETS,
    GLOTTIS_PARAM_NAMES,
    N_GLOTTIS_PARAMS,
    TARGET_SR,
    EFFORT_DEFAULTS,
    TAG_TO_VOICING,
    TAG_TO_VO_TARGET,
    TAG_TO_GLOTTIS_PRESET,
    SpeakerConfig,
    GlottisPreset,
)


# ==========================================================================
# Input data structures
# ==========================================================================

@dataclass
class Segment:
    """Phonemic segment with derived attributes.

    Attributes
    ----------
    key : str
        IPA key (e.g. 'a', 'b', 's', 'tS').
    kind : str
        'V' for vowel, 'C' for consonant.
    t_start : float
        Start time (ms).
    t_end : float
        End time (ms).
    duration_ms : float
        Duration (ms).
    voice : bool
        Voiced segment.
    nasal : bool
        Nasal segment.
    vot_ms : float
        Voice Onset Time (ms). 0 = voiced from release onward.
    f0_hz : float, optional
        Local F0 contour (Hz). If None, uses the global contour.
    stress : float
        Degree of stress [0, 1]. 0 = no stress.
    glottal_tag : str, optional
        Abstract glottal tag (e.g. 'modal', 'voiceless').
    velum_tag : str, optional
        Abstract velar tag (e.g. 'oral', 'nasal').
    """
    key: str
    kind: str  # 'V' or 'C'
    t_start: float = 0.0
    t_end: float = 0.0
    duration_ms: float = 100.0
    voice: bool = True
    nasal: bool = False
    vot_ms: float = 0.0
    f0_hz: Optional[float] = None
    stress: float = 0.0
    glottal_tag: str = 'modal'
    velum_tag: str = 'oral'

    @property
    def is_voiced(self) -> bool:
        return self.voice

    @property
    def is_nasal(self) -> bool:
        return self.nasal


@dataclass
class Syllable:
    """Syllabic structure.

    Attributes
    ----------
    onset : list[Segment]
        Onset consonants.
    nucleus : Segment
        Vocalic nucleus.
    coda : list[Segment]
        Coda consonants.
    stress : float
        Degree of stress [0, 1].
    t_start : float
        Start time (ms), computed automatically.
    t_end : float
        End time (ms), computed automatically.
    """
    onset: List[Segment] = field(default_factory=list)
    nucleus: Optional[Segment] = None
    coda: List[Segment] = field(default_factory=list)
    stress: float = 0.0
    t_start: float = 0.0
    t_end: float = 0.0

    @property
    def duration_ms(self) -> float:
        return self.t_end - self.t_start

    @property
    def all_segments(self) -> List[Segment]:
        segs = list(self.onset)
        if self.nucleus is not None:
            segs.append(self.nucleus)
        segs.extend(self.coda)
        return segs


# ==========================================================================
# Syllabic envelope
# ==========================================================================

def _syllabic_envelope(t: np.ndarray,
                       t_nucleus_start: float,
                       t_nucleus_end: float,
                       t_syl_start: float,
                       t_syl_end: float,
                       ramp_ms: float = 30.0) -> np.ndarray:
    """Compute the syllabic envelope E_syll(t).

    Template: rise toward the nucleus, plateau, fall in the margin.
    The envelope is in [0, 1] and is continuous.

    Parameters
    ----------
    t : np.ndarray
        Time vector (ms).
    t_nucleus_start, t_nucleus_end : float
        Nucleus boundaries (ms).
    t_syl_start, t_syl_end : float
        Syllable boundaries (ms).
    ramp_ms : float
        Attack/release ramp duration (ms).

    Returns
    -------
    np.ndarray
        Envelope E_syll(t) in [0, 1].
    """
    E = np.zeros_like(t, dtype=np.float64)

    # Rise phase (attack toward the nucleus)
    attack_mask = (t >= t_syl_start) & (t < t_nucleus_start)
    ramp_start = max(t_syl_start, t_nucleus_start - ramp_ms)
    in_ramp = (t >= ramp_start) & (t < t_nucleus_start)
    if np.any(in_ramp):
        alpha = (t[in_ramp] - ramp_start) / max(1.0, t_nucleus_start - ramp_start)
        alpha = np.clip(alpha, 0, 1)
        # Smooth (cosine) attack function
        E[in_ramp] = 0.5 * (1 - np.cos(np.pi * alpha))

    # Nucleus phase (plateau at 1)
    nucleus_mask = (t >= t_nucleus_start) & (t <= t_nucleus_end)
    E[nucleus_mask] = 1.0

    # Relaxation phase (fall after the nucleus)
    relax_mask = (t > t_nucleus_end) & (t <= t_syl_end)
    ramp_end = min(t_syl_end, t_nucleus_end + ramp_ms)
    in_relax = (t > t_nucleus_end) & (t <= ramp_end)
    if np.any(in_relax):
        alpha = (t[in_relax] - t_nucleus_end) / max(1.0, ramp_end - t_nucleus_end)
        alpha = np.clip(alpha, 0, 1)
        E[in_relax] = 0.5 * (1 + np.cos(np.pi * alpha))

    # Outside the syllable: E = 0 (already initialized)
    return E


# ==========================================================================
# Main class: ProsodySource
# ==========================================================================

