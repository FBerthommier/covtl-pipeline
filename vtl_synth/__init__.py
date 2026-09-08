# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
vtl_synth
=========
Articulatory synthesis from text: Berthommier COVTL model coupled
with the VocalTractLab 2.4 synthesizer (JD3 speaker).

Layout (aligned on the vtl-pipeline reference repository)::

    vtl_synth/core     synthesis engine (former ``pipeline`` package,
                       26 modules) + the Pipeline orchestrator
    vtl_synth/cli      ``vtl-synth`` command line
    vtl_synth/video    sagittal frame rendering + MP4 encoding
    vtl_synth/vtl      VocalTractLab API facade (vocaltractlab-cython)
    vtl_synth/utils    g2p (CMUdict -> engine SAMPA) and helpers
    vtl_synth/data     JD3.speaker (package data)

Quick start::

    from vtl_synth import Pipeline
    result = Pipeline().run("this is easy for us", output_dir="./out")
"""

from __future__ import annotations

__version__ = '1.0.2'

from vtl_synth.core.pipeline import Pipeline, PipelineResult
from vtl_synth.core.build_phrase_tract import (
    build_phrase_tract,
    build_batch_tract,
)
from vtl_synth.core.text_to_tract import text_to_tract
from vtl_synth.core.synth import (
    is_vtl_available,
    get_vtl_error,
    get_vtl_info,
    synthesize_audio,
    synthesize_to_wav,
)
from vtl_synth.core.constants import (
    TRACT_PARAM_NAMES,
    GLOTTIS_PARAM_NAMES,
    TRACT_SR,
    N_TRACT_PARAMS,
    N_GLOTTIS_PARAMS,
)

__all__ = [
    '__version__',
    # orchestration
    'Pipeline',
    'PipelineResult',
    # engine entry points (full API in vtl_synth.core)
    'build_phrase_tract',
    'build_batch_tract',
    'text_to_tract',
    # VTL synthesis
    'is_vtl_available',
    'get_vtl_error',
    'get_vtl_info',
    'synthesize_audio',
    'synthesize_to_wav',
    # constants
    'TRACT_PARAM_NAMES',
    'GLOTTIS_PARAM_NAMES',
    'TRACT_SR',
    'N_TRACT_PARAMS',
    'N_GLOTTIS_PARAMS',
]
