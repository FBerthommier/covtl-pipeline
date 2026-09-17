# -*- coding: utf-8 -*-
"""
constants.py — généré par adapt_speaker.py (covtl-speaker)
=========================================================
Speaker : s1

Ne pas éditer à la main : régénérer via
    python adapt_speaker.py s1.speaker

Toutes les valeurs dépendantes du speaker sont dérivées du fichier
.speaker par la procédure formalisée (procedure_adaptation.md).
Les sections indépendantes du speaker (enveloppe, timing, tags, presets
génériques) sont recopiées de la référence SynthVTL24b.

Journal de la dérivation COVTL :
#   LD  : c1=c0=0.272708 (fermeture min=0 à ρ=1) ; c1 x0.8 = 0.218167
#   TTY : c0=(0.8−(-1.5945))/2.3=1.041087 ; c1=-1.5945+c0+0.15=-0.403413 (contact/occlusion apicale)
#   TCY : c1 -1.069367 → -0.819367 (occlusion vélaire /g,k/)
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
# COVTL — coefficients (c1, c0, c2) dérivés du .speaker (s1)
# =============================================================================
# Ordre des tuples : (c1, c0, c2). Solveur 3x3 sur a/i/u natifs puis
# décalages LD/TTY/TCY (fermeture labiale, contact apical, occlusion vélaire).

CO_VTL: Dict[str, Tuple[float, float, float]] = {
    'HX':  ( 0.784133,  0.431733, 0.000000),
    'HY':  (-5.445700,  0.968650, 3.227228),
    'JX':  (-0.233200,  0.257712, 2.701907),
    'JA':  (-3.092767,  1.331624, 5.220639),
    'LP':  ( 0.071733,  0.303205, 1.429054),
    'LD':  ( 0.218167,  0.272708, 4.401742),
    'TCX':  ( 1.114233,  1.696020, 5.689108),
    'TCY':  (-0.819367,  0.672112, 5.611551),
    'TTX':  ( 3.879367,  0.974612, 4.166337),
    'TTY':  (-1.516167,  0.232119, 4.398511),
    'TBX':  ( 2.465167,  0.593884, 3.839222),
    'TBY':  (-0.065333,  1.152158, 0.931334),
    'TS1':  ( 0.327233,  0.357629, 3.592613),
    'TS2':  ( 0.025200,  0.036277, 0.802868),
    'TS3':  (-0.047100,  0.509839, 1.393340),
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
# '@' : (0.700, 160°) choisie par coût multi-critères sur la fonction d'aire
# (réduction du bunching du centroïde — bombement 8.91 → 7.70 cm² —,
# lèvres ouvertes, constriction médiane préservée, pointe libre).

VOWEL_TARGETS: Dict[str, Tuple[float, float]] = {
    'a': (1.000, np.pi),
    'i': (0.690, 5 * np.pi / 3),
    'u': (0.550, np.pi / 3),
    'e': (0.541, 4.756022),
    'E': (0.300, 2.740167),
    'o': (1.000, 1.780236),
    'O': (1.000, 2.024582),
    '6': (0.891, 2.958333),
    '9': (0.619, 2.330015),
    '@': (0.700, 2.792527),
    'y': (0.670, 0.514872),
    '2': (1.000, 1.348267),
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
    'b': (0.97, 1.221730,
              ['JA', 'LD', 'LP']),
    'd': (1.69, 5.393067,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY']),
    'g': (1.10, 0.000000,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'v': (0.62, 6.108652,
              ['JA', 'JX', 'LP', 'LD']),
    'z': (1.70, 5.375614,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'z_front': (1.60, 5.375614,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'Z': (1.51, 6.108652,
              ['JA', 'TCX', 'TBX', 'TBY', 'LP']),
    'D': (1.70, 5.305801,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'R': (1.25, 4.066617,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),
    'dZ': (1.51, -0.401426,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'LP']),
    'l': (1.66, 4.619887,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'L': (1.51, 4.310964,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'C': (1.63, 5.637413,
              ['JA', 'TCX', 'TCY']),
    'X': (1.25, 4.066617,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),
    'm': (0.97, 1.221730,
              ['JA', 'LD', 'LP']),
    'n': (1.69, 0.122173,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY']),
    'N': (1.20, np.pi / 3,
              []),
    'J': (1.20, 5 * np.pi / 3,
              []),
    'w': (0.60, np.pi / 3,
              ['JA', 'LP', 'LD', 'TCX', 'TCY']),
    'j': (0.80, 5 * np.pi / 3,
              ['JA', 'TCX', 'TCY']),
    'ɥ': (0.67, 0.514872,
              ['JA', 'TCX', 'TCY']),
    'h': (0.50, np.pi,
              []),
    'g_vel': (1.10, 0.000000,
              ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'g_pal': (0.71, 6.091199,
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
# Presets glottaux (modèle géométrique natif du speaker s1)
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
            f0=114.908, pressure=7850.264, lag=1.222,
            x_bottom=0.02, x_top=0.03, chink_area=0.1,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'default': GlottisPreset(
            name='default',
            f0=114.908, pressure=7850.264, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.05,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'h': GlottisPreset(
            name='h',
            f0=122.165, pressure=7999.997, lag=1.222,
            x_bottom=0.045, x_top=0.045, chink_area=0.1,
            rel_amp=0.002, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'hoarse': GlottisPreset(
            name='hoarse',
            f0=134.9, pressure=8000, lag=0.88,
            x_bottom=0.02, x_top=0.04, chink_area=0.16,
            rel_amp=1, double_pulsing=0.203,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'hoarse2': GlottisPreset(
            name='hoarse2',
            f0=134.9, pressure=8000, lag=0.88,
            x_bottom=-0.01, x_top=-0.01, chink_area=0.16,
            rel_amp=1, double_pulsing=0.203,
            pulse_skewness=0.5, f0_flutter=25, aspiration_strength=-10,
        ),
    'modal': GlottisPreset(
            name='modal',
            f0=134.9, pressure=8000, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.05,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'pressed': GlottisPreset(
            name='pressed',
            f0=134.9, pressure=8000, lag=1.222,
            x_bottom=0, x_top=0.01, chink_area=0.025,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'stop': GlottisPreset(
            name='stop',
            f0=122.165, pressure=7999.997, lag=1.222,
            x_bottom=-0.01, x_top=-0.01, chink_area=-0.001,
            rel_amp=-0.204, double_pulsing=0.504,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiced-fricative': GlottisPreset(
            name='voiced-fricative',
            f0=161.515, pressure=0, lag=1.222,
            x_bottom=0.05, x_top=0.05, chink_area=0.1,
            rel_amp=1, double_pulsing=0.047,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiced-plosive': GlottisPreset(
            name='voiced-plosive',
            f0=161.515, pressure=0, lag=1.222,
            x_bottom=0.01, x_top=0.02, chink_area=0.1,
            rel_amp=1, double_pulsing=0.05,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiceless-fricative': GlottisPreset(
            name='voiceless-fricative',
            f0=117.993, pressure=8000, lag=1.222,
            x_bottom=0.1, x_top=0.1, chink_area=0.1,
            rel_amp=0, double_pulsing=0.046,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'voiceless-plosive': GlottisPreset(
            name='voiceless-plosive',
            f0=117.923, pressure=7999.327, lag=1.222,
            x_bottom=0.1, x_top=0.1, chink_area=0.1,
            rel_amp=0, double_pulsing=0.054,
            pulse_skewness=0, f0_flutter=0, aspiration_strength=0,
        ),
    'whisper': GlottisPreset(
            name='whisper',
            f0=134.9, pressure=8000, lag=0.88,
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
TBY_VELAR_OCCLUSION_MIN: float = 1.086825
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
    name: str = 's1'
    f0_default: float = 114.908
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
