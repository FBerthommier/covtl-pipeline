# -*- coding: utf-8 -*-
"""Tests of the syltraj engine (trajectory and block structure).

ACTIVE engine (engine='syl'). These tests lock in the
structure the engine must produce, independently of the fine values.
"""
import numpy as np
import pytest

from vtl_synth.core.syltraj import build_phrase_pval


class TestBuildPhrasePval:
    def test_shapes_and_finiteness(self):
        pval, blocks, nodes, anchors = build_phrase_pval('ba')
        assert pval.ndim == 2
        assert pval.shape[1] == 15          # 15 params COVTL
        assert pval.shape[0] > 0
        assert np.isfinite(pval).all()
        assert len(blocks) == len(pval) or sum(b.n_steps for b in blocks) \
            == pval.shape[0]

    @pytest.mark.parametrize('phrase', ['ba', 'ta', 'kadi'])
    def test_block_steps_match_pval(self, phrase):
        pval, blocks, _, _ = build_phrase_pval(phrase)
        assert sum(b.n_steps for b in blocks) == pval.shape[0]

    def test_ba_has_plateau_and_arc_blocks(self):
        _, blocks, _, _ = build_phrase_pval('ba')
        kinds = {b.kind for b in blocks}
        assert 'plateau' in kinds           # vocalic nucleus
        assert 'arc' in kinds or 'attack' in kinds or 'decay' in kinds

    def test_two_words_two_vowel_plateaus(self):
        # NB: the inter-word pause is added at the build_phrase_tract level,
        # not in syltraj (which chains words together) — so we check for
        # one vocalic plateau per vowel.
        pval, blocks, _, _ = build_phrase_pval('ba da')
        assert np.isfinite(pval).all()
        kinds = [b.kind for b in blocks]
        assert kinds.count('plateau') == 2, kinds

    def test_nodes_anchors_consistent(self):
        _, blocks, nodes, anchors = build_phrase_pval('bada')
        assert len(nodes) > 0
        assert len(anchors) > 0
        # each anchor points to a valid node index
        # (the terminal 'synth' anchor may point to the sentinel == len(nodes))
        for a in anchors:
            assert a.i <= len(nodes)

    def test_deterministic(self):
        p1, b1, _, _ = build_phrase_pval('ba')
        p2, b2, _, _ = build_phrase_pval('ba')
        assert np.array_equal(p1, p2)
        assert len(b1) == len(b2)
