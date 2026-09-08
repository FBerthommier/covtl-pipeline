# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
notation.py — IPA-SAMPA notation normalization gateway
(CDC_passerelle_IPA_SAMPA.md — single source, cf. COVTL reference
reference: SIMPLE_TO_IPA table + feature-based classification).

Principle: an input symbol is RESOLVED BY TABLE, never fabricated.
All modules consume the canonical core K (keys of VOWEL_TARGETS /
CONSONANT_TARGETS) via this module; no local tables elsewhere.

Usage:
    from vtl_synth.core.notation import normalize_text, unknown_chars, is_vowel
    text_k = normalize_text(text)            # → K keys + '~' markers
    unknowns = unknown_chars(text)           # diagnostic
    is_vowel(key) -> bool                    # (handles the '~' marker)

A '~' suffixed to a vowel = NASAL vowel (rendered by partial VO
extension in build_phrase_tract).
"""

from __future__ import annotations

import re
import unicodedata

from .constants import VOWEL_TARGETS, CONSONANT_TARGETS

_TILDE = '\u0303'

# ==========================================================================
# Canonical core K
# ==========================================================================

VOWELS_K = frozenset(VOWEL_TARGETS.keys())
CONSONANTS_K = frozenset(CONSONANT_TARGETS.keys())
ALL_K = VOWELS_K | CONSONANTS_K

# ==========================================================================
# Conversion tables (to K)
# ==========================================================================

# Character/spelling alias → K (French accents, spelled uvular r…)
CHAR_ALIAS: dict = {
    'é': 'e', 'è': 'E', 'ê': 'E', 'ë': 'E', 'à': 'a', 'â': 'a',
    'î': 'i', 'ï': 'i', 'ô': 'o', 'ö': 'o', 'û': 'u', 'ù': 'u',
    'ü': 'u', 'ç': 's', 'É': 'e', 'È': 'E', 'À': 'a',
    'r': 'R',          # spelled r → French uvular
    'ɡ': 'g',          # IPA single-story g
    'H': 'ɥ',          # SAMPA H = glide ɥ (lowercase h = glottal)
}

# Nasal vowels: precomposed → oral key + '~'
NASAL_PRECOMPOSED: dict = {
    'ã': 'a~', 'ẽ': 'e~', 'ĩ': 'i~', 'õ': 'o~', 'ũ': 'u~',
}

# IPA + combining-tilde sequences → K key + '~' (nasal vowels)
_NASAL_SEQ = {
    'a' + _TILDE: 'a~', 'e' + _TILDE: 'e~', 'i' + _TILDE: 'i~',
    'o' + _TILDE: 'o~', 'u' + _TILDE: 'u~', 'ɛ' + _TILDE: 'E~',
    'ɔ' + _TILDE: 'O~', 'œ' + _TILDE: '9~', 'ə' + _TILDE: '@~',
    'ɑ' + _TILDE: 'a~', 'y' + _TILDE: 'y~', 'ø' + _TILDE: '2~',
    'E' + _TILDE: 'E~', 'O' + _TILDE: 'O~', '9' + _TILDE: '9~',
    '2' + _TILDE: '2~', 'a' + _TILDE: 'a~', '@' + _TILDE: '@~',
}

# Unicode IPA → K (single- and multi-character symbols)
IPA_TO_K: dict = {
    'ʃ': 'S', 'ʒ': 'Z', 'tʃ': 'tS', 'dʒ': 'dZ',
    'ŋ': 'N', 'ɲ': 'J', 'ʁ': 'R', 'ʀ': 'R',
    'œ': '9', 'ɛ': 'E', 'ɔ': 'O', 'ø': '2', 'ə': '@', 'ɑ': 'a',
    'θ': 'T', 'ð': 'D', 'χ': 'X', 'ç': 's', 'ɡ': 'g',
    'ʎ': 'J', 'ʟ': 'L',
}

# Unicode diphthongs (components) — kept from legacy
DIPHTHONG_UNICODE: dict = {
    'aɪ': 'aI', 'aʊ': 'aU', 'ɔɪ': 'OI', 'eɪ': 'eI', 'oʊ': 'oU',
    'ɪ': 'I', 'ʏ': 'Y', 'ʊ': 'U',
}

# ==========================================================================
# Normalization
# ==========================================================================

_REPLACE_ORDER: list = None


def _replace_order() -> list:
    """(source, destination) table sorted by decreasing length."""
    global _REPLACE_ORDER
    if _REPLACE_ORDER is None:
        table = {}
        table.update(_NASAL_SEQ)          # nasal sequences first
        table.update(IPA_TO_K)
        table.update(DIPHTHONG_UNICODE)
        table.update(CHAR_ALIAS)
        table.update(NASAL_PRECOMPOSED)
        _REPLACE_ORDER = sorted(table.items(), key=lambda x: -len(x[0]))
    return _REPLACE_ORDER


def normalize_text(text: str) -> str:
    """Normalize a string (IPA/SAMPA/accents) to K keys + '~'.

    - NFC (canonical compose/decompose);
    - nasal vowel sequences → key + '~';
    - IPA symbols → K keys;
    - accents/spellings → K keys;
    - separators ('.', '-', '|', space) and '~' are preserved.
    """
    text = unicodedata.normalize('NFC', text)
    for src, dst in _replace_order():
        if src in text:
            text = text.replace(src, dst)
    return text


def unknown_chars(text: str) -> list[str]:
    """Characters not recognized after normalization (excluding separators)."""
    normalized = normalize_text(text)
    known = ALL_K | {' ', '.', '-', '|', '~'}
    return sorted({ch for ch in normalized if ch not in known
                   and ch.strip()})


def is_vowel(key: str) -> bool:
    """Vowel predicate (handles the nasal '~' marker)."""
    return key.rstrip('~') in VOWELS_K


def is_nasal(key: str) -> bool:
    return key.endswith('~')
