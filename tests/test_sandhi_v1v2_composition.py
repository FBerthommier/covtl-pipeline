# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Composition test — inter-word sandhi (covtl-sandhi) x the V1V2 nasal
gate (core/nasal_preproc.py).

Why this test exists
--------------------
The V1V2 corpus (AUDIT_V1V2) was run with the sandhi options OFF: the
two layers were never composed on the same phrase. The composition is
expected to be *complementary*, not conflicting:

* where inter-word sandhi fires, it removes exactly the phrases the
  V1V2 gate exists for — the linking consonant is inserted between the
  nasal vowel and the following vowel, so the V~.V hiatus of the
  isolated form (« mon ami » mO~.a.mi -> mO~.na.mi) disappears and the
  gate becomes a no-op;
* where sandhi does not fire (off baseline, pause '%', unlinked pair),
  the hiatus survives and the gate keeps doing its job;
* scope note: only fr carries nasal vowels in this framework (the es/
  it/pt/de g2ps emit no '~'), so the composition cases are French;
  and called standalone, split_nasal_hiatus is conservative on
  '%'-bearing strings (identity fallback — the pause splitting happens
  upstream in build_phrase_tract, before the gate).

Two parts:

  (a) always runs — the V1V2 layer alone, on literal SAMPA forms
      (isolated vs linked), no rule package needed;
  (b) runs only when the covtl-sandhi Branch B rule package is
      importable (pip-installed, or copied over the hook stub) — the
      actual composition through the package gateway
      (apply_sandhi_text / apply_sandhi_sampa) followed by
      split_nasal_hiatus.

Engine-free: operates on the SAMPA strings at the
build_phrase_tract input boundary (the gate's real input).
"""
from __future__ import annotations

import pytest

from vtl_synth.core.nasal_preproc import split_nasal_hiatus


# ---------------------------------------------------------------------------
# (a) V1V2 layer alone — the isolated forms carry the hiatus, the linked
#     forms (what sandhi produces) do not.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("isolated,linked", [
    ("mO~.a.mi", "mO~.na.mi"),     # fr « mon ami » — latent n
    ("9~.a.mi", "9~.na.mi"),       # fr « un ami » — latent n
    ("kO~.a.ta", "kO~.ta.ta"),     # fr hiatus before a consonant-initial
                                   # word: no sandhi, gate active either way
])
def test_v1v2_gate_sees_the_hiatus_only_in_the_isolated_form(
        isolated, linked):
    motor_i, info_i = split_nasal_hiatus(isolated)
    assert motor_i != isolated            # the gate rewrites the hiatus
    assert info_i["runs"], "expected nasal vowel runs on the isolated form"


def test_v1v2_gate_identity_without_nasal_hiatus():
    # oral phrase (fr « les amis » linked): the layer must not touch it
    motor, _ = split_nasal_hiatus("le.za.mi")
    assert motor == "le.za.mi"


# ---------------------------------------------------------------------------
# (b) composition through the covtl-sandhi gateway (Branch B required).
#     The stub shipped by Branch A is the IDENTITY: with the stub alone,
#     apply_sandhi_text returns the base g2p and the test degrades to
#     part (a) semantics — hence the skip.
# ---------------------------------------------------------------------------

sandhi = pytest.importorskip(
    "sandhi",
    reason="covtl-sandhi Branch B rule package (pip install covtl-sandhi, "
           "or copy sandhi/ over vtl_synth/utils/sandhi/)")


def _stub_g2p(lex):
    def g2p(text, warnings=None, **kw):
        return ".".join(lex.get(w.lower().strip(".,!?;:"), w.lower())
                        for w in str(text or "").split())
    return g2p


_G2P_FR = _stub_g2p({"mon": "mO~", "ami": "a.mi", "un": "9~"})


@pytest.mark.parametrize("text,isolated,linked", [
    ("mon ami", "mO~.a.mi", "mO~.na.mi"),
    ("un ami", "9~.a.mi", "9~.na.mi"),
])
def test_sandhi_removes_the_v1v2_hiatus(text, isolated, linked):
    warnings_out: list = []
    sampa_on = sandhi.apply_sandhi_text(
        "fr", text, _G2P_FR, level="standard", mode="g2p",
        warnings=warnings_out)
    sampa_off = _G2P_FR(text)

    # the gateway turned the isolated form into the linked form
    assert sampa_on == linked, (text, sampa_on)
    assert sampa_off == isolated

    # V1V2 gate: rewrites the isolated form, identity on the linked one
    assert split_nasal_hiatus(sampa_off)[0] != sampa_off
    assert split_nasal_hiatus(sampa_on)[0] == sampa_on


def test_sandhi_off_keeps_the_hiatus_for_the_gate():
    # off = identity: the phrase the gate sees still carries V~.V
    sampa = sandhi.apply_sandhi_text(
        "fr", "mon ami", _G2P_FR, level="off", mode="g2p")
    assert sampa == "mO~.a.mi"
    motor, info = split_nasal_hiatus(sampa)
    assert motor != sampa and info["runs"]


def test_expressive_pause_blocks_the_fusion_marker_kept():
    # across a '%' breath pause the pair never fuses: the linked form is
    # NOT produced, the marker and the hiatus survive. Standalone, the
    # gate is conservative on '%' strings (identity fallback, documented
    # in nasal_preproc) — in the pipeline the pause is split upstream
    # (build_phrase_tract) and each side of '%' reaches the gate alone.
    sampa = sandhi.apply_sandhi_sampa(
        "fr", "mon ami", "mO~.%.a.mi", _G2P_FR,
        level="standard", mode="g2p")
    assert sampa == "mO~.%.a.mi"          # no fusion, marker untouched
