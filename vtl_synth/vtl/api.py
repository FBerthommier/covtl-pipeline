# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
api.py
======
VocalTractLab API facade.

The actual binding lives in ``vtl_synth.core.synth`` (single entry
point to Peter Birkholz's VocalTractLab SDK via Paul Krug's
``vocaltractlab-cython`` wrapper).  This module re-exports it under
the ``vtl_synth.vtl`` namespace to mirror the layout of the
vtl-pipeline reference repository:

    from vtl_synth.vtl.api import synthesize_to_wav, get_vtl_info

Unlike the reference repository, which loads a native
``libVocalTractLabApi`` shared library by ctypes, the VTL engine here
is provided entirely by the ``vocaltractlab-cython`` wheel (DLL
included); the only bundled binary data is the speaker file
``vtl_synth/data/vtl_binaries/JD3.speaker``.
"""

from __future__ import annotations

from vtl_synth.core.synth import (
    is_vtl_available,
    get_vtl_error,
    get_vtl_info,
    get_active_speaker,
    synthesize_audio,
    synthesize_to_wav,
    render_tract_svg,
    render_tract_svgs,
    svgs_to_video,
    synthesize_video,
    get_tract_param_info,
    get_glottis_param_info,
    get_vowel_shape,
    get_glottis_shape,
    get_cross_sections,
    get_centerline,
    get_outlines,
    get_transfer_function,
)

__all__ = [
    'is_vtl_available',
    'get_vtl_error',
    'get_vtl_info',
    'get_active_speaker',
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
]
