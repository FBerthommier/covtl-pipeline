"""Non-regression tests for audit finding D-11 — pending point overwritten
at double pauses (syltraj).

Pre-fix behavior (covtl-pipeline @ 48442aa9): for "bi |" the tokenizer emits
GAP before PAUSE, so the anchor walk visits two consecutive pause nodes and
the term/term branch overwrote ``pending_pt`` with the neutral [0, 0] — the
terminal pause arc departed from the neutral instead of the preceding vowel,
with a 0.9082402563682233 VTL-unit jump (Hy parameter) at the decay→terminal
junction. The fix preserves the pending point when one is already held;
pause-arc departure is the preceding vowel (pause diphthong V_e → V_o,
arXiv:2307.02299 §2.2). Sequences without consecutive pause nodes are
byte-identical (hashes recorded on the pre-fix engine @ 48442aa9).
"""
import hashlib

import numpy as np
import pytest

from vtl_synth.core import syltraj
from vtl_synth.core.constants import VOWEL_TARGETS

TC = TV = 16  # audit harness gesture steps


def _build(seq):
    return syltraj.build_phrase_pval(seq, t_cons=TC, t_voy=TV, sampa_guard='off')


def _arcs(seq):
    """Recorded (departure, arrival) of every arc appended for ``seq``."""
    import vtl_synth.core.syltraj as syl

    out = []
    orig = syl._append_arc

    def spy(blocks, pt_dep, pt_arr, D, nu, K, Pexp):
        out.append((list(map(float, pt_dep)), list(map(float, pt_arr))))
        return orig(blocks, pt_dep, pt_arr, D, nu, K, Pexp)

    syl._append_arc = spy
    try:
        syl.build_phrase_pval(seq, t_cons=TC, t_voy=TV, sampa_guard='off')
    finally:
        syl._append_arc = orig
    return out


def test_double_pause_preserves_pending_point():
    """The terminal pause arc of "bi |" departs from the preceding vowel."""
    arcs = _arcs('bi |')
    vowel = np.array(VOWEL_TARGETS['i'], dtype=float)
    departure = np.array(arcs[-1][0], dtype=float)
    assert np.allclose(departure, vowel, atol=1e-9), (
        f'terminal arc departs from {departure.tolist()}, expected the '
        f'preceding vowel /i/ target {vowel.tolist()}')


def test_double_pause_continuity():
    """No trajectory discontinuity at double pauses (was 0.9082402563682233)."""
    for seq in ('bi |', 'bi | ba'):
        Pval, _, _, _ = _build(seq)
        d = np.abs(np.diff(Pval, axis=0)).max(axis=1)
        assert d.max() < 0.5, f'{seq!r}: max inter-step jump {d.max()!r}'


def test_pause_arity_unchanged():
    """The GAP-before-PAUSE tokenization (audit D-12) is preserved: "bi |"
    still walks two consecutive pause nodes, and the block schedule is
    unchanged ([initial 20, cluster 32, plateau 16, decay 16, terminal 32])."""
    _, blocks, nodes, _ = _build('bi |')
    tail = [n.kind for n in nodes[-2:]]
    assert tail == ['pause', 'pause'], f'expected two consecutive pause nodes, got {tail}'
    assert [b.n_steps for b in blocks] == [20, 32, 16, 16, 32]


# sha256 of the pre-fix Pval matrices (engine @ 48442aa9, float64 C-order) —
# the fix must not touch sequences without consecutive pause nodes.
_SINGLE_PAUSE_SHA = {
    'bi ba': '161494bd6b25e2ce4734fb5b06456610f8222779da7f687c4719e478452b4846',
    'bi.ba': '03fbee82929b4f9f752e9b83c22b4a089b96828597f4cde5c0b972eecd2d9c59',
}


@pytest.mark.parametrize('seq', ['bi ba', 'bi.ba'])
def test_single_pause_paths_unchanged(seq):
    Pval, _, _, _ = _build(seq)
    digest = hashlib.sha256(Pval.tobytes()).hexdigest()
    assert digest == _SINGLE_PAUSE_SHA[seq], (
        f'{seq!r}: Pval changed (sha256 {digest}) — single-pause paths must '
        f'stay byte-identical to the pre-fix engine @ 48442aa9')
