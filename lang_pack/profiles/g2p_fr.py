# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_fr.py (v2)
==============
French grapheme-to-phoneme gateway (text → engine SAMPA), v2.

Improvements over the legacy v1 (cf. ``g2p_fr_legacy.py``)
----------------------------------------------------------
1. **Silent final consonants handled correctly** — the trailing run of
   mute consonants is stripped on the orthography BEFORE the rule pass:
   "J'attends" → /Zata~/ (v1 gave /Zata~d/ — the /d/ was pronounced).
   Guards keep pronounced finals: "net", "but", "sud", "ouest"…
2. **Verbal -ent ending** ("ils chantent", "ils chantaient") dropped
   when len ≥ 6, except pronounced nouns ("content", "moment"…).
3. **Final mute -e** dropped ("chaise" → /SEz/), WITH the French
   voicing effect: the final /s/ before the mute -e becomes /z/, and
   the consonant preceding the -e is no longer stripped
   ("petite" → /p@tit/).
4. **External pronunciation lexicon** — the CMUdict-equivalent. Drop a
   lexicon file at ``vtl_synth/data/fr_lexicon.tsv`` (or point
   ``$COVTL_FR_LEXICON`` at it); formats accepted:
     - ``word<TAB>keys``  engine keys, space-separated
     - ``word<TAB>IPA``   Wikipron/Lexique-style IPA (auto-detected and
       converted, cf. ``_IPA_TO_KEYS``).
   Suggested download (Wikipron, CC BY-SA):
     https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/fra_latn_broad_filtered.tsv
   Lexicon entries take priority over everything else (like CMUdict
   for English). The loader is lazy and failure-tolerant: a missing or
   malformed lexicon degrades gracefully to the rule engine.
   Since v1.0.7 the loading machinery is shared by all languages:
   :mod:`vtl_synth.utils.lexicon_loader` (same TSV format, same
   heuristic for duplicate entries); ``_load_lexicon`` below is a thin
   delegate kept for backward compatibility.

Conversion order per word: lexicon → ``_FR_EXCEPTIONS`` → elision
split → orthographic preprocessing (silent endings) → rule table
(imported from the legacy module).

This module reuses ``_FR_EXCEPTIONS`` and ``_FR_RULES`` from
``g2p_fr_legacy.py`` (single source of the v1 data).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from vtl_synth.core.phonemes import keys_to_connected

# v1 data (exceptions dictionary + rule table) — reused, not duplicated.
from vtl_synth.utils.g2p_fr_legacy import (
    _FR_EXCEPTIONS,
    _FR_RULES,
    _COMMA_RE,
    _SENT_PUNCT_RE,
    _WORD_RE,
    _normalize_input,
)

_FR_RULES_SORTED: list = sorted(_FR_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Pronunciation lexicon (CMUdict-equivalent layer)
# ===========================================================================
# Delegates to the shared multilingual loader (v1.0.7): the French spec
# (filename / env var / IPA table) lives in lexicon_loader.LEXICONS.

from vtl_synth.utils.lexicon_loader import (
    lexicon_for as _lexicon_for,
    load_lexicon as _load_lexicon_shared,
    ipa_to_keys as _ipa_keys,
)

_DEFAULT_LEXICON = Path(__file__).resolve().parent.parent / 'data' / 'fr_lexicon.tsv'

# IPA (Wikipron/Lexique French) → engine SAMPA keys — moved to
# lexicon_loader._FR_IPA_TO_KEYS (single source); re-exported for the
# legacy callers/tests that introspect this module.


def _ipa_to_keys(ipa: str) -> List[str]:
    """Convert a Wikipron/Lexique French IPA transcription to engine keys."""
    return _ipa_keys(ipa, 'fr')


def _load_lexicon(path: Optional[Path] = None) -> dict:
    """Load the French TSV lexicon (delegate to :mod:`lexicon_loader`).

    Returns {} when no lexicon is installed (graceful degradation).
    """
    if path is None:
        return _lexicon_for('fr')
    return _load_lexicon_shared('fr', path)


_LEXICON: Optional[dict] = None      # lazy singleton (delegates to loader)


def _lexicon() -> dict:
    global _LEXICON
    if _LEXICON is None:
        _LEXICON = _lexicon_for('fr')
    return _LEXICON


# ===========================================================================
# Words whose final consonant IS pronounced (exceptions to the stripping)
# ===========================================================================

_FINAL_PRONOUNCED: set = {
    # -t pronounced
    'net', 'but', 'sud', 'ouest', 'est', 'ouest', 'direct', 'act',
    'fact', 'chut', 'brut', 'transat', 'foot', 'toast', 'self',
    # -p pronounced
    'cap', 'stop', 'snap', 'club', 'snob', 'job', 'rob',
    # -g pronounced (loanwords)
    'ring', 'bing', 'jazz', 'bus', 'plus', 'rabais',
    # -d pronounced (loanwords)
    'standard', 'iced', 'weekend', 'week-end',
    # -s pronounced
    'as', 'atlas', 'alors', 'basis', 'virus', 'rebus', 'rhinocéros',
    'jazz', 'fils',
    # -x pronounced
    'mieux', 'moeurs',
}

# Words ending in -ent where the ending is NOT a verb suffix.
_ENT_PRONOUNCED: set = {
    'content', 'comment', 'moment', 'avant', 'vent', 'dent', 'lent',
    'temporairement', 'présent', 'absent', 'different', 'différent',
    'parent', 'courant', 'couronne', 'souvent', 'littéralement',
    'évidemment', 'constamment', 'lent', 'printemps', 'temps',
}

# Monosyllabic function words where the final mute -e IS the pronunciation
# (schwa): never drop their final -e.
_SCHWA_WORDS: set = {'je', 'le', 'que', 'ne', 'me', 'te', 'se', 'de', 'ce'}


# ===========================================================================
# Orthographic preprocessing
# ===========================================================================

def _strip_silent_endings(word: str) -> str:
    """Strip the trailing run of silent letters on the orthography.

    Guards keep pronounced finals ("net", "sud", "club"…) and the
    -ent verbal/nominal ambiguity (cf. ``_ENT_PRONOUNCED``).
    """
    # 1. verbal -ent(s) (3rd person plural): "chantent" -> "chant",
    #    "chantaient" -> "chanta" (ai -> E). len >= 6 keeps "sent"(v.
    #    sentir) and 4-5-letter nouns in the pronounced set.
    if len(word) >= 6 and word.endswith('ents') and word not in _ENT_PRONOUNCED:
        word = word[:-4]
    elif len(word) >= 6 and word.endswith('ent') and word not in _ENT_PRONOUNCED:
        word = word[:-3]
    # 2. iterate over the trailing silent consonants
    for _ in range(3):
        if len(word) <= 2 or word in _FINAL_PRONOUNCED:
            break
        last, prev = word[-1], word[-2:-1]
        if last in 'sxz':
            word = word[:-1]
        elif last == 'd' and prev in 'nm':          # grand, attends…
            word = word[:-1]
        elif last == 't' and word not in _FINAL_PRONOUNCED:
            word = word[:-1]
        elif last == 'p' and word not in _FINAL_PRONOUNCED:
            word = word[:-1]
        elif last == 'g' and prev in 'n':           # long, sang…
            word = word[:-1]
        else:
            break
    return word


def _word_to_keys(word: str, warnings: list) -> list:
    """Convert one French word to a list of engine SAMPA keys (v2)."""
    word_lc = word.lower().replace('’', "'")

    # (0) external pronunciation lexicon — highest priority
    lex_keys = _lexicon().get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) built-in exceptions dictionary
    if word_lc in _FR_EXCEPTIONS:
        return _FR_EXCEPTIONS[word_lc].split()

    # (b) elision apostrophe ("l'eau", "j'ai"…)
    if "'" in word_lc:
        elision_prefixes = {
            'l': 'l', 'j': 'Z', 'm': 'm', 'n': 'n', 's': 'z',
            't': 't', 'd': 'd', 'c': 'k', 'qu': 'k',
        }
        prefix_keys: list = []
        rest = word_lc
        while "'" in rest:
            head, _, tail = rest.partition("'")
            if head in elision_prefixes:
                prefix_keys.append(elision_prefixes[head])
            rest = tail
        rest_keys = _word_to_keys(rest, warnings) if rest else []
        return prefix_keys + rest_keys

    # (c) orthographic preprocessing
    drop_mute_e = False
    if (word_lc.endswith('e') and len(word_lc) >= 3
            and not word_lc.endswith(('ée', 'ë'))
            and word_lc not in _SCHWA_WORDS
            and word_lc[:-1] not in _FINAL_PRONOUNCED):
        word_lc = word_lc[:-1]
        drop_mute_e = True
    else:
        word_lc = _strip_silent_endings(word_lc)

    # (d) rule pass
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        matched = False
        for pat, repl in _FR_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:
                    keys.extend(repl.split())
                i += len(pat)
                matched = True
                break
        if not matched:
            warnings.append(
                f"FR g2p: unknown character {word_lc[i]!r} in word {word!r}"
            )
            keys.append(word_lc[i])
            i += 1

    keys = [k for k in keys if k]

    # (e) post-processing of the dropped mute -e: the preceding
    # consonant is voiced (French s -> z) and NOT silent.
    if drop_mute_e and keys and keys[-1] == 's':
        keys[-1] = 'z'
    return keys


def _phrase_to_sampa(phrase: str, warnings: list) -> str:
    """Convert one phrase (words only) to SAMPA."""
    words = _WORD_RE.findall(phrase)
    if not words:
        return ''
    tokens: List[str] = []
    for w in words:
        keys = _word_to_keys(w, warnings)
        if not keys:
            continue
        tokens.append(keys_to_connected(keys))
    return '.'.join(tokens)


def text_to_sampa_fr(text: str, warnings: list = None, **kwargs) -> str:
    """Convert French ``text`` to an engine SAMPA sequence (v2).

    Same contract as v1 (and as ``vtl_synth.utils.g2p.text_to_sampa``):
    sentence punctuation becomes ``|``; commas become short pauses.

    Enhancements over v1:
      * trailing run of silent consonants stripped ("J'attends" ->
        /Zata~/);
      * verbal -ent(s) dropped ("ils chantent" -> /Sɑ̃t/);
      * final mute -e dropped with the s -> z voicing ("chaise" ->
        /SEz/; "petite" -> /p@tit/);
      * external pronunciation lexicon (CMUdict-equivalent layer) via
        ``vtl_synth/data/fr_lexicon.tsv`` or ``$COVTL_FR_LEXICON``
        (Wikipron/Lexique IPA accepted, auto-converted).
    """
    own = warnings is None
    if own:
        warnings = []

    text = _normalize_input(text)

    phrases = _SENT_PUNCT_RE.split(text)
    out_phrases: List[str] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        parts = _COMMA_RE.split(phrase)
        sampa_parts = [_phrase_to_sampa(p, warnings) for p in parts]
        sampa_parts = [s for s in sampa_parts if s]
        if sampa_parts:
            out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p-fr] {w}')
    return ' | '.join(out_phrases)


__all__ = [
    'text_to_sampa_fr',
    '_FR_EXCEPTIONS',
    '_FR_RULES',
    '_load_lexicon',
    '_ipa_to_keys',
]
