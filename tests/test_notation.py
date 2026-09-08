# -*- coding: utf-8 -*-
"""Tests of the notation layer (pipeline/notation.py).

Complements the canonical core K tests (CDC_passerelle_IPA_SAMPA).
"""
import pytest

from vtl_synth.core.notation import is_vowel, normalize_text, unknown_chars


class TestNormalizeText:
    def test_vowels_unchanged(self):
        for v in 'aeiouyE O@269'.replace(' ', ''):
            assert normalize_text(v) == v

    def test_consonants_unchanged(self):
        # NB: 'r' absent — normalized to 'R' (see test_uvular_r_canonical)
        for c in 'bdfgjklmnpstvzSZJN':
            assert normalize_text(c) == c

    def test_uvular_r_canonical(self):
        # 'R' is the canonical form of the uvular: 'r' is normalized to 'R'
        assert normalize_text('R') == 'R'
        assert normalize_text('r') == 'R'

    def test_idempotent(self):
        for s in ['bonjour', 'ba da ga', 'E~', 'a~']:
            assert normalize_text(normalize_text(s)) == normalize_text(s)


class TestIsVowel:
    def test_vowel_keys(self):
        for v in ('a', 'e', 'i', 'o', 'u', 'y', 'E', 'O', '@', '2', '6', '9'):
            assert is_vowel(v), v

    def test_consonant_keys(self):
        for c in ('b', 'd', 'g', 'k', 'p', 't', 's', 'S', 'z', 'Z', 'R', 'l'):
            assert not is_vowel(c), c


class TestUnknownChars:
    def test_known_phrase_no_unknowns(self):
        assert unknown_chars('ba da ga') == []

    def test_unknown_char_reported(self):
        unk = unknown_chars('ba$x')
        assert '$' in unk
