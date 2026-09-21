# -*- coding: utf-8 -*-
"""Expressive prosody tests (v1.0.8 — option, default OFF).

Covers the specification docs/PROMPT_prosodie_expressivite.md §6.5
(archived design document, in French):

  (a) off mode = bit-identical outputs (g2p sampa unchanged, syltraj
      unchanged without the '%' marker);
  (b) chunking: expected boundaries per language, no chain >
      max_chain_words, inseparable connectives, dangling words;
  (c) out-of-band stress: Wikipron ˈ/ˌ capture, CMUdict digits,
      es/it/pt/de orthographic rules;
  (d) expressive F0 contour: measurable accents (sustained bump),
      smoothness (no jump > 5 Hz/frame), nuclear fall;
  (e) SAMPA assembly: the boundary-free expressive plan is the g2p
      SAMPA to the character (conventions preserved).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vtl_synth.utils import chunking
from vtl_synth.utils.chunking import (
    chunk_part, chunk_sentence, chunk_word_list, split_sentences,
)
from vtl_synth.utils.prosody_f0 import (
    EXPRESSIVITY_PROFILES, ChunkPlan, ExpressivityProfile, WordPlan,
    _make_chunk_plan, apply_expressive_f0, orthographic_stress_index,
    plan_expressive_text, token_nuclei, word_stress,
)
from vtl_synth.utils.lexicon_loader import ipa_to_keys_stress

ALL_LANGS = ('en', 'fr', 'es', 'de', 'it', 'pt')


# ===========================================================================
# (a) bit-identity, mode off
# ===========================================================================

def test_syltraj_unchanged_without_breath_marker():
    """Without '%' in the phrase, pause_breath_ms changes NOTHING
    (same blocks, same durations — bit-identity of the off mode)."""
    import vtl_synth.core.syltraj as sj
    p1, b1, _, _ = sj.build_phrase_pval('ba.na.na ba')
    p2, b2, _, _ = sj.build_phrase_pval('ba.na.na ba', pause_breath_ms=130)
    assert [(b.kind, b.n_steps, b.breath) for b in b1] == \
           [(b.kind, b.n_steps, b.breath) for b in b2]
    assert np.array_equal(p1, p2)


def test_syltraj_breath_marker_shorter_pause():
    import vtl_synth.core.syltraj as sj
    _, blocks, _, _ = sj.build_phrase_pval('ba.na.na % ba',
                                           pause_breath_ms=130)
    breaths = [b for b in blocks if b.breath]
    assert len(breaths) == 1
    # 130 ms = 13 steps @100 Hz — shorter than the comma pause (20)
    assert breaths[0].n_steps == 13
    assert breaths[0].n_steps < 20


@pytest.mark.parametrize('lang,text', [
    ('en', 'this is easy for us'),
    ('fr', 'bonjour je cherche une route'),
])
def test_pipeline_off_bit_identical(lang, text, tmp_path):
    """Pipeline(expressive=False) — unchanged code path: the SAMPA
    transcript is exactly the language g2p output (no '%')."""
    from vtl_synth import Pipeline
    from vtl_synth.utils.setlang import get_profile
    out1 = tmp_path / 'off'
    r = Pipeline(lang=lang, expressive=False).text_to_wav(
        text, output_dir=str(out1), label='off')
    assert '%' not in r.sampa
    # the transcript is the language g2p output
    plain = get_profile(lang).g2p_callable(text)
    assert r.sampa == plain


# ===========================================================================
# (b) chunking
# ===========================================================================

def test_chunk_boundary_before_conjunction():
    for lang, text, conj in [
        ('en', 'the cat and the dog', 'and'),
        ('fr', 'je viens mais je pars', 'mais'),
        ('es', 'vivo en Madrid y trabajo', 'y'),
        ('de', 'ich komme weil ich muss', 'weil'),
        ('it', 'vengo ma non resto', 'ma'),
        ('pt', 'eu venho mas fico', 'mas'),
    ]:
        chunks = chunk_part(text, lang)
        starts = [c[0].lower() for c in chunks]
        assert conj in starts, f'{lang}: no boundary before {conj!r}'


def test_chunk_bigram_inseparable():
    """« parce que » (fr): boundary BEFORE the pair, never inside."""
    chunks = chunk_part('je reste parce que tu chantes', 'fr')
    starts = [c[0].lower() for c in chunks]
    assert 'parce' in starts
    for c in chunks:
        joined = ' '.join(w.lower() for w in c)
        assert 'parce' not in joined or 'que' in joined


def test_chunk_hard_limit_balanced():
    """Boundary-free run > max: balanced split, no chain >
    max_chain_words."""
    words = ('one two three four five six seven'.split())
    for max_chain in (3, 4, 5):
        chunks = chunk_word_list(words, 'en', max_chain=max_chain)
        assert all(len(c) <= max_chain for c in chunks), \
            f'max_chain={max_chain}: {[len(c) for c in chunks]}'
        flat = [w for c in chunks for w in c]
        assert flat == words                      # nothing lost/reordered


@pytest.mark.parametrize('lang', ALL_LANGS)
def test_chunk_no_chain_over_limit(lang):
    text = {
        'en': 'the quick brown fox jumps over the lazy dog again today',
        'fr': 'je cherche une belle route pour aller au travail vite',
        'es': 'me llamo Javier y vivo en Madrid con mi familia feliz',
        'de': 'ich suche eine schoene Strasse in Koenigsberg heute',
        'it': 'la famiglia vive in campagna con nonna Giulia sempre',
        'pt': 'o menino comeu o pao com manteiga da mae ontem',
    }[lang]
    chunks = chunk_part(text, lang)
    assert all(len(c) <= 5 for c in chunks)
    assert [w for c in chunks for w in c] == \
        chunking.WORD_RES[lang].findall(text)


def test_chunk_comma_splits_parts():
    sent = chunk_sentence('je viens, je pars', 'fr')
    assert len(sent) == 2                        # two parts (commas)
    assert all(isinstance(part, list) for part in sent)


def test_chunk_dangling_function_word_moves():
    """A final determiner is absorbed by the next block (rule 4)."""
    chunks = chunk_part('je vois le chien de mon voisin', 'fr')
    for c in chunks[:-1]:
        assert c[-1].lower() not in chunking.CHUNK_WORDS['fr']['never_start'] \
            or len(c) == 1


def test_split_sentences_mirrors_g2p_punctuation():
    assert split_sentences('bonjour. je pars ! vraiment ?') == \
        ['bonjour', 'je pars', 'vraiment']


# ===========================================================================
# (c) out-of-band stress
# ===========================================================================

def test_ipa_to_keys_stress_capture():
    """ˈ primary / ˌ secondary → syllable index, pure keys."""
    keys, stress = ipa_to_keys_stress('m u ˈn i ð o', 'es')
    assert keys == ['m', 'u', 'n', 'i', 'D', 'o']
    assert stress == 1
    keys, stress = ipa_to_keys_stress('ˌa ˈb a', 'es')
    assert stress == 1                           # primary wins
    keys, stress = ipa_to_keys_stress('r e i', 'es')
    assert stress is None                        # no mark
    # stress NEVER pollutes the engine keys
    assert 'ˈ' not in ''.join(ipa_to_keys_stress('ˈa ˈb', 'es')[0])


def test_lexicon_stress_channel_synthetic(tmp_path, monkeypatch):
    """A Wikipron TSV WITH ˈ marks feeds the out-of-band channel."""
    from vtl_synth.utils import lexicon_loader as ll
    tsv = tmp_path / 'mini_es.tsv'
    tsv.write_text('mundo\tm u ˈn i ð o\n', encoding='utf-8')
    monkeypatch.setenv('COVTL_ES_LEXICON', str(tsv))
    ll.reset_cache('es')
    assert ll.stress_for('es').get('mundo') == 1
    assert ll.lexicon_for('es')['mundo'] == ['m', 'u', 'n', 'i', 'D', 'o']
    ll.reset_cache('es')


@pytest.mark.skipif(not __import__('cmudict', fromlist=['x']).__dict__,
                    reason='cmudict absent')
def test_word_stress_english_cmu():
    # abandon: AH0 B AE1 N D AH0 N → accent on the 2nd syllable
    assert word_stress('abandon', 'en', 3) == 1
    # table: T EY1 B AH0 L → accent on the 1st
    assert word_stress('table', 'en', 2) == 0


@pytest.mark.parametrize('lang,word,n,expected', [
    # es: penultimate by default, oxytone on final consonant ≠ n/s
    ('es', 'señor', 2, 1),      # se-ñor: final -r → oxytone
    ('es', 'gato', 2, 0),       # ga-to: penultimate
    ('es', 'ciudad', 2, 1),     # ends in -d → oxytone
    # es: written accent (teléfono = 4 vowel groups te-lé-fo-no)
    ('es', 'teléfono', 4, 1),
    ('es', 'cámara', 3, 0),
    # pt: -l/-r/-i/-u endings are oxytone, else penultimate
    ('pt', 'papel', 2, 1),
    ('pt', 'pao', 1, 0),
    # it: penultimate
    ('it', 'famiglia', 3, 1),
    ('it', 'città', 2, 1),
    # de: first syllable
    ('de', 'Strasse', 2, 0),
])
def test_orthographic_stress_rules(lang, word, n, expected):
    assert orthographic_stress_index(word, lang, n) == expected


def test_token_nuclei():
    assert token_nuclei('Di.si.zi') == ['i', 'i', 'i']
    assert token_nuclei('tRa.vaj') == ['a', 'a']
    assert token_nuclei('a~.tRa') == ['a', 'a']   # nasal normalized
    assert token_nuclei('quack') == []            # non-segmentable


# ===========================================================================
# (e) SAMPA assembly of the expressive plan
# ===========================================================================

def test_plan_sampa_equals_g2p_without_boundaries():
    """Short-enough sentence (no boundary inserted): the plan SAMPA is
    EXACTLY the g2p one — same '.'/' '/'|' conventions."""
    from vtl_synth.utils.setlang import get_profile
    for lang, text in [('fr', 'bonjour'), ('en', 'hello')]:
        expr = EXPRESSIVITY_PROFILES[lang]
        sampa, plans = plan_expressive_text(
            text, lang, get_profile(lang).g2p_callable, expr)
        assert sampa == get_profile(lang).g2p_callable(text)


def test_plan_inserts_breath_markers_and_chunks():
    from vtl_synth.utils.setlang import get_profile
    text = ('je cherche une belle route pour aller au travail '
            'parce que le train ne marche plus')
    expr = EXPRESSIVITY_PROFILES['fr']
    sampa, plans = plan_expressive_text(
        text, 'fr', get_profile('fr').g2p_callable, expr)
    assert '%' in sampa
    assert sampa.count(' | ') == 0                # a single phrase
    chunks = plans[0]
    assert len(chunks) >= 3
    # every chunk carries at least one accent (fr: group accent)
    assert all(c.accents for c in chunks)
    # the chunk words re-assemble the sentence
    words = [wp.word for c in chunks for wp in c.words]
    assert ' '.join(words) == text


def test_make_chunk_plan_group_accent_french():
    wps = [WordPlan('je', 'Z@', ['@'], None),
           WordPlan('cherche', 'SERS', ['E'], None)]
    plan = _make_chunk_plan(wps, 'fr')
    assert plan.nuclei == ['@', 'E']
    assert plan.accents == [(1, 1.0)]             # last syllable


def test_make_chunk_plan_lexical_accents_english():
    # 'the' = function word: only cat (first lexical) and dog (last)
    # carry an accent; cat → CMUdict K AE1 T = syllable 0
    wps = [WordPlan('the', 'D@', ['@'], None),
           WordPlan('cat', 'kAt', ['a'], 0),
           WordPlan('sees', 'siz', ['i'], 0),
           WordPlan('dog', 'dOg', ['O'], 0)]
    plan = _make_chunk_plan(wps, 'en')
    idx = [a[0] for a in plan.accents]
    assert 1 in idx and 3 in idx and 0 not in idx


# ===========================================================================
# (d) expressive F0 contour (real synthesis, syl engine)
# ===========================================================================

def _build_phrase(phrase, **kw):
    from vtl_synth.core.build_phrase_tract import build_phrase_tract
    return build_phrase_tract(phrase, phrase_id=None, label='pytest',
                              return_data=True, verbose=False, **kw)


def _voiced_stats(glott400):
    f0 = glott400[:, 0]
    voiced = glott400[:, 6] > 0.1
    return f0, voiced


def test_apply_expressive_f0_accents_and_smoothness():
    """Measurable accents (local max > base +10 %) and smoothness
    (no jump > 5 Hz/frame between voiced frames)."""
    from vtl_synth.core.syltraj import get_last_build
    tract, glott = _build_phrase('ba.na.na % ba.da.ga', pause_breath_ms=130)
    blocks = get_last_build()['block_info']
    # dummy plan: 2 chunks, nuclear accent on the last syllable
    plan = [ChunkPlan(sampa='ba.na.na', nuclei=['a', 'a', 'a'],
                      accents=[(2, 1.0)]),
            ChunkPlan(sampa='ba.da.ga', nuclei=['a', 'a', 'a'],
                      accents=[(0, 1.0), (2, 1.0)])]
    expr = ExpressivityProfile(accent_amplitude=0.20,
                               nuclear_fall_factor=0.88)
    ok = apply_expressive_f0(glott, 102.216, 1.06, 0.85, expr, plan,
                             blocks)
    assert ok, 'chunks↔segments alignment expected'
    f0, voiced = _voiced_stats(glott)
    # (1) accents: the maximum of the 1st chunk exceeds the local base
    # by base +10 % (amplitude 0.20)
    seg_voiced = f0[voiced]
    assert seg_voiced.max() > 1.10 * np.median(seg_voiced)
    # (2) smoothness: max jump between consecutive voiced frames
    vv = voiced[:-1] & voiced[1:]
    assert np.abs(np.diff(f0))[vv].max() < 5.0
    # (3) nuclear fall: the END of the last written segment descends
    # below 0.9×base (the last voiced frames stop before the fall,
    # which is carried by the mostly unvoiced tail)
    from vtl_synth.utils.prosody_f0 import _segments_from_blocks
    segs = _segments_from_blocks(blocks)
    f0_end = float(f0[segs[-1][1] * 4 - 1])
    assert f0_end < 0.90 * 102.216


def test_apply_expressive_f0_fallback_on_misalignment():
    """Plans ≠ segments (different counts) → False: the caller falls
    back to the monotone declination."""
    from vtl_synth.core.syltraj import get_last_build
    tract, glott = _build_phrase('ba.na.na')
    blocks = get_last_build()['block_info']
    plan = [ChunkPlan(sampa='ba.na.na', nuclei=['a', 'a', 'a']),
            ChunkPlan(sampa='xx', nuclei=['a'])]   # 2 plans, 1 segment
    expr = ExpressivityProfile()
    assert apply_expressive_f0(glott, 102.216, 1.06, 0.85, expr,
                               plan, blocks) is False


def test_build_phrase_tract_breath_passthrough():
    """pause_breath_ms passes through build_phrase_tract: breath block
    of the right duration; without the marker, strictly identical
    blocks."""
    from vtl_synth.core.syltraj import get_last_build
    _build_phrase('ba.na.na ba')
    blocks_plain = list(get_last_build()['block_info'])
    _build_phrase('ba.na.na % ba', pause_breath_ms=130)
    blocks_breath = get_last_build()['block_info']
    breaths = [b for b in blocks_breath if b.breath]
    assert len(breaths) == 1 and breaths[0].n_steps == 13
    # without the marker, no breath block appears
    assert not any(b.breath for b in blocks_plain)


# ===========================================================================
# end-to-end expressive pipeline (audio)
# ===========================================================================

@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_pipeline_expressive_end_to_end(lang, tmp_path):
    from vtl_synth import Pipeline
    text = {
        'en': 'this is easy for us because the engine needs air',
        'fr': 'je cherche une belle route pour aller au travail',
    }[lang]
    r = Pipeline(lang=lang, expressive=True).text_to_wav(
        text, output_dir=str(tmp_path / lang), label='expr')
    assert '%' in r.sampa
    # no coarticulated word group > 5 words: the chains between
    # separators ('.', ' ', '|', '%')
    import re
    chains = re.split(r'[ %|.]+', r.sampa)
    words = [c for c in chains if c]
    # each element = ONE connected word (the internal '.' joins
    # syllables, not words) — the chain-limit check is done on the
    # plan (chunking tests); here we check the presence of the
    # separators and the produced audio
    assert r.wav_path.exists() and r.duration_s > 1.0


def test_pipeline_expressive_requires_g2p(tmp_path):
    """Phonetic input: the expressive mode is ignored (with a
    warning), no '%' marker in the transcript."""
    from vtl_synth import Pipeline
    r = Pipeline(lang='fr', expressive=True).text_to_wav(
        'ba.na.na', output_dir=str(tmp_path / 'ph'), use_g2p=False,
        label='ph')
    assert '%' not in r.sampa
