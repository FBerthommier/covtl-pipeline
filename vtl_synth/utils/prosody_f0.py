# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
prosody_f0.py
=============
Expressive prosody: sculpted F0 contour + pitch accents
(v1.0.8 — OPTION, default OFF).

The monotone mode
(:func:`vtl_synth.core.pipeline.apply_f0_declination`) applies a
LINEAR declination per phrase: a long phrase is a flat ramp,
perceived as monotonous. This module replaces it — in expressive mode
only — with a three-component contour per breath group (chunk, see
:mod:`vtl_synth.utils.chunking`):

  1. **base declination kept** (onset → final of the language
     profile) BUT with an attack reset at every chunk (the attack
     profile no longer occurs only at the first phrase);
  2. **local pitch accents**: an asymmetric bump (soft rise ~70 ms,
     fall ~60–90 ms depending on the language, NO jump — the glottal
     synthesizer follows f0 sample by sample) placed on the stressed
     syllable of the bearing word, with optional cumulative downstep
     after each accent (German, Ladd 2008);
  3. **terminal nuclear fall** on the last stressed syllable of the
     last chunk (depth per language).

Lexical stress travels OUT OF BAND (never in the SAMPA stream):
Wikipron ˈ/ˌ via
:func:`vtl_synth.utils.lexicon_loader.ipa_to_keys_stress`, CMUdict
digits (0/1/2) for English, then per-language orthographic fallback
rules (written accent es/it/pt, penultimate by default, first
syllable for de, GROUP accent for fr — Jun & Fougeron 2002: no
internal lexical accent in French).

A DOCUMENTED simplification to 2–3 parameters per language
(amplitudes, fall depth, reset), justified by the references cited in
:mod:`vtl_synth.utils.setlang` (Face 2003 / Grice et al. 2005 /
Avesani 1995 / Frota 2000 / Pierrehumbert 1980…): this is a
computable caricature of the contours, not a ToBI implementation.

The module touches ONLY the glottis f0 column and the pause durations
(the '%' marker of syltraj) — never the tract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from vtl_synth.utils.chunking import CHUNK_WORDS, chunk_sentence, split_sentences

# Block sampling factor @100 Hz → glottis @400 Hz.
_SR_STEP = 4


# ===========================================================================
# ExpressivityProfile
# ===========================================================================

@dataclass
class ExpressivityProfile:
    """Per-language expressivity parameters (option, default off).

    pause_breath_ms : duration of the '%' breath pause (130 ms,
        shorter than the 200 ms comma pause).
    max_chain_words : no breath group exceeds this number of words
        (syntactic breathing).
    accent_amplitude : amplitude of the pitch bumps, as a FRACTION of
        f0_base (0.16 = +16 % ≈ +16 Hz at 102 Hz).
    accent_rise_ms / accent_fall_ms : half-widths of the bump
        (rise / fall) — smoothness is guaranteed by construction
        (asymmetric Gaussian, no jump).
    chunk_reset : share of the attack reset recovered at each chunk
        (0 = no reset, 1 = full attack like at phrase head).
    downstep : multiplicative factor of the base level after each
        accent (1.0 = none; 0.985 — marked German downstep, Ladd
        2008).
    nuclear_fall_factor : SUPPLEMENTARY terminal multiplier of the
        nuclear fall (0.90 = the end of the last chunk descends 10 %
        below the final_gain level — German/Portuguese low terminal).
    """
    pause_breath_ms: float = 130.0
    max_chain_words: int = 5
    accent_amplitude: float = 0.14
    accent_rise_ms: float = 70.0
    accent_fall_ms: float = 90.0
    chunk_reset: float = 0.7
    downstep: float = 1.0
    nuclear_fall_factor: float = 0.95


#: Per-language parameters — the amplitudes follow the ranges described
#: in the intonation literature (see the module docstring):
#: de (Grice et al. 2005: marked accents + downstep + deep low
#: terminal) > es (Face 2003: broad pre-nuclear rises) ≈ it (Avesani
#: 1995) > en (Pierrehumbert 1980) > pt (Frota 2000: narrower range)
#: > fr (Jun & Fougeron 2002: moderate final AP accent).
#: Perceptual calibration: +18–24 Hz on f0_base ≈ 102 Hz = 3–4
#: semitones, the usual range of read-speech pitch accents.
EXPRESSIVITY_PROFILES: Dict[str, ExpressivityProfile] = {
    'en': ExpressivityProfile(
        accent_amplitude=0.20, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.7, downstep=0.99, nuclear_fall_factor=0.92),
    'fr': ExpressivityProfile(
        accent_amplitude=0.16, accent_rise_ms=70.0, accent_fall_ms=80.0,
        chunk_reset=0.6, downstep=1.0, nuclear_fall_factor=0.90),
    'es': ExpressivityProfile(
        accent_amplitude=0.22, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.8, downstep=1.0, nuclear_fall_factor=0.94),
    'de': ExpressivityProfile(
        accent_amplitude=0.24, accent_rise_ms=70.0, accent_fall_ms=60.0,
        chunk_reset=1.0, downstep=0.975, nuclear_fall_factor=0.88),
    'it': ExpressivityProfile(
        accent_amplitude=0.22, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.8, downstep=1.0, nuclear_fall_factor=0.93),
    'pt': ExpressivityProfile(
        accent_amplitude=0.18, accent_rise_ms=70.0, accent_fall_ms=80.0,
        chunk_reset=0.7, downstep=1.0, nuclear_fall_factor=0.90),
}


# ===========================================================================
# Vowel nuclei of a SAMPA token
# ===========================================================================

def token_nuclei(token: str) -> List[str]:
    """Vowel keys (one per syllable) of a connected SAMPA token.

    ``'Di.si.zi'`` → ``['i', 'i', 'i']``; nasal keys are normalized
    without '~' (like the syltraj plateaus). Non-segmentable token →
    [] (the caller falls back to the group accent).
    """
    from vtl_synth.core.constants import VOWEL_TARGETS
    from vtl_synth.core.phonemes import greedy_sampa_split
    # '~' (nasality) removed before splitting: the nuclei are compared
    # with the syltraj plateau keys, which carry no '~' themselves
    residual = token.replace('.', '').replace(' ', '').replace('~', '')
    keys = greedy_sampa_split(residual)
    if not keys:
        return []
    return [k for k in keys if k in VOWEL_TARGETS]


# ===========================================================================
# Out-of-band lexical stress
# ===========================================================================

_ARPA_VOWELS = frozenset({
    'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'EY', 'ER', 'IH', 'IY',
    'OW', 'OY', 'UH', 'UW',
})

# Vowel letters for the orthographic rules (es/it/pt) — written
# accents mark the irregular syllable in these orthographies.
_ACCENTED_LETTERS = {
    'es': 'áéíóú', 'it': 'àèéìòóù', 'pt': 'áàâãéêíóôõú',
}
_VOWEL_LETTERS = {
    'es': 'aeiouáéíóúü',
    'it': 'aeiouàèéìòóù',
    'pt': 'aeiouáàâãéêíóôõú',
}
_STRONG = frozenset('aeoàèòáéóâêôãõ')
# Portuguese oxytone endings (spec §4: -l -r -i -u -im -ns, and final
# nasals -ão/-ães/-ões)
_PT_OXYTONE_RE = re.compile(
    r'(?:l|r|z|i|u|im|ins|ns|ns|ái|éu|ói)$|ãos?$|ães$|õe?s?$')
# Spanish endings: final consonant ≠ n/s → oxytone
_ES_OXYTONE_RE = re.compile(r'(?:[^aeiouáéíóúns])$')


def _cmu_stress(word: str) -> Optional[int]:
    """Stressed-syllable index from the CMUdict digits (0/1/2).

    Primary accent '1' wins over secondary '2'. Counts the ARPAbet
    vowel symbols before the bearing symbol (each ARPAbet vowel =
    exactly one engine nucleus).
    """
    try:
        import cmudict
    except Exception:                                      # pragma: no cover
        return None
    variants = cmudict.dict().get(word.lower())
    if not variants:
        return None
    primary = secondary = None
    n_vow = 0
    for sym in variants[0]:
        if sym.rstrip('012') in _ARPA_VOWELS:
            if sym.endswith('1') and primary is None:
                primary = n_vow
            elif sym.endswith('2') and secondary is None:
                secondary = n_vow
            n_vow += 1
    return primary if primary is not None else secondary


def _vowel_groups(word: str, lang: str) -> List[Tuple[int, int, int]]:
    """Orthographic vowel groups: (start, end, accented position).

    accented position = index of the accented character WITHIN the
    group, or -1.
    """
    vowels = _VOWEL_LETTERS[lang]
    accented = set(_ACCENTED_LETTERS[lang])
    groups: List[Tuple[int, int, int]] = []
    start = -1
    acc_pos = -1
    for i, ch in enumerate(word.lower()):
        if ch in vowels:
            if start < 0:
                start, acc_pos = i, -1
            if ch in accented and acc_pos < 0:
                acc_pos = i - start
        elif start >= 0:
            groups.append((start, i - 1, acc_pos))
            start = -1
    if start >= 0:
        groups.append((start, len(word) - 1, acc_pos))
    return groups


def _group_yield(group: Tuple[int, int, int], word: str, lang: str) -> int:
    """Number of SAMPA nuclei produced by one vowel group.

    1 by default (diphthong ai/ei/ia/ua… = nucleus + glide); 2 for a
    hiatus: accented weak vowel (í a, ú e… — the written accent breaks
    the diphthong) or two adjacent strong vowels (le-er).
    """
    seg = word[group[0]:group[1] + 1].lower()
    if len(seg) >= 2:
        weak_accented = any(c in 'íìúù' for c in seg)
        if weak_accented:
            return 2
        strong_pairs = all(c in _STRONG for c in seg)
        if strong_pairs and len(set(seg)) >= 1 and seg[0] != seg[1]:
            return 2
        if len(seg) == 2 and seg[0] == seg[1]:
            return 2                      # doubled vowel (leer, cooperar)
    return 1


def orthographic_stress_index(word: str, lang: str,
                              n_nuclei: int) -> Optional[int]:
    """Stressed-syllable index from the orthography (es/it/pt/de).

    Hierarchy: written accent → that syllable; otherwise a per-
    language rule (es: oxytone if the final consonant ≠ n/s, else
    penultimate; it: penultimate; pt: oxytone on the endings
    -l/-r/-i/-u/-im/-ns/-ão, else penultimate; de: first syllable —
    documented approximation, prefixes not handled).
    The index is computed in the SAMPA-nuclei space (n_nuclei), the
    diphthong/hiatus divergence being corrected by tail counting.
    """
    if n_nuclei <= 0:
        return None
    if lang == 'de':
        return 0
    if lang not in ('es', 'it', 'pt'):
        return None
    groups = _vowel_groups(word, lang)
    if not groups:
        return None
    yields = [_group_yield(g, word, lang) for g in groups]

    acc = next((gi for gi, g in enumerate(groups) if g[2] >= 0), None)
    if acc is not None:
        tail = sum(yields[acc + 1:])
        base = n_nuclei - tail - yields[acc]   # first nucleus of the group
        seg = word.lower()[groups[acc][0]:groups[acc][1] + 1]
        # position of the accented character among the vowel letters
        # of the group (hiatus í-a: accent on the 1st nucleus; a-í: 2nd)
        vow = _VOWEL_LETTERS[lang]
        vow_idx = [j for j, c in enumerate(seg) if c in vow]
        pos_in_group = vow_idx.index(groups[acc][2]) if groups[acc][2] < len(vow_idx) else 0
        within = 1 if (yields[acc] == 2 and pos_in_group >= 1) else 0
        return max(0, min(base + within, n_nuclei - 1))

    wl = word.lower()
    if lang == 'es':
        last = bool(_ES_OXYTONE_RE.search(wl)) and not wl.endswith(('n', 's'))
        return n_nuclei - 1 if last else max(0, n_nuclei - 2)
    if lang == 'pt':
        last = bool(_PT_OXYTONE_RE.search(wl))
        return n_nuclei - 1 if last else max(0, n_nuclei - 2)
    # it
    return max(0, n_nuclei - 2)


def word_stress(word: str, lang: str, n_nuclei: int) -> Optional[int]:
    """Stressed-syllable index of a word (out-of-band stress).

    Order: CMUdict digits (en) → Wikipron ˈ/ˌ mark of the loaded
    lexicon → per-language orthographic rule → None (the caller falls
    back to the group accent). Never ≥ n_nuclei.
    """
    if n_nuclei <= 0:
        return None
    wl = word.lower().replace('’', "'")
    idx: Optional[int] = None
    if lang == 'en':
        idx = _cmu_stress(wl)
        if idx is None:
            idx = 0 if n_nuclei == 1 else min(0, n_nuclei - 1)
    else:
        try:
            from vtl_synth.utils.lexicon_loader import LEXICONS, stress_for
            if lang in LEXICONS:
                s = stress_for(lang).get(wl)
                if s is not None and 0 <= s < n_nuclei:
                    return s
        except Exception:                                  # pragma: no cover
            pass
        idx = orthographic_stress_index(word, lang, n_nuclei)
    if idx is None:
        return None
    return max(0, min(int(idx), n_nuclei - 1))


# ===========================================================================
# Expressive plan: text → breathed SAMPA + per-chunk plans
# ===========================================================================

@dataclass
class WordPlan:
    """One word: connected SAMPA token, nuclei, out-of-band stress."""
    word: str
    token: str
    nuclei: List[str] = field(default_factory=list)
    stress: Optional[int] = None


@dataclass
class ChunkPlan:
    """One breath group: words, SAMPA ('.'-joined), nuclei, accents.

    accents: list of (nucleus index, weight) — the nuclear accent is
    determined by position (last accent of the last chunk).
    """
    words: List[WordPlan] = field(default_factory=list)
    sampa: str = ''
    nuclei: List[str] = field(default_factory=list)
    word_start: List[int] = field(default_factory=list)
    accents: List[Tuple[int, float]] = field(default_factory=list)


def _norm(word: str) -> str:
    return word.lower().replace('’', "'")


def _make_chunk_plan(wps: Sequence[WordPlan], lang: str) -> ChunkPlan:
    """Assemble a chunk plan and choose the pitch accents.

    Policy (documented simplification):

      * fr: no lexical accent — a GROUP accent on the last syllable
        of the chunk (Jun & Fougeron 2002: AP-final accent);
      * others: accents on the stressed syllable of the FIRST and
        LAST lexical word of the chunk (de-accentuation of function
        words and intermediate words — a given/new heuristic);
      * no lexical word (function words only): group accent.
    """
    chunk = ChunkPlan(words=list(wps), sampa='.'.join(wp.token for wp in wps))
    off = 0
    for wp in wps:
        chunk.word_start.append(off)
        chunk.nuclei.extend(wp.nuclei)
        off += len(wp.nuclei)
    if not chunk.nuclei:
        return chunk
    if lang == 'fr':
        chunk.accents = [(len(chunk.nuclei) - 1, 1.0)]
        return chunk
    unacc = CHUNK_WORDS.get(lang, CHUNK_WORDS['en'])['unaccentable']
    lexical = [i for i, wp in enumerate(wps)
               if _norm(wp.word) not in unacc]
    picks = []
    if lexical:
        picks = [lexical[0]]
        if lexical[-1] != lexical[0]:
            picks.append(lexical[-1])
    accents: List[Tuple[int, float]] = []
    for wi in picks:
        wp = wps[wi]
        if not wp.nuclei:
            continue
        syl = wp.stress if wp.stress is not None else len(wp.nuclei) - 1
        syl = max(0, min(syl, len(wp.nuclei) - 1))
        idx = chunk.word_start[wi] + syl
        if all(idx != a[0] for a in accents):
            accents.append((idx, 1.0))
    if not accents:
        accents = [(len(chunk.nuclei) - 1, 1.0)]
    chunk.accents = sorted(accents)
    return chunk


def plan_expressive_text(text: str,
                         lang: str,
                         g2p_callable: Callable,
                         expr: ExpressivityProfile,
                         warnings: Optional[list] = None,
                         ) -> Tuple[str, Optional[List[List[ChunkPlan]]]]:
    """Text → (breathed SAMPA, per-phrase plans).

    The assembled SAMPA is IDENTICAL to the language g2p output except
    that breath groups are separated by the ``' % '`` marker (breath
    pause): words joined by ``.``, parts (commas) by ``' '``, phrases
    by ``' | '`` — the same conventions as ``text_to_sampa``. The g2p
    is called WORD BY WORD (the package g2p modules are strictly
    word-level: lexicon → exceptions → rules), which yields a
    verifiable words↔tokens plan.

    Returns (sampa, plans); plans[i] = the flattened chunks of phrase
    i, or None if NO phrase could be planned (the caller falls back to
    the monotone declination).
    """
    own = warnings is None
    if own:
        warnings = []
    phrase_sampas: List[str] = []
    plans: List[List[ChunkPlan]] = []
    for sentence in split_sentences(text):
        parts = chunk_sentence(sentence, lang,
                               max_chain=expr.max_chain_words)
        part_strs: List[str] = []
        phrase_chunks: List[ChunkPlan] = []
        for part in parts:
            chunk_strs: List[str] = []
            for words in part:
                wps: List[WordPlan] = []
                for w in words:
                    tok = g2p_callable(w, warnings=warnings).strip()
                    if not tok:
                        continue
                    nuclei = token_nuclei(tok)
                    stress = word_stress(w, lang, len(nuclei))
                    wps.append(WordPlan(w, tok, nuclei, stress))
                if not wps:
                    continue
                chunk_strs.append('.'.join(wp.token for wp in wps))
                phrase_chunks.append(_make_chunk_plan(wps, lang))
            if chunk_strs:
                part_strs.append(' % '.join(chunk_strs))
        if part_strs:
            phrase_sampas.append(' '.join(part_strs))
            plans.append(phrase_chunks)
    if not plans:
        return ' | '.join(phrase_sampas), None
    return ' | '.join(phrase_sampas), plans


# ===========================================================================
# F0 contour sculpting
# ===========================================================================

def _segments_from_blocks(block_info) -> List[Tuple[int, int]]:
    """Content segments (steps @100 Hz) separated by pause blocks.

    The 'pause' / 'initial' / 'terminal' blocks are separators; the
    phrase-head 'initial' block is skipped (leading silence).
    """
    segs: List[Tuple[int, int]] = []
    off = 0
    seg_start: Optional[int] = None
    for b in block_info:
        sep = b.kind in ('pause', 'initial', 'terminal')
        if seg_start is None:
            if not sep:
                seg_start = off
        elif sep:
            segs.append((seg_start, off))
            seg_start = None
        off += b.n_steps
    if seg_start is not None:
        segs.append((seg_start, off))
    return segs


def _plateaus_from_blocks(block_info, seg: Tuple[int, int]):
    """Vowel plateaus (steps @100 Hz, key) of one segment."""
    out: List[Tuple[int, int, str]] = []
    off = 0
    s, e = seg
    for b in block_info:
        if b.kind == 'plateau' and off + b.n_steps > s and off < e:
            lo = max(off, s)
            hi = min(off + b.n_steps, e)
            out.append((lo, hi, b.vowel_key or ''))
        off += b.n_steps
    return out


def apply_expressive_f0(glott400: np.ndarray,
                        f0_base: float,
                        onset_gain: float,
                        final_gain: float,
                        expr: ExpressivityProfile,
                        chunk_plans: Sequence[ChunkPlan],
                        block_info) -> bool:
    """Sculpt the expressive F0 of one phrase (glottis column 0).

    Returns True when the contour could be applied, False when the
    chunks↔segments alignment fails (the caller falls back to the
    monotone declination). Modifies NO other column: the tract and the
    amplitude remain the engine's.
    """
    n = len(glott400)
    segs = _segments_from_blocks(block_info)
    if not segs or len(segs) != len(chunk_plans):
        return False

    # f0 written per chunk (for bridging the inter-segment gaps): the
    # pause regions keep the engine f0, but their edges may remain
    # voiced (post-pause attack/arc) — without a bridge, the junction
    # with the next chunk's attack reset jumps.
    written: List[Tuple[int, int]] = []
    K = len(segs)
    for k, (seg, plan) in enumerate(zip(segs, chunk_plans)):
        s400 = seg[0] * _SR_STEP
        e400 = min(seg[1] * _SR_STEP, n)
        L = e400 - s400
        if L <= 12:
            continue
        # --- base declination + attack reset -------------------------
        start_gain = onset_gain if k == 0 else \
            1.0 + (onset_gain - 1.0) * expr.chunk_reset
        end_gain = onset_gain + (final_gain - onset_gain) * (k + 1) / K
        progress = np.linspace(0.0, 1.0, L)
        decl = start_gain + (end_gain - start_gain) * progress
        ramp_len = min(10, L // 5)
        if ramp_len > 0:
            decl[:ramp_len] = np.linspace(1.0, decl[ramp_len - 1], ramp_len)

        # --- plateau ↔ nucleus alignment ------------------------------
        plateaus = _plateaus_from_blocks(block_info, seg)
        keys_engine = [p[2] for p in plateaus]
        aligned = keys_engine == list(plan.nuclei)
        if aligned:
            accents = plan.accents
        else:
            # fallback: group accent (last syllable of the chunk)
            accents = [(len(plateaus) - 1, 1.0)] if plateaus else []
        accents = [(i, w) for i, w in accents
                   if plateaus and 0 <= i < len(plateaus)]
        if not plateaus:
            # no localized nucleus: declination only
            glott400[s400:e400, 0] = f0_base * decl
            continue

        # --- pitch bumps + downstep -----------------------------------
        bumps = np.zeros(L)
        down_count = np.zeros(L)
        accent_ends: List[int] = []
        t = np.arange(L)
        for nuc_idx, weight in accents:
            p0, p1, _ = plateaus[nuc_idx]
            # bump center: 35 % into the plateau (H* peak on the
            # stressed syllable), positions relative to the chunk @400 Hz
            c = int((p0 - seg[0] + 0.35 * (p1 - p0)) * _SR_STEP)
            c = max(0, min(L - 1, c))
            amp = expr.accent_amplitude * weight
            sigma = np.where(t < c,
                             expr.accent_rise_ms * 0.4,
                             expr.accent_fall_ms * 0.4)
            bumps += amp * np.exp(-0.5 * ((t - c) / sigma) ** 2)
            accent_ends.append(int(c + 3.0 * expr.accent_fall_ms * 0.4))
        for fe in accent_ends:
            down_count[fe:] += 1
        decl = decl * (expr.downstep ** down_count)

        # --- nuclear fall (last chunk) --------------------------------
        nuclear_mult = np.ones(L)
        if k == K - 1 and accents:
            p0, p1, _ = plateaus[accents[-1][0]]
            c_nuc = int((p0 - seg[0] + 0.35 * (p1 - p0)) * _SR_STEP)
            c_nuc = max(0, min(L - 1, c_nuc))
            if e400 > s400 + c_nuc:
                s_term = np.clip(
                    (np.arange(L) - c_nuc) / max(1, L - c_nuc), 0.0, 1.0)
                nuclear_mult = 1.0 - (1.0 - expr.nuclear_fall_factor) * s_term

        f0 = f0_base * decl * (1.0 + bumps) * nuclear_mult
        # short smoothing (anti numerical corner) over the chunk
        if L > 3:
            kernel = np.ones(5) / 5.0
            f0 = np.convolve(f0, kernel, mode='same')
            # edges: re-stick the unsmoothed extremities
            f0[:2] = f0[2]
            f0[-2:] = f0[-3]
        glott400[s400:e400, 0] = f0
        written.append((s400, e400))

    # --- inter-chunk bridges: linear ramp over the pause regions
    # (f0 is ignored when rel_amp ≈ 0, and continuous when the attack
    # is already voiced) — guarantees no jump at the junction.
    for (s0, e0), (s1, e1) in zip(written, written[1:]):
        gap = s1 - e0
        if gap > 0:
            f0a = float(glott400[e0 - 1, 0])
            f0b = float(glott400[s1, 0])
            glott400[e0:s1, 0] = np.linspace(f0a, f0b, gap + 2)[1:-1]
    return True


__all__ = [
    'ExpressivityProfile', 'EXPRESSIVITY_PROFILES',
    'token_nuclei', 'word_stress', 'orthographic_stress_index',
    'WordPlan', 'ChunkPlan', 'plan_expressive_text',
    'apply_expressive_f0',
]
