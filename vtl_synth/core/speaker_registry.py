# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
speaker_registry.py
===================
Single source of truth for the multi-speaker registry.

The registry lives in ``vtl_synth/data/speakers/`` (created by the
``install_speaker.py`` tool, 2026-09-11)::

    vtl_synth/data/speakers/
        registry.json        # entries: speaker file + constants + f0 + hashes
        ACTIVE_SPEAKER       # marker: short name of the active speaker
        jd3.speaker  jd3_constants.py
        s1.speaker   s1_constants.py
        s2.speaker   s2_constants.py

Design decision (documented per spec §2.1): the active speaker is **not**
written inside ``core/constants.py``.  The installer swaps constants.py as
a whole (bit-exact copy of the registry source file), so the installed
constants always keeps the SHA-256 of its source — the active name is
read from the separate ``ACTIVE_SPEAKER`` marker instead.

Layers driven by the registry:

  * geometry / glottis / f0_default : ``core/constants.py`` (swapped file)
  * orthogonal branch (VS/VO/TRX/TRY/TS3) : the ``.speaker`` file resolved
    by :func:`active_speaker_file` (used by speaker_jd.py and
    build_phrase_tract.py instead of the former hardcoded JD3 path)
  * audio + SVG/video : the ``vocaltractlab_cython`` wheel initializes its
    DLL at import time with ``site-packages/vocaltractlab_cython/
    resources/JD3.speaker``.  The installer swaps that shared resource
    (with backup/restore); the swap takes effect in the **next** process.
    The installed wheel (0.0.13, last cp39 build) exposes neither
    ``load_speaker`` nor ``vtlInitialize``/``vtlClose`` on
    ``VocalTractLabApi``, so no hot reload is possible — see
    :func:`wheel_speaker_name` for how the announcement detects the
    resource content instead.

This module must not import anything from ``vtl_synth`` (it is imported
by ``speaker_jd`` at module load; keep it cycle-free).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Package root (vtl_synth/) — registry folder ships as package data
_PKG_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = _PKG_ROOT / 'data' / 'speakers'
REGISTRY_JSON = REGISTRY_DIR / 'registry.json'
ACTIVE_MARKER = REGISTRY_DIR / 'ACTIVE_SPEAKER'

# Language pack (setup_lang.py, 2026-09-15): the managed LANG SECTION
# replaces the native VOWEL_TARGETS..VOWEL_EFFORT_GAIN region of
# constants.py. The two installers are independent: a speaker swap
# carries the section over, a language switch re-edits it in place.
# Coherence checks therefore compare a CANONICAL form of the constants
# in which that region is neutralized on both sides.
LANG_SECTION_BEGIN = '# === LANG SECTION — BEGIN'
LANG_SECTION_END = '# === LANG SECTION — END'
_LANG_SECTION_RE = re.compile(
    re.escape(LANG_SECTION_BEGIN) + r'.*?' + re.escape(LANG_SECTION_END) +
    r'[^\r\n]*\n?', re.S)
_NATIVE_VOWEL_RE = re.compile(
    r'(?ms)^VOWEL_TARGETS:.*?^VOWEL_EFFORT_GAIN:.*?^\}\n?')

# Legacy fallback when the registry is missing (shipped original)
LEGACY_SPEAKER_FILE = _PKG_ROOT / 'data' / 'vtl_binaries' / 'JD3.speaker'

DEFAULT_NAME = 'jd3'


# ==========================================================================
# Hashing
# ==========================================================================

def sha256_of(path) -> str:
    """SHA-256 hex digest of a file (empty string when unreadable)."""
    p = Path(path)
    if not p.is_file():
        return ''
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def hash12(path) -> str:
    """First 12 hex chars of the SHA-256 of a file ('?' when absent)."""
    h = sha256_of(path)
    return h[:12] if h else '?'


def canonical_constants_text(text: str) -> str:
    """Neutralize the vowel/language region of a constants source.

    Two managed forms are neutralized so a constants.py whose only
    difference is the installed language hashes equal to its speaker
    source file:

      - the managed LANG SECTION (marker-only since v1.2.0 — with or
        without embedded vowel targets for pre-v1.2.0 files), AND
      - the native VOWEL_TARGETS..VOWEL_EFFORT_GAIN block, which stays
        in place since v1.2.0 (the language pack no longer overwrites
        it — D24) and therefore also differs between an installed file
        (section present) and its section-less source.
    """
    text = _LANG_SECTION_RE.sub('', text, count=1)
    return _NATIVE_VOWEL_RE.sub('', text, count=1)


def canonical_hash12(path) -> str:
    """hash12 of the canonical (vowel-region-neutralized) constants."""
    p = Path(path)
    if not p.is_file():
        return '?'
    text = p.read_text(encoding='utf-8', errors='replace')
    canonical = canonical_constants_text(text)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]


def active_lang() -> Optional[str]:
    """Language of the installed LANG SECTION (None when absent)."""
    src = _PKG_ROOT / 'core' / 'constants.py'
    if not src.is_file():
        return None
    m = re.search(r"^ACTIVE_LANG:\s*str\s*=\s*'([a-z]+)'",
                  src.read_text(encoding='utf-8', errors='replace'), re.M)
    return m.group(1) if m else None


# ==========================================================================
# Registry access
# ==========================================================================

def registry_available() -> bool:
    """True when registry.json and the speaker files are present."""
    return REGISTRY_JSON.is_file()


def load_registry() -> Dict[str, dict]:
    """Loads registry.json; entries only (the '_meta' key is dropped)."""
    if not registry_available():
        return {}
    data = json.loads(REGISTRY_JSON.read_text(encoding='utf-8'))
    return {k: v for k, v in data.items() if not k.startswith('_')}


def load_meta() -> dict:
    """Loads the '_meta' section of registry.json (may be empty)."""
    if not registry_available():
        return {}
    data = json.loads(REGISTRY_JSON.read_text(encoding='utf-8'))
    return data.get('_meta', {})


def list_speakers() -> List[str]:
    """Sorted short names of the registered speakers (['jd3', 's1', ...])."""
    return sorted(load_registry().keys())


def get_entry(name: str) -> dict:
    """Registry entry for ``name``.

    Raises
    ------
    KeyError
        With an explicit message when the name is unknown.
    """
    reg = load_registry()
    if name not in reg:
        raise KeyError(
            f"unknown speaker '{name}' — registered: {sorted(reg)}")
    return reg[name]


def speaker_file_path(name: str) -> Path:
    """Absolute path of a registered .speaker file."""
    return REGISTRY_DIR / get_entry(name)['speaker']


def constants_source_path(name: str) -> Path:
    """Absolute path of a registered constants source file."""
    return REGISTRY_DIR / get_entry(name)['constants']


# ==========================================================================
# Active speaker (marker file)
# ==========================================================================

def active_name() -> str:
    """Short name of the active speaker (marker ACTIVE_SPEAKER).

    Falls back to 'jd3' when the marker or the registry is missing
    (degraded mode: the legacy vtl_binaries/JD3.speaker is then used).
    """
    if not registry_available():
        return DEFAULT_NAME
    name = ''
    if ACTIVE_MARKER.is_file():
        name = ACTIVE_MARKER.read_text(encoding='ascii').strip()
    reg = load_registry()
    if name not in reg:
        return DEFAULT_NAME
    return name


def set_active(name: str) -> None:
    """Writes the ACTIVE_SPEAKER marker (name must be registered)."""
    get_entry(name)  # validates
    ACTIVE_MARKER.write_text(name, encoding='ascii')


def active_speaker_file() -> str:
    """Path of the .speaker file the orthogonal branch must read.

    Registry-driven replacement of the former hardcoded
    ``data/vtl_binaries/JD3.speaker`` default.  Resolved at **each call**
    (not at import) so speaker switches apply without re-importing.
    Falls back to the legacy shipped JD3.speaker when the registry is
    unavailable.
    """
    if registry_available():
        try:
            return str(speaker_file_path(active_name()))
        except KeyError:
            pass
    return str(LEGACY_SPEAKER_FILE)


def active_constants_hash() -> str:
    """Canonical SHA-256 (12 chars) of the *expected* constants source.

    Canonical = with the vowel/language region neutralized, so the
    installed file compares equal even when a LANG SECTION (language
    pack) has been injected over the speaker's native vowel block.
    """
    if not registry_available():
        return '?'
    return canonical_hash12(constants_source_path(active_name()))


def installed_constants_hash() -> str:
    """Canonical SHA-256 (12 chars) of the installed core/constants.py."""
    return canonical_hash12(_PKG_ROOT / 'core' / 'constants.py')


def constants_coherent() -> bool:
    """True when the installed constants matches the active registry entry.

    Compares canonical forms: a managed LANG SECTION (language pack)
    does not count as an incoherence — the two installers are
    independent by design.
    """
    if not registry_available():
        return True
    return installed_constants_hash() == active_constants_hash()


# ==========================================================================
# Wheel (audio + SVG/video layer)
# ==========================================================================

def wheel_resource_path() -> Optional[Path]:
    """Path of the shared .speaker resource embedded in the wheel.

    The wheel initializes its DLL at import time with this file, whatever
    repository executes: it is shared by every installation using the
    same ``vocaltractlab_cython`` package.
    """
    try:
        import vocaltractlab_cython  # noqa: WPS433 (deliberate, read-only)
    except ImportError:
        return None
    p = Path(vocaltractlab_cython.__file__).parent / 'resources' / 'JD3.speaker'
    return p if p.is_file() else None


def wheel_speaker_name() -> Optional[str]:
    """Which registered speaker the wheel resource file contains.

    Detected by hashing the resource file and matching it against the
    registry speaker hashes, plus the pristine wheel resource hash stored
    in registry.json ``_meta.wheel_default_sha256`` (mapped to 'jd3';
    that original differs from jd3.speaker only by whitespace but byte
    hashes differ).

    Returns None when the wheel/resource is unavailable, and
    'unknown:<hash12>' when the content matches no registered speaker.

    Limitation: this inspects the file on disk, i.e. what the **next**
    process will load.  A process started *before* a swap keeps the
    previously loaded speaker in memory (no vtlInitialize/vtlClose in
    wheel 0.0.13) — the announcement says so when layers disagree.
    """
    p = wheel_resource_path()
    if p is None:
        return None
    h = sha256_of(p)
    if not h:
        return None
    for name, entry in load_registry().items():
        if entry.get('speaker_sha256') == h:
            return name
    meta = load_meta()
    if meta.get('wheel_default_sha256') == h:
        return 'jd3'
    return f'unknown:{h[:12]}'


# ==========================================================================
# Announcement (spec §2.3)
# ==========================================================================

def describe(f0_used: Optional[float] = None) -> str:
    """Builds the active-speaker announcement (no printing).

    Two lines (plus explicit warnings when layers disagree)::

        Speaker actif : s1 (DVTD sujet 1 male)  constants=f100ab03b579  f0_default=114.908 Hz
                        geometry: s1  ortho: s1  audio wheel: s1  video: s1

    ``f0_used`` (Hz) is mentioned on a third line when it differs from
    the speaker's f0_default (i.e. it was forced via --f0 / Pipeline
    argument).
    """
    try:
        name = active_name()
        entry = get_entry(name)
        desc = entry.get('description', '')
        f0_def = entry.get('f0_default')
    except KeyError:
        name, desc, f0_def = DEFAULT_NAME, 'registre indisponible', None

    wheel = wheel_speaker_name()
    wheel_txt = wheel if wheel is not None else 'indisponible'
    video_txt = wheel if wheel is not None else 'indisponible'

    lines = [
        f"Speaker actif : {name} ({desc})  "
        f"constants={installed_constants_hash()}  "
        f"f0_default={f0_def} Hz",
        f"{'':16s}geometry: {name}  ortho: {name}  "
        f"audio wheel: {wheel_txt}  video: {video_txt}",
    ]

    if wheel is not None and wheel != name:
        lines.append(
            f"{'':16s}!! INCOHERENCE audio : la ressource wheel contient "
            f"'{wheel}' alors que le speaker actif est '{name}'. "
            f"(install incomplet ? ou process lance avant l'install : "
            f"la DLL charge son .speaker a l'import, relancer le programme)")
    if not constants_coherent():
        lines.append(
            f"{'':16s}!! INCOHERENCE constants : le constants.py installe "
            f"({installed_constants_hash()}) != source du speaker actif "
            f"({active_constants_hash()}) — relancer install_speaker.py")

    if f0_used is not None and f0_def is not None \
            and abs(float(f0_used) - float(f0_def)) > 1e-9:
        lines.append(
            f"{'':16s}f0 force : {f0_used:.3f} Hz "
            f"(f0_default du speaker : {f0_def} Hz)")

    return '\n'.join(lines)


def announce(f0_used: Optional[float] = None) -> str:
    """Prints and returns the active-speaker announcement (§2.3)."""
    text = describe(f0_used=f0_used)
    print(text)
    return text
