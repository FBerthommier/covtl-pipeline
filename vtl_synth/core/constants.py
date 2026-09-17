# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
constants.py
=============
COVTL coefficients, consonant and vowel targets, glottis presets,
and parameter order for the 400 Hz VTL .tract file.

All values are taken from:
  - documentation_VTL_Berthommier_EN.pdf (shifted COVTL, selectors, targets)
  - rapport_espace_vocalique.pdf (JD2 vowel targets)
  - rapport_vecteur_VTL_400Hz.pdf (layout of the complete vector)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


# =============================================================================
# Sampling frequencies
# =============================================================================

TRACT_SR: int = 400        # Target frequency of the .tract file (Hz)
TARGET_SR: int = 100       # Internal frequency of the Berthommier model (Hz)
AUDIO_SR: int = 44100      # VTL audio frequency (Hz)

# =============================================================================
# Envelope parameters (COVTL token-based amplitude envelope)
# =============================================================================
# Source: the COVTL reference model.
#
# FS   : sampling frequency of the COVTL envelope (Hz).
#        Corresponds to the ratio TARGET_SR / T_S, i.e. the number of
#        "steps per sample" used by build_envelope_from_blocks.
#        With TARGET_SR=100 and T_S=0.01, FS = 10000 Hz.
# T_S  : sampling period of the trajectory model (s).
#        At TARGET_SR=100 Hz, one step = 0.01 s = 10 ms.
#
# TOKEN_AMPL_MIN : minimum amplitude per token type.
#   Tokens not listed have a minimum amplitude of 0.
#   Used by _env_transition for generic cases.
#
# _PLOSIVE_TOKENS : set of tokens representing plosives.
#   Used by build_envelope_tokens to convert C → c in
#   plosive clusters not at a syllable boundary.
# =============================================================================
FS: int = 10000             # Envelope sampling frequency (Hz)
T_S: float = 0.01          # Trajectory step period (s)

TOKEN_AMPL_MIN: Dict[str, float] = {
    'V': 1.0,   # Vowel (full voicing)
    'N': 0.3,   # Nasal
    'L': 0.3,   # Lateral
    'R': 0.3,   # Rhotic/approximant
    'r': 0.3,   # Rhotic variant
    'y': 0.5,   # Vowel-onset (anticipation)
}

_PLOSIVE_TOKENS: frozenset = frozenset({'C'})

# =============================================================================
# Dimensions of the VTL vector
# =============================================================================

N_TRACT_PARAMS: int = 19   # Vocal tract parameters
N_GLOTTIS_PARAMS: int = 11 # Parameters of the geometric glottis model

# =============================================================================
# Names and order of the tract parameters (19)
# =============================================================================
# Order conforms to the VTL 2.3 .tract file
TRACT_PARAM_NAMES: Tuple[str, ...] = (
    'HX', 'HY',      # 0-1:   Hyoid
    'JX', 'JA',      # 2-3:   Jaw
    'LP', 'LD',      # 4-5:   Lips
    'VS', 'VO',      # 6-7:   Velopharynx (nasality — EXTENSION)
    'TCX', 'TCY',    # 8-9:   Tongue body (antero-posterior)
    'TTX', 'TTY',    # 10-11: Tongue tip
    'TBX', 'TBY',    # 12-13: Tongue base (dorso-velar)
    'TRX', 'TRY',    # 14-15: Tongue root
    'TS1', 'TS2',    # 16-17: Tongue sides
    'TS3',           # 18:   Posterior tongue sides (mode — orthogonal if needed)
)

# Indices of the extension parameters (not handled by COVTL)
IDX_VS = 6   # Velum shape
IDX_VO = 7   # Velum opening
IDX_TS3 = 18 # Tongue side 3 (mode)

# Tract parameters handled by COVTL (all except VS, VO, and auto TRX/TRY)
COVTL_PARAMS: Tuple[str, ...] = (
    'HX', 'HY', 'JX', 'JA', 'LP', 'LD',
    'TCX', 'TCY', 'TTX', 'TTY', 'TBX', 'TBY',
    'TS1', 'TS2', 'TS3',
)

# Number of COVTL parameters (used by build_global_pval)
N_VTL_PARAMS: int = len(COVTL_PARAMS)  # 15

# Parameters left to VTL auto (TRX, TRY)
AUTO_PARAMS: Tuple[str, ...] = ('TRX', 'TRY')

# =============================================================================
# Names and order of the glottis parameters (11) — geometric model
# =============================================================================
GLOTTIS_PARAM_NAMES: Tuple[str, ...] = (
    'f0',                   # 0:  Fundamental frequency (Hz)
    'pressure',             # 1:  Subglottal pressure (dPa)
    'x_bottom',             # 2:  Lower displacement of the vocal folds
    'x_top',                # 3:  Upper displacement of the vocal folds
    'chink_area',           # 4:  Posterior opening (breathiness)
    'lag',                  # 5:  Phase lag
    'rel_amp',              # 6:  Relative amplitude
    'double_pulsing',       # 7:  Double pulsing
    'pulse_skewness',       # 8:  Pulse skewness
    'f0_flutter',           # 9:  F0 flutter (%)
    'aspiration_strength',  # 10: Aspiration (dB)
)

# =============================================================================
# COEFCEN — rho reduction coefficient at syllable boundaries
# =============================================================================
# Source: Berthommier model, §3 (vocalic anticipation/completion)
#
# At syllable boundaries, the vowel does not reach its full
# target: rho is reduced by a coefficient < 1.
#
# For a vowel in anticipation position (V_o):
#   rho_anchor = DELTA_O * rho_v
# For a vowel in completion position (V_e):
#   rho_anchor = DELTA_E * rho_v
#
# DELTA_O and DELTA_E are distinct: in the Berthommier model,
# anticipation (V_o) and completion (V_e) are not symmetric.
# V_o is an anticipation that prepares the transition to the next
# consonant; V_e is the completion of the vowel before the coda
# consonant or the next syllable.
#
# Historically COEFCEN (= 0.70) merged the two. They are now
# separated for conformance with the reference model.
# =============================================================================

COEFCEN: float = 0.70   # DEPRECATED (LANG-003, 2026-09-04): use DELTA_O
                        # (V_o anticipation) or DELTA_E (V_e completion);
                        # kept only for backward compat.
DELTA_O: float = 0.70   # Reduction coefficient for V_o (anticipation)
DELTA_E: float = 0.70   # Reduction coefficient for V_e (completion)

# =============================================================================
# NEUTRAL_RHO / NEUTRAL_THETA — Neutral tract position (schwa @)
# =============================================================================
# Used by gesture.py for terminal anchors and fallbacks
# when no vowel is available in the context.
# =============================================================================
NEUTRAL_RHO: float = 0.42
NEUTRAL_THETA: float = 3.141592653589793  # π (schwa)

# =============================================================================
# Tcons / Tvoy — Syllabic timing parameters
# =============================================================================
# Source: Berthommier model, §3; reference github timit-ro-maeda.
#
# Syllabic timing is driven by two parameters that control
# the relative duration of the consonantal and vocalic arcs in each
# superposition graph.
#
# T_BASE_DEFAULT (T) is the base period of an elementary arc.
# The effective arc durations are derived as follows:
#
#   For CV (without sustain):
#     total consonantal arc = 2 * T * Tcons    (V_o→C + C→V)
#     total vocalic arc    = 2 * T * Tvoy      (V_o→V)
#     Both branches have the same total duration (2*T).
#
#   For CV with sustain (nucleus_duration > 2*T*Tvoy):
#     total consonantal arc = 2 * T * Tcons
#     vocalic transition arc = 2 * T * Tvoy
#     sustain_vocalic = nucleus_duration - 2 * T * Tvoy  (≥ 0)
#     The C branch is padded to the total V duration.
#
#   For CVC:
#     Onset  (C1→V)  : duration proportional to (dur_C1 + ½* dur_V)
#     Coda   (V→C2)  : duration proportional to (dur_C2 + ½* dur_V)
#     Vocalic sustain = max(0, dur_V - part_transition)
#
# Tcons and Tvoy are multiplicative factors (default 1.0 = nominal
# duration). Increasing Tcons lengthens consonantal transitions.
# =============================================================================
TCONS_DEFAULT: float = 1.5   # Consonantal duration factor (120 ms / 80 ms)
TVOY_DEFAULT: float = 0.5    # Vocalic duration factor (80 ms total / 160 ms nominal)

# =============================================================================
# C_BEFORE_PAUSE_HOLD_MS — Hold for a C ending before a pause
# =============================================================================
# Source: reference github timit-ro-maeda.
#
# When a syllable ends with a coda consonant and is followed
# by a pause (or is utterance-final), the consonant is held
# (hold) for a fixed duration before the transition to neutral.
#
# This hold prevents the consonant from being "swallowed" by the
# transition to silence. It results in a stationary point at the
# consonant's target point in the complex plane.
#
# Typical value: 40–60 ms (a final stop is held
# about 50 ms before the silent release).
# =============================================================================
C_BEFORE_PAUSE_HOLD_MS: float = 50.0

# =============================================================================
# SUSTAIN_FRACTION_MIN — Minimum fraction of nucleus_duration for sustain
# =============================================================================
# If the vocalic nucleus duration exceeds 2*T*Tvoy (the vocalic
# transition duration), the excess is allocated to sustain.
# SUSTAIN_FRACTION_MIN defines the threshold (as a fraction of 2*T*Tvoy)
# below which no sustain is generated.
# =============================================================================
SUSTAIN_FRACTION_MIN: float = 0.0  # 0 = as soon as dur > 2*T*Tvoy

# =============================================================================
# COVTL — Coefficients (c1, c0, c2) shifted for VTL
# =============================================================================
# Source: documentation_VTL_Berthommier_EN.pdf, §3
# LD c1 reduced (×0.8) to avoid negative LD at high rho.
# TTY: original Maeda coefficients. Apical contact for /d/
# is obtained with rho=1.10 (consonant target), not by a c1
# shift. TTY artifacts on /i/ and /u/ are avoided with rho(i)=0.60
# and rho(u)=0.55 (compensation for the raised c1(TCY), cf. VOWEL_TARGETS).
# TTY: c1 raised by +0.15 (−0.609700 → −0.459700) for the apical
# occlusion of /d,t/ (0.000 cm² over the 12 vowels, alveolar zone). Tuple
# order (c1, c0, c2): the lever is the FIRST element. TTY belongs to no
# other consonant selector; negligible vowel cost (/i/ 0.137 cm²).
# Study: output/velar_contact/dental_closure_rounds2-10.md
CO_VTL: Dict[str, Tuple[float, float, float]] = {
    'HX':  ( 0.722233,  0.555533,  0.000000),
    'HY':  (-5.155867,  1.246761,  3.361756),
    'JX':  (-0.025000,  0.050000,  2.094395),
    'JA':  (-3.371067,  1.299456,  5.354986),
    'LP':  ( 0.382967,  0.617041,  1.042238),
    'LD':  ( 0.466400,  0.583000,  4.092457),  # c1×0.8=0.4664; original from the Maeda model
    'TCX': ( 1.090767,  1.528173,  5.373564),
    'TCY': (-0.914133,  0.690945,  6.031444),  # c1+0.25 (velar occlusion /g/)
    'TTX': ( 4.044400,  0.832384,  4.466027),  # original Maeda coefficients
    'TTY': (-0.459700,  1.084300,  0.116283),  # c1+0.15 (apical occlusion /d,t/; Maeda origin −0.609700)
    'TBX': ( 2.795833,  1.272045,  4.907833),
    'TBY': ( 0.159033,  0.836452,  0.076068),
    'TS1': ( 0.248667,  0.049433,  0.545179),
    'TS2': ( 0.031067,  0.032478,  4.484628),
    'TS3': ( 0.032933,  0.119409,  2.897420),
}

# =============================================================================
# COVTL_TO_FULL -- mapping COVTL key (15 params) -> full VTL tract index (19)
# =============================================================================
# Native VTL order (confirmed JD3.speaker index 14-18):
#   HX HY JX JA LP LD VS VO TCX TCY TTX TTY TBX TBY TRX TRY TS1 TS2 TS3
# VS(6) and VO(7) are extensions (TimedEnvelope/ortho), TRX(14) TRY(15)
# are left at 0 (VTL auto).  Single source of the mapping — used by
# AssembleTract.assemble() and the VV probe of build_phrase_tract (reminder BUG-009:
# any modification must go through here only).
# =============================================================================
COVTL_TO_FULL: Dict[str, int] = {
    'HX': 0, 'HY': 1, 'JX': 2, 'JA': 3,
    'LP': 4, 'LD': 5,
    'TCX': 8, 'TCY': 9, 'TTX': 10, 'TTY': 11,
    'TBX': 12, 'TBY': 13,
    'TS1': 16, 'TS2': 17, 'TS3': 18,
}

# =============================================================================
# CO -- COVTL matrix (N_VTL_PARAMS, 3) for arc_B / compute_P
# =============================================================================
# Source: the COVTL reference model.
# Columns: [c0, c1, c2]  (different order from the CO_VTL dict, which is (c1, c0, c2)).
# Rows: COVTL_PARAMS order.
# Used by polar.compute_P and polar.arc_B for direct projection.
# =============================================================================
CO = np.zeros((N_VTL_PARAMS, 3), dtype=np.float64)
for _idx, _pname in enumerate(COVTL_PARAMS):
    _c1, _c0, _c2 = CO_VTL[_pname]
    CO[_idx, 0] = _c0   # column 0 = c0
    CO[_idx, 1] = _c1   # column 1 = c1
    CO[_idx, 2] = _c2   # column 2 = c2

# =============================================================================
# Vowel targets (ρ, θ) — strict Maeda anchors
# =============================================================================
# Source: rapport_espace_vocalique.pdf, §2
# /a/, /i/, /u/ are fixed at the Maeda anchors (ρ=1).
# The other vowels are adjusted by least squares with ρ <= 1.
# === LANG SECTION — BEGIN (managed by setup_lang.py — do not edit by hand)
# English — strict Maeda anchors (original covtl-pipeline calibration).
# /a/, /i/, /u/ close to the Maeda anchors (ρ≤1); the other vowels are
# adjusted by least squares. English notation: no nasal vowels, /r/ is
# alveolar (resolved by the notation alias layer, not by the targets).
ACTIVE_LANG: str = 'en'

VOWEL_TARGETS: Dict[str, Tuple[float, float]] = {
    'a': (1.000, np.pi),           # 180° — STRICT
    'i': (0.600, 5 * np.pi / 3),   # 300° — compensation for the raised c1(TCY)
    'u': (0.550, np.pi / 3),       #  60° — compensation for the raised c1(TCY)
    'e': (0.988, 4.581),           # 262.5°
    'E': (0.594, 3.563),           # 204.1°
    'o': (1.000, 1.827),           # 104.7° — clamped
    'O': (1.000, 2.616),           # 149.9° — clamped
    '6': (0.894, 3.053),           # 174.9° (œ)
    '9': (0.722, 3.105),           # 177.9° (œ̃)
    # '@' (schwa): centre of the a-i-u triangle, ρ̄ = 0.7167, θ = π.
    '@': (0.7167, np.pi),          # centre du triangle a-i-u (ə)
    'y': (0.519, 4.548),           # 260.6°
    '2': (0.396, 3.946),           # 226.1° (ø)
}

# Effort gain per vowel (relative intensity): compensates the intrinsic
# intensity gap of high vowels vs /a/ (clamped downstream to 1.5).
VOWEL_EFFORT_GAIN: Dict[str, float] = {
    'i': 1.5,
    'u': 1.5,
    'e': 1.5,
    'y': 1.3,
    '2': 1.2,
}
# === LANG SECTION — END =============================================================

# =============================================================================
# Front vowels — palatal context for g/k
# =============================================================================
# Front vowels (theta > π) trigger palatalization
# of velars: /g/ and /k/ use the g_pal selector (without TCX)
# instead of g_vel (with TCX). /a/ (theta = π exactly) is velar.
# The test is implemented in projection.py: theta_vowel > np.pi.
# =============================================================================

# =============================================================================
# Consonant targets (ρ, θ, selector)
# =============================================================================
# Source: documentation_VTL_Berthommier_EN.pdf, §5-6
# Selector: list of COVTL parameters to be replaced by the C target.
# Parameters outside the selector inherit from the current vowel.
#
# Voiced / voiceless pair convention:
#   Voiced/voiceless pairs share the same place of articulation,
#   hence the same (ρ, θ) target and the same COVTL selector. The
#   voicing distinction is handled by the glottal source (V(t),
#   glottis preset), NOT by the tract.
#
#   CONSONANT_TARGETS contains ONLY the canonical (voiced) form.
#   Voiceless keys are resolved to their voiced counterpart
#   by _normalize_consonant_key() in berthommier.py:
#     p→b, t→d, k→g, f→v, s→z, S→Z, T→D, tS→dZ
#
#   For g/k, the target depends on the vowel context (vel vs pal).
#   g_target(theta_vowel) dynamically chooses g_vel or g_pal.
# =============================================================================
CONSONANT_TARGETS: Dict[str, Tuple[float, float, List[str]]] = {
    # --- Plosives (voiced — canonical forms) ---
    'b':    (1.06, np.radians(50),  ['JA', 'LD', 'LP']),
    # Lightened /b,p/ selector (2026-09-01, round 11 study): TCX/TCY removed.
    # Labial closure only needs JA (jaw) + LD (closure)
    # + LP (protrusion). Without TCX/TCY in the selector, the tongue follows
    # the vocalic branch during /b/ (coarticulation): the global c1(TCY)+0.25
    # raise (for /g/ occlusion) no longer applies to the /b/ target and the
    # parasitic velar contact during /bV/ disappears (margins 0.126–1.056 cm²,
    # labial closure 0.000 preserved). Partial removal (−TCY alone or −TCX alone)
    # is not enough: both must be removed.
    'd':    (1.10, 3 * np.pi / 2, ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY']),
    'g':    (1.45, np.pi / 3,      ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    # g/k: secondary conditional target (function g_target) → g_vel / g_pal
    # The vel/pal choice depends on the vowel context (theta > pi → palatal).

    # --- Fricatives (voiced — canonical forms) ---
    'v':    (1.14, np.radians(353), ['JA', 'JX', 'LP', 'LD']),
    # θ_v 330→353 (2026-09-02, round 14): LD(v,330°)≈0.40 is dominated by
    # c1=0.466 (ρ has no effect, even inverted); θ353 tightens the
    # labiodental gap to 0.223-0.234 cm² (JD3 reference 0.15, window 0.15-0.25),
    # lingual gap open everywhere, brighter frication (/fu/ 3387→4403 Hz).
    # Lightened /f,v/ selector (2026-09-01, round 13): TCX/TCY removed.
    # The labiodental constriction only needs the jaw (JA, JX)
    # and the lips (LP, LD). Before: PARASITIC tongue contact 0.000 cm²
    # during /f,v/ (tongue against palate/velum — predating the velar
    # fix), healthy labiodental gap masked. After: no tongue contact
    # (margins 0.126–1.017 cm²). As for /b/, the removal must cover
    # both TCX AND TCY.
    'z':    (1.00, np.radians(289), ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    # z_front: contextual variant of /z,s/ before a high front
    # vowel (θ<90° or θ>290° — essentially /i,u/; resolution in
    # projection.get_consonant_target, mechanism like g_vel/g_pal).
    # ρ 1.00→0.90: the high tongue tip in the /i,u/ context closes the
    # alveolar groove at ρ1.00 (gap 0.000); ρ0.90 opens it (0.194/0.106 cm²)
    # with the /s/ spectrum preserved (centroid 4230/3590 Hz vs /S/ 1793-2196).
    'z_front': (0.90, np.radians(289), ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    # Lightened /S,Z/ selector (2026-09-02, round 14): TCY removed —
    # JD3 tt-postalveolar-fricative profile (tip/blade high, CENTER LOW
    # TCY −1.14/−1.75): our θ351 target projects TCY=−0.21 (too high,
    # occlusion 12/12); without TCY in the selector, the center follows the
    # vowel (coarticulation) → gaps 0.263–1.230 cm² over the 12 vowels, place
    # 12.2–15.3 cm post-alveolar, ʃ spectrum (centroid 2837–3535 Hz).
    'Z':    (1.02, np.radians(351), ['JA', 'TCX', 'TBX', 'TBY', 'LP']),
    'D':    (1.15, np.radians(271), ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'R':    (1.28, np.radians(234), ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),

    # --- Affricates (voiced — canonical forms) ---
    'dZ':   (1.15, np.radians(7),   ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'LP']),

    # --- Laterals ---
    'l':    (1.15, np.radians(7),   ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'L':    (1.25, np.radians(7),   ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),

    # --- Palatals ---
    'C':    (1.15, np.radians(353),  ['JA', 'TCX', 'TCY']),
    # NB (2026-09-17, audit): the glide /j/ is defined in the Glides
    # section below (FIX-2, coordinates of /i/) — the former palatal
    # 'j' entry (1.22, 1°) was a SHADOWED duplicate key (later dict
    # entry always won) and has been removed; the effective target is
    # unchanged.

    # --- Uvulars ---
    'X':    (1.28, np.radians(234), ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2']),

    # --- Nasals ---
    # Fix (2026-09-02): /m,n/ get a CLOSURE gesture
    # (m labial [JA,LD,LP]; n alveolar [JA,TCX,TCY,TBX,TBY,TTX,TTY]).
    # Before (empty selector): no closure — /m,n/ realized as
    # weak vowels (m labio 0.74-1.04, n 0.03-0.57 cm²).
    # After: full closure (m 0.000-0.293, n 0.000-0.196) with
    # nasality preserved by the VO extension (VO=1.0 measured during
    # nasals). /N,/J/: derived places (velum/dorsal) — to be provided
    # later if needed.
    'm':    (1.06, np.radians(50),  ['JA', 'LD', 'LP']),
    'n':    (1.10, np.radians(7),   ['JA', 'TCX', 'TCY', 'TBX', 'TBY',
                                     'TTX', 'TTY']),
    'N':    (1.20, np.radians(60),  []),
    'J':    (1.20, 5 * np.pi / 3,  []),

    # --- Glides / approximants ---
    'w':    (0.60, np.radians(60),  ['JA', 'LP', 'LD', 'TCX', 'TCY']),
    # Glides (reference v14 FIX-2: via the vowel tree) — the anchors
    # are the REFERENCE vowel radii, deliberately kept independent of
    # the calibrated vowel plateaus (rho_i = 0.60, rho_u = 0.55 in
    # VOWEL_TARGETS): a glide is a consonantal target, not a plateau.
    #   /j/ → reference coordinates of /i/ (unrounded)  → (0.80, 300°)
    #   /ɥ/ → coordinates of /y/ (rounded)               → (0.519, 260.6°)
    #   /w/ → reference coordinates of /u/ (rounded)     → (0.60, 60°)
    # is_vowel=False (no plateau — these are C nodes); selector
    # depends on rounding: rounded w → LP/LD in the selector with ρ 0.6
    # (rounded labiovelar constriction 0.14-0.15 cm²; ρ≥0.7 with
    # LP/LD creates a labial OCCLUSION 0.000 = [b]-like);
    # unrounded j → i coords (0.8, 300°).
    'j':    (0.80, 5 * np.pi / 3,   ['JA', 'TCX', 'TCY']),
    # /j/: target = coordinates of /i/ (FIX-2) — replaces (1.22, 1°)
    # palatal-closure; unrounded.

    # --- Glide ɥ (reference FIX-2: coordinates of /y/,
    # rounding tracked by the vocalic background — selector without labials) ---
    'ɥ':    (0.519, 4.548,          ['JA', 'TCX', 'TCY']),

    # --- Glottal ---
    # h: near-neutral, no COVTL selector.
    'h':    (0.50, np.radians(180), []),

    # --- g/k: conditional targets (vel/pal) ---
    # g_target(theta_vowel) dynamically chooses:
    #   theta > pi → g_pal (palatal)
    #   otherwise → g_vel (velar)
    # g_vel: rho 1.30 → 1.45 (with c1(TCY)+0.25) for complete velar
    # occlusion (0.000 cm² on a o O u 6 9 — cf. closure_final.md).
    # g_pal: rho 1.30 INTACT — it already closes at baseline, and its TBX
    # leaves the VTL bounds from rho 1.30 on.
    # k_vel is covered: /k/ resolves to the same g_vel target.
    'g_vel': (1.45, np.pi / 3,     ['JA', 'TCX', 'TCY', 'TBX', 'TBY']),
    'g_pal': (1.30, 5 * np.pi / 3, ['JA', 'TCY', 'TBX', 'TBY']),  # TCX removed: g_pal is palatal, not velar
}


# =============================================================================
# ALL_PHONEME_KEYS — Complete registry of phonemes recognized by the pipeline
# =============================================================================
# This set is used by the tokenizers (parsing.py, text_to_tract.py)
# to recognize valid symbols. It includes:
#   - The canonical keys of CONSONANT_TARGETS (voiced)
#   - The voiceless counterparts resolved by _normalize_consonant_key
#   - The special keys g_vel, g_pal, g, k
#   - All the vowels of VOWEL_TARGETS
# =============================================================================
_VOICELESS_KEYS = {'p', 't', 'k', 'f', 's', 'S', 'T', 'tS'}
ALL_CONSONANT_KEYS: Tuple[str, ...] = tuple(
    sorted(set(CONSONANT_TARGETS.keys()) | _VOICELESS_KEYS | {'g', 'k'})
)
ALL_PHONEME_KEYS = set(ALL_CONSONANT_KEYS) | set(VOWEL_TARGETS.keys())

# =============================================================================
# VOICED_CONSONANT_KEYS — voiced consonants (for pre-voicing V(t))
# =============================================================================
# Used by build_phrase_tract (V_from_blocks step): during cluster
# blocks, V(t) = 1 for voiced consonants (voicing bar of stops
# /b,d,g/, nasals, liquids, voiced fricatives), V(t) = 0 for
# voiceless ones. /h/ is treated as voiceless (glottis preset rel_amp≈0).
VOICED_CONSONANT_KEYS: frozenset = frozenset(
    set(ALL_CONSONANT_KEYS) - _VOICELESS_KEYS - {'h'}
)

# Consonantal nasals (VO = velum opening during their sub-interval)
NASAL_CONSONANT_KEYS: frozenset = frozenset({'m', 'n', 'N', 'J'})

# Nasal vowel: PARTIAL velum opening (TAG_TO_VO_TARGET
# ['nasalized'] = 0.5). VO=0 closed-velum baseline = -0.1.
VO_NASALIZED_VOWEL: float = 0.5


# =============================================================================
# Glottis presets (VTL geometric model)
# =============================================================================
# Each preset defines the 11 default glottis parameters.
# Speaker-dependent values can be overridden via speaker_config.
@dataclass
class GlottisPreset:
    """Glottis configuration for a phonation mode."""
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
        return np.array([
            self.f0,
            self.pressure,
            self.x_bottom,
            self.x_top,
            self.chink_area,
            self.lag,
            self.rel_amp,
            self.double_pulsing,
            self.pulse_skewness,
            self.f0_flutter,
            self.aspiration_strength,
        ], dtype=np.float64)

    def to_dict(self) -> Dict[str, float]:
        return {name: getattr(self, name) for name in GLOTTIS_PARAM_NAMES}


# --- Generic presets (speaker-independent, abstract tags) ---
GLOTTIS_PRESETS: Dict[str, GlottisPreset] = {
    'modal': GlottisPreset(
        name='modal',
        f0=120.0, pressure=800.0,
        x_bottom=0.0, x_top=0.0,
        chink_area=0.0, lag=0.0, rel_amp=1.0,
    ),
    'voiceless': GlottisPreset(
        name='voiceless',
        f0=120.0, pressure=400.0,
        x_bottom=1.0, x_top=1.0,
        chink_area=20.0, lag=0.0, rel_amp=0.0,
    ),
    'breathy': GlottisPreset(
        name='breathy',
        f0=120.0, pressure=600.0,
        x_bottom=0.3, x_top=0.5,
        chink_area=15.0, lag=0.0, rel_amp=0.6,
    ),
    'creaky': GlottisPreset(
        name='creaky',
        f0=80.0, pressure=1000.0,
        x_bottom=-0.2, x_top=-0.1,
        chink_area=0.0, lag=0.1, rel_amp=0.8,
        pulse_skewness=0.5, double_pulsing=0.3,
    ),
    'whisper': GlottisPreset(
        name='whisper',
        f0=120.0, pressure=500.0,
        x_bottom=0.8, x_top=1.0,
        chink_area=40.0, lag=0.0, rel_amp=0.0,
    ),
    'voiceless_fricative': GlottisPreset(
        name='voiceless_fricative',
        f0=120.0, pressure=600.0,
        x_bottom=0.7, x_top=0.9,
        chink_area=10.0, lag=0.0, rel_amp=0.1,
        aspiration_strength=10.0,
    ),
    'aspirated': GlottisPreset(
        name='aspirated',
        f0=120.0, pressure=700.0,
        x_bottom=0.5, x_top=0.8,
        chink_area=10.0, lag=0.0, rel_amp=0.3,
        aspiration_strength=15.0,
    ),
}


# =============================================================================
# JD3 glottis presets — values extracted from the JD3.speaker file
# =============================================================================
# These are the native values from the JD3 speaker file.
# They are used by the source branch for VTL synthesis.
# The names match the shapes of the geometric glottis model.
#
# VTL → GlottisPreset attribute mapping:
#   F0 → f0, PR → pressure, XB → x_bottom, XT → x_top,
#   CA → chink_area, PL → lag, RA → rel_amp, DP → double_pulsing,
#   PS → pulse_skewness, FL → f0_flutter, AS → aspiration_strength
#
# NOTE: the PR pressure is in dPa in VTL (native values ~7850-8000).
# =============================================================================
JD3_GLOTTIS_PRESETS: Dict[str, GlottisPreset] = {
    'default': GlottisPreset(
        name='default',
        f0=102.216, pressure=7850.264, lag=1.222,
        x_bottom=0.0102, x_top=0.0204, chink_area=0.050,
        rel_amp=1.000, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'modal': GlottisPreset(
        name='modal',
        f0=120.000, pressure=8000.000, lag=1.222,
        x_bottom=0.0102, x_top=0.0204, chink_area=0.050,
        rel_amp=1.000, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'stop': GlottisPreset(
        name='stop',
        f0=108.672, pressure=7999.997, lag=1.222,
        x_bottom=-0.0098, x_top=-0.0101, chink_area=-0.001,
        rel_amp=-0.204, double_pulsing=0.504,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'pressed': GlottisPreset(
        name='pressed',
        f0=120.000, pressure=8000.000, lag=1.222,
        x_bottom=0.0001, x_top=0.0102, chink_area=0.025,
        rel_amp=1.000, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'breathy': GlottisPreset(
        name='breathy',
        f0=102.216, pressure=7850.264, lag=1.222,
        x_bottom=0.0197, x_top=0.0305, chink_area=0.100,
        rel_amp=1.000, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'h': GlottisPreset(
        name='h',
        f0=108.672, pressure=8000.000, lag=1.222,
        x_bottom=0.0449, x_top=0.0452, chink_area=0.100,
        rel_amp=0.002, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'whisper': GlottisPreset(
        name='whisper',
        f0=120.000, pressure=8000.000, lag=0.880,
        x_bottom=0.0998, x_top=0.1002, chink_area=0.250,
        rel_amp=0.000, double_pulsing=0.000,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'hoarse': GlottisPreset(
        name='hoarse',
        f0=120.000, pressure=8000.000, lag=0.880,
        x_bottom=0.0204, x_top=0.0403, chink_area=0.160,
        rel_amp=1.000, double_pulsing=0.203,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'voiced-fricative': GlottisPreset(
        name='voiced-fricative',
        f0=143.675, pressure=0.000, lag=1.222,
        x_bottom=0.0501, x_top=0.0501, chink_area=0.100,
        rel_amp=1.000, double_pulsing=0.047,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'voiced-plosive': GlottisPreset(
        name='voiced-plosive',
        f0=143.675, pressure=0.000, lag=1.222,
        x_bottom=0.0102, x_top=0.0200, chink_area=0.100,
        rel_amp=1.000, double_pulsing=0.050,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'voiceless-fricative': GlottisPreset(
        name='voiceless-fricative',
        f0=104.960, pressure=8000.000, lag=1.222,
        x_bottom=0.1002, x_top=0.0998, chink_area=0.100,
        rel_amp=0.000, double_pulsing=0.046,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'voiceless-plosive': GlottisPreset(
        name='voiceless-plosive',
        f0=104.899, pressure=7999.327, lag=1.222,
        x_bottom=0.0998, x_top=0.0998, chink_area=0.100,
        rel_amp=0.000, double_pulsing=0.054,
        pulse_skewness=0.000, f0_flutter=0.000, aspiration_strength=0.000,
    ),
    'hoarse2': GlottisPreset(
        name='hoarse2',
        f0=120.000, pressure=8000.000, lag=0.880,
        x_bottom=-0.0098, x_top=-0.0098, chink_area=0.160,
        rel_amp=1.000, double_pulsing=0.203,
        pulse_skewness=0.500, f0_flutter=25.000, aspiration_strength=-10.000,
    ),
}


# =============================================================================
# Phonetic tag → glottis preset mapping (speaker-independent)
# =============================================================================
# Source: rapport_vecteur_VTL_400Hz.pdf, §6
# An abstract tag (<glottal=voiceless>) remains invariant.
# The actual VTL values are in GLOTTIS_PRESETS and can
# be recalibrated per speaker.
TAG_TO_GLOTTIS_PRESET: Dict[str, str] = {
    # Abstract tags → generic presets (speaker-independent)
    'voiced': 'modal',
    'voiceless': 'voiceless',
    'breathy': 'breathy',
    'creaky': 'creaky',
    'whisper': 'whisper',
    'modal': 'modal',
    'voiceless_fricative': 'voiceless_fricative',
    'aspirated': 'aspirated',
    # --- JD3 direct (VTL native shapes) ---
    'stop': 'stop',
    'pressed': 'pressed',
    'h': 'h',
    'hoarse': 'hoarse',
    'hoarse2': 'hoarse2',
    'voiced-fricative': 'voiced-fricative',
    'voiced-plosive': 'voiced-plosive',
    'voiceless-fricative': 'voiceless-fricative',
    'voiceless-plosive': 'voiceless-plosive',
    'default': 'default',
}

# Phonetic tag → velum target mapping (VO)
TAG_TO_VO_TARGET: Dict[str, float] = {
    'nasal': 1.0,       # Velum open
    'oral': 0.0,        # Velum closed
    'nasalized': 0.5,   # Velum partially open
    'denasal': 0.0,
}

# Phonetic tag → voicing value V(t) mapping in [0, 1]
TAG_TO_VOICING: Dict[str, float] = {
    'voiced': 1.0,
    'voiceless': 0.0,
    'breathy': 0.6,
    'creaky': 0.9,
    'whisper': 0.0,
    'aspirated': 0.0,   # V=0 during the aspiration phase
}


# =============================================================================
# Pressure and amplitude ranges for the E(t) effort model
# =============================================================================
@dataclass
class EffortBounds:
    """Bounds for deriving pressure and rel_amp from E(t).

    The default values match the VocalTractLab JD3 speaker.
    VTL subglottal pressure is in dPa (P_min ≈ 400 for
    whispering, P_max ≈ 8000 for a loud voice).
    """
    P_min: float = 400.0     # Minimum pressure (dPa) — whispering
    P_max: float = 8000.0    # Maximum pressure (dPa) — loud voice
    R_min: float = 0.3       # Minimum relative amplitude
    R_max: float = 1.2       # Maximum relative amplitude

EFFORT_DEFAULTS: EffortBounds = EffortBounds()


# =============================================================================
# Constants for the pulmonary Pexp timer (bursts and frication)
# =============================================================================
# Source: VTL 2.3 specs, session 12 (user architecture).
#
# The pulmonary Pexp timer is ADDITIVE and INDEPENDENT of the Berthommier
# kinematic Pexp (exponent of the arc cos(theta/2)^Pexp in polar.py).
#
# This timer modulates subglottal pressure for:
#   - Plosives: pressure peak at release (burst)
#   - Fricatives: pressure held during the constriction
#
# Pressure is computed in pulmonary_effort.py and does not interact
# with the Berthommier kinematic model.
# =============================================================================

# --- Fricatives (all, both voiced and voiceless) ---
FRICATIVE_KEYS: frozenset = frozenset({
    'f', 'v', 's', 'z', 'S', 'Z', 'T', 'D', 'C', 'X', 'R',
})

# Time constant for the pulmonary Pexp timer (ms)
TAU_PEXP_MS: float = 12.0

# Pexp pressure for fricatives (fraction of P_MAX, added)
PEXP_FRICATIVE_PRESSURE: float = 0.8

# Pexp pressure for plosive bursts (fraction of P_MAX, peak)
PEXP_BURST_PRESSURE: float = 1.0

# Burst peak duration (ms) — corresponds to a physiological ~5-10 ms
BURST_PEAK_DURATION_MS: float = 7.5

# Burst rise time (ms)
BURST_RISE_MS: float = 2.5

# Burst decay time (ms)
BURST_DECAY_MS: float = 15.0


# =============================================================================
# Virtual targets for plosives (high-speed occlusion/release)
# =============================================================================
# Source: VTL 2.3 specs, session 12.
#
# Plosives need an intermediate virtual target to force
# complete occlusion and fast release. This mechanism is
# analogous to the virtual targets for /l/ (speed_factor: 1.5) in timers.py.
#
# The virtual target forces rho to a minimal occlusion threshold that
# guarantees full tract closure for each place of articulation.
#
# The rho_occlusion values are derived from the CONSONANT_TARGETS targets:
#   - b/p: rho=1.06, occlusion threshold ~1.10 (labial, LD=0 required)
#   - d/t: rho=1.10, occlusion threshold ~1.15 (apical, TTY contact)
#   - g/k: rho=1.45 (g_vel), occlusion threshold ~1.45 (velar, raised TCY)
# =============================================================================

# Minimum TBY clamp for velar occlusion (g/k).
# Value derived from the COVTL coefficient: c1_TBY + c0_TBY.
# At rho=1.30 and theta=pi/3, the COVTL projection gives TBY ~ 0.77.
# This clamp guarantees TBY reaches the velar occlusion threshold.
TBY_VELAR_OCCLUSION_MIN: float = CO_VTL['TBY'][0] + CO_VTL['TBY'][1]  # c1 + c0 = 0.995485

# Maximum TCX clamp for velar occlusion (g/k, g_vel only).
# g_pal is excluded: its occlusion is palatal (anterior TCX), not velar.
# The vel/pal distinction is made via theta_vowel > pi (cf. projection.py).
# At rho=1.30, theta=60°, the COVTL projection gives TCX = +0.343 cm
# (tongue center too far anterior for velar contact).
# The clamp forces TCX into the posterior zone so the back of
# the tongue can contact the soft palate.
# Threshold determined by a VTL sweep over /ga/, /gu/, /go/ (velar zone 5-10 cm).
TCX_VELAR_OCCLUSION_MAX: float = -0.050

# Minimum TCY clamp for velar occlusion (g/k, g_vel only).
# At rho=1.30, theta=60°, the COVTL projection gives TCY = -0.923 cm
# (tongue center too low). The clamp raises TCY so the back
# of the tongue reaches the palate.
# Threshold determined jointly with TCX_VELAR_OCCLUSION_MAX.
TCY_VELAR_OCCLUSION_MIN: float = -0.225

# Minimal rho threshold to guarantee occlusion by place
# g/k: 1.45 = g_vel target (g_pal contexts stay at 1.30 and
# close via the raised c1(TCY)).
PLOSIVE_OCCLUSION_RHO: Dict[str, float] = {
    'b': 1.10, 'p': 1.10,   # Labial: LD must reach 0
    'd': 1.15, 't': 1.15,   # Apical: TTY contact, high TBX/TBY
    'g': 1.45, 'k': 1.45,   # Velar: g_vel at rho 1.45 (raised TCY)
}

# Virtual target parameters for plosives
# NOTE: inert downstream (metadata) — kinematics follow CONSONANT_TARGETS.
PLOSIVE_VIRTUAL_TARGETS: Dict[str, dict] = {
    'b': {
        'rho_virtual': 1.12,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.35,
        'rho_min_occlusion': 1.10,
    },
    'p': {
        'rho_virtual': 1.12,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.35,
        'rho_min_occlusion': 1.10,
    },
    'd': {
        'rho_virtual': 1.18,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.30,
        'rho_min_occlusion': 1.15,
    },
    't': {
        'rho_virtual': 1.18,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.30,
        'rho_min_occlusion': 1.15,
    },
    'g': {
        'rho_virtual': 1.45,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.30,
        'rho_min_occlusion': 1.45,
    },
    'k': {
        'rho_virtual': 1.45,
        'speed_factor': 2.0,
        'occlusion_duration_factor': 0.30,
        'rho_min_occlusion': 1.45,
    },
}


# =============================================================================
# Speaker configuration (JD3 default values)
# =============================================================================
@dataclass
class SpeakerConfig:
    """Speaker configuration for recalibrating presets.

    Makes tags speaker-independent at the phonetic level,
    and speaker-specific at the VTL level.

    When use_jd_presets=True, the native JD3 presets are used
    directly (values extracted from the .speaker file) instead of
    the generic presets.
    """
    name: str = 'JD3'
    f0_default: float = 102.216   # JD3 resting F0 from shape 'default'
    f0_range: Tuple[float, float] = (80.0, 200.0)
    # Use the native JD3 presets (extracted from the .speaker file)
    use_jd_presets: bool = True
    # Per-speaker glottis preset overrides
    preset_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Effort bounds overrides
    effort: EffortBounds = field(default_factory=lambda: EffortBounds(
        P_min=400.0, P_max=8000.0, R_min=0.3, R_max=1.2
    ))

    def get_preset(self, preset_name: str) -> GlottisPreset:
        """Return a preset, with speaker overrides applied.

        If use_jd_presets=True and the preset exists in JD3_GLOTTIS_PRESETS,
        uses the native JD3 value. Otherwise, falls back to GLOTTIS_PRESETS.
        """
        if self.use_jd_presets and preset_name in JD3_GLOTTIS_PRESETS:
            base = JD3_GLOTTIS_PRESETS[preset_name]
        elif preset_name in GLOTTIS_PRESETS:
            base = GLOTTIS_PRESETS[preset_name]
        else:
            # Fallback: create a default preset
            base = GlottisPreset(name=preset_name)

        if preset_name in self.preset_overrides:
            overrides = self.preset_overrides[preset_name]
            for key, value in overrides.items():
                setattr(base, key, value)
        return base
