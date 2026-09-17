# -*- coding: utf-8 -*-
"""
constants.py — généré par adapt_speaker.py (covtl-speaker)
=========================================================
Speaker : s2

Ne pas éditer à la main : régénérer via
    python adapt_speaker.py s2.speaker

Toutes les valeurs dépendantes du speaker sont dérivées du fichier
.speaker par la procédure formalisée (procedure_adaptation.md).
Les sections indépendantes du speaker (enveloppe, timing, tags, presets
génériques) sont recopiées de la référence SynthVTL24b.

Journal de la dérivation COVTL :
#   LD  : c1=c0=0.275277 (fermeture min=0 à ρ=1) ; c1 x0.8 = 0.220222
#   TTY : c0=(0.8−(-1.2986))/2.3=0.912435 ; c1=-1.2986+c0+0.15=-0.236165 (contact/occlusion apicale)
#   TCY : c1 -1.805600 → -1.555600 (occlusion vélaire /g,k/)
#   TTY : c0/c2 natifs conservés, c1 += 0.15 (règle JD3 (0.80−Va)/2.3 non transférée, correctif bunching)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


# =============================================================================
# Sampling frequencies
# =============================================================================

TRACT_SR: int = 400
TARGET_SR: int = 100
AUDIO_SR: int = 44100

# =============================================================================
# Envelope parameters (COVTL token-based amplitude envelope)
# =============================================================================

FS: int = 10000
T_S: float = 0.01

TOKEN_AMPL_MIN: Dict[str, float] = {
    'V': 1.0, 'N': 0.3, 'L': 0.3, 'R': 0.3, 'r': 0.3, 'y': 0.5,
}

_PLOSIVE_TOKENS: frozenset = frozenset({'C'})

# =============================================================================
# Dimensions of the VTL vector
# =============================================================================

N_TRACT_PARAMS: int = 19
N_GLOTTIS_PARAMS: int = 11

TRACT_PARAM_NAMES: Tuple[str, ...] = (
    'HX', 'HY', 'JX', 'JA', 'LP', 'LD', 'VS', 'VO',
    'TCX', 'TCY', 'TTX', 'TTY', 'TBX', 'TBY', 'TRX', 'TRY',
    'TS1', 'TS2', 'TS3',
)

IDX_VS = 6
IDX_VO = 7
IDX_TS3 = 18

COVTL_PARAMS: Tuple[str, ...] = (
    'HX', 'HY', 'JX', 'JA', 'LP', 'LD',
    'TCX', 'TCY', 'TTX', 'TTY', 'TBX', 'TBY',
    'TS1', 'TS2', 'TS3',
)

N_VTL_PARAMS: int = len(COVTL_PARAMS)

AUTO_PARAMS: Tuple[str, ...] = ('TRX', 'TRY')

GLOTTIS_PARAM_NAMES: Tuple[str, ...] = (
    'f0', 'pressure', 'x_bottom', 'x_top', 'chink_area', 'lag',
    'rel_amp', 'double_pulsing', 'pulse_skewness', 'f0_flutter',
    'aspiration_strength',
)

# =============================================================================
# Coefficients syllabiques (indépendants du speaker)
# =============================================================================

COEFCEN: float = 0.70
DELTA_O: float = 0.70
DELTA_E: float = 0.70

NEUTRAL_RHO: float = 0.42
NEUTRAL_THETA: float = 3.141592653589793

TCONS_DEFAULT: float = 1.5
TVOY_DEFAULT: float = 0.5

C_BEFORE_PAUSE_HOLD_MS: float = 50.0
SUSTAIN_FRACTION_MIN: float = 0.0

# =============================================================================
# COVTL — coefficients (c1, c0, c2) dérivés du .speaker (s2)
# =============================================================================
# Ordre des tuples : (c1, c0, c2). Solveur 3x3 sur a/i/u natifs puis
# décalages LD/TTY/TCY (fermeture labiale, contact apical, occlusion vélaire).

CO_VTL: Dict[str, Tuple[float, float, float]] = {
    'HX':  ( 0.784400,  0.431200, 0.000000),
    'HY':  (-5.314533,  0.266218, 3.359312),
    'JX':  (-0.092800,  0.098347, 0.709730),
    'JA':  (-3.387667,  0.658891, 4.415484),
    'LP':  ( 0.605700,  0.550437, 0.203310),
    'LD':  ( 0.220222,  0.275277, 1.762732),
    'TCX':  ( 0.847500,  1.417187, 5.400294),
    'TCY':  (-1.555600,  0.587167, 0.407014),
    'TTX':  ( 4.043367,  0.927450, 4.145138),
    'TTY':  (-1.588867,  0.637012, 2.333867),
    'TBX':  ( 2.050800,  0.751791, 4.324290),
    'TBY':  (-0.357233,  1.169258, 6.166936),
    'TS1':  ( 0.534833,  0.060755, 5.492521),
    'TS2':  ( 0.055200,  0.067495, 0.633457),
    'TS3':  (-0.135400,  0.193221, 2.322870),
}

COVTL_TO_FULL: Dict[str, int] = {
    'HX': 0, 'HY': 1, 'JX': 2, 'JA': 3, 'LP': 4, 'LD': 5,
    'TCX': 8, 'TCY': 9, 'TTX': 10, 'TTY': 11, 'TBX': 12, 'TBY': 13,
    'TS1': 16, 'TS2': 17, 'TS3': 18,
}

CO = np.zeros((N_VTL_PARAMS, 3), dtype=np.float64)
for _idx, _pname in enumerate(COVTL_PARAMS):
    _c1, _c0, _c2 = CO_VTL[_pname]
    CO[_idx, 0] = _c0
    CO[_idx, 1] = _c1
    CO[_idx, 2] = _c2

# =============================================================================
# Cibles vocaliques (ρ, θ) — dérivées du .speaker
# =============================================================================
# Ancres strictes a/i/u ; i et u compensées pour le relèvement c1(TCY) ;
# autres voyelles : moindres carrés ρ ≤ 1 ;
# '@' : (0.350, 170°) choisie par coût multi-critères sur la fonction d'aire
# (réduction du bunching du centroïde — bombement 6.88 → 5.46 cm² —, pointe
# libre 0.94, lèvres ouvertes, constriction médiane préservée).

VOWEL_TARGETS: Dict[str, Tuple[float, float]] = {
    'a': (1.000, np.pi),
    'i': (0.550, 5 * np.pi / 3),
    'u': (0.589, np.pi / 3),
    'e': (1.000, 4.838925),
    'E': (0.368, 0.030543),
    'o': (1.000, 1.492257),
    'O': (1.000, 1.732239),
    '6': (0.690, 2.792527),
    '9': (0.578, 1.326450),
    '@': (0.350, 2.967060),
    'y': (0.618, 5.672320),
    '2': (0.707, 0.514872),
}

# =============================================================================
# VOWEL_EFFORT_GAIN — gain d'effort par voyelle (calibrage acoustique JD3,
# indépendant du speaker tant que non recalé)
# =============================================================================
VOWEL_EFFORT_GAIN: Dict[str, float] = {
    'i': 1.5, 'u': 1.5, 'e': 1.5, 'y': 1.3, '2': 1.2,
}

# =============================================================================
# Cibles consonantiques (ρ, θ, sélecteur) — dérivées du .speaker
# =============================================================================
# Fit contextuel (a/i/u) + deltas de fermeture calibrés sur JD3.
# Sélecteurs = décisions phonétiques (parité Maeda, allégements r11/r13/r14).

CONSONANT_TARGETS: Dict[str, Tuple[float, float, List[str]]] = {
    'b': (0.96, 4.895320,
              ['JA', 'LD', 'LP']),
    'd': (1.49, 4.537856,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY']),
    'g': (1.20, 0.523599,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'v': (0.82, 6.265732,
              ['JA', 'JX', 'LP', 'LD']),
    'z': (1.44, 4.590216,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'z_front': (1.34, 4.590216,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'Z': (1.20, 6.091199,
              ['JA', 'TCX', 'TBX', 'TBY', 'LP']),
    'D': (1.63, 4.468043,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'R': (1.61, 4.415683,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),
    'dZ': (1.85, -0.750492,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'LP']),
    'l': (1.60, 2.752294,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'L': (1.48, 2.350363,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'C': (1.83, 5.637413,
              ['JA', 'TCX', 'TCY']),
    'X': (1.61, 4.415683,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),
    'm': (0.96, 4.895320,
              ['JA', 'LD', 'LP']),
    'n': (1.49, 0.122173,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY']),
    'N': (1.20, np.pi / 3,
              []),
    'J': (1.20, 5 * np.pi / 3,
              []),
    'w': (0.60, np.pi / 3,
              ['JA', 'LP', 'LD', 'TCX', 'TCY']),
    'j': (0.80, 5 * np.pi / 3,
              ['JA', 'TCX', 'TCY']),
    'ɥ': (0.62, 5.672320,
              ['JA', 'TCX', 'TCY']),
    'h': (0.50, np.pi,
              []),
    'g_vel': (1.20, 0.523599,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'g_pal': (1.41, 5.934119,
              ['JA', 'TCY', 'TBX', 'TBY']),
}

_VOICELESS_KEYS = {'p', 't', 'k', 'f', 's', 'S', 'T', 'tS'}
ALL_CONSONANT_KEYS: Tuple[str, ...] = tuple(
    sorted(set(CONSONANT_TARGETS.keys()) | _VOICELESS_KEYS | {'g', 'k'})
)
ALL_PHONEME_KEYS = set(ALL_CONSONANT_KEYS) | set(VOWEL_TARGETS.keys())

VOICED_CONSONANT_KEYS: frozenset = frozenset(
    set(ALL_CONSONANT_KEYS) - _VOICELESS_KEYS - {'h'}
)

NASAL_CONSONANT_KEYS: frozenset = frozenset({'m', 'n', 'N', 'J'})
VO_NASALIZED_VOWEL: float = 0.5


# =============================================================================
# Presets glottaux (modèle géométrique natif du speaker s2)
# =============================================================================
@dataclass
class GlottisPreset:
    name: str
    f0: float = 120.0
    pressure: float = 800.0
    x_bottom: float = 0.0
    x_top: float = 0.0
    chink_area: float = 0.0
    lag: float = 0.0
    rel_amp: float = 1.0
    double_pulsing: float = 0.0
    pulse_skewness: float = 0.0
    f0_flutter: float = 0.0
    aspiration_strength: float = 0.0

    def to_vector(self) -> np.ndarray:
        return np.array([self.f0, self.pressure, self.x_bottom, self.x_top,
                         self.chink_area, self.lag, self.rel_amp,
                         self.double_pulsing, self.pulse_skewness,
                         self.f0_flutter, self.aspiration_strength],
                        dtype=np.float64)

    def to_dict(self) -> Dict[str, float]:
        return {name: getattr(self, name) for name in GLOTTIS_PARAM_NAMES}


GLOTTIS_PRESETS: Dict[str, GlottisPreset] = {
    'modal': GlottisPreset(name='modal'),
    'voiceless': GlottisPreset(name='voiceless', pressure=400.0,
                               x_bottom=1.0, x_top=1.0, chink_area=20.0, rel_amp=0.0),
    'breathy': GlottisPreset(name='breathy', pressure=600.0,
                             x_bottom=0.3, x_top=0.5, chink_area=15.0, rel_amp=0.6),
    'creaky': GlottisPreset(name='creaky', f0=80.0, pressure=1000.0,
                            x_bottom=-0.2, x_top=-0.1, lag=0.1, rel_amp=0.8,
                            pulse_skewness=0.5, double_pulsing=0.3),
    'whisper': GlottisPreset(name='whisper', pressure=500.0,
                             x_bottom=0.8, x_top=1.0, chink_area=40.0, rel_amp=0.0),
    'voiceless_fricative': GlottisPreset(name='voiceless_fricative', pressure=600.0,
                                         x_bottom=0.7, x_top=0.9, chink_area=10.0,
                                         rel_amp=0.1, aspiration_strength=10.0),
    'aspirated': GlottisPreset(name='aspirated', pressure=700.0,
                               x_bottom=0.5, x_top=0.8, chink_area=10.0,
                               rel_amp=0.3, aspiration_strength=15.0),
}

# Presets natifs extraits du fichier .speaker (modèle sélectionné).
# NB : le nom historique JD3_GLOTTIS_PRESETS est conservé pour compatibilité
# avec les importeurs du pipeline (glottal_source.py, SpeakerConfig).
JD3_GLOTTIS_PRESETS: Dict[str, GlottisPreset] = {
    'breathy': GlottisPreset(
            name='breathy',
            f0=181.008, pressure=7850.264, lag=1.222,
            x_bottom=0.02, x_top=0.03, chink_area=0.1,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'default': GlottisPreset(
            name='default',
            f0=181.008, pressure=7850.264, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.05,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'h': GlottisPreset(
            name='h',
            f0=192.44, pressure=7999.997, lag=1.222,
            x_bottom=0.045, x_top=0.045, chink_area=0.1,
            rel_amp=0.002, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'hoarse': GlottisPreset(
            name='hoarse',
            f0=212.5, pressure=8000, lag=0.88,
            x_bottom=0.02, x_top=0.04, chink_area=0.16,
            rel_amp=1, double_pulsing=0.203,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'hoarse2': GlottisPreset(
            name='hoarse2',
            f0=212.5, pressure=8000, lag=0.88,
            x_bottom=-0.01, x_top=-0.01, chink_area=0.16,
            rel_amp=1, double_pulsing=0.203,
            pulse_skewness=0.5, f0_flutter=25, aspiration_strength=-10,
        ),
    'modal': GlottisPreset(
            name='modal',
            f0=212.5, pressure=8000, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.05,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'pressed': GlottisPreset(
            name='pressed',
            f0=212.5, pressure=8000, lag=1.222,
            x_bottom=0, x_top=0.01, chink_area=0.025,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'stop': GlottisPreset(
            name='stop',
            f0=192.44, pressure=7999.997, lag=1.222,
            x_bottom=-0.01, x_top=-0.01, chink_area=-0.001,
            rel_amp=-0.204, double_pulsing=0.504,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiced-fricative': GlottisPreset(
            name='voiced-fricative',
            f0=254.425, pressure=0, lag=1.222,
            x_bottom=0.05, x_top=0.05, chink_area=0.1,
            rel_amp=1, double_pulsing=0.047,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiced-plosive': GlottisPreset(
            name='voiced-plosive',
            f0=254.425, pressure=0, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.1,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiceless-fricative': GlottisPreset(
            name='voiceless-fricative',
            f0=185.867, pressure=8000, lag=1.222,
            x_bottom=0.1, x_top=0.1, chink_area=0.1,
            rel_amp=0, double_pulsing=0.046,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiceless-plosive': GlottisPreset(
            name='voiceless-plosive',
            f0=185.758, pressure=7999.327, lag=1.222,
            x_bottom=0.1, x_top=0.1, chink_area=0.1,
            rel_amp=0, double_pulsing=0.054,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'whisper': GlottisPreset(
            name='whisper',
            f0=212.5, pressure=8000, lag=0.88,
            x_bottom=0.1, x_top=0.1, chink_area=0.25,
            rel_amp=0, double_pulsing=0,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
}

TAG_TO_GLOTTIS_PRESET: Dict[str, str] = {
    'voiced': 'modal', 'voiceless': 'voiceless', 'breathy': 'breathy',
    'creaky': 'creaky', 'whisper': 'whisper', 'modal': 'modal',
    'voiceless_fricative': 'voiceless_fricative', 'aspirated': 'aspirated',
    'stop': 'stop', 'pressed': 'pressed', 'h': 'h', 'hoarse': 'hoarse',
    'hoarse2': 'hoarse2', 'voiced-fricative': 'voiced-fricative',
    'voiced-plosive': 'voiced-plosive',
    'voiceless-fricative': 'voiceless-fricative',
    'voiceless-plosive': 'voiceless-plosive', 'default': 'default',
}

TAG_TO_VO_TARGET: Dict[str, float] = {
    'nasal': 1.0, 'oral': 0.0, 'nasalized': 0.5, 'denasal': 0.0,
}

TAG_TO_VOICING: Dict[str, float] = {
    'voiced': 1.0, 'voiceless': 0.0, 'breathy': 0.6, 'creaky': 0.9,
    'whisper': 0.0, 'aspirated': 0.0,
}


# =============================================================================
# Effort (bornes dérivées du speaker : P_max = pression native maximale)
# =============================================================================
@dataclass
class EffortBounds:
    P_min: float = 400.0
    P_max: float = 8000.0
    R_min: float = 0.3
    R_max: float = 1.2


EFFORT_DEFAULTS: EffortBounds = EffortBounds()

FRICATIVE_KEYS: frozenset = frozenset({
    'f', 'v', 's', 'z', 'S', 'Z', 'T', 'D', 'C', 'X', 'R',
})

TAU_PEXP_MS: float = 12.0
PEXP_FRICATIVE_PRESSURE: float = 0.8
PEXP_BURST_PRESSURE: float = 1.0
BURST_PEAK_DURATION_MS: float = 7.5
BURST_RISE_MS: float = 2.5
BURST_DECAY_MS: float = 15.0

# =============================================================================
# Occlusives — cibles virtuelles et seuils
# =============================================================================
TBY_VELAR_OCCLUSION_MIN: float = 0.812025
TCX_VELAR_OCCLUSION_MAX: float = -0.050
TCY_VELAR_OCCLUSION_MIN: float = -0.225

PLOSIVE_OCCLUSION_RHO: Dict[str, float] = {
    'b': 1.10, 'p': 1.10, 'd': 1.15, 't': 1.15, 'g': 1.45, 'k': 1.45,
}

PLOSIVE_VIRTUAL_TARGETS: Dict[str, dict] = {
    'b': {'rho_virtual': 1.12, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.35, 'rho_min_occlusion': 1.10},
    'p': {'rho_virtual': 1.12, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.35, 'rho_min_occlusion': 1.10},
    'd': {'rho_virtual': 1.18, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.30, 'rho_min_occlusion': 1.15},
    't': {'rho_virtual': 1.18, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.30, 'rho_min_occlusion': 1.15},
    'g': {'rho_virtual': 1.45, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.30, 'rho_min_occlusion': 1.45},
    'k': {'rho_virtual': 1.45, 'speed_factor': 2.0,
          'occlusion_duration_factor': 0.30, 'rho_min_occlusion': 1.45},
}


# =============================================================================
# Configuration du speaker
# =============================================================================
@dataclass
class SpeakerConfig:
    name: str = 's2'
    f0_default: float = 181.008
    f0_range: Tuple[float, float] = (80.0, 200.0)
    use_jd_presets: bool = True
    preset_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)
    effort: EffortBounds = field(default_factory=lambda: EffortBounds(
        P_min=400.0, P_max=8000.0, R_min=0.3, R_max=1.2
    ))

    def get_preset(self, preset_name: str) -> GlottisPreset:
        if self.use_jd_presets and preset_name in JD3_GLOTTIS_PRESETS:
            base = JD3_GLOTTIS_PRESETS[preset_name]
        elif preset_name in GLOTTIS_PRESETS:
            base = GLOTTIS_PRESETS[preset_name]
        else:
            base = GlottisPreset(name=preset_name)
        if preset_name in self.preset_overrides:
            for key, value in self.preset_overrides[preset_name].items():
                setattr(base, key, value)
        return base
