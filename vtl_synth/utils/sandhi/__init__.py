# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""vtl_synth.utils.sandhi — Branch A: the pipeline hook (STUB).

Cross-word sandhi (French liaison, English a-an + onset linking,
Italian raddoppiamento + euphonic d, Spanish enlace, Portuguese
encadeamento, German Glottalversatz) — see the covtl-sandhi package
(Branch B) for the full rule set.

Two-branch architecture
-----------------------
* **Branch A (this file)** — a light HOOK shipped as a pipeline patch:
  the ``--sandhi`` / ``--sandhi-mode`` options and the call sites.
  This stub is the IDENTITY: every entry point returns its input
  unchanged, so a pipeline patched with Branch A but WITHOUT Branch B
  produces **bit-identical outputs** to the unpatched repository
  (``--sandhi off``, the default, never even reaches this module).
* **Branch B (covtl-sandhi)** — the full rule package. Activate it
  either by copying the package's ``sandhi/`` CONTENT over this stub
  (``cp -r sandhi/. vtl_synth/utils/sandhi/`` — note the ``/.``:
  the destination folder of the stub ALREADY EXISTS, a plain
  ``cp -r sandhi/ vtl_synth/utils/sandhi/`` would nest it one level
  too deep) or by ``pip install covtl-sandhi`` (the pipeline
  resolves ``import sandhi`` from site-packages when the stub is
  still in place).

The stub exposes EXACTLY the public API of the full package
(``SANDHI_LEVELS``, ``SANDHI_MODES``, ``SANDHI_LANGS``, ``SANDHI_FULL``,
``sandhi_supported``, ``sandhi_oracle``, ``apply_sandhi``,
``join_words_keys``, ``apply_sandhi_text``, ``sandhi_rewrite_text``,
``apply_sandhi_sampa``) so that the pipeline call sites work
untouched in all three states: stub / pip package / copied package.

Levels — ``off | minimal | standard | careful``
----------------------------------------------
A monotone *coverage filter* over each language's rule set (it never
changes the phonology of a rule that fires):

* ``off``      — identity, bit-identical baselines (CLI default);
* ``minimal``  — categorical, exceptionless sandhi only;
* ``standard`` — recommended (API default): adds the productive
  rules; equals the historical 5-language patch (v3) for fr/it/es/
  pt/de;
* ``careful``  — hyperarticulate register (fr: liaison after plural
  nouns; de: glottal boundary before function words too); where the
  language has no register-dependent rule (it, es, pt, en at v0.1)
  careful equals standard — stated honestly, never silently.

Modes — ``g2p | post | pre`` (the three historical implementations
kept as an option; ``g2p``, the recommended one, is the default)
------------------------------------------------------------------
* ``g2p``  — liaison-aware per-word oracle + pair merge with
  corrected tokens (fr « faut il » -> ``fo.til``);
* ``post`` — SAMPA post-processor, the base g2p untouched;
* ``pre``  — orthographic rewrite before the g2p (no-op with a
  warning for de/en: the phenomenon has no spelling).
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

__all__ = [
    'SANDHI_LEVELS',
    'SANDHI_MODES',
    'SANDHI_LANGS',
    'SANDHI_FULL',
    'level_rank',
    'sandhi_supported',
    'sandhi_oracle',
    'apply_sandhi',
    'join_words_keys',
    'apply_sandhi_text',
    'sandhi_rewrite_text',
    'apply_sandhi_sampa',
]

#: Accepted values of the ``sandhi`` option (hook + CLI + API).
SANDHI_LEVELS = ('off', 'minimal', 'standard', 'careful')

#: Gateway modes — the three historical implementations.
SANDHI_MODES = ('g2p', 'post', 'pre')

#: Languages with a rule module — EMPTY in the stub (the Branch B
#: package ships fr/en/it/es/de/pt).
SANDHI_LANGS = frozenset()            # type: ignore[assignment]

#: False in the stub (Branch B sets True): the rule package is NOT
#: installed. The pipeline warns once per run when a sandhi level is
#: requested while this stays False.
SANDHI_FULL = False

_LEVEL_RANK = {'off': 0, 'minimal': 1, 'standard': 2, 'careful': 3}


def level_rank(level: str) -> int:
    """Rank of a sandhi level (0 for ``off``) — validates EARLY so
    that a typo never silently degrades to ``off``."""
    low = str(level or 'off').lower()
    if low not in _LEVEL_RANK:
        raise ValueError(
            f"sandhi level must be one of {'/'.join(SANDHI_LEVELS)}, "
            f"got {level!r}")
    return _LEVEL_RANK[low]


def sandhi_supported(lang: str) -> bool:
    """True when the language has a sandhi rule module (never, in
    the stub)."""
    return False


def sandhi_oracle(lang: str, word: str,
                  g2p: Callable[..., str]) -> str:
    """Per-word token of the ACTIVE g2p (identity view — the stub has
    no closed-class corrections)."""
    return (g2p(word, warnings=None) or '').strip() \
        if g2p is not None else ''


def apply_sandhi(lang: str,
                 words: Sequence[str],
                 keys: Sequence[str],
                 level: str = 'standard',
                 *,
                 g2p: Optional[Callable[..., str]] = None,
                 warnings: Optional[list] = None) -> List[str]:
    """Low-level entry (per-word keys, after per-word G2P) — the stub
    returns ``keys`` unchanged (identity)."""
    level_rank(level)                  # validate early, like Branch B
    words = list(words or [])
    keys = list(keys or [])
    if len(words) != len(keys):
        raise ValueError(
            f'apply_sandhi: words and keys must have the same length '
            f'({len(words)} != {len(keys)})')
    return keys


def join_words_keys(keys: Sequence[str], sep: str = ' ') -> str:
    """Boundary-aware join of per-word keys into an engine phrase
    (same contract as Branch B: an empty fragment marks an absorbed
    slot, a leading space absorbs the separator)."""
    parts = [k for k in keys if k]
    out = ''
    for k in parts:
        if not out:
            out = k
        elif k.startswith(' ') or out.endswith((' ', '.')):
            out += k
        else:
            out += sep + k
    return out


def apply_sandhi_text(lang: str,
                      text: str,
                      g2p: Callable[..., str],
                      level: str = 'standard',
                      mode: str = 'g2p',
                      warnings: Optional[list] = None) -> str:
    """Gateway over a whole text (monotone path) — the stub returns
    the base g2p output, with a warning that Branch B is missing."""
    level_rank(level)
    if mode not in SANDHI_MODES:
        raise ValueError(
            f"mode must be one of {'/'.join(SANDHI_MODES)}, got {mode!r}")
    own = warnings is None
    if own:
        warnings = []
    if level_rank(level):
        warnings.append(
            'sandhi: rule package (covtl-sandhi, Branch B) not '
            'installed — text passed through the base g2p unchanged')
    return g2p(text, warnings=warnings)


def sandhi_rewrite_text(lang: str,
                        text: str,
                        g2p: Callable[..., str],
                        level: str = 'standard',
                        warnings: Optional[list] = None) -> str:
    """Mode ``pre`` alone: the REWRITTEN ORTHOGRAPHY — the stub
    returns the text unchanged."""
    level_rank(level)
    return text


def apply_sandhi_sampa(lang: str,
                       text: str,
                       sampa: str,
                       g2p: Callable[..., str],
                       level: str = 'standard',
                       mode: str = 'g2p',
                       warnings: Optional[list] = None) -> str:
    """Expressive-path variant (breath-marked SAMPA) — the stub
    returns ``sampa`` unchanged, so the F0 plans stay as planned."""
    level_rank(level)
    return sampa
