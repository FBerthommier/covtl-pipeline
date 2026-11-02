# -*- coding: utf-8 -*-
"""Tests of the nasal_preproc gate (V1V2 nasal/oral hiatus fix).

The gate factorizes nasality out of the syltraj parametric space:
hiatus-member nasal vowels are oralized in the motor chain (the
background arc then carries the base diphthong transition on oral
targets), and nasality is re-injected downstream in the orthogonal
velar-port control space (VO extension + existing 20 ms timer).

These tests lock in:
  * the surgical scope of the oralization (hiatus members ONLY —
    held nasal vowels keep the plateau path);
  * the tokenizer round-trip safety (fallback on mismatch);
  * the runs ↔ background-groups alignment and the VO intervals,
    including the merge of adjacent nasal slots (V~.V~);
  * the non-perturbation: oral chains and held nasals produce
    bit-identical tracts, only the VO column may change;
  * the effective nasality after synthesis (VO >= 0.4 on the nasal
    halves, back to baseline on the oral half).
"""
import numpy as np
import pytest

from vtl_synth.core.syltraj import build_phrase_pval
from vtl_synth.core.nasal_preproc import (
    split_nasal_hiatus,
    nasal_hiatus_intervals,
    vo_nasal_segment,
    get_last_nasal_plan,
)


# ---------------------------------------------------------------------------
# Split: surgical oralization
# ---------------------------------------------------------------------------

class TestSplitNasalHiatus:
    def test_oral_chain_unchanged(self):
        for ph in ('ta.ata', 'kOma.a.le.vu', 'ba na', 'i.a.avi'):
            motor, plan = split_nasal_hiatus(ph)
            assert motor == ph
            assert plan['events'] == []

    def test_held_nasal_unchanged(self):
        # kOma~: the nasal vowel has no vowel neighbour -> plateau path
        motor, plan = split_nasal_hiatus('kOma~')
        assert motor == 'kOma~'
        assert plan['events'] == []
        assert plan['runs'] == []

    def test_nasal_oral_hiatus_oralized(self):
        motor, plan = split_nasal_hiatus('ta~.ata')
        assert motor == 'ta.ata'
        assert plan['events'] == [{'run': 0, 'member': 0, 'key': 'a'}]

    def test_oral_nasal_hiatus_oralized(self):
        motor, plan = split_nasal_hiatus('ta.a~ta')
        assert motor == 'ta.ata'
        assert plan['events'] == [{'run': 0, 'member': 1, 'key': 'a'}]

    def test_both_nasal_members(self):
        motor, plan = split_nasal_hiatus('ta~.a~ta')
        assert motor == 'ta.ata'
        assert plan['events'] == [
            {'run': 0, 'member': 0, 'key': 'a'},
            {'run': 0, 'member': 1, 'key': 'a'}]

    def test_vvv_run_last_member(self):
        motor, plan = split_nasal_hiatus('i.a.a~vi')
        assert motor == 'i.a.avi'
        assert plan['events'] == [{'run': 0, 'member': 2, 'key': 'a'}]
        assert len(plan['runs'][0]) == 3

    def test_documented_case(self):
        motor, plan = split_nasal_hiatus('kOma~.a.le.vu')
        assert motor == 'kOma.a.le.vu'
        assert plan['events'] == [{'run': 0, 'member': 0, 'key': 'a'}]

    def test_mixed_held_and_hiatus_nasals(self):
        # a~ held (plateau) at the end, 9~ in hiatus at the start
        motor, plan = split_nasal_hiatus('9~.a.ta~')
        assert motor == '9.a.ta~'
        assert plan['events'] == [{'run': 0, 'member': 0, 'key': '9'}]

    @pytest.mark.parametrize('phrase', [
        'ta~.ata', 'ta.a~ta', 'ta~.a~ta', '9~.a~', 'mO~.O~kl',
        'i.a.a~vi', 'la.O~zjEm', 'pao~', 'a~aR.diR', 'a~y.Se',
    ])
    def test_round_trip_tokens(self, phrase):
        # the motor chain must re-tokenize to the original tokens with
        # the '~' stripped exactly at the oralized positions
        _, plan = split_nasal_hiatus(phrase)
        assert not plan['fallback']
        assert plan['motor']            # non-empty
        nodes = plan['nodes_view']
        # node count is preserved (oralization never adds/removes nodes)
        from vtl_synth.core.nasal_preproc import _tokenize
        n_orig = sum(1 for t in _tokenize(phrase) if t != 'DOT')
        assert len(nodes) == n_orig


# ---------------------------------------------------------------------------
# Runs <-> background groups: VO intervals
# ---------------------------------------------------------------------------

class TestNasalHiatusIntervals:
    # fr pipeline profile: t_voy = 120 ms = 12 steps @100 Hz
    # (a direct call without t_voy would use the engine default,
    # 60 ms -> 2-step vowels, truncated nasalization as for the
    # plateaus — same behavior as the existing path)
    T_VOY = 12

    def _blocks(self, phrase):
        _, blocks, _, _ = build_phrase_pval(phrase, t_voy=self.T_VOY,
                                            sampa_guard='off')
        return blocks

    def test_first_half(self):
        # ta~.ata: background 2*T_voy=24 steps; a~ owns the FIRST half
        _, plan = split_nasal_hiatus('ta~.ata')
        blocks = self._blocks(plan['motor'])
        ivs = nasal_hiatus_intervals(blocks, plan, t_voy=self.T_VOY)
        assert len(ivs) == 1
        t0, t1, key = ivs[0]
        assert key == 'a'
        assert t1 - t0 == self.T_VOY
        bg = [b for b in blocks if b.kind == 'background'][0]
        off = sum(b.n_steps for b in blocks[:blocks.index(bg)])
        assert t0 == off and t1 == off + bg.n_steps // 2

    def test_second_half(self):
        _, plan = split_nasal_hiatus('ta.a~ta')
        blocks = self._blocks(plan['motor'])
        ivs = nasal_hiatus_intervals(blocks, plan, t_voy=self.T_VOY)
        assert len(ivs) == 1
        t0, t1, _ = ivs[0]
        bg = [b for b in blocks if b.kind == 'background'][0]
        off = sum(b.n_steps for b in blocks[:blocks.index(bg)])
        assert t0 == off + bg.n_steps // 2 and t1 == off + bg.n_steps

    def test_adjacent_nasal_slots_merged(self):
        # 9~.a~: both halves nasal -> ONE merged interval (the velum
        # must not close between the two nasal halves)
        _, plan = split_nasal_hiatus('9~.a~')
        blocks = self._blocks(plan['motor'])
        ivs = nasal_hiatus_intervals(blocks, plan, t_voy=self.T_VOY)
        assert len(ivs) == 1
        t0, t1, key = ivs[0]
        assert t1 - t0 == 2 * self.T_VOY            # whole background
        assert key == '9+a'

    def test_vvv_last_member_interval(self):
        _, plan = split_nasal_hiatus('i.a.a~vi')
        blocks = self._blocks(plan['motor'])
        ivs = nasal_hiatus_intervals(blocks, plan, t_voy=self.T_VOY)
        assert len(ivs) == 1
        t0, t1, _ = ivs[0]
        assert t1 - t0 == self.T_VOY
        bgs = [b for b in blocks if b.kind == 'background']
        total_bg = sum(b.n_steps for b in bgs)
        off = sum(b.n_steps for b in blocks[:blocks.index(bgs[0])])
        assert t1 == off + total_bg                 # last slot of the run

    def test_no_events_no_intervals(self):
        _, plan = split_nasal_hiatus('ta.ata')
        blocks = self._blocks('ta.ata')
        assert nasal_hiatus_intervals(blocks, plan, t_voy=self.T_VOY) == []

    def test_t_voy_derived_from_plateaus(self):
        _, plan = split_nasal_hiatus('ta~.ata')
        blocks = self._blocks('ta.ata')
        ivs = nasal_hiatus_intervals(blocks, plan, t_voy=None)
        assert len(ivs) == 1 and ivs[0][1] - ivs[0][0] == self.T_VOY


# ---------------------------------------------------------------------------
# VO ramp (same shape as the plateau path)
# ---------------------------------------------------------------------------

class TestVoNasalSegment:
    def test_shape_and_target(self):
        seg = vo_nasal_segment(12, 0.5)
        assert len(seg) == 12
        assert seg.max() == pytest.approx(0.5)
        assert seg[0] == pytest.approx(-0.1)
        assert seg[-1] == pytest.approx(-0.1)

    def test_ramp_bounds(self):
        seg = vo_nasal_segment(20, 0.5)
        # ramp = min(max(2, 4), 20//4) = 4 samples
        assert seg[3] == pytest.approx(0.5)
        assert seg[-4] == pytest.approx(0.5)

    def test_tiny_segment_valid(self):
        seg = vo_nasal_segment(1, 0.5)
        assert len(seg) == 1 and np.isfinite(seg).all()


# ---------------------------------------------------------------------------
# Synthesis: effective nasality + non-perturbation
# ---------------------------------------------------------------------------

VO_COL = 7


def _read_tract(path):
    rows, started = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# ---'):
            started = True
            continue
        if not started or not line.strip() or line.startswith('# sample'):
            continue
        rows.append([float(x) for x in line.split()])
    return np.asarray(rows)


class TestSynthesisNasality:
    """build_phrase_tract level (needs the installed speaker)."""

    @pytest.fixture(scope='class')
    def tracts(self, tmp_path_factory):
        from vtl_synth.core.build_phrase_tract import build_phrase_tract
        out = {}
        d = tmp_path_factory.mktemp('tr')
        for rid, ph in (('H0', 'ta.ata'), ('H1', 'ta~.ata'),
                        ('H2', 'ta.a~ta'), ('H3', 'ta~.a~ta'),
                        ('T3', 'kOma~')):
            data = build_phrase_tract(ph, phrase_id=1, label=rid,
                                      output_dir=str(d), verbose=False,
                                      t_cons=14, t_voy=12,
                                      return_data=True)
            out[rid] = data[0]
        return out

    def test_oral_baseline_vo_closed(self, tracts):
        # H0: no nasal vowel at all -> VO pinned at the baseline
        assert np.allclose(tracts['H0'][:, VO_COL], -0.1)

    def test_nasality_realized_on_nasal_half(self, tracts):
        # H1: a~ owns the first half of the background; after the 20 ms
        # timer the smoothed VO must reach >= 0.4 there (healthy
        # plateau reference: 0.49-0.50)
        plan = get_last_nasal_plan()
        assert plan is not None
        vo = tracts['H1'][:, VO_COL]
        assert vo.max() >= 0.4

    def test_vo_returns_to_baseline_on_oral_half(self, tracts):
        # H1: second half of the background = oral /a/ -> VO back to
        # the closed baseline
        vo = tracts['H1'][:, VO_COL]
        assert vo[-1] == pytest.approx(-0.1, abs=0.02)

    def test_held_nasal_unchanged(self, tracts):
        # T3 kOma~: plateau path (existing) — max VO on the healthy
        # plateau still ~0.5
        vo = tracts['T3'][:, VO_COL]
        assert vo.max() >= 0.4

    def test_minimal_pairs_differ(self, tracts):
        # the byte-identity defect (audit §4.5) is inverted: the four
        # minimal pairs must differ (at least in the VO column)
        h0, h1, h2, h3 = (tracts[k][:, VO_COL] for k in ('H0', 'H1', 'H2', 'H3'))
        assert not np.array_equal(h0, h1)
        assert not np.array_equal(h0, h2)
        assert not np.array_equal(h0, h3)
        assert not np.array_equal(h1, h2)
        assert not np.array_equal(h1, h3)
        assert not np.array_equal(h2, h3)

    def test_parametric_space_identical(self, tracts):
        # CORE of the fix: outside the VO column the four minimal
        # pairs share the SAME parametric trajectory (oral base
        # diphthong) — syltraj's elaboration is untouched
        cols = [c for c in range(tracts['H0'].shape[1]) if c != VO_COL]
        for other in ('H1', 'H2', 'H3'):
            assert tracts[other].shape == tracts['H0'].shape
            for c in cols:
                assert np.array_equal(tracts['H0'][:, c], tracts[other][:, c]), \
                    f'column {c} differs between H0 and {other}'


# ---------------------------------------------------------------------------
# P6 — Portuguese: nasal diphthongs, inter-word boundaries, inert gate
# ---------------------------------------------------------------------------

class TestP6Portuguese:
    """Mission P6 §7.1 — pt nasal keys ride the SAME gate (cão -> k@~w,
    sem -> s@~j, algum -> algu~…). The pt lexicon has NO intra-word
    V~.V (0/35690 words: a nasal vowel is never adjacent to an oral
    vowel inside a word), so the intra-word S4 situation is covered by
    the H minimal pairs above (direct SAMPA input)."""

    def test_pt_nasal_diphthong_is_hold(self):
        # 'cão' -> k@~w : the nasal vowel is followed by a GLIDE (w),
        # not by a vowel -> no hiatus, plateau path, gate inert
        motor, plan = split_nasal_hiatus('k@~w')
        assert motor == 'k@~w'
        assert plan['events'] == []
        assert plan['runs'] == []

    def test_pt_inter_word_nasal_oral(self):
        # 'acauã ele' -> kaw@~.e.l@ : hiatus @~.e across the word dot
        motor, plan = split_nasal_hiatus('kaw@~.e.l@')
        assert motor == 'kaw@.e.l@'
        assert plan['events'] == [{'run': 0, 'member': 0, 'key': '@'}]
        runs = plan['runs']
        assert [m['nasal'] for run in runs for m in run] == [True, False]

    def test_pt_inter_word_oral_nasal(self):
        # 'ele um' -> e.l@.u~ : hiatus @.u~ (oral -> nasal)
        motor, plan = split_nasal_hiatus('e.l@.u~')
        assert motor == 'e.l@.u'
        assert plan['events'] == [{'run': 0, 'member': 1, 'key': 'u'}]
        runs = plan['runs']
        assert [m['nasal'] for run in runs for m in run] == [False, True]

    def test_pt_final_nasal_plateau_unchanged(self):
        # 'atum' -> @tu~ : word-final nasal -> plateau path, gate inert
        motor, plan = split_nasal_hiatus('@tu~')
        assert motor == '@tu~'
        assert plan['events'] == []

    def test_p6_gate_inert_without_tilde(self):
        # es / it / de / en emit no '~' at all: the gate is structurally
        # inert on their g2p outputs (mission §7.2 sweep, engine side).
        # The samples are given in the ENGINE's normalized conventions
        # (the pt-style normalization maps ɡ->g, ɾ->R, ə->e); the gate
        # re-normalizes nothing and returns the phrase unchanged when no
        # tilde is present.
        from vtl_synth.core.syltraj import _normalize_word as _syl_norm
        from vtl_synth.core.continuous import _normalize_ipa
        for ph in ('el.pe.Ro.beRDe', 'il.gat.to.neRo', 'das.gRy:.n@.haUs',
                   'd@.gri:n.tri:'):
            phn = _normalize_ipa(_syl_norm(ph))
            motor, plan = split_nasal_hiatus(phn)
            assert motor == phn
            assert plan['events'] == []
