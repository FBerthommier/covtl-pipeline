# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
sampa_guard.py
==============
Engine-level input guard for phonetic (SAMPA/IPA) strings.

Implements the change recommended by CORRECTIONS v2.1 §2: the engine
parsers (``continuous.parse_ipa_with_markers``, ``parsing._tokenize_word``,
``syltraj.tokenize_phrase``) used to drop unknown symbols *silently*, so a
typo such as ``klincan`` (lowercase ``c`` is not an engine key) synthesized
``klinan`` without any diagnostic. This module breaks that silence at the
public engine boundaries without altering any synthesis output.

Policies
--------
``'warn'`` (default)
    Emit an :class:`UnknownSegmentWarning` listing every dropped symbol
    and its position in the normalized input. The synthesis then proceeds
    exactly as before (bit-identical tract/wav).
``'error'``
    Raise :class:`SampaGuardError` (a ``ValueError``) before synthesis,
    listing the dropped symbols.
``'off'``
    No diagnostic at all (pre-guard behaviour, for benchmarks).

Policy resolution order (``resolve_policy``):
1. the explicit ``sampa_guard=`` argument of the public API
   (``Pipeline.run``, ``build_phrase_tract``, ``parse_to_segments``,
   ``parse_input``, ``build_phrase_pval``);
2. the environment variable ``VTL_SAMPA_GUARD``
   (values: ``warn`` | ``error`` | ``off``; any other value falls back
   to ``warn`` with a notice);
3. the default ``warn``.

CLI: ``vtl-synth run --sampa-guard error ...``.

Coverage and known limitations
------------------------------
- ``unknown_symbols()`` mirrors the tokenization walk of
  ``continuous.parse_ipa_with_markers`` (diphthongs first, then the
  inventory, longest match first) on the *normalized* string, so it
  reports exactly what the continuous reference parser drops.
- The syltraj regex inventory is slightly smaller (the selector keys
  ``g_vel`` / ``z_front`` / ``g_pal`` are not text-reachable there), so
  exotic inputs built from selector keys can drop a small superset; the
  reference walk remains the contract.
- Tolerated markers (never reported): space, ``.`` ``-`` (syllable),
  ``|`` (phrase anchor), ``~`` (nasality, honoured by the syl engine),
  ``,`` (deliberately stripped by ``parse_ipa_with_markers``), ``%``
  (breath pause of the syl engine). Nasal ``~`` and ``%`` are honoured
  by the production engine (``engine='syl'``) even though the legacy
  continuous path ignores them.

This module has no numpy dependency so lightweight tooling and unit
tests can import it freely.
"""

from __future__ import annotations

import os
import warnings
from typing import List, Optional, Tuple

from vtl_synth.core.constants import ALL_PHONEME_KEYS

__all__ = [
    'SampaGuardError',
    'UnknownSegmentWarning',
    'DEFAULT_POLICY',
    'ENV_VAR',
    'POLICIES',
    'resolve_policy',
    'unknown_symbols',
    'guard_input',
]

#: Valid guard policies.
POLICIES: Tuple[str, ...] = ('warn', 'error', 'off')

#: Policy applied when neither an argument nor the environment overrides.
DEFAULT_POLICY: str = 'warn'

#: Environment variable consulted by ``resolve_policy``.
ENV_VAR: str = 'VTL_SAMPA_GUARD'

#: Markers handled (not dropped) by the engine — never reported.
_TOLERATED: frozenset = frozenset(' .-|~,%')

# Longest-first ordering of the engine inventory (module-level cache;
# constants.py has no dependency on the rest of core, so importing it
# here cannot create a cycle).
_KEYS_BY_LENGTH: List[str] = sorted(
    (k for k in ALL_PHONEME_KEYS if k), key=len, reverse=True)

# Diphthong keys come from continuous.py, which imports this module:
# the import is therefore deferred to first use (see _diphthong_keys()).
_DIPHTHONG_KEYS: Optional[List[str]] = None


class SampaGuardError(ValueError):
    """Raised in ``'error'`` policy when the input contains symbols
    that the engine parsers would silently drop."""


class UnknownSegmentWarning(UserWarning):
    """Emitted in ``'warn'`` policy (default) when the input contains
    symbols that the engine parsers will silently drop."""


def _diphthong_keys() -> List[str]:
    """Diphthong keys, longest first (lazy import: continuous.py
    imports this module at load time)."""
    global _DIPHTHONG_KEYS
    if _DIPHTHONG_KEYS is None:
        from vtl_synth.core.continuous import DIPHTHONG_DECOMPOSITIONS
        _DIPHTHONG_KEYS = sorted(
            (k for k in DIPHTHONG_DECOMPOSITIONS if k),
            key=len, reverse=True)
    return _DIPHTHONG_KEYS


def resolve_policy(explicit: Optional[str] = None) -> str:
    """Resolve the active guard policy.

    Precedence: *explicit* argument, then ``VTL_SAMPA_GUARD``, then
    ``DEFAULT_POLICY`` ('warn'). An invalid environment value falls back
    to the default with a notice (never crashes a synthesis run).
    """
    if explicit is not None:
        if explicit in POLICIES:
            return explicit
        warnings.warn(
            f'invalid sampa_guard policy {explicit!r}; '
            f"expected one of {', '.join(POLICIES)}; using 'warn'",
            UserWarning, stacklevel=3)
        return DEFAULT_POLICY
    env = os.environ.get(ENV_VAR)
    if env is not None:
        if env in POLICIES:
            return env
        warnings.warn(
            f'{ENV_VAR}={env!r} is invalid; '
            f"expected one of {', '.join(POLICIES)}; using 'warn'",
            UserWarning, stacklevel=3)
    return DEFAULT_POLICY


def unknown_symbols(text: str) -> List[Tuple[str, int]]:
    """Symbols of *text* that the engine parsers will silently drop.

    Walks *text* exactly like the reference tokenizer
    (``continuous.parse_ipa_with_markers``): tolerated markers first,
    then diphthong keys, then the phoneme inventory — longest match
    first at every position. Returns ``[(symbol, position), ...]``
    (positions in *text* as given, i.e. post-normalization when called
    from the engine boundaries).
    """
    unknowns: List[Tuple[str, int]] = []
    diphthongs = _diphthong_keys()
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _TOLERATED:
            i += 1
            continue
        for key in diphthongs:
            if text.startswith(key, i):
                i += len(key)
                break
        else:
            for key in _KEYS_BY_LENGTH:
                if text.startswith(key, i):
                    i += len(key)
                    break
            else:
                unknowns.append((ch, i))
                i += 1
    return unknowns


def _format_unknowns(unknowns: List[Tuple[str, int]]) -> str:
    """Human-readable grouping: 'c' at position 4; 'q' at positions 2, 9."""
    positions: dict = {}
    for ch, pos in unknowns:
        positions.setdefault(ch, []).append(pos)
    parts = []
    for ch in sorted(positions):
        pos_list = sorted(positions[ch])
        label = 'position' if len(pos_list) == 1 else 'positions'
        parts.append(f'{ch!r} at {label} {", ".join(map(str, pos_list))}')
    return '; '.join(parts)


def guard_input(
    text: str,
    *,
    source: str,
    policy: Optional[str] = None,
    stacklevel: int = 3,
) -> List[Tuple[str, int]]:
    """Apply the SAMPA guard to *text* at an engine boundary.

    Parameters
    ----------
    text : str
        Normalized phonetic input (the string the parsers will consume).
    source : str
        Name of the calling boundary, for the diagnostic message
        (e.g. ``'build_phrase_tract'``).
    policy : str, optional
        ``'warn'`` | ``'error'`` | ``'off'``; ``None`` resolves through
        the environment (see :func:`resolve_policy`). Internal calls
        from an already-guarded boundary pass ``'off'`` explicitly.
    stacklevel : int
        Warning stacklevel (points at the user's call site).

    Returns
    -------
    list[tuple[str, int]]
        The dropped ``(symbol, position)`` pairs (empty when clean or
        when the policy is ``'off'``).
    """
    resolved = resolve_policy(policy)
    if resolved == 'off':
        return []
    unknowns = unknown_symbols(text)
    if not unknowns:
        return []
    detail = (_format_unknowns(unknowns)
              + f" in normalized input {text!r}")
    hint = ("These symbols are not in the engine phoneme inventory "
            "(constants.ALL_PHONEME_KEYS); the parsers will drop them "
            "and the synthesis will proceed WITHOUT them. To abort "
            "instead: sampa_guard='error', --sampa-guard error, or "
            f"{ENV_VAR}=error.")
    if resolved == 'error':
        raise SampaGuardError(
            f'[{source}] {len(unknowns)} unknown symbol(s) in the '
            f'phonetic input: {detail}. {hint}')
    warnings.warn(
        f'[{source}] {len(unknowns)} unknown symbol(s) will be silently '
        f'dropped: {detail}. {hint}',
        UnknownSegmentWarning, stacklevel=stacklevel)
    return unknowns
