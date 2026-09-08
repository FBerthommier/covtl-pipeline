# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
tag_system.py
===============
Phonetic, articulatory, and control tag system.

Tags are the interface between the Berthommier TTS and VTL.
They come in three levels:

  A. Phonetic tags (property of the phoneme)
     <voicing=voiced>, <nasal=true>, <aspiration=true>

  B. Articulatory tags (VTL configuration)
     <glottal_shape=modal>, <velum=closed>

  C. Control tags (direct value or degree)
     <glottal_opening=0.65>, <pressure=0.8>, <f0=135>

Key principle (§6 of the specification):
  A tag should NOT necessarily give a VTL value.
  <glottal=voiceless> is preferable to <VO=0.42>.
  A lookup table determines the VTL configuration.
  This makes it possible to change speakers without rewriting the TTS.

  phonetics → abstract tag → speaker configuration → VTL parameters

JD2/JD3 compatibility (§7):
  <glottal=voiceless> remains invariant.
  (VO,VS,TS3)_JD2 ≠ (VO,VS,TS3)_JD3.
  The functional structure is transferred, the values are recalibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from vtl_synth.core.prosody_source import Segment
from vtl_synth.core.constants import (
    TAG_TO_VOICING,
    TAG_TO_VO_TARGET,
    TAG_TO_GLOTTIS_PRESET,
    CONSONANT_TARGETS,
    VOWEL_TARGETS,
)


# ==========================================================================
# Tag types
# ==========================================================================

PHONETIC_TAGS = {
    'voicing',      # voiced | voiceless | breathy | creaky
    'nasal',        # true | false
    'continuant',   # true | false (fricative vs stop)
    'strident',     # true | false
    'aspiration',   # true | false
    'labial',       # true | false
    'coronal',      # true | false
    'dorsal',       # true | false
    'place',        # labial | alveolar | palatal | velar | uvular
    'manner',       # stop | fricative | nasal | lateral | approximant
    'rounding',     # true | false
    'high',         # true | false
    'low',          # true | false
    'front',        # true | false
    'back',         # true | false
    'tense',        # true | false
}

ARTICULATORY_TAGS = {
    'glottal_shape',  # modal | voiceless | breathy | creaky | whisper
    'velum',          # open | closed | partial
    'tongue_mode',    # neutral | raised | lowered
}

CONTROL_TAGS = {
    'glottal_opening',      # 0.0 - 1.0
    'pressure',             # 200 - 2000 dPa
    'f0',                   # 50 - 500 Hz
    'aspiration_strength',  # 0 - 30 dB
    'chink_area',           # 0 - 50
}


# ==========================================================================
# Default tags for phonemes
# ==========================================================================

# Format: IPA key → dict of phonetic tags
DEFAULT_PHONEME_TAGS: Dict[str, Dict[str, Any]] = {
    # --- Vowels ---
    'a':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'central', 'manner': 'vowel', 'rounding': False,
           'low': True, 'back': True, 'tense': True},
    'i':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': False,
           'high': True, 'front': True, 'tense': True},
    'u':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'back', 'manner': 'vowel', 'rounding': True,
           'high': True, 'back': True, 'tense': True},
    'e':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': False,
           'high': False, 'front': True, 'tense': True},
    'E':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': False,
           'high': False, 'front': True, 'tense': False},
    'o':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'back', 'manner': 'vowel', 'rounding': True,
           'high': False, 'back': True, 'tense': True},
    'O':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'back', 'manner': 'vowel', 'rounding': True,
           'high': False, 'back': True, 'tense': False},
    'y':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': True,
           'high': True, 'front': True, 'tense': True},
    '@':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'central', 'manner': 'vowel', 'rounding': False,
           'high': False, 'back': False, 'tense': False},
    # --- Nasals ---
    'm':  {'voicing': 'voiced', 'nasal': True, 'continuant': False,
           'place': 'labial', 'manner': 'nasal', 'labial': True},
    'n':  {'voicing': 'voiced', 'nasal': True, 'continuant': False,
           'place': 'alveolar', 'manner': 'nasal', 'coronal': True},
    'J':  {'voicing': 'voiced', 'nasal': True, 'continuant': False,
           'place': 'palatal', 'manner': 'nasal', 'palatal': True},
    'N':  {'voicing': 'voiced', 'nasal': True, 'continuant': False,
           'place': 'velar', 'manner': 'nasal', 'dorsal': True},
    # --- Voiced stops ---
    'b':  {'voicing': 'voiced', 'nasal': False, 'continuant': False,
           'place': 'labial', 'manner': 'stop', 'labial': True},
    'd':  {'voicing': 'voiced', 'nasal': False, 'continuant': False,
           'place': 'alveolar', 'manner': 'stop', 'coronal': True},
    'g':  {'voicing': 'voiced', 'nasal': False, 'continuant': False,
           'place': 'velar', 'manner': 'stop', 'dorsal': True},
    # --- Voiceless stops ---
    'p':  {'voicing': 'voiceless', 'nasal': False, 'continuant': False,
           'place': 'labial', 'manner': 'stop', 'labial': True,
           'aspiration': True},
    't':  {'voicing': 'voiceless', 'nasal': False, 'continuant': False,
           'place': 'alveolar', 'manner': 'stop', 'coronal': True,
           'aspiration': True},
    'k':  {'voicing': 'voiceless', 'nasal': False, 'continuant': False,
           'place': 'velar', 'manner': 'stop', 'dorsal': True,
           'aspiration': True},
    # --- Fricatives ---
    'f':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'labiodental', 'manner': 'fricative', 'labial': True,
           'strident': False},
    'v':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'labiodental', 'manner': 'fricative', 'labial': True,
           'strident': False},
    's':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'alveolar', 'manner': 'fricative', 'coronal': True,
           'strident': True},
    'z':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'alveolar', 'manner': 'fricative', 'coronal': True,
           'strident': True},
    'S':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'postalveolar', 'manner': 'fricative', 'coronal': True,
           'strident': True, 'rounding': True},
    'Z':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'postalveolar', 'manner': 'fricative', 'coronal': True,
           'strident': True, 'rounding': True},
    'T':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'dental', 'manner': 'fricative', 'coronal': True,
           'strident': False},
    'D':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'dental', 'manner': 'fricative', 'coronal': True,
           'strident': False},
    'X':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'uvular', 'manner': 'fricative', 'dorsal': True,
           'strident': False},
    'R':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'uvular', 'manner': 'fricative', 'dorsal': True,
           'strident': False},
    # --- Affricates ---
    'tS': {'voicing': 'voiceless', 'nasal': False, 'continuant': False,
           'place': 'postalveolar', 'manner': 'affricate', 'coronal': True,
           'strident': True, 'rounding': True},
    'dZ': {'voicing': 'voiced', 'nasal': False, 'continuant': False,
           'place': 'postalveolar', 'manner': 'affricate', 'coronal': True,
           'strident': True, 'rounding': True},
    # --- Approximants and laterals ---
    'l':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'alveolar', 'manner': 'lateral', 'coronal': True},
    'L':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'alveolar', 'manner': 'lateral', 'coronal': True},
    'j':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'palatal', 'manner': 'approximant'},
    'C':  {'voicing': 'voiceless', 'nasal': False, 'continuant': True,
           'place': 'palatal', 'manner': 'fricative'},
    'w':  {'voicing': 'voiced', 'nasal': False, 'continuant': True,
           'place': 'labial', 'manner': 'approximant', 'labial': True,
           'rounding': True, 'back': True, 'high': True},
    # --- French nasal vowels ---
    '6':  {'voicing': 'voiced', 'nasal': True, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': True,
           'tense': True},
    '9':  {'voicing': 'voiced', 'nasal': True, 'continuant': True,
           'place': 'central', 'manner': 'vowel', 'rounding': True,
           'tense': True},
    '2':  {'voicing': 'voiced', 'nasal': True, 'continuant': True,
           'place': 'front', 'manner': 'vowel', 'rounding': True,
           'high': True, 'tense': True},
}


# ==========================================================================
# Tag → glottal and velum mapping
# ==========================================================================

# Derivation of the glottal preset from phonetic traits
def _derive_glottal_tag(tags: Dict[str, Any]) -> str:
    """Derives the glottal tag from phonetic traits."""
    voicing = tags.get('voicing', 'voiced')
    aspiration = tags.get('aspiration', False)
    manner = tags.get('manner', '')

    if voicing == 'voiceless':
        if aspiration or manner == 'stop':
            return 'aspirated'
        if manner == 'fricative' or manner == 'affricate':
            return 'voiceless_fricative'
        return 'voiceless'
    elif voicing == 'breathy':
        return 'breathy'
    elif voicing == 'creaky':
        return 'creaky'
    elif voicing == 'whisper':
        return 'whisper'
    return 'modal'


def _derive_velum_tag(tags: Dict[str, Any]) -> str:
    """Derives the velum tag from phonetic traits."""
    if tags.get('nasal', False) or tags.get('manner') == 'nasal':
        return 'nasal'
    return 'oral'


def _derive_vot_ms(tags: Dict[str, Any]) -> float:
    """Derives the VOT (ms) from phonetic traits."""
    voicing = tags.get('voicing', 'voiced')
    if voicing == 'voiceless':
        manner = tags.get('manner', '')
        place = tags.get('place', '')
        if manner == 'stop':
            # VOT varies by place of articulation
            if place == 'labial':
                return 20.0
            elif place == 'alveolar':
                return 40.0
            elif place == 'velar':
                return 50.0
            else:
                return 30.0
        return 0.0  # fricatives, affricates
    return 0.0  # voiced


# ==========================================================================
# Tag interpreter
# ==========================================================================

class TagInterpreter:
    """Tag interpreter: phonetic traits → segment attributes.

    This is the core of the extension engine. It takes as input
    segments with their phonetic traits (level-A tags)
    and produces the concrete attributes used by ProsodySource:
      - glottal_tag (level B)
      - velum_tag (level B)
      - vot_ms
      - voice, nasal (derived booleans)

    Level C (direct control) makes it possible to override
    the automatic derivations.

    Parameters
    ----------
    tag_overrides : dict, optional
        Manual overrides per IPA key.
        Format: {'b': {'glottal_opening': 0.5}, ...}
    speaker_vtl_mapping : dict, optional
        Speaker-specific mapping for abstract tags.
        Format: {'voiceless': {'VO': 1.0, 'VS': 0.0, 'TS3': 0.0}, ...}
    """

    def __init__(
        self,
        tag_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        speaker_vtl_mapping: Optional[Dict[str, Dict[str, float]]] = None,
    ):
        self.tag_overrides = tag_overrides or {}
        self.speaker_vtl_mapping = speaker_vtl_mapping or {}

    def apply(self, segment: Segment) -> Segment:
        """Applies the tags to a segment, modifying it in place.

        1. Gets the default phonetic tags for this phoneme.
        2. Applies the manual overrides (level C).
        3. Derives the articulatory tags (level B).
        4. Fills in the segment attributes.

        Parameters
        ----------
        segment : Segment
            Segment to annotate.

        Returns
        -------
        Segment
            The same segment, modified in place.
        """
        # 1. Default tags
        tags = DEFAULT_PHONEME_TAGS.get(segment.key, {}).copy()

        # 2. Manual overrides (level C)
        if segment.key in self.tag_overrides:
            tags.update(self.tag_overrides[segment.key])

        # 3. Derivation of the articulatory tags (level B)
        segment.glottal_tag = _derive_glottal_tag(tags)
        segment.velum_tag = _derive_velum_tag(tags)
        segment.vot_ms = _derive_vot_ms(tags)

        # 4. Derived booleans
        segment.voice = tags.get('voicing', 'voiced') != 'voiceless'
        segment.nasal = tags.get('nasal', False) or tags.get('manner') == 'nasal'

        return segment

    def apply_all(self, segments: List[Segment]) -> List[Segment]:
        """Applies the tags to all segments.

        Parameters
        ----------
        segments : list[Segment]
            List of segments to annotate.

        Returns
        -------
        list[Segment]
            Annotated segments.
        """
        return [self.apply(seg) for seg in segments]
