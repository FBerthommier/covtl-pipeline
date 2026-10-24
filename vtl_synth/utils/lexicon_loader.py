# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
lexicon_loader.py
=================
Shared pronunciation-lexicon loader (Wikipron TSV), used by all the
multilingual g2p front-ends (fr, es, de, it, pt).

Factorized from ``g2p_fr.py``'s ``_load_lexicon`` (v2): each language
describes its lexicon with a ``LexiconSpec`` (file name, environment
variable, IPA → engine keys table). The loader is lazy,
failure-tolerant (missing lexicon → graceful degradation to the rules)
and caches its results.

Formats accepted per ``word<TAB>pron`` line (auto-detected):
  * engine SAMPA keys separated by spaces (``a t a~``);
  * Wikipron IPA (``atɑ̃``), converted through the language table.

Wikipron sources (Wiktionary data, CC BY-SA 3.0 — see
``vtl_synth/data/README_fr_lexicon.md`` and the per-language
``README_xx_lexicon.md`` notes):

  ========  ======  =====================================================
  language  code    Wikipron file (data/scrape/tsv/, master branch)
  ========  ======  =====================================================
  fr        fra     fra_latn_broad_filtered.tsv
  es        spa     spa_latn_ca_broad_filtered.tsv   (Castilian, /θ/)
  de        deu     deu_latn_broad_filtered.tsv
  it        ita     ita_latn_broad_filtered.tsv
  pt        por     por_latn_po_broad_filtered.tsv   (European Portuguese)
  ========  ======  =====================================================

The raw URL has the form ::
https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/<fichier>
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vtl_synth.core.constants import ALL_CONSONANT_KEYS

# Union of the vowels of ALL languages (language_vowel_sets): the
# "token = valid engine key" test must not depend on the ACTIVE
# language (e.g. German 'I'/'U'/'Y' must be recognized even when
# the active language section is 'en'). Lazy import to avoid any
# import cycle at package load time.
def _all_vowel_keys() -> frozenset:
    from vtl_synth.utils.language_vowel_sets import VOWEL_SETS
    keys = set()
    for entry in VOWEL_SETS.values():
        keys.update(entry['vowels'].keys())
    return frozenset(keys)


# Valid keys for the "engine keys" branch of the loader: consonants +
# all known vowels + nasal vowels (base + '~').
_VALID_KEYS: frozenset = frozenset(
    set(ALL_CONSONANT_KEYS) | _all_vowel_keys()
    | {k + '~' for k in _all_vowel_keys()}
    | {'a~', 'e~', 'i~', 'o~', 'u~', 'y~', '9~', '2~', '@~',
       'E~', 'O~', '6~'}
)


# ===========================================================================
# IPA → engine key tables (per language)
# ===========================================================================
# Conventions:
#   * the input is NFC-normalized before conversion (the decomposed
#     nasals of the Portuguese Wikipron compose by themselves for
#     a/e/i/o/u; ɐ̃ ɛ̃ ɔ̃ etc. remain decomposed → 2-char entries);
#   * ordered table: longest patterns first (the conversion is greedy
#     position by position, in list order);
#   * phonemes without an engine equivalent: documented approximations
#     (ɾ→R: no alveolar rhotic in the inventory; ʔ→'': no glottal
#     stop; t͡s→'t s': no dental affricate).

_TILDE = '\u0303'
_TIE = '\u0361'          # t͡ʃ (affricate tie)
_NONSYL = '\u032F'       # a̯ (diacritique non-syllabique)
_SYLL = '\u0329'         # m̩ (diacritique syllabique)

# --- common base (ASCII IPA + shared symbols) -------------------------
_BASE_IPA_TO_KEYS: List[Tuple[str, str]] = [
    ('t' + _TIE + 'ʃ', 'tS'), ('d' + _TIE + 'ʒ', 'dZ'),
    (_TIE, ''),
    ('tʃ', 'tS'), ('dʒ', 'dZ'),
    # falling diphthongs written as full vowels (Wikipron
    # es/it/pt: 'rey' → r e i; rising ones use explicit j/w)
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'), ('ou', 'o w'),
    ('ʃ', 'S'), ('ʒ', 'Z'), ('ŋ', 'N'), ('ɲ', 'J'), ('ʁ', 'R'),
    ('ʀ', 'R'), ('ɾ', 'R'), ('β', 'b'), ('ɣ', 'g'), ('ʝ', 'j'),
    ('ɡ', 'g'),
    ('ɛ', 'E'), ('ɔ', 'O'), ('ə', '@'), ('ɑ', 'a'), ('œ', '9'),
    ('ø', '2'), ('ɐ', '@'), ('θ', 'T'), ('ð', 'D'),
    ('ː', ''), ('ˑ', ''), ('ˈ', ''), ('ˌ', ''),
    ('(', ''), (')', ''), ('‿', ''),
    ('j', 'j'), ('w', 'w'), ('l', 'l'), ('r', 'R'), ('h', 'h'),
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('y', 'y'),
    ('p', 'p'), ('b', 'b'), ('t', 't'), ('d', 'd'), ('k', 'k'),
    ('g', 'g'), ('f', 'f'), ('v', 'v'), ('s', 's'), ('z', 'z'),
    ('m', 'm'), ('n', 'n'),
]

# --- precomposed nasals (NFC) --------------------------------------------
_NASAL_PRECOMPOSED: List[Tuple[str, str]] = [
    ('ã', 'a~'), ('ẽ', 'e~'), ('ĩ', 'i~'), ('õ', 'o~'), ('ũ', 'u~'),
    ('ɐ' + _TILDE, '@~'), ('ɛ' + _TILDE, 'E~'), ('ɔ' + _TILDE, 'O~'),
    ('ɑ' + _TILDE, 'a~'),   # no precomposed form (Wikipron fra)
    ('y' + _TILDE, 'y~'), ('ø' + _TILDE, '2~'), ('œ' + _TILDE, '9~'),
    ('ə' + _TILDE, '@~'), ('i' + _TILDE, 'i~'), ('u' + _TILDE, 'u~'),
    ('o' + _TILDE, 'o~'), ('e' + _TILDE, 'e~'), ('a' + _TILDE, 'a~'),
    # nasal glides (w̃ j̃, Portuguese) → plain glide (approximation:
    # the nasality of the adjacent vowel dominates)
    ('w' + _TILDE, 'w'), ('j' + _TILDE, 'j'),
    (_TILDE, ''),
]

_FR_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + _BASE_IPA_TO_KEYS + [
        ('ç', 's'),          # notation.py: foreign ç → /s/ (French)
        ('χ', 'X'),
        ('x', 'X'),
        ('ɥ', 'ɥ'),
    ])

_ES_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + _BASE_IPA_TO_KEYS + [
        ('x', 'X'),          # Spanish j, g+e/i /x/ → uvular fricative
        ('t' + _TIE + 's', 't s'),
        ('ts', 't s'),
    ])

_DE_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        # diphthongs with the non-syllabic diacritic (aɪ̯ aʊ̯ …) and
        # flat forms (Wikipron writes aɪ̯ / aɪ interchangeably)
        ('aɪ' + _NONSYL, 'a j'), ('aʊ' + _NONSYL, 'a w'),
        ('ɔɪ' + _NONSYL, 'O j'), ('ɔʏ' + _NONSYL, 'O j'),
        ('eɪ' + _NONSYL, 'e j'), ('oʊ' + _NONSYL, 'o w'),
        ('aɪ', 'a j'), ('aʊ', 'a w'), ('ɔʏ', 'O j'), ('ɔɪ', 'O j'),
        ('ɪ' + _NONSYL, 'j'), ('ʊ' + _NONSYL, 'w'),
        ('ʏ' + _NONSYL, 'j'),
        ('ɐ' + _NONSYL, 'a'),
        (_NONSYL, ''),
        # German dental affricates (Zeit → t͡saɪt)
        ('t' + _TIE + 's', 't s'), ('d' + _TIE + 'z', 'd z'),
        # syllabic consonants → supporting vowel + consonant (the
        # engine cannot synthesize a lone syllabic nasal:
        # 'guten' → ɡuːtn̩ must give g u t @ n)
        ('n' + _SYLL, '@ n'), ('m' + _SYLL, '@ m'),
        ('l' + _SYLL, '@ l'),
        ('ç', 'C'),          # ich-laut → engine palatal fricative 'C'
        ('x', 'X'), ('χ', 'X'),   # ach-laut → uvular fricative 'X'
        ('ʔ', ''),           # glottal stop: absent from the inventory
        # CORRECTIONS v2.1 (g2p-de leak, 2026-10-23): lax ɪ/ʊ/ʏ ->
        # tense i/u/y of the core inventory. The 'I'/'U'/'Y' keys
        # exist on the language-pack side (language_vowel_sets,
        # formantic calibration) but NOT in the engine inventory
        # (constants.ALL_PHONEME_KEYS): before this fix the vowels
        # were emitted then silently dropped by the parsers
        # ("Butter" -> /bt@/, "Mütter" -> /mt@/, "ist" -> /st/).
        ('ɪ', 'i'), ('ʊ', 'u'), ('ʏ', 'y'),
        ('ʋ', 'v'), ('ɱ', 'm'), ('ɘ', '@'), ('ɒ', 'O'),
        (_SYLL, ''),         # other residual syllabics
        ('̥', ''), ('ʰ', ''), ('̊', ''), ('̍', ''),
    ] + _BASE_IPA_TO_KEYS)

_IT_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        ('ao', 'a w'),       # ciao → t͡ʃao: falling diphthong
        # Tuscan /ə/ (atonic e: "come" → ˈkomə): Italian has NO
        # schwa — the '@' key does not exist in its engine inventory
        ('ə', 'e'),
        ('ʎ', 'L'),          # Italian lateral-liquid → engine key 'L'
        ('t' + _TIE + 's', 't s'), ('d' + _TIE + 'z', 'd z'),
        ('ts', 't s'),
    ] + _BASE_IPA_TO_KEYS)

_PT_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        # residual 'ø' (a few TSV borrowings): Portuguese has no
        # front rounded vowel — the '2' key is absent from its
        # engine inventory
        ('ø', 'e'),
        ('ʎ', 'L'),
    ] + _BASE_IPA_TO_KEYS)


# ===========================================================================
# Per-language specification
# ===========================================================================

@dataclass
class LexiconSpec:
    """Description of a language's pronunciation lexicon.

    filename: TSV name inside ``vtl_synth/data/``
    env_var: environment variable overriding the path
    ipa_to_keys: ordered IPA → keys table (longest patterns first)
    source_file: original Wikipron file (traceability)
    variant_policy: choice among the Wiktionary duplicates:
      * ``'short'`` (fr legacy) — avoid liaison artifacts,
        prefer the schwa for words ≤ 3 letters, else the
        shortest form;
      * ``'grapheme'`` (es, de, it, pt) — avoid the artifacts, then
        the variant whose length is closest to the word's grapheme
        count (the Romance/German orthographies are close to one
        grapheme per phoneme; this rejects elided clitic variants:
        it. "la" → /a/ vs /la/, pt. "bom"), tie → the longest.
    """

    lang: str
    filename: str
    env_var: str
    ipa_to_keys: List[Tuple[str, str]]
    source_file: str
    display_name: str
    expected_min: int = 10000
    variant_policy: str = 'grapheme'
    # Spot corrections applied AFTER loading (clearly faulty or
    # dialectal Wiktionary data: the es variant "en" → /em/).
    # Lexicon priority preserved — these are corrected lexicon
    # entries, not g2p exceptions.
    overrides: Dict[str, List[str]] = field(default_factory=dict)


LEXICONS: Dict[str, LexiconSpec] = {
    'fr': LexiconSpec(
        'fr', 'fr_lexicon.tsv', 'COVTL_FR_LEXICON', _FR_IPA_TO_KEYS,
        'fra_latn_broad_filtered.tsv', 'Français',
        variant_policy='short'),
    'es': LexiconSpec(
        'es', 'es_lexicon.tsv', 'COVTL_ES_LEXICON', _ES_IPA_TO_KEYS,
        'spa_latn_ca_broad_filtered.tsv', 'Español',
        overrides={'en': ['e', 'n']}),
    'de': LexiconSpec(
        'de', 'de_lexicon.tsv', 'COVTL_DE_LEXICON', _DE_IPA_TO_KEYS,
        'deu_latn_broad_filtered.tsv', 'Deutsch'),
    'it': LexiconSpec(
        'it', 'it_lexicon.tsv', 'COVTL_IT_LEXICON', _IT_IPA_TO_KEYS,
        'ita_latn_broad_filtered.tsv', 'Italiano'),
    'pt': LexiconSpec(
        'pt', 'pt_lexicon.tsv', 'COVTL_PT_LEXICON', _PT_IPA_TO_KEYS,
        'por_latn_po_broad_filtered.tsv', 'Português'),
}

_DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


# ===========================================================================
# IPA → keys conversion
# ===========================================================================

def ipa_to_keys(ipa: str, lang: str) -> List[str]:
    """Converts an IPA transcription (Wikipron) to engine keys.

    The sequence is NFC-normalized then DESPACED before conversion:
    Wikipron separates each phone with a space ("rey" →
    ``r e i``), and falling diphthongs are written as separate
    full vowels — the table must therefore see ``rei`` as one block
    to apply ``ei → e j``. Greedy conversion position by position
    over the language table; unknown glyphs are silently ignored
    (same contract as ``g2p_fr._ipa_to_keys``).

    Word-stress marks (ˈ primary, ˌ secondary) are STRIPPED here —
    use :func:`ipa_to_keys_stress` to keep them (expressive prosody:
    pitch-accent placement).
    """
    return ipa_to_keys_stress(ipa, lang)[0]


def ipa_to_keys_stress(ipa: str,
                       lang: str) -> Tuple[List[str], Optional[int]]:
    """:func:`ipa_to_keys` variant that keeps the word stress.

    Returns ``(keys, stressed_index)`` where ``stressed_index`` is
    the index of the stressed syllable (counted in emitted vowels,
    the Wikipron ˈ/ˌ mark preceding the stressed syllable onset)
    or ``None`` when the transcription carries no mark.

    The stress travels OUT OF BAND: it never appears in the engine
    keys (the engine inventory is not polluted), only in the
    parallel channel dedicated to expressive prosody
    (``stress_for`` below).
    """
    table = LEXICONS[lang].ipa_to_keys
    ipa = unicodedata.normalize('NFC', ipa).replace(' ', '')
    out: List[str] = []
    primary: Optional[int] = None
    secondary: Optional[int] = None
    vowel_keys = _all_vowel_keys()
    i = 0
    while i < len(ipa):
        ch = ipa[i]
        if ch == '\u02C8':                         # ˈ primary stress
            n_vow = sum(1 for k in out if k.rstrip('~') in vowel_keys)
            primary = n_vow
            i += 1
            continue
        if ch == '\u02CC':                         # ˌ secondary stress
            n_vow = sum(1 for k in out if k.rstrip('~') in vowel_keys)
            secondary = n_vow
            i += 1
            continue
        for pat, repl in table:
            if ipa.startswith(pat, i):
                out.extend(repl.split())
                i += len(pat)
                break
        else:
            i += 1                      # unknown glyph — skipped
    stress = primary if primary is not None else secondary
    return out, stress


def _ipa_chars(lang: str) -> set:
    """Non-ASCII glyphs of the table — a sign the line is IPA."""
    return {c for pat, _ in LEXICONS[lang].ipa_to_keys
            for c in pat if ord(c) > 127}


# ===========================================================================
# TSV loading
# ===========================================================================

def _best_candidate(word: str, cands: List[List[str]],
                    policy: str = 'grapheme') -> List[str]:
    """Picks the best pronunciation among lexicon duplicates.

    The Wiktionary lists several transcriptions per spelling with no
    frequency ranking. Policies (cf. ``LexiconSpec``):

    ``'short'`` (inherited from g2p_fr v2):
      1. avoid liaison artifacts (empty key);
      2. monosyllabic function words (≤ 3 letters): prefer the
         schwa realization ("de" → /də/, not /dam/);
      3. else the shortest realization (canonical form).

    ``'grapheme'`` (es, de, it, pt):
      1. avoid liaison artifacts;
      2. the variant closest, in length, to the word's grapheme
         count (rejects elided clitic variants:
         it. "la" → /a/ vs /la/);
      3. tie → the longest.
    """
    cands = [c for c in cands if c] or [[]]
    if len(cands) == 1:
        return cands[0]

    if policy == 'short':
        def score(c: List[str]) -> tuple:
            junk = 1 if any(k == '' for k in c) else 0
            schwa = 1 if (len(word) <= 3 and '@' in c) else 0
            return (junk, -schwa, len(c))
    else:
        def score(c: List[str]) -> tuple:
            junk = 1 if any(k == '' for k in c) else 0
            return (junk, abs(len(c) - len(word)), -len(c))

    return min(cands, key=score)


def load_lexicon(lang: str, path: Optional[Path] = None) -> dict:
    """Loads the TSV lexicon of ``lang``: ``word<TAB>keys-or-IPA``.

    Returns {} when the lexicon is missing or unusable (graceful
    degradation: the language g2p falls back to its rules).

    In parallel, fills the out-of-band stress channel
    (``ipa_to_keys_stress``) queryable via :func:`stress_for`:
    stressed syllable index per word (None when the transcription
    carries no mark — "engine keys" branch or unstressed Wikipron).
    """
    spec = LEXICONS[lang]
    path = path or Path(os.environ.get(spec.env_var,
                                       str(_DATA_DIR / spec.filename)))
    ipa_glyphs = _ipa_chars(lang)
    candidates: dict = {}
    stress_cands: dict = {}
    n_lines = 0
    with_open = 0
    if not path.exists():
        _STRESS_CACHE[lang] = {}
        return {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            n_lines += 1
            line = line.strip()
            if not line or line.startswith('#') or '\t' not in line:
                continue
            word, _, pron = line.partition('\t')
            word = word.strip().lower().replace('’', "'")
            pron = pron.strip()
            if not word or not pron:
                continue
            tokens = pron.split()
            if (any(c in pron for c in ipa_glyphs)
                    or any(t not in _VALID_KEYS for t in tokens)):
                keys, stress = ipa_to_keys_stress(pron, lang)
            else:                                       # engine keys
                keys = [t if t != 'r' else 'R' for t in tokens]
                stress = None
            if keys:
                candidates.setdefault(word, []).append(keys)
                stress_cands.setdefault(word, []).append(stress)
    lex = {}
    stress = {}
    for w, cands in candidates.items():
        idx = cands.index(_best_candidate(w, cands,
                                          policy=spec.variant_policy))
        lex[w] = cands[idx]
        stress[w] = stress_cands[w][idx]
    if spec.overrides:
        lex.update(spec.overrides)
    if not lex and n_lines > 0:
        # file present but nothing usable — probably an HTML page
        # saved instead of the raw TSV (classic GitHub mistake).
        print(f'[lexicon-{lang}] WARNING: {path} contains no usable '
              f'TSV entry ({n_lines} lines) — lexicon ignored. '
              'Check that the file is the raw TSV (GitHub "Raw" '
              'link), see data/README_fr_lexicon.md')
    _STRESS_CACHE[lang] = stress
    return lex


# ===========================================================================
# Lazy per-language cache
# ===========================================================================

_CACHE: Dict[str, Optional[dict]] = {}
# Out-of-band stress channel (expressive prosody): word → stressed
# syllable index (None = unspecified). Filled by load_lexicon.
_STRESS_CACHE: Dict[str, dict] = {}


def lexicon_for(lang: str) -> dict:
    """Lexicon of ``lang`` (lazy singleton, None when absent).

    Returns an empty dict when the file is missing — callers must
    treat that as "rules only".
    """
    if lang not in _CACHE:
        _CACHE[lang] = load_lexicon(lang)
    return _CACHE[lang] or {}


def stress_for(lang: str) -> dict:
    """Per-word stress index (out-of-band channel, v1.0.8).

    ``{word: stressed_syllable_index | None}`` — the index counts
    syllables in emitted vowels (cf. :func:`ipa_to_keys_stress`).
    Lexicon not loaded → {} (the caller falls back to its
    per-language fallback rules).
    """
    lexicon_for(lang)                    # ensures loading
    return _STRESS_CACHE.get(lang, {})


def lexicon_size(lang: str) -> int:
    """Number of loaded entries (0 when the lexicon is absent)."""
    return len(lexicon_for(lang))


def reset_cache(lang: Optional[str] = None) -> None:
    """Invalidates the cache (tests / file swap)."""
    if lang is None:
        _CACHE.clear()
        _STRESS_CACHE.clear()
    else:
        _CACHE.pop(lang, None)
        _STRESS_CACHE.pop(lang, None)


def has_lexicon(lang: str) -> bool:
    """True when the TSV file of ``lang`` is present on disk."""
    spec = LEXICONS[lang]
    return (Path(os.environ.get(spec.env_var,
                                str(_DATA_DIR / spec.filename))).exists())


__all__ = [
    'LexiconSpec', 'LEXICONS', 'load_lexicon', 'lexicon_for',
    'lexicon_size', 'reset_cache', 'has_lexicon', 'ipa_to_keys',
    'ipa_to_keys_stress', 'stress_for',
]
