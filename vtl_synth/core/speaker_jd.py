# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
speaker_jd.py
=============
Parsing of the VTL speaker file (XML) and extraction of the source
(glottis) parameters and of the orthogonal (non-COVTL tract) parameters.

This module is the **side branch** of the Berthommier pipeline:
  - Main branch : (rho, theta) -> COVTL -> 15 tract params
  - Side branch : Speaker JD -> source (11 glottis params)
                                         -> orthogonal (VS, VO, TRX, TRY, contextual TS3)

The extracted values are faithful to the JD3.speaker file and
can be injected into ProsodySource and AssembleTract.

Source: JD3.speaker (VTL XML speaker file)
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from vtl_synth.core.constants import (
    GLOTTIS_PARAM_NAMES,
    TRACT_PARAM_NAMES,
    N_TRACT_PARAMS,
    N_GLOTTIS_PARAMS,
    GlottisPreset,
    SpeakerConfig,
    GLOTTIS_PRESETS,
    TAG_TO_GLOTTIS_PRESET,
)


# ==========================================================================
# Default path of the speaker file
# ==========================================================================

# Package root (vtl_synth/); the speaker file ships as package data
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SPEAKER_FILE = os.path.join(
    _PKG_ROOT, 'data', 'vtl_binaries', 'JD3.speaker')


# ==========================================================================
# Data structures
# ==========================================================================

@dataclass
class TractShape:
    """Full tract target (19 params) for a phoneme/context.

    Attributes
    ----------
    name : str
        Name of the shape (e.g. 'a', 'tt-alveolar-closure(i)').
    params : dict[str, float]
        Values of the 19 tract parameters.
    """
    name: str
    params: Dict[str, float] = field(default_factory=dict)

    def to_vector(self, order: Tuple[str, ...] = TRACT_PARAM_NAMES) -> np.ndarray:
        """Returns the 19-param vector in VTL order.

        Parameters
        ----------
        order : tuple[str, ...]
            Parameter order (default: TRACT_PARAM_NAMES).

        Returns
        -------
        np.ndarray, shape (19,)
        """
        return np.array([self.params.get(p, 0.0) for p in order], dtype=np.float64)

    def get_orthogonal(self) -> Dict[str, float]:
        """Returns only the orthogonal parameters (outside COVTL).

        The orthogonal parameters are: VS, VO, TRX, TRY.
        TS3 is also extracted because it has contextual values
        in the JD file (fricatives: 1.0, laterals: -1.0).

        Returns
        -------
        dict[str, float]
        """
        ortho = {}
        for p in ('VS', 'VO', 'TRX', 'TRY', 'TS3'):
            if p in self.params:
                ortho[p] = self.params[p]
        return ortho


@dataclass
class GlottisShape:
    """Glottal configuration extracted from the speaker file.

    Attributes
    ----------
    name : str
        Name of the shape (e.g. 'modal', 'voiceless-fricative').
    model_type : str
        Type of glottal model ('Geometric glottis', etc.).
    params : dict[str, float]
        Values of the glottal control parameters.
    """
    name: str
    model_type: str = 'Geometric glottis'
    params: Dict[str, float] = field(default_factory=dict)

    def to_vector(self, order: Tuple[str, ...] = GLOTTIS_PARAM_NAMES) -> np.ndarray:
        """Returns the 11-param glottis vector in VTL order.

        Parameters
        ----------
        order : tuple[str, ...]
            Parameter order (default: GLOTTIS_PARAM_NAMES).

        Returns
        -------
        np.ndarray, shape (11,)
        """
        return np.array([self.params.get(p, 0.0) for p in order], dtype=np.float64)

    def to_glottis_preset(self) -> GlottisPreset:
        """Converts to a GlottisPreset compatible with the pipeline.

        Mapping of VTL names to GlottisPreset attributes:
          F0 -> f0, PR -> pressure (in dPa, native value),
          XB -> x_bottom, XT -> x_top, CA -> chink_area,
          PL -> lag, RA -> rel_amp, DP -> double_pulsing,
          PS -> pulse_skewness, FL -> f0_flutter, AS -> aspiration_strength

        Returns
        -------
        GlottisPreset
        """
        VTL_TO_PRESET = {
            'F0': 'f0',
            'PR': 'pressure',
            'XB': 'x_bottom',
            'XT': 'x_top',
            'CA': 'chink_area',
            'PL': 'lag',
            'RA': 'rel_amp',
            'DP': 'double_pulsing',
            'PS': 'pulse_skewness',
            'FL': 'f0_flutter',
            'AS': 'aspiration_strength',
        }
        kwargs = {'name': self.name}
        for vtl_name, preset_attr in VTL_TO_PRESET.items():
            if vtl_name in self.params:
                kwargs[preset_attr] = self.params[vtl_name]
        return GlottisPreset(**kwargs)


@dataclass
class SpeakerData:
    """Complete data extracted from a VTL speaker file.

    Attributes
    ----------
    speaker_file : str
        Path of the speaker file.
       tract_shapes : dict[str, TractShape]
        All tract shapes (vowels, contextual consonants).
       glottis_shapes : dict[str, GlottisShape]
        All glottal shapes (by model).
       selected_glottis_model : str
        Name of the selected glottal model.
    param_defs : dict[str, dict]
        Definitions of the tract parameters (min, max, neutral).
    glottis_param_defs : dict[str, dict]
        Definitions of the glottal parameters.
    glottis_static_params : dict[str, dict]
        Static parameters of the glottal model.
    """
    speaker_file: str
    tract_shapes: Dict[str, TractShape] = field(default_factory=dict)
    glottis_shapes: Dict[str, GlottisShape] = field(default_factory=dict)
    selected_glottis_model: str = ''
    param_defs: Dict[str, dict] = field(default_factory=dict)
    glottis_param_defs: Dict[str, dict] = field(default_factory=dict)
    glottis_static_params: Dict[str, dict] = field(default_factory=dict)


# ==========================================================================
# Parsing XML
# ==========================================================================

def parse_speaker_file(speaker_file: str = DEFAULT_SPEAKER_FILE) -> SpeakerData:
    """Parses a VTL speaker file (XML) and extracts all the data.

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    SpeakerData
        Complete speaker data.
    """
    if not os.path.exists(speaker_file):
        raise FileNotFoundError(f"Speaker file not found: {speaker_file}")

    tree = ET.parse(speaker_file)
    root = tree.getroot()

    data = SpeakerData(speaker_file=speaker_file)

    # --- Tract shapes ---
    vt_model = root.find('vocal_tract_model')
    if vt_model is not None:
        _parse_tract_anatomy(vt_model, data)
        _parse_tract_shapes(vt_model, data)

    # --- Glottis models ---
    glottis_models = root.find('glottis_models')
    if glottis_models is not None:
        _parse_glottis_models(glottis_models, data)

    return data


def _parse_tract_anatomy(vt_model: ET.Element, data: SpeakerData) -> None:
    """Extracts the tract parameter definitions.

    In the JD file, the <param> elements are inside <anatomy>.
    """
    anatomy = vt_model.find('anatomy')
    search_root = anatomy if anatomy is not None else vt_model
    for param in search_root.findall('param'):
        name = param.get('name', '')
        data.param_defs[name] = {
            'index': int(param.get('index', -1)),
            'description': param.get('description', ''),
            'unit': param.get('unit', ''),
            'min': float(param.get('min', 0.0)),
            'max': float(param.get('max', 0.0)),
            'neutral': float(param.get('neutral', 0.0)),
        }


def _parse_tract_shapes(vt_model: ET.Element, data: SpeakerData) -> None:
    """Extracts all tract shapes."""
    shapes_elem = vt_model.find('shapes')
    if shapes_elem is None:
        return

    for shape_elem in shapes_elem.findall('shape'):
        name = shape_elem.get('name', '')
        params = {}
        for param_elem in shape_elem.findall('param'):
            pname = param_elem.get('name', '')
            pvalue = float(param_elem.get('value', 0.0))
            params[pname] = pvalue
        data.tract_shapes[name] = TractShape(name=name, params=params)


def _parse_glottis_models(glottis_models: ET.Element, data: SpeakerData) -> None:
    """Extracts all glottal models and shapes."""
    for model in glottis_models.findall('glottis_model'):
        model_type = model.get('type', '')
        is_selected = model.get('selected', '0') == '1'

        if is_selected:
            data.selected_glottis_model = model_type

        # Static parameters
        static_elem = model.find('static_params')
        if static_elem is not None:
            for param in static_elem.findall('param'):
                name = param.get('name', '')
                data.glottis_static_params[name] = {
                    'index': int(param.get('index', -1)),
                    'description': param.get('description', ''),
                    'unit': param.get('unit', ''),
                    'min': float(param.get('min', 0.0)),
                    'max': float(param.get('max', 0.0)),
                    'neutral': float(param.get('neutral', 0.0)),
                }

        # Control parameters
        control_elem = model.find('control_params')
        if control_elem is not None:
            for param in control_elem.findall('param'):
                name = param.get('name', '')
                data.glottis_param_defs[name] = {
                    'index': int(param.get('index', -1)),
                    'description': param.get('description', ''),
                    'unit': param.get('unit', ''),
                    'min': float(param.get('min', 0.0)),
                    'max': float(param.get('max', 0.0)),
                    'neutral': float(param.get('neutral', 0.0)),
                }

        # Glottal shapes
        shapes_elem = model.find('shapes')
        if shapes_elem is None:
            continue

        for shape_elem in shapes_elem.findall('shape'):
            name = shape_elem.get('name', '')
            params = {}
            for cp in shape_elem.findall('control_param'):
                cpname = cp.get('name', '')
                cpvalue = float(cp.get('value', 0.0))
                params[cpname] = cpvalue

            key = f"{model_type}:{name}" if not is_selected else name
            data.glottis_shapes[key] = GlottisShape(
                name=name,
                model_type=model_type,
                params=params,
            )


# ==========================================================================
# Extraction for the source branch (glottis)
# ==========================================================================

def get_jd_glottis_presets(
    speaker_file: str = DEFAULT_SPEAKER_FILE,
) -> Dict[str, GlottisPreset]:
    """Extracts the JD glottal presets from the speaker file.

    Returns a dictionary compatible with the pipeline's GLOTTIS_PRESETS,
    with the real values of the JD speaker.

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    dict[str, GlottisPreset]
        Glottal presets extracted from the JD file.
        Keys: 'default', 'stop', 'pressed', 'modal', 'breathy', 'h',
               'whisper', 'hoarse', 'voiced-fricative', 'voiced-plosive',
               'voiceless-fricative', 'voiceless-plosive', 'hoarse2'.
    """
    data = parse_speaker_file(speaker_file)
    presets = {}

    for key, shape in data.glottis_shapes.items():
        # Only take shapes from the selected model
        if shape.model_type != data.selected_glottis_model:
            continue
        presets[shape.name] = shape.to_glottis_preset()

    return presets


# ==========================================================================
# Extraction for the orthogonal branch (non-COVTL tract)
# ==========================================================================

def get_orthogonal_targets(
    speaker_file: str = DEFAULT_SPEAKER_FILE,
) -> Dict[str, Dict[str, float]]:
    """Extracts the orthogonal parameters per tract shape.

    For each tract shape in the JD file, returns the values
    of the parameters not handled by COVTL:
      - VS (velum shape)
      - VO (velum opening)
      - TRX, TRY (tongue root)
      - TS3 (posterior sides — contextual variable)

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    dict[str, dict[str, float]]
        {shape_name: {param: value, ...}, ...}
    """
    data = parse_speaker_file(speaker_file)
    ortho = {}

    for name, shape in data.tract_shapes.items():
        ortho[name] = shape.get_orthogonal()

    return ortho


def get_ts3_context_map(
    speaker_file: str = DEFAULT_SPEAKER_FILE,
) -> Dict[str, float]:
    """Builds the TS3 contextual map from the JD shapes.

    In the JD file, TS3 varies with the articulatory context:
      - Fricatives (dental, alveolar, postalveolar, palatal): TS3 ~ 1.0
      - Laterals (alveolar-lateral, postalveolar-lateral): TS3 ~ -1.0
      - Stops and vowels: TS3 ~ 0.0

    This map is used by the orthogonal branch to override the TS3
    value of the COVTL core depending on the consonantal context.

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    dict[str, float]
        {context_pattern: ts3_value, ...}
        The keys are patterns like 'fricative', 'lateral', 'closure', etc.
    """
    ortho = get_orthogonal_targets(speaker_file)
    ts3_map = {}

    for shape_name, params in ortho.items():
        if 'TS3' in params:
            ts3_map[shape_name] = params['TS3']

    return ts3_map


def get_vowel_orthogonal_defaults(
    speaker_file: str = DEFAULT_SPEAKER_FILE,
) -> Dict[str, Dict[str, float]]:
    """Extracts the orthogonal values per vowel from JD.

    Returns a dictionary {vowel: {VS, VO, TRX, TRY}}
    for the pure vowels of the JD file.

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    dict[str, dict[str, float]]
    """
    data = parse_speaker_file(speaker_file)
    vowel_ortho = {}

    # Pure vowels (without contextual suffix)
    pure_vowels = {'a', 'e', 'i', 'o', 'u', 'E:', '2', 'y', 'I', 'E', 'O', 'U', '9', 'Y', '@', '6'}

    for name, shape in data.tract_shapes.items():
        if name in pure_vowels:
            ortho = shape.get_orthogonal()
            # Remove TS3 from vowel defaults (handled by COVTL)
            ortho.pop('TS3', None)
            vowel_ortho[name] = ortho

    return vowel_ortho


def get_consonant_orthogonal_targets(
    speaker_file: str = DEFAULT_SPEAKER_FILE,
) -> Dict[str, Dict[str, float]]:
    """Extracts the orthogonal targets per consonantal context.

    Returns a dictionary structured by consonant type and
    vowel context: {consonant_type: {vowel: {param: value}}}.

    Parameters
    ----------
    speaker_file : str
        Path to the .speaker file.

    Returns
    -------
    dict[str, dict[str, dict[str, float]]]
    """
    data = parse_speaker_file(speaker_file)
    consonant_ortho = {}

    # Name patterns of contextual consonants
    # Format: 'll-labial-closure(a)', 'tt-alveolar-fricative(i)', etc.
    import re
    pattern = re.compile(r'^([a-z]+(?:-[a-z]+)*?)\(([aieuoyE2@69OIUY])\)$')

    for name, shape in data.tract_shapes.items():
        if name in {'a', 'e', 'i', 'o', 'u', 'E:', '2', 'y', 'I', 'E',
                    'O', 'U', '9', 'Y', '@', '6'}:
            continue
        if '-raw' in name:
            continue

        m = pattern.match(name)
        if m:
            cons_type = m.group(1)  # e.g. 'tt-alveolar-fricative'
            vowel_ctx = m.group(2)  # e.g. 'a'
            ortho = shape.get_orthogonal()

            if cons_type not in consonant_ortho:
                consonant_ortho[cons_type] = {}
            consonant_ortho[cons_type][vowel_ctx] = ortho

    return consonant_ortho


# ==========================================================================
# VTL synthesis interface (for alignment with the GitHub)
# ==========================================================================



# ==========================================================================
# Summary / debug
# ==========================================================================

def print_speaker_summary(speaker_file: str = DEFAULT_SPEAKER_FILE) -> None:
    """Prints a summary of the speaker file (debug/inspection)."""
    data = parse_speaker_file(speaker_file)

    print(f"Speaker file: {data.speaker_file}")
    print(f"Tract shapes: {len(data.tract_shapes)}")
    print(f"Selected glottis model: {data.selected_glottis_model}")
    print(f"Glottis shapes: {len(data.glottis_shapes)}")
    print(f"Defined tract parameters: {len(data.param_defs)}")
    print(f"Glottis control parameters: {len(data.glottis_param_defs)}")
    print(f"Static glottis parameters: {len(data.glottis_static_params)}")
    print()

    # Tract shapes
    print("=== Tract shapes ===")
    for name in sorted(data.tract_shapes.keys()):
        shape = data.tract_shapes[name]
        ortho = shape.get_orthogonal()
        ts3 = ortho.get('TS3', '—')
        vs = ortho.get('VS', '—')
        vo = ortho.get('VO', '—')
        print(f"  {name:40s}  VS={vs:>7}  VO={vo:>7}  TS3={ts3:>7}")

    print()

    # Glottal shapes (selected model)
    print(f"=== Glottal shapes ({data.selected_glottis_model}) ===")
    for key in sorted(data.glottis_shapes.keys()):
        shape = data.glottis_shapes[key]
        if shape.model_type != data.selected_glottis_model:
            continue
        f0 = shape.params.get('F0', 0)
        pr = shape.params.get('PR', 0)
        ra = shape.params.get('RA', 0)
        xb = shape.params.get('XB', 0)
        xt = shape.params.get('XT', 0)
        ca = shape.params.get('CA', 0)
        print(f"  {shape.name:25s}  F0={f0:>8.1f}  PR={pr:>8.1f}  "
              f"RA={ra:>6.3f}  XB={xb:>7.4f}  XT={xt:>7.4f}  CA={ca:>7.4f}")


if __name__ == '__main__':
    print_speaker_summary()
