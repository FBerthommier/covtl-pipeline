# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""base.py — shared helpers of the covtl-sandhi package.

Only stdlib here: the package must import with or without the
covtl-pipeline environment (standalone demos, tests, third-party
callers), exactly like the historical per-language liaison modules.

What lives here:

* the four **sandhi levels** and their rank (the level is a *coverage
  filter* on the rule set of each language module — it never changes
  the phonology of a rule that fires);
* a tiny **data-file loader** — every rule table that a user may want
  to extend (h aspiré list, liaison triggers, Italian raddoppiamento
  triggers, ...) is embedded as a Python default *and* read from
  ``sandhi/data/*.txt`` when present, one entry per line, ``#``
  comments allowed;
* the **boundary-aware key join** used by the low-level
  :func:`apply_sandhi` entry point (per-word keys -> phrase string).

This module deliberately knows nothing about individual languages.
"""

from __future__ import annotations

from pathlib import Path
from typing import FrozenSet, Iterable, List, Sequence, Tuple

__all__ = [
    'SANDHI_LEVELS',
    'LEVEL_MINIMAL',
    'LEVEL_STANDARD',
    'LEVEL_CAREFUL',
    'level_rank',
    'normalize_lang',
    'load_wordlist',
    'split_final_key',
    'join_words_keys',
]

#: Accepted values of the ``sandhi`` option (hook + CLI + API).
SANDHI_LEVELS: Tuple[str, ...] = ('off', 'minimal', 'standard', 'careful')

#: Ranks — monotone rule coverage: minimal <= standard <= careful.
#: ``off`` (rank 0) is the identity: no cross-word phonology at all.
_LEVEL_RANK: dict = {
    'off': 0,
    'minimal': 1,     # categorical, exceptionless rules only
    'standard': 2,    # + productive/optional rules (recommended)
    'careful': 3,     # + hyperarticulate register (style soutenu)
}

LEVEL_MINIMAL = 1
LEVEL_STANDARD = 2
LEVEL_CAREFUL = 3


def level_rank(level: str) -> int:
    """Rank of a sandhi level (0 for ``off``).

    Raises
    ------
    ValueError
        Unknown level — the hook and the CLI validate early so that a
        typo never silently degrades to ``off``.
    """
    low = str(level or 'off').lower()
    if low not in _LEVEL_RANK:
        raise ValueError(
            f"sandhi level must be one of {'/'.join(SANDHI_LEVELS)}, "
            f"got {level!r}")
    return _LEVEL_RANK[low]


def normalize_lang(lang: str) -> str:
    """Two-letter, lower-case language code ('' when None)."""
    return (lang or '').strip().lower()


#: Directory of the optional data files (``sandhi/data``).
_DATA_DIR = Path(__file__).resolve().parent / 'data'


def load_wordlist(filename: str,
                  fallback: FrozenSet[str]) -> FrozenSet[str]:
    """Read ``sandhi/data/<filename>`` (one word per line, ``#``
    comments, leading/trailing blanks stripped, case-folded).

    When the file is missing or unreadable the embedded ``fallback``
    frozenset is returned, so the package is always importable and
    testable — the txt files are an *editable view* of the defaults,
    not a hard dependency.
    """
    path = _DATA_DIR / filename
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return fallback
    words = set()
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            words.add(line.lower())
    return frozenset(words) if words else fallback


#: SAMPA multi-character keys that must never be split (affricates).
_TOKEN_PAIRS: Tuple[str, ...] = ('tS', 'dZ', 'ts')


def split_final_key(tok: str) -> Tuple[str, str]:
    """Split a connected token into (head, final_key).

    The final key keeps multi-character consonants whole ('tS', 'dZ',
    'ts'): ``'wAtS'`` -> ``('wA', 'tS')``. Used by the displacement
    rules (es/pt/en linking): the final consonantal key of W1 becomes
    the onset of the vowel-initial W2.
    """
    if not tok:
        return ('', '')
    two = tok[-2:]
    if two in _TOKEN_PAIRS:
        return (tok[:-2], two)
    return (tok[:-1], tok[-1:])


def join_words_keys(keys: Sequence[str], sep: str = ' ') -> str:
    """Join per-word keys into one phrase string (engine notation).

    Contract of the low-level :func:`apply_sandhi` entry point:

    * an **empty** fragment marks a word slot absorbed by a fusion
      (never emitted by the current modules, kept for extensions);
    * a fragment already carrying a **boundary space** (German
      Glottalversatz marks the word boundary with ' ', the engine
      short-pause notation) absorbs the separator — no doubling.
    """
    parts: List[str] = [k for k in keys if k]
    out = ''
    for k in parts:
        if not out:
            out = k
        elif k.startswith(' ') or out.endswith((' ', '.')):
            out += k
        else:
            out += sep + k
    return out


def iter_pairs(words: Sequence[str]
               ) -> Iterable[Tuple[int, str, str]]:
    """Adjacent (index, w1, w2) pairs of a flat word list."""
    for k in range(len(words) - 1):
        yield k, words[k], words[k + 1]
