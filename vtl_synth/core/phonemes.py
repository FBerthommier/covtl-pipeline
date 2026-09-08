# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
phonemes.py
===========
Phoneme tables shared by the g2p gateway and the CLI.

Two notation systems meet here:

  * the engine inventory (SAMPA-like keys, from ``constants.py``):
    vowels ``a e i o u y E O @ 2 6 9`` and consonants
    ``p b t d k g f v s z S Z T D tS dZ m n J l R j w h ɥ`` plus
    the specialised selector keys (``C L N X z_front g_pal g_vel``)
  * ARPAbet (CMUdict, 39 symbols), the output of the English
    grapheme-to-phoneme dictionary.

The ``ARPA_TO_SAMPA`` table maps every ARPAbet symbol onto one engine
key (or a short sequence of keys for diphthongs and rhotacised
vowels).  Stress digits (0/1/2) are stripped before lookup.

This module has no dependency on numpy or VTL so that it can be used
by lightweight tooling (``vtl-synth inspect``, unit tests, ...).
"""

from __future__ import annotations

from vtl_synth.core.constants import (
    ALL_PHONEME_KEYS,
    CONSONANT_TARGETS,
    VOWEL_TARGETS,
)

# --------------------------------------------------------------------------
# Engine inventory (re-exported for convenience)
# --------------------------------------------------------------------------

SAMPA_VOWELS: frozenset = frozenset(VOWEL_TARGETS.keys())
SAMPA_CONSONANTS: frozenset = frozenset(CONSONANT_TARGETS.keys())

# Longest-first ordering for the greedy splitter
_KEYS_BY_LENGTH = sorted(ALL_PHONEME_KEYS, key=len, reverse=True)

# --------------------------------------------------------------------------
# ARPAbet -> SAMPA (engine keys)
# --------------------------------------------------------------------------

ARPA_TO_SAMPA: dict = {
    # stops
    'P': 'p', 'B': 'b', 'T': 't', 'D': 'd', 'K': 'k', 'G': 'g',
    # affricates
    'CH': 'tS', 'JH': 'dZ',
    # fricatives
    'F': 'f', 'V': 'v', 'TH': 'T', 'DH': 'D', 'S': 's', 'Z': 'z',
    'SH': 'S', 'ZH': 'Z', 'HH': 'h',
    # nasals
    'M': 'm', 'N': 'n', 'NG': 'J',
    # liquids and glides
    'L': 'l', 'R': 'R', 'W': 'w', 'Y': 'j',
    # monophthong vowels (French-style SAMPA targets)
    'AA': 'a', 'AE': 'a', 'AH': '@', 'AO': 'O', 'EH': 'E', 'EY': 'e',
    'IH': 'i', 'IY': 'i', 'OW': 'o', 'UH': 'u', 'UW': 'u',
    # diphthongs and rhotacised vowels -> key sequences
    'AW': 'a w', 'AY': 'a j', 'OY': 'O j', 'ER': '@ R',
}

# --------------------------------------------------------------------------
# Punctuation -> engine pause/separators
# --------------------------------------------------------------------------

# Sentence-ending punctuation becomes a '|' phrase separator (long
# pause); comma and dash become a plain space (short inter-word pause).
SENTENCE_PUNCTUATION = '.!?;:'
PAUSE_PUNCTUATION = ','


def greedy_sampa_split(token: str) -> list:
    """Split ``token`` into engine keys (longest match first).

    Returns an empty list when the token cannot be fully segmented
    with the engine inventory, which is the test used by
    :func:`is_sampa_token`.
    """
    keys = []
    i = 0
    while i < len(token):
        for key in _KEYS_BY_LENGTH:
            if key and token.startswith(key, i):
                keys.append(key)
                i += len(key)
                break
        else:
            return []
    return keys


def is_sampa_token(token: str) -> bool:
    """True when ``token`` is fully covered by the engine inventory.

    '.' (syllable) and '~' (nasality) separators are tolerated.
    """
    if not token:
        return False
    residual = token.replace('.', '').replace('~', '')
    if not residual and any(c in token for c in '.~'):
        return True
    return len(greedy_sampa_split(residual)) > 0


def arpa_to_sampa(word_arpa: list) -> str:
    """Convert one CMUdict ARPAbet entry (list of symbols) to SAMPA."""
    out = []
    for sym in word_arpa:
        sym = sym.rstrip('012')          # strip stress markers
        out.append(ARPA_TO_SAMPA.get(sym, sym))
    return ' '.join(out)


# --------------------------------------------------------------------------
# Syllabification (connected engine chains)
# --------------------------------------------------------------------------
#
# The synthesis engine builds coarticulation across a *connected*
# segment chain: a space-separated phoneme list would make every
# phoneme its own word (inter-word pause between each).  The engine
# input for one orthographic word is therefore a single connected
# token with '.' between syllabic groups, e.g. ``Di.si.zi.zi.fOR.@s``
# (the '.' is the engine syllable separator, see parsing.py).

def syllabify_keys(keys: list) -> list:
    """Group engine keys into syllabic groups (onset maximization).

    Each group is a list of keys; rules (the simple default used as a
    *hint* — the engine re-checks each '.' with its coarticulation
    test ``parsing._should_split_at_dot``):

    * every vowel key closes a nucleus (and the syllable);
    * a single intervocalic consonant goes to the onset of the next
      syllable (``ba.na.na``);
    * longer intervocalic clusters split coda/onset before the last
      consonant (``big`` + ``dug`` chain -> ``big.dug``);
    * word-final consonants are the coda of the last syllable
      (``fOR``, ``@s``).
    """
    groups = []
    cur = []
    i = 0
    while i < len(keys):
        key = keys[i]
        if key in SAMPA_VOWELS:
            cur.append(key)
            groups.append(cur)
            cur = []
            i += 1
        else:
            j = i
            while j < len(keys) and keys[j] not in SAMPA_VOWELS:
                j += 1
            run = keys[i:j]
            if j == len(keys):
                # word-final consonants -> coda of the last syllable
                if groups:
                    groups[-1].extend(run)
                else:
                    cur.extend(run)
            elif len(run) == 1:
                cur.append(run[0])       # onset of the next nucleus
            else:
                # cluster: all but last -> coda of the previous
                # syllable, last -> onset of the next
                if groups:
                    groups[-1].extend(run[:-1])
                else:
                    cur.extend(run[:-1])
                cur.append(run[-1])
            i = j
    if cur:
        groups.append(cur)
    return groups or [list(keys)]


def keys_to_connected(keys: list) -> str:
    """Engine keys -> connected syllabified token ('ba.na.na')."""
    groups = syllabify_keys(keys)
    return '.'.join(''.join(g) for g in groups)


def sampa_to_connected(sampa: str) -> str:
    """Reconnect one space-separated SAMPA word into engine notation.

    ``D i s i z i`` -> ``Di.si.zi.zi``.  Non-segmentable input is
    returned unchanged.
    """
    residual = sampa.replace('.', '').replace(' ', '')
    keys = greedy_sampa_split(residual)
    if not keys and '~' in residual:
        keys = greedy_sampa_split(residual.replace('~', ''))
    if not keys:
        return sampa
    return keys_to_connected(keys)
