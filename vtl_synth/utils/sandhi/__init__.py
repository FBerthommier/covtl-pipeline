# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""covtl-sandhi — cross-word sandhi for the COVTL pipeline languages.

This package is the **full rule set** (Branch B of the distribution).
The light hook shipped by Branch A (``covtl-pipeline-sandhi-hook``)
imports :func:`apply_sandhi` from here once the package is installed
into ``vtl_synth/utils/sandhi/``; without it, the hook falls back to
the identity stub and the pipeline behaves exactly as before.

Public API
----------
``SANDHI_LEVELS``
    ``('off', 'minimal', 'standard', 'careful')`` — a monotone
    *coverage filter* over each language's rule set:

    * ``off``      — identity, bit-identical baselines (the default);
    * ``minimal``  — categorical, exceptionless sandhi only
      (fr: obligatory liaison; it: d eufonico + monosyllabic
      triggers; es: y->e / o->u alternation; pt: encadeamento after
      function words; de: Glottalversatz before vowel-initial nouns;
      en: a -> an);
    * ``standard`` — recommended: adds the productive/optional rules
      (fr: facultative liaison of the common class; it: full
      raddoppiamento trigger list incl. oxytons; es: enlace; pt:
      encadeamento everywhere + EP voicing; de: boundary before every
      vowel-initial lexical word; en: onset linking / linking-r);
    * ``careful``  — hyperarticulate register (fr: style soutenu,
      liaison after plural nouns; de: boundary before function words
      too). Where the language has no register-dependent rule (it, es,
      pt, en at v0.1) careful equals standard — stated honestly in
      the docs, never silently.

``sandhi_supported(lang)``
    True when a rule module exists for the language.

``apply_sandhi(lang, words, keys, level, *, g2p=None, warnings=None)``
    LOW-LEVEL entry: called **after per-word G2P, before the phrase
    join ('.' / space)**. Takes the orthographic words and their
    per-word SAMPA keys, returns the modified per-word keys (same
    length). Merged pairs are expressed inside the slots (fr
    ``['fo', 'i'] -> ['fo', 'ti']``, es ``['los', 'a.mi.gos'] ->
    ['lo', 'sa.mi.gos']``); the German boundary marks W2 with a
    leading space. This entry inherits the base g2p's per-word tokens
    (no oracle corrections): for full fidelity use the gateway below.

``join_words_keys(keys, sep)``
    Boundary-aware join of per-word keys into an engine phrase.

``apply_sandhi_text(lang, text, g2p, level, mode, warnings)``
    GATEWAY used by the pipeline hook (monotone path). ``mode`` keeps
    the three historical implementations as an option:

    * ``'g2p'`` (default, recommended) — liaison-aware per-word
      oracle + pair merge with corrected tokens;
    * ``'post'`` — SAMPA post-processor, the base g2p untouched;
    * ``'pre'``  — orthographic rewrite before the g2p (returns the
      g2p output over the rewritten text).

``sandhi_rewrite_text(lang, text, g2p, level, warnings)``
    Mode ``'pre'`` alone: the REWRITTEN ORTHOGRAPHY (not the SAMPA),
    so the pipeline can hand it to the expressive planner.

``apply_sandhi_sampa(lang, text, sampa, g2p, level, mode, warnings)``
    Expressive-path variant: merges the pairs into an already
    produced (breath-marked '%') SAMPA — never across a pause, so the
    F0 plans of the prosody patch stay aligned. ``mode='g2p'`` (the
    planner saw the oracle tokens) rewrites the pair slots; ``'post'``
    (planner saw the base g2p) inserts only.

``sandhi_oracle(lang, word, g2p)``
    Corrected per-word token of a language module (used to wrap the
    g2p of the expressive plan).

The inter-word '.' joining performed by the language g2p is **not**
sandhi: it is plain connected speech inside one phrase. Sandhi is
what happens AT the word boundary (latent consonant, gemination,
displacement, glottal boundary). The engine, the polar/syltraj
modules and the prosody patch are never touched.
"""

from __future__ import annotations

import importlib
from typing import Callable, Dict, List, Optional, Sequence

from .base import (
    LEVEL_CAREFUL,
    LEVEL_MINIMAL,
    LEVEL_STANDARD,
    SANDHI_LEVELS,
    join_words_keys,
    level_rank,
    normalize_lang,
)

__all__ = [
    'SANDHI_LEVELS',
    'SANDHI_LANGS',
    'SANDHI_FULL',
    'sandhi_supported',
    'get_module',
    'sandhi_oracle',
    'apply_sandhi',
    'join_words_keys',
    'apply_sandhi_text',
    'sandhi_rewrite_text',
    'apply_sandhi_sampa',
]

#: Full rule package is installed (the Branch A stub sets this False).
SANDHI_FULL: bool = True

#: Languages with a rule module in this package (the covtl-pipeline
#: language pack: fr, en, es, de, it, pt — 'en' is the pipeline
#: default profile, CMUdict gateway).
SANDHI_LANGS = frozenset({'fr', 'en', 'it', 'es', 'de', 'pt'})

#: Gateway modes — the three historical implementations, kept as an
#: option (the recommended one is 'g2p').
SANDHI_MODES = ('g2p', 'post', 'pre')

_modules: Dict[str, object] = {}


def get_module(lang: str):
    """Rule module of a language (None when unsupported)."""
    code = normalize_lang(lang)
    if code not in SANDHI_LANGS:
        return None
    if code not in _modules:
        _modules[code] = importlib.import_module(f'.{code}', __name__)
    return _modules[code]


def sandhi_supported(lang: str) -> bool:
    """True when the language has a sandhi rule module."""
    return get_module(lang) is not None


def sandhi_oracle(lang: str, word: str,
                  g2p: Callable[..., str]) -> str:
    """Corrected per-word token of ``lang``'s module for ``word``."""
    mod = get_module(lang)
    if mod is None:
        return (g2p(word, warnings=None) or '').strip() \
            if g2p is not None else ''
    return mod.sandhi_oracle(word, g2p)


def apply_sandhi(lang: str,
                 words: Sequence[str],
                 keys: Sequence[str],
                 level: str = 'standard',
                 *,
                 g2p: Optional[Callable[..., str]] = None,
                 warnings: Optional[list] = None) -> List[str]:
    """Low-level entry — per-word keys, AFTER per-word G2P.

    Parameters
    ----------
    words : sequence of str
        Orthographic word tokens of ONE phrase part (no sentence
        punctuation; the caller's g2p handles the splitting).
    keys : sequence of str
        Per-word SAMPA of ``words`` (same length; '' for words the
        g2p skipped).
    level : str
        One of :data:`SANDHI_LEVELS` ('off' returns ``keys`` copy).
    g2p : callable, optional
        Unused by the current modules (kept for extensions that need
        to re-query the g2p mid-pair).

    Returns
    -------
    list of str
        New per-word keys, same length as ``keys``. Adjacent-pair
        sandhi is expressed *inside* the two slots, e.g.
        ``['fo', 'i'] -> ['fo', 'ti']`` (fr minimal), ``['los',
        'a.mi.gos'] -> ['lo', 'sa.mi.gos']`` (es standard); the
        German glottal boundary marks the W2 slot with a leading
        space: ``['ajn', 'a.pf@l'] -> ['ajn', ' a.pf@l']``.

    See Also
    --------
    join_words_keys : join the result into an engine phrase.
    """
    rank = level_rank(level)
    words = list(words or [])
    keys = list(keys or [])
    if len(words) != len(keys):
        raise ValueError(
            f'apply_sandhi: words and keys must have the same length '
            f'({len(words)} != {len(keys)})')
    out = list(keys)
    if rank == 0 or len(words) < 2:
        return out
    mod = get_module(lang)
    if mod is None:
        if warnings is not None:
            warnings.append(
                f"sandhi: no rule module for {lang!r} "
                f"({'/'.join(sorted(SANDHI_LANGS))}) — keys unchanged")
        return out
    for k in range(len(words) - 1):
        merged = mod.decide_pair(
            words[k], words[k + 1], out[k], out[k + 1],
            first_in_part=(k == 0), level=level)
        if merged is not None:
            out[k], out[k + 1] = merged
    return out


def apply_sandhi_text(lang: str,
                      text: str,
                      g2p: Callable[..., str],
                      level: str = 'standard',
                      mode: str = 'g2p',
                      warnings: Optional[list] = None) -> str:
    """Gateway over a whole text (monotone path — the hook entry).

    ``mode='g2p'`` (recommended): per-word oracle of the language
    module + pair merge with corrected tokens (fr: « faut il » ->
    ``fo.til``). ``mode='post'``: SAMPA post-processor, base g2p
    untouched. ``mode='pre'``: orthographic rewrite, then the base
    g2p. Without a pair, every mode returns the base g2p output.
    """
    own = warnings is None
    if own:
        warnings = []
    mod = get_module(lang)
    if mod is None:
        if level_rank(level) and normalize_lang(lang) not in SANDHI_LANGS:
            warnings.append(
                f"sandhi: no rule module for {lang!r} — "
                f"text passed through unchanged")
        return g2p(text, warnings=warnings)
    if mode not in SANDHI_MODES:
        raise ValueError(
            f"mode must be one of {'/'.join(SANDHI_MODES)}, got {mode!r}")
    if mode == 'pre':
        text2 = mod.apply_sandhi_pre(text, g2p, level=level,
                                     warnings=warnings)
        return g2p(text2, warnings=warnings)
    if mode == 'post':
        base = g2p(text, warnings=warnings)
        return mod.apply_sandhi_post(text, base, g2p, level=level,
                                     warnings=warnings)
    return mod.sandhi_g2p(text, g2p, level=level, warnings=warnings)


def sandhi_rewrite_text(lang: str,
                        text: str,
                        g2p: Callable[..., str],
                        level: str = 'standard',
                        warnings: Optional[list] = None) -> str:
    """Mode ``'pre'`` alone: the REWRITTEN TEXT (orthography).

    Used by the pipeline hook so that the expressive planner sees the
    same respelled porteurs as the monotone path. Languages without
    an orthographic encoding (de: the glottal boundary has no
    spelling) return the text unchanged, with a warning per skipped
    pair — the modes g2p/post carry the phenomenon instead.
    """
    own = warnings is None
    if own:
        warnings = []
    mod = get_module(lang)
    if mod is None:
        return text
    return mod.apply_sandhi_pre(text, g2p, level=level,
                                warnings=warnings)


def apply_sandhi_sampa(lang: str,
                       text: str,
                       sampa: str,
                       g2p: Callable[..., str],
                       level: str = 'standard',
                       mode: str = 'g2p',
                       warnings: Optional[list] = None) -> str:
    """Expressive-path variant: merge the pairs into an already
    produced SAMPA (breath markers '%' of the prosody plan present).

    ``mode='g2p'`` — the planner was fed the ORACLE tokens (hook:
    ``sandhi_oracle``), so the pair slots are REWRITTEN with the
    corrected tokens. ``mode='post'`` — the planner saw the base g2p:
    INSERTION ONLY, the tokens of the plan are kept. Never inserts
    across a pause; on any alignment failure the phrase is returned
    unchanged (the F0 plans stay aligned by design: a consonant is
    never a nucleus).
    """
    own = warnings is None
    if own:
        warnings = []
    mod = get_module(lang)
    if mod is None:
        return sampa
    if mode not in SANDHI_MODES:
        raise ValueError(
            f"mode must be one of {'/'.join(SANDHI_MODES)}, got {mode!r}")
    if mode == 'pre':
        return sampa          # the rewritten text was already planned
    return mod.apply_sandhi_post(
        text, sampa, g2p, level=level, warnings=warnings,
        token_view='oracle' if mode == 'g2p' else 'base',
        replace_tokens=(mode == 'g2p'))
