# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
language_vowel_sets.py
======================
Per-language vowel inventories for automatic calibration.

Each entry contains:
  - ``vowels``: dict {engine key → (expected_F1, expected_F2, cardinal_θ, description)}
    The F1/F2 formants are reference values for an average male
    speaker of the language (in Hz). The cardinal_θ angle is the
    angular position in Maeda's vowel plane (in radians), inherited
    from timit-to-maeda for the supported languages.
  - ``cardinal_corners``: the 3 corners of the vowel triangle
    (keys of the extreme vowels, usually /a/ /i/ /u/).
  - ``schwa``: key of the schwa (center of the triangle), or None.

The inventories are extensible: a contributor can add a new
language by creating a new VOWEL_SETS['xx'] entry.

Formant references:
  - FR : Fant (1973), Rastatter (1980), Calliope (1989)
  - EN : Peterson & Barney (1952), Hillenbrand et al. (1995)
  - ES : Quilis (1981), Bradlow (1996)
  - DE : Jørgensen (1969), Simpson (2009)
  - IT : Ferrero et al. (1978)
  - PT : Delgado-Martins (1999), Escudero et al. (2009)
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Tuple, List, Optional


# Type alias: (F1, F2, theta_rad, description)
VowelEntry = Tuple[float, float, float, str]


VOWEL_SETS: Dict[str, dict] = {
    # =====================================================================
    # Français
    # =====================================================================
    'fr': {
        'display_name': 'Français',
        'cardinal_corners': ['a', 'i', 'u'],
        'schwa': '@',
        'vowels': {
            # Cardinal oral vowels (timit-to-maeda angles)
            'i':  (280, 2200, 5 * np.pi / 3,     'antérieure haute'),         # 300°
            'e':  (380, 2000, 3 * np.pi / 2,     'antérieure mi-haute'),      # 270°
            'E':  (530, 1700, 4 * np.pi / 3,     'antérieure mi-basse'),      # 240°
            'a':  (700, 1100, np.pi,             'centrale basse'),           # 180°
            'O':  (570, 870,  2 * np.pi / 3,     'postérieure mi-basse'),     # 120°
            'o':  (450, 800,  np.pi / 2,         'postérieure mi-haute'),     #  90°
            'u':  (300, 870,  np.pi / 3,         'postérieure haute'),        #  60°
            'y':  (290, 1800, 5.5 * np.pi / 3,    'antérieure haute arrondie'),# 330°
            '2':  (370, 1500, 5.5 * np.pi / 3,    'antérieure mi-haute arrondie /ø/'),  # 330°
            # Nasal vowels (no cardinal angle — interpolated from the oral ones)
            '6':  (500, 1500, np.pi,             'nasale mi-antérieure /œ/'), # 180° approx
            '9':  (500, 1500, np.pi,             'nasale mi-antérieure /œ̃/'),
            # Schwa (center of the triangle, computed automatically)
            '@':  (500, 1500, np.pi,             'schwa /ə/'),
        },
    },

    # =====================================================================
    # English
    # =====================================================================
    'en': {
        'display_name': 'English',
        'cardinal_corners': ['a', 'i', 'u'],
        'schwa': '@',
        'vowels': {
            # English vowels (Peterson & Barney 1952)
            'i':  (300, 2200, 5 * np.pi / 3,     'high front tense /iː/'),    # 300°
            'I':  (400, 1800, 5 * np.pi / 3,     'high front lax /ɪ/'),        # 300° (rho plus bas)
            'e':  (450, 2000, 3 * np.pi / 2,     'mid front /eɪ/'),            # 270°
            'E':  (570, 1800, 4 * np.pi / 3,     'mid-low front /ɛ/'),         # 240°
            '{':  (660, 1700, np.pi,             'low front /æ/'),             # 180°
            'a':  (730, 1100, np.pi,             'low central /ɑː/'),         # 180°
            'O':  (570, 870,  2 * np.pi / 3,     'mid-low back /ɔː/'),         # 120°
            'o':  (450, 800,  np.pi / 2,         'mid back /oʊ/'),            #  90°
            'U':  (440, 1000, np.pi / 3,         'high back lax /ʊ/'),        #  60°
            'u':  (300, 870,  np.pi / 3,         'high back tense /uː/'),     #  60°
            '@':  (500, 1500, np.pi,             'schwa /ə/'),
            'V':  (600, 1200, np.pi,             'mid-central /ʌ/'),
        },
    },

    # =====================================================================
    # Español
    # =====================================================================
    'es': {
        'display_name': 'Español',
        'cardinal_corners': ['a', 'i', 'u'],
        'schwa': None,  # l'espagnol n'a pas de schwa phonologique
        'vowels': {
            # Spanish vowels (Quilis 1981)
            'i':  (280, 2300, 5 * np.pi / 3,     'alta anterior /i/'),        # 300°
            'e':  (400, 1900, 3 * np.pi / 2,     'media anterior /e/'),       # 270°
            'E':  (520, 1700, 4 * np.pi / 3,     'media-baja anterior /ɛ/'),  # 240°
            'a':  (700, 1100, np.pi,             'baja central /a/'),         # 180°
            'O':  (570, 970,  2 * np.pi / 3,     'media-baja posterior /ɔ/'),# 120°
            'o':  (450, 830,  np.pi / 2,         'media posterior /o/'),      #  90°
            'u':  (320, 780,  np.pi / 3,         'alta posterior /u/'),       #  60°
        },
    },

    # =====================================================================
    # Deutsch
    # =====================================================================
    'de': {
        'display_name': 'Deutsch',
        'cardinal_corners': ['a', 'i', 'u'],
        'schwa': '@',
        'vowels': {
            # German vowels (Jørgensen 1969, Simpson 2009)
            'i':  (280, 2200, 5 * np.pi / 3,     'high front tense /iː/'),    # 300°
            'I':  (350, 1900, 5 * np.pi / 3,     'high front lax /ɪ/'),
            'e':  (370, 2100, 3 * np.pi / 2,     'mid front tense /eː/'),     # 270°
            'E':  (520, 1750, 4 * np.pi / 3,     'mid-low front /ɛː/'),       # 240°
            'a':  (690, 1100, np.pi,             'low central /aː/'),         # 180°
            'O':  (560, 890,  2 * np.pi / 3,     'mid-low back /ɔ/'),         # 120°
            'o':  (430, 770,  np.pi / 2,         'mid back tense /oː/'),      #  90°
            'U':  (410, 950,  np.pi / 3,         'high back lax /ʊ/'),
            'u':  (300, 870,  np.pi / 3,         'high back tense /uː/'),    #  60°
            'y':  (290, 1750, 5.5 * np.pi / 3,    'high front rounded /yː/'),# 330°
            'Y':  (350, 1600, 5.5 * np.pi / 3,    'high front rounded lax /ʏ/'),
            '2':  (380, 1500, 5.5 * np.pi / 3,    'mid front rounded /øː/'),# 330°
            '9':  (500, 1400, 5.5 * np.pi / 3,    'mid front rounded lax /œ/'),
            '@':  (500, 1400, np.pi,             'schwa /ə/'),
        },
    },

    # =====================================================================
    # Italiano
    # =====================================================================
    'it': {
        'display_name': 'Italiano',
        'cardinal_corners': ['a', 'i', 'u'],
        'schwa': None,  # l'italien n'a pas de schwa phonologique
        'vowels': {
            # Italian vowels (Ferrero et al. 1978; average male)
            'i':  (280, 2250, 5 * np.pi / 3,     'anteriore alta /i/'),      # 300°
            'e':  (400, 1950, 3 * np.pi / 2,     'media anteriore /e/'),     # 270°
            'E':  (550, 1750, 4 * np.pi / 3,     'aperta anteriore /ɛ/'),    # 240°
            'a':  (700, 1150, np.pi,             'centrale bassa /a/'),      # 180°
            'O':  (580, 950,  2 * np.pi / 3,     'aperta posteriore /ɔ/'),   # 120°
            'o':  (450, 850,  np.pi / 2,         'media posteriore /o/'),    #  90°
            'u':  (310, 800,  np.pi / 3,         'posteriore alta /u/'),     #  60°
        },
    },

    # =====================================================================
    # Português (europeu)
    # =====================================================================
    'pt': {
        'display_name': 'Português',
        'cardinal_corners': ['a', 'i', 'u'],
        # No DERIVED schwa: '@' (/ɐ/) is a full-fledged vowel in
        # European Portuguese (post-tonic) — it is calibrated like
        # the other vowels, not as the center of the triangle.
        'schwa': None,
        'vowels': {
            # Portuguese vowels (Delgado-Martins 1999; Escudero et
            # al. 2009 — average male; nasals are rendered with the
            # engine's '~' convention: a~, e~, i~, o~, u~, @~)
            'i':  (280, 2200, 5 * np.pi / 3,     'anterior alta /i/'),       # 300°
            'e':  (400, 2000, 3 * np.pi / 2,     'semiaberta anterior /e/'), # 270°
            'E':  (550, 1800, 4 * np.pi / 3,     'aberta anterior /ɛ/'),     # 240°
            'a':  (700, 1150, np.pi,             'central /a/'),             # 180°
            '@':  (600, 1400, np.pi,             'central média /ɐ/'),       # 180° (rho propre)
            'O':  (580, 950,  2 * np.pi / 3,     'aberta posterior /ɔ/'),    # 120°
            'o':  (430, 830,  np.pi / 2,         'semiaberta posterior /o/'),#  90°
            'u':  (310, 800,  np.pi / 3,         'posterior alta /u/'),      #  60°
        },
    },
}


# =====================================================================
# Helpers
# =====================================================================

def get_vowel_set(lang: str) -> dict:
    """Returns the vowel inventory of a language."""
    lang = lang.lower()
    if lang not in VOWEL_SETS:
        available = ', '.join(sorted(VOWEL_SETS.keys()))
        raise KeyError(f"language {lang!r} not in VOWEL_SETS; available: {available}")
    return VOWEL_SETS[lang]


def list_supported_languages() -> list:
    """Returns the sorted list of supported language codes."""
    return sorted(VOWEL_SETS.keys())


def get_cardinal_corners(lang: str) -> List[str]:
    """Returns the 3 corners of the language's vowel triangle."""
    return get_vowel_set(lang)['cardinal_corners']


def get_schwa_key(lang: str) -> Optional[str]:
    """Returns the schwa key of the language, or None."""
    return get_vowel_set(lang).get('schwa')


def get_vowel_targets(lang: str) -> Dict[str, Tuple[float, float, float, str]]:
    """Returns the language's {key → (F1, F2, theta, description)} dict."""
    return get_vowel_set(lang)['vowels']
