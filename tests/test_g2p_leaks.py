# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
test_g2p_leaks.py
=================
Regression tests for the g2p synthesis leak fixes (CORRECTIONS v2.1,
covtl-corrections-patch v1.0.0, 2026-10-23).

Two pre-existing leaks, revealed by the SAMPA guard (the guard itself
never changed any synthesis output):

* **g2p-de** — the Wikipron IPA table (``_DE_IPA_TO_KEYS``) and the
  exceptions emitted the lax vowel keys ``I``/``U``/``Y``, absent from
  the engine inventory (``constants.ALL_PHONEME_KEYS``): the parsers
  dropped them silently ("Butter" -> /bt@/, "Mütter" -> /mt@/,
  "ist" -> /st/). The table now maps ɪ/ʊ/ʏ to the tense i/u/y
  (documented lax -> tense approximation, consistent with the module's
  "ö/ü always tense" policy).
* **g2p-pt** — 'qu' spellings not covered by que/qui/qua/quo (e.g.
  "quente", where the nasalization placeholder breaks the 'que'
  pattern) leaked a raw ``q`` key, absent from the inventory. A
  ``('qu', 'k')`` fallback rule was added (longest-match-first keeps
  que/qui/qua/quo ahead of it).

The SAMPA guard is used here as the oracle: after the fixes, the g2p
output of every tested language must be fully covered by the engine
inventory (``unknown_symbols`` == []).
"""

from __future__ import annotations

from vtl_synth.core.sampa_guard import unknown_symbols
from vtl_synth.utils.lexicon_loader import ipa_to_keys
from vtl_synth.utils.g2p import text_to_sampa as text_to_sampa_en
from vtl_synth.utils.g2p_de import text_to_sampa_de, _DE_EXCEPTIONS
from vtl_synth.utils.g2p_es import text_to_sampa_es
from vtl_synth.utils.g2p_fr import text_to_sampa_fr
from vtl_synth.utils.g2p_it import text_to_sampa_it
from vtl_synth.utils.g2p_pt import text_to_sampa_pt


# ---------------------------------------------------------------------------
# g2p-de: IPA table (lexicon branch, pure conversion — no TSV)
# ---------------------------------------------------------------------------

def test_de_ipa_table_lax_to_tense():
    """ɪ/ʊ/ʏ (lax) -> i/u/y (tense): I/U/Y keys absent from the core."""
    assert ipa_to_keys('mʏtɐ', 'de') == ['m', 'y', 't', '@']
    assert ipa_to_keys('bʊtɐ', 'de') == ['b', 'u', 't', '@']
    assert ipa_to_keys('zɪnt', 'de') == ['z', 'i', 'n', 't']
    assert ipa_to_keys('ɪç', 'de') == ['i', 'C']
    assert ipa_to_keys('vʊntɐ', 'de') == ['v', 'u', 'n', 't', '@']


def test_de_exceptions_no_inventory_invalid_keys():
    """No exception emits the I/U/Y keys (engine inventory)."""
    for word, pron in _DE_EXCEPTIONS.items():
        assert not ({'I', 'U', 'Y'} & set(pron.split())), (word, pron)


def test_de_documented_leak_examples():
    """The documented examples of the leak (before -> after)."""
    w: list = []
    assert text_to_sampa_de('Butter', w) == 'bu.t@'      # was bUt@
    assert text_to_sampa_de('Mütter', w) == 'my.t@'      # was mYt@
    assert text_to_sampa_de('ist', w) == 'ist'           # was Ist
    assert text_to_sampa_de('und', w) == 'unt'           # was Unt
    assert text_to_sampa_de('sind', w) == 'zint'         # was zInt
    assert text_to_sampa_de('Die Butter ist gut.', w) == 'di.bu.t@.ist.gut'
    assert w == []                                       # zero silent leak


def test_de_g2p_output_passes_guard():
    """Guard oracle: every g2p-de output is covered by the inventory."""
    for txt in ['ist', 'und', 'sind', 'mit', 'nicht', 'unter',
                'Butter', 'Mütter', 'Die Butter ist gut.',
                'König und Glück', 'schön', 'über']:
        w: list = []
        s = text_to_sampa_de(txt, w)
        unknowns = unknown_symbols(s)
        assert unknowns == [], (txt, s, unknowns)


# ---------------------------------------------------------------------------
# g2p-pt: "qu" fallback -> "k"
# ---------------------------------------------------------------------------

def test_pt_qu_fallback():
    """"qu" not covered by que/qui/qua/quo -> /k/ (no more 'q' leak)."""
    w: list = []
    assert text_to_sampa_pt('quente', w) == 'k@~t@'      # was qu.@~t@
    assert w == []
    w = []
    assert text_to_sampa_pt('o pão quente', w) == 'o.p@~w.k@~t@'
    assert w == []
    # non-word: raw fallback (qu + accented vowel, no nasalization)
    w = []
    s = text_to_sampa_pt('aquêloro', w)
    assert s == 'a.ke.lo.Ru' and w == [], (s, w)


def test_pt_qu_covered_paths_unchanged():
    """que/qui/qua/quo keep priority over the fallback."""
    w: list = []
    assert text_to_sampa_pt('aqui', w) == '@.ki'         # lexicon (ɐˈki)
    assert text_to_sampa_pt('quando', w) == 'kw@~du'     # exception
    assert text_to_sampa_pt('o quê', w) == 'o.ke'        # lexicon
    assert w == []


def test_pt_g2p_output_passes_guard():
    """Guard oracle: every g2p-pt output is covered by the inventory."""
    for txt in ['quente', 'o pão quente', 'aqui', 'quando', 'o quê',
                'a casa branca', 'o gato come peixe']:
        w: list = []
        s = text_to_sampa_pt(txt, w)
        unknowns = unknown_symbols(s)
        assert unknowns == [], (txt, s, unknowns)


# ---------------------------------------------------------------------------
# Non-regression: en / fr / es / it unchanged and covered by the inventory
# ---------------------------------------------------------------------------

def test_other_languages_unchanged_and_guard_clean():
    """The de/pt fixes do not touch the other languages."""
    cases = [
        (text_to_sampa_en, 'the cat sat on the mat'),
        (text_to_sampa_en, 'clean pan'),
        (text_to_sampa_fr, 'bonjour tout le monde'),
        (text_to_sampa_fr, 'Le chat dort.'),
        (text_to_sampa_es, 'el perro corre rápido'),
        (text_to_sampa_es, 'una casa grande'),
        (text_to_sampa_it, 'la casa è bella'),
        (text_to_sampa_it, 'il gatto nero'),
    ]
    for g2p, txt in cases:
        w: list = []
        s = g2p(txt, w)
        unknowns = unknown_symbols(s)
        assert unknowns == [], (txt, s, unknowns)
        assert w == [], (txt, w)
