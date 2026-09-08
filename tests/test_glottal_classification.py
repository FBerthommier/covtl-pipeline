# -*- coding: utf-8 -*-
"""Tests of glottal classification (pipeline/glottal_source.py).

Locks in the BUG-ACTIVE-001 (real .voice field) and
BUG-ACTIVE-002 (distinct 'voiceless-plosive' preset) fixes.
"""
import pytest

from vtl_synth.core.glottal_source import (
    VALID_SHAPES,
    classify_segment_events,
    glottal_shape_for_segment,
)
from vtl_synth.core.prosody_source import Segment


def _seg(key, voice, kind='C'):
    return Segment(key=key, kind=kind, t_start=0.0, t_end=60.0, voice=voice)


class TestGlottalShapeForSegment:
    @pytest.mark.parametrize('key', ['p', 't', 'k'])
    def test_voiceless_plosive_uses_dedicated_preset(self, key):
        # BUG-ACTIVE-002: distinct JD3 preset, not the fricative fallback
        assert glottal_shape_for_segment(key, 0.0) == 'voiceless-plosive'

    @pytest.mark.parametrize('key', ['b', 'd', 'g'])
    def test_voiced_plosive_modal_prevoicing(self, key):
        # C1-C3: glottis in phonatory configuration during the closure
        assert glottal_shape_for_segment(key, 1.0) == 'modal'

    def test_voiceless_fricative(self):
        assert glottal_shape_for_segment('s', 0.0) == 'voiceless-fricative'

    def test_voiced_fricative(self):
        assert glottal_shape_for_segment('z', 1.0) == 'voiced-fricative'

    @pytest.mark.parametrize('key', ['a', 'e', 'i', 'o', 'u'])
    def test_vowels_modal(self, key):
        assert glottal_shape_for_segment(key, 1.0) == 'modal'

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError):
            glottal_shape_for_segment('$', 1.0)

    def test_all_shapes_in_valid_vocabulary(self):
        for key, voicing in [('p', 0.0), ('b', 1.0), ('s', 0.0), ('z', 1.0),
                             ('a', 1.0), ('m', 1.0)]:
            assert glottal_shape_for_segment(key, voicing) in VALID_SHAPES


class TestClassifySegmentEvents:
    def test_voice_field_is_read(self):
        # BUG-ACTIVE-001: Segment has no .voicing — the real field is
        # .voice (bool). A voiceless segment must no longer come out 'voiced'.
        events = classify_segment_events([
            _seg('s', voice=False), _seg('z', voice=True)])
        labels = [label for label, _ in events]
        assert labels == ['voiceless-fricative', 'voiced-fricative']

    def test_vowel_kind_forces_modal(self):
        events = classify_segment_events([_seg('a', voice=False, kind='V')])
        assert events[0][0] == 'modal'

    def test_events_sorted_by_frame(self):
        segs = [_seg('z', voice=True), _seg('s', voice=False)]
        segs[1].t_start, segs[1].t_end = 0.0, 60.0
        segs[0].t_start, segs[0].t_end = 60.0, 120.0
        frames = [f for _, f in classify_segment_events(segs)]
        assert frames == sorted(frames)
