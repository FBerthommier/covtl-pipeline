# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
covtl-pipeline synthesis engine
===============================

Generation of 400 Hz VTL parameter vectors from text,
using the Berthommier articulatory model (COVTL) for place
and a tag-based extension engine for the complementary variables.

Architecture
-----------
    Text → segments + syllables
         → Berthommier core: (ρ,θ) → 15-19 tract params (place)
         → TimedEnvelope: anchors+FeatureTimer → E(t), VO(t), V(t), f0(t)
         → Assembler: B(t) + E(t) → .tract file at 400 Hz → VTL

VTL(t) = B(t) + E(t)

where B(t) = Berthommier output (tract place)
and   E(t) = complementary extension (voicing, nasality, f0, pressure, glottis)

E(t) has no timing of its own: it is indexed by the
events already produced by B(t).  Coarticulation and the envelope are inherited.
"""

from vtl_synth.core.constants import (
    CO_VTL,
    CONSONANT_TARGETS,
    VOWEL_TARGETS,
    ALL_PHONEME_KEYS,
    GLOTTIS_PRESETS,
    TRACT_PARAM_NAMES,
    GLOTTIS_PARAM_NAMES,
    TRACT_SR,
    TARGET_SR,
    N_TRACT_PARAMS,
    N_GLOTTIS_PARAMS,
    COEFCEN,
    TCONS_DEFAULT,
    TVOY_DEFAULT,
    C_BEFORE_PAUSE_HOLD_MS,
)
from vtl_synth.core.projection import (
    project_vtl_frame, g_target,
    superimpose as superimpose_covtl,
)
from vtl_synth.core.polar import (
    polar_arc as covtl_arc,
)
from vtl_synth.core.amplitude_envelope import (
    build_envelope_tokens,
    build_envelope_from_blocks,
)
from vtl_synth.core.enveloppe import (
    TimedEnvelope,
    FeatureTimer,
    FeatureEvent,
    envelope_from_anchors,
    anchors_to_segments,
    create_timed_envelope_from_segments,
    chain_elements_to_anchors,
    parse_to_anchors,
    VOT_BY_PLACE,
    NASAL_CARRYOVER_MS,
)
from vtl_synth.core.tag_system import (
    TagInterpreter,
    PHONETIC_TAGS,
    ARTICULATORY_TAGS,
    CONTROL_TAGS,
)
from vtl_synth.core.assemble_tract import AssembleTract
from vtl_synth.core.timers import (
    build_all_timers,
    build_extension_curves,
    TimerData,
    VoicingMark,
    NasalityMark,
    LateralMark,
)
from vtl_synth.core.text_to_tract import text_to_tract
from vtl_synth.core.build_phrase_tract import build_phrase_tract, build_batch_tract
from vtl_synth.core.synth import (
    is_vtl_available, get_vtl_error, get_vtl_info,
    synthesize_audio, synthesize_to_wav,
    render_tract_svg, render_tract_svgs,
    svgs_to_video, synthesize_video,
    get_tract_param_info, get_glottis_param_info,
    get_vowel_shape, get_glottis_shape,
    get_cross_sections, get_centerline, get_outlines,
    get_transfer_function, get_active_speaker,
)
from vtl_synth.core.phonemes import (
    ARPA_TO_SAMPA,
    SAMPA_VOWELS,
    SAMPA_CONSONANTS,
    arpa_to_sampa,
    is_sampa_token,
)
from vtl_synth.core.pipeline import (
    Pipeline,
    PipelineResult,
    apply_f0_declination,
    label_of,
)

__all__ = [
    # Constants
    'CO_VTL',
    'CONSONANT_TARGETS',
    'VOWEL_TARGETS',
    'ALL_PHONEME_KEYS',
    'GLOTTIS_PRESETS',
    'TRACT_PARAM_NAMES',
    'GLOTTIS_PARAM_NAMES',
    'TRACT_SR',
    'TARGET_SR',
    'N_TRACT_PARAMS',
    'N_GLOTTIS_PARAMS',
    'COEFCEN',
    'TCONS_DEFAULT',
    'TVOY_DEFAULT',
    'C_BEFORE_PAUSE_HOLD_MS',
    # Core model — polar / projection / trajectory
    'project_vtl_frame',
    'g_target',
    'superimpose_covtl',
    'covtl_arc',
    # COVTL amplitude envelope (token-based, from build_global_pval BlockInfo)
    'build_envelope_tokens',
    'build_envelope_from_blocks',
    # Timed envelopes (anchor-based, glottal source)
    'TimedEnvelope',
    'FeatureTimer',
    'FeatureEvent',
    'envelope_from_anchors',
    'anchors_to_segments',
    'create_timed_envelope_from_segments',
    'chain_elements_to_anchors',
    'parse_to_anchors',
    'VOT_BY_PLACE',
    'NASAL_CARRYOVER_MS',
    'TagInterpreter',
    'AssembleTract',
    # Timers (voicing, nasality, laterality)
    'build_all_timers',
    'build_extension_curves',
    'TimerData',
    'VoicingMark',
    'NasalityMark',
    'LateralMark',
    'text_to_tract',
    # Full phrase pipeline (Berthommier + source + orthogonal → 400 Hz)
    'build_phrase_tract',
    'build_batch_tract',
    # Synthesis (VTL)
    'is_vtl_available',
    'get_vtl_error',
    'get_vtl_info',
    'synthesize_audio',
    'synthesize_to_wav',
    'render_tract_svg',
    'render_tract_svgs',
    'svgs_to_video',
    'synthesize_video',
    'get_tract_param_info',
    'get_glottis_param_info',
    'get_vowel_shape',
    'get_glottis_shape',
    'get_cross_sections',
    'get_centerline',
    'get_outlines',
    'get_transfer_function',
    'get_active_speaker',
    # Tag types
    'PHONETIC_TAGS',
    'ARTICULATORY_TAGS',
    'CONTROL_TAGS',
    # Phoneme tables (ARPAbet/SAMPA gateway)
    'ARPA_TO_SAMPA',
    'SAMPA_VOWELS',
    'SAMPA_CONSONANTS',
    'arpa_to_sampa',
    'is_sampa_token',
    # High-level orchestration
    'Pipeline',
    'PipelineResult',
    'apply_f0_declination',
    'label_of',
]
