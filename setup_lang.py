#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
setup_lang.py
=============
Language installation and switching for the covtl-pipeline.

This is the language counterpart of the speaker installation (which
drops a ``.speaker`` file into ``vtl_synth/data/vtl_binaries/``): it
installs the language-pack modules into the pipeline and switches the
active language by rewriting a managed section of
``vtl_synth/core/constants.py`` (vowel targets + effort gains). The
JD3 speaker is kept untouched.

Every command prints the currently active language.

Language pack layout (v1.0.7)
-----------------------------
The default source is the **installable language package** at the
repository root ::

    lang_pack/
    ├── profiles/        g2p gateway + language profiles (→ utils/)
    ├── lexicons/        Wikipron TSV + license notices  (→ data/)
    ├── lang_blocks/     LANG SECTION fragments per language (blocks.py)
    ├── integration/     patched pipeline.py / utils__init__.py
    ├── install_lang.bat / install_lang.sh   one-command entry points
    ├── manual/          LaTeX user manual (English US)
    └── README.md / LICENSE.md / ARCHITECTURE.md

``lang_pack/lang_blocks/blocks.py`` is the single source of truth for
the per-language vowel-target blocks (loaded here via importlib; the
old inline ``LANG_BLOCKS`` dict is gone). If ``lang_pack/`` is absent,
setup falls back to the legacy layout of the covtl-language-pack zip
(``../modules``, flat five-module set, fr/en blocks only) — users of
the existing zip pack are not broken.

Vowel targets are NOT assumed to transfer between languages: the polar
targets had to be mechanically adjusted to VTL/JD3 for the original
calibration, so each language gets its own derivation. Two paths:

* built-in blocks ``fr`` (LPC-calibrated v1.0.6, validated in situ) and
  ``en`` (original pipeline calibration, covered by the regression
  baselines); the v1.0.7 languages (es, de, it, pt) carry in-situ
  calibrated targets with the measured F1/F2 written as comments;
* ``calibrate <lang>`` (or ``install --calibrate``): re-derives rho for
  every vowel of the language via the pack's ``find_best_rho`` (VTL
  transfer function + LPC, JD3), for any language of
  ``language_vowel_sets.VOWEL_SETS`` (en, fr, es, de, it, pt). The
  measured F1/F2 achieved at the calibrated rho are written as comments
  next to each target — the mechanical proof travels with the constants.
  ``--in-situ`` additionally refines each rho through REAL synthesis +
  LPC measurement (the same criterion as ``verify``), which corrects
  the static derivation when the gestural dynamics displace F1/F2.

Usage
-----
::

    python setup_lang.py install [--lang fr] [--pack DIR] [--calibrate]
    python setup_lang.py setlang fr|en
    python setup_lang.py calibrate <lang> [--fine] [--in-situ]
    python setup_lang.py verify
    python setup_lang.py show
    python setup_lang.py list
    python setup_lang.py restore [--purge]

Reversibility
-------------
* ``install``/``setlang`` save the pristine ``constants.py`` as
  ``constants.py.bak`` on first intervention; patched ``pipeline.py``
  and ``utils/__init__.py`` are backed up as ``.bak`` as well.
* ``restore`` puts the original files back. ``--purge`` additionally
  removes the installed language modules (module manifest) and the
  lexicon files the install itself brought in (data manifest —
  repository-tracked or user-modified data files are never deleted).
* Switching languages is itself reversible: each ``setlang`` rewrites
  the managed LANG SECTION from a per-language block, so ``setlang en``
  undoes ``setlang fr`` and conversely.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

PIPELINE_ROOT = Path(__file__).resolve().parent
UTILS_DIR = PIPELINE_ROOT / 'vtl_synth' / 'utils'
CORE_DIR = PIPELINE_ROOT / 'vtl_synth' / 'core'
DATA_DIR = PIPELINE_ROOT / 'vtl_synth' / 'data'
CONSTANTS = CORE_DIR / 'constants.py'

# Language-pack locations, in resolution order:
#   1. <repo>/lang_pack   — installable language package (v1.0.7)
#   2. <repo>/../modules  — legacy layout of the covtl-language-pack zip
LANG_PACK_DIR = PIPELINE_ROOT / 'lang_pack'
LEGACY_PACK_DIR = PIPELINE_ROOT.parent / 'modules'

# Modules copied from the language pack into vtl_synth/utils/ —
# full v1.0.7 set (lang_pack/profiles/ layout) + expressive prosody
# (v1.0.8: chunking.py, prosody_f0.py).
LANG_MODULES = (
    'setlang.py',
    'g2p.py',
    'g2p_fr.py',
    'g2p_fr_legacy.py',
    'g2p_es.py',
    'g2p_de.py',
    'g2p_it.py',
    'g2p_pt.py',
    'lexicon_loader.py',
    'language_vowel_sets.py',
    'calibrate_vowels.py',
    'chunking.py',
    'prosody_f0.py',
)
# Legacy flat layout (../modules): the v1.0.0 five-module set.
LANG_MODULES_LEGACY = (
    'setlang.py',
    'g2p.py',
    'g2p_fr.py',
    'language_vowel_sets.py',
    'calibrate_vowels.py',
)
# Pack files that replace pipeline files (backed up as .bak)
PATCHED_FILES = {
    'pipeline.py': CORE_DIR / 'pipeline.py',
    'utils__init__.py': UTILS_DIR / '__init__.py',
}

LANG_SECTION_BEGIN = '# === LANG SECTION — BEGIN'
LANG_SECTION_END = '# === LANG SECTION — END'
ACTIVE_LANG_RE = re.compile(r"^ACTIVE_LANG:\s*str\s*=\s*'([a-z]+)'", re.M)
_MANIFEST = '.lang_pack_manifest'
_DATA_MANIFEST = '.lang_pack_data_manifest'

# Lexicon files shipped/expected by the pack (lang_pack/lexicons/).
_LEXICON_FILES = (
    ('fr', 'fr_lexicon.tsv'),
    ('es', 'es_lexicon.tsv'),
    ('de', 'de_lexicon.tsv'),
    ('it', 'it_lexicon.tsv'),
    ('pt', 'pt_lexicon.tsv'),
)


# ===========================================================================
# Per-language LANG SECTION rendering
# ===========================================================================
# Each block renders the managed section for one language: ACTIVE_LANG
# marker + language-calibrated VOWEL_TARGETS + VOWEL_EFFORT_GAIN. The
# six language blocks live in lang_pack/lang_blocks/blocks.py (single
# source of truth, loaded below); only the fr/en blocks are kept here
# as a fallback for the legacy zip-pack layout, which has no blocks.py.

def _lang_block(lang: str, header: str, vowels: str, effort: str) -> str:
    return f"""{LANG_SECTION_BEGIN} (managed by setup_lang.py — do not edit by hand)
{header}
ACTIVE_LANG: str = '{lang}'

VOWEL_TARGETS: Dict[str, Tuple[float, float]] = {{
{vowels}
}}

# Effort gain per vowel (relative intensity): compensates the intrinsic
# intensity gap of high vowels vs /a/ (clamped downstream to 1.5).
VOWEL_EFFORT_GAIN: Dict[str, float] = {{
{effort}
}}
{LANG_SECTION_END} =============================================================
"""


# fr/en fallback blocks — MUST stay identical to the corresponding
# entries of lang_pack/lang_blocks/blocks.py (guarded by
# tests/test_multilang.py::test_fallback_blocks_match_pack).
_FALLBACK_BLOCKS = {
    'fr': _lang_block(
        'fr',
        """# Français — cibles vocaliques calibrées par LPC (v1.0.6, 2026-09-13).
# Angles θ de timit-to-maeda (positions cardinales stables), ρ calibrés
# par mesure LPC des formants sur le moteur COVTL, JD3 (homme français).
# F2 cibles (homme français moyen) :
#   /i/ 2200 /e/ 2000 /E/ 1700 /a/ 1100 /O/ 870 /o/ 800 /u/ 870
#   /y/ 1800 /2/ 1500 /@/ 1500""",
        """    'i':  (0.340, 5 * np.pi / 3),         # 300° — F2=2200 (parfait)
    'e':  (0.850, 3 * np.pi / 2),         # 270° — F2=2015 (parfait)
    'E':  (1.000, 4 * np.pi / 3),         # 240° — F2=1598 (correct)
    'a':  (0.520, np.pi),                 # 180° — F2=1839 (un peu haut)
    'O':  (0.950, 2 * np.pi / 3),         # 120° — F2=1884 (haut mais acceptable)
    'o':  (0.300, np.pi / 2),             #  90° — F2=2085 (haut)
    'u':  (0.400, np.pi / 3),             #  60° — F2 mesuré ~870 (LPC instable sur /u/)
    'y':  (0.650, 5.5 * np.pi / 3),       # 330° — F2=1817 (parfait)
    '2':  (0.900, 5.5 * np.pi / 3),       # 330° — F2=1508 (parfait)
    # Voyelles nasales conservées de covtl-pipeline (pas dans timit-to-maeda)
    '6':  (0.894, 3.053),                 # 174.9° (œ) — nasal mid-front
    '9':  (0.722, 3.105),                 # 177.9° (œ̃) — nasal mid-front
    # '@' (schwa) : centre du triangle a-i-u.
    # ρ̄ = (0.520 + 0.340 + 0.400)/3 = 0.420, θ = π.
    '@':  (0.420, np.pi),                 # centre du triangle a-i-u (ə)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,   # /e/ came out -7.5 dB vs /a/ (phrase 2 of input.txt)
    'y': 1.3,   # high/mid front vowels: same order of correction
    '2': 1.2,""",
    ),
    'en': _lang_block(
        'en',
        """# English — strict Maeda anchors (original covtl-pipeline calibration).
# /a/, /i/, /u/ close to the Maeda anchors (ρ≤1); the other vowels are
# adjusted by least squares. English notation: no nasal vowels, /r/ is
# alveolar (resolved by the notation alias layer, not by the targets).""",
        """    'a': (1.000, np.pi),           # 180° — STRICT
    'i': (0.600, 5 * np.pi / 3),   # 300° — compensation for the raised c1(TCY)
    'u': (0.550, np.pi / 3),       #  60° — compensation for the raised c1(TCY)
    'e': (0.988, 4.581),           # 262.5°
    'E': (0.594, 3.563),           # 204.1°
    'o': (1.000, 1.827),           # 104.7° — clamped
    'O': (1.000, 2.616),           # 149.9° — clamped
    '6': (0.894, 3.053),           # 174.9° (œ)
    '9': (0.722, 3.105),           # 177.9° (œ̃)
    # '@' (schwa): centre of the a-i-u triangle, ρ̄ = 0.7167, θ = π.
    '@': (0.7167, np.pi),          # centre du triangle a-i-u (ə)
    'y': (0.519, 4.548),           # 260.6°
    '2': (0.396, 3.946),           # 226.1° (ø)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,
    'y': 1.3,
    '2': 1.2,""",
    ),
}


# ===========================================================================
# Helpers
# ===========================================================================

def _info(msg: str) -> None:
    print(f"[setup_lang] {msg}")


def _die(msg: str) -> None:
    print(f"[setup_lang] ERREUR : {msg}", file=sys.stderr)
    sys.exit(1)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ===========================================================================
# Language-pack resolution (lang_pack/ by default, ../modules fallback)
# ===========================================================================

def _pack_layout(pack_dir: Path) -> str | None:
    """Detect the layout of ``pack_dir`` ('lang_pack' | 'legacy' | None)."""
    p = Path(pack_dir)
    if (p / 'profiles' / 'setlang.py').exists() or \
            (p / 'lang_blocks' / 'blocks.py').exists():
        return 'lang_pack'
    if (p / 'setlang.py').exists():
        return 'legacy'
    return None


def _resolve_pack(explicit: str | None = None):
    """Resolve the language-pack directory.

    Returns (pack_dir, layout): the explicit ``--pack`` directory or
    $COVTL_LANG_PACK if given, else ``lang_pack/`` at the repo root,
    else the legacy ``../modules`` layout. (None, None) when nothing
    plausible exists.
    """
    cand = explicit or os.environ.get('COVTL_LANG_PACK')
    if cand:
        p = Path(cand)
        return p, _pack_layout(p)
    if LANG_PACK_DIR.is_dir():
        return LANG_PACK_DIR, _pack_layout(LANG_PACK_DIR)
    if LEGACY_PACK_DIR.is_dir():
        return LEGACY_PACK_DIR, _pack_layout(LEGACY_PACK_DIR)
    return None, None


def _load_pack_blocks(pack_dir: Path) -> dict:
    """Load LANG_BLOCKS from ``<pack>/lang_blocks/blocks.py`` (importlib).

    Returns {} when the pack has no blocks.py (legacy layout). The
    section markers of the loaded module MUST agree with this module's
    (the regex replacement depends on it).
    """
    path = Path(pack_dir) / 'lang_blocks' / 'blocks.py'
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location('covtl_lang_blocks', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if (mod.LANG_SECTION_BEGIN, mod.LANG_SECTION_END) != \
            (LANG_SECTION_BEGIN, LANG_SECTION_END):
        _die(f"marqueurs de section incohérents dans {path}")
    blocks = dict(mod.LANG_BLOCKS)
    for lang, block in blocks.items():
        if LANG_SECTION_BEGIN not in block or LANG_SECTION_END not in block:
            _die(f"bloc {lang!r} sans marqueurs de section dans {path}")
    return blocks


def _load_lang_blocks():
    """Module-level resolution: LANG_BLOCKS from the default pack."""
    pack_dir, layout = _resolve_pack()
    if pack_dir is not None and layout == 'lang_pack':
        blocks = _load_pack_blocks(pack_dir)
        if blocks:
            return blocks
    return dict(_FALLBACK_BLOCKS)


LANG_BLOCKS: dict = _load_lang_blocks()

# Default pack directory for the CLI (resolved at import so that every
# command sees the same LANG_BLOCKS / pack as `install` would).
_pack_dir, _pack_layout_resolved = _resolve_pack()
DEFAULT_PACK_DIR = _pack_dir if _pack_dir is not None else LANG_PACK_DIR


# ===========================================================================
# Helpers (display, backup, section rewriting)
# ===========================================================================

def _display(lang: str) -> str:
    names = {'fr': 'Français', 'en': 'English', 'es': 'Español',
             'de': 'Deutsch', 'it': 'Italiano', 'pt': 'Português'}
    return names.get(lang, lang)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _module_source(pack_dir: Path, layout: str, name: str) -> Path:
    sub = 'profiles' if layout == 'lang_pack' else '.'
    return Path(pack_dir) / sub / name


def _patched_source(pack_dir: Path, layout: str, name: str) -> Path:
    sub = 'integration' if layout == 'lang_pack' else '.'
    return Path(pack_dir) / sub / name


def _lang_module_names(layout: str) -> tuple:
    return LANG_MODULES if layout == 'lang_pack' else LANG_MODULES_LEGACY


def report_current() -> None:
    """Print the currently active language (called by every command)."""
    lang = get_current_lang()
    speaker = _active_speaker_name()
    if lang is None:
        _info("Langue en cours : (aucune — language pack non installé)")
    else:
        warn = ("  !! cibles calibrées JD3 — HYPOTHÈSE"
                if speaker not in (None, 'jd3') else "")
        _info(f"Langue en cours : {lang} ({_display(lang)})  "
              f"[speaker: {speaker or 'JD3'}]{warn}")


def get_current_lang() -> str | None:
    """Return the ACTIVE_LANG recorded in the managed LANG SECTION."""
    src = CONSTANTS.read_text(encoding='utf-8')
    m = ACTIVE_LANG_RE.search(src)
    return m.group(1) if m else None


def _active_speaker_name() -> str | None:
    """Active speaker of the multi-speakers registry, if any (None when
    the repository has no speaker system — e.g. covtl-languages)."""
    marker = PIPELINE_ROOT / 'vtl_synth' / 'data' / 'speakers' / 'ACTIVE_SPEAKER'
    if not marker.exists():
        return None
    return marker.read_text(encoding='utf-8').strip() or None


def _ensure_jd3() -> None:
    """Garde-fou multi-speakers : les cibles vocaliques du pack sont
    calibrées in situ sur JD3 — toute activation/measure de langue
    réinstalle d'abord le speaker jd3 (constants + marqueur + wheel).

    Ne fait rien dans les dépôts sans registre speaker, ou quand jd3
    est déjà actif. Après réinstallation, constants.py est remplacé en
    entier : la LANG SECTION doit être ré-amorcée (cf.
    _replace_lang_section, chemin de première intervention).
    """
    speaker = _active_speaker_name()
    if speaker is None or speaker == 'jd3':
        return
    _info(f"garde-fou speaker : '{speaker}' est actif — les cibles du pack "
          f"sont calibrées in situ sur JD3 ; réinstallation du speaker jd3…")
    r = subprocess.run(
        [sys.executable, str(PIPELINE_ROOT / 'install_speaker.py'),
         'install', 'jd3'],
        cwd=str(PIPELINE_ROOT), capture_output=True, text=True)
    tail = '\n'.join((r.stdout or '').splitlines()[-6:])
    if r.returncode != 0:
        _die("échec de la réinstallation du speaker jd3 "
             "(install_speaker.py install jd3) :\n" + tail)
    _info(f"  speaker jd3 réinstallé (langue transportée par "
          f"install_speaker : {get_current_lang() or 'native'})")


def _backup(path: Path) -> None:
    """One-time backup: never overwrite an existing .bak (reversibility)."""
    bak = path.with_suffix(path.suffix + '.bak')
    if not bak.exists():
        shutil.copy2(path, bak)
        _info(f"  sauvegarde : {bak.relative_to(PIPELINE_ROOT)}")


def _replace_lang_section(src: str, lang: str, block: str | None = None) -> str:
    """Rewrite the managed LANG SECTION of constants.py for ``lang``."""
    block = block or LANG_BLOCKS[lang]
    if LANG_SECTION_BEGIN in src:
        pattern = re.compile(
            re.escape(LANG_SECTION_BEGIN) + r'.*?' + re.escape(LANG_SECTION_END) +
            r'[^\r\n]*\n', re.S)
        if not pattern.search(src):
            _die("marqueurs LANG SECTION incohérents dans constants.py")
        return pattern.sub(lambda _m: block, src, count=1)
    # First intervention: replace the original static definitions with
    # the generated LANG SECTION, so exactly one definition remains.
    # The BARE region (VOWEL_TARGETS through VOWEL_EFFORT_GAIN) is used
    # — not the commented header box — so the installed file stays
    # canonically identical to its speaker source outside the managed
    # region (speaker_registry.canonical_constants_text compares the
    # same bare region on the source side).
    region = re.compile(
        r'(?ms)^VOWEL_TARGETS:.*?^VOWEL_EFFORT_GAIN:.*?^\}\n')
    if not region.search(src):
        _die("section VOWEL_TARGETS/VOWEL_EFFORT_GAIN introuvable dans constants.py")
    # le bloc se termine deja par \n et la region en consomme un :
    # pas de \n supplementaire (alignement canonique, cf. plus haut)
    return region.sub(lambda _m: block, src, count=1)


# ===========================================================================
# Mechanical calibration (find_best_rho on VTL/JD3)
# ===========================================================================
# The polar targets are engine-dependent (rho compensates the COVTL
# coefficient shifts), so they must be re-derived per language, never
# copied. calibrate_block() runs the pack's find_best_rho for every
# vowel of language_vowel_sets.VOWEL_SETS[lang] and renders a LANG
# SECTION whose comments carry the measured F1/F2 — the demonstration
# of functioning is part of the artifact.

def _fmt_theta(theta: float) -> str:
    if abs(theta - np.pi) < 1e-9:
        return 'np.pi'
    return f'np.radians({np.degrees(theta):.1f})'


def _display_all() -> dict:
    d = {'fr': 'Français', 'en': 'English', 'es': 'Español',
         'de': 'Deutsch', 'it': 'Italiano', 'pt': 'Português'}
    try:
        from vtl_synth.utils.language_vowel_sets import VOWEL_SETS
        for code, entry in VOWEL_SETS.items():
            d.setdefault(code, entry.get('display_name', code))
    except ImportError:
        pass
    return d


def calibrate_targets(lang: str, rho_step: float = 0.02):
    """Derive rho per vowel for ``lang`` via VTL + LPC (find_best_rho).

    Returns (entries, display_name, corners) where entries is a list of
    (key, rho, theta, f1_measured, f2_measured, err_hz, description).
    """
    import datetime
    import numpy as np
    from vtl_synth.core.constants import CO_VTL, COVTL_TO_FULL
    from vtl_synth.utils.calibrate_vowels import find_best_rho
    from vtl_synth.utils.language_vowel_sets import get_vowel_set, get_schwa_key

    vset = get_vowel_set(lang)
    corners = vset['cardinal_corners']
    schwa = get_schwa_key(lang)
    entries = []
    for key, (f1_att, f2_att, theta, desc) in vset['vowels'].items():
        if key == schwa:
            continue                      # derived from the corners below
        rho, f1, f2, err = find_best_rho(
            f1_att, f2_att, theta, CO_VTL, COVTL_TO_FULL,
            rho_min=0.2, rho_max=1.5, rho_step=rho_step)
        entries.append([key, rho, theta, f1, f2, err, desc])
    if schwa:
        # Pipeline convention: schwa = centre of the a-i-u triangle.
        corner_rhos = [e[1] for e in entries if e[0] in corners] or [0.5]
        rho = float(np.mean(corner_rhos))
        entries.append([schwa, rho, np.pi, float('nan'), float('nan'),
                        float('nan'),
                        f"schwa — centre du triangle {'-'.join(corners)} "
                        f"(rhō={rho:.3f})"])
    return entries, vset['display_name'], corners


def render_calibrated_block(lang: str, entries, display_name: str,
                            in_situ: bool = False) -> str:
    """Render the LANG SECTION for derived targets.

    ``in_situ=True`` marque que les F1/F2 des commentaires sont mesurés
    sur l'audio VTL réellement synthétisé (chaîne LPC de ``verify``),
    pas sur la fonction de transfert statique.
    """
    import datetime
    import numpy as np
    date = datetime.date.today().isoformat()
    if in_situ:
        method = ("calibrés MÉCANIQUEMENT (find_best_rho, fonction de\n"
                  "# transfert VTL) PUIS RAFFINÉS IN SITU par synthèse "
                  "réelle +\n# mesure LPC (même critère que verify) le "
                  f"{date}.\n"
                  "# Les F1/F2 en commentaire sont les valeurs MESURÉES "
                  "sur l'audio.")
    else:
        method = ("calibrés MÉCANIQUEMENT sur VTL/JD3 le "
                  f"{date}.\n"
                  "# rho optimal par voyelle via find_best_rho (fonction "
                  "de\n# transfert VTL + LPC) contre les formants de "
                  "référence de la langue\n"
                  "# (language_vowel_sets).")
    vowel_lines = []
    for key, rho, theta, f1, f2, err, desc in entries:
        if np.isnan(f1):
            note = desc
        else:
            note = (f"θ={np.degrees(theta):.0f}° — calibré VTL/JD3 : "
                    f"F1={f1:.0f} F2={f2:.0f} Hz (err {err:.0f} Hz) — {desc}")
        vowel_lines.append(f"    {key!r}: ({rho:.3f}, {_fmt_theta(theta)}),"
                           f"  # {note}")
    keys = {e[0] for e in entries}
    # Compensation des fermées (cf. bloc fr) : i/u/e (et leurs
    # contreparties laxées allemandes I/U) à 1.5, y/Y à 1.3, 2 à 1.2.
    # Hypothèse de départ — à ajuster après écoute + mesure.
    effort_lines = [f"    {k!r}: 1.5," for k in ('i', 'u', 'e', 'I', 'U')
                    if k in keys]
    effort_lines += [f"    {k!r}: 1.3," for k in ('y', 'Y') if k in keys]
    effort_lines += [f"    {k!r}: 1.2," for k in ('2',) if k in keys]
    header = (f"# {display_name} ({lang}) — cibles dérivées MÉCANIQUEMENT "
              f"sur VTL/JD3 le {date}.\n"
              "# rho optimal par voyelle via find_best_rho (fonction de "
              "transfert VTL + LPC)\n"
              "# contre les formants de référence de la langue "
              "(language_vowel_sets).")
    return _lang_block(lang, header, '\n'.join(vowel_lines),
                       '\n'.join(effort_lines))


def write_lang_section(lang: str, block: str) -> str:
    """Backup then rewrite the LANG SECTION of constants.py with ``block``."""
    src = CONSTANTS.read_text(encoding='utf-8')
    _backup(CONSTANTS)
    CONSTANTS.write_text(_replace_lang_section(src, lang, block=block),
                         encoding='utf-8')
    return CONSTANTS.read_text(encoding='utf-8')


def cmd_calibrate(lang: str, fine: bool = False,
                  in_situ: bool = False) -> None:
    """Calibrate ``lang`` on VTL/JD3 and activate it.

    ATTENTION : cette dérivation statique (tract figé au point cible)
    est un POINT DE DÉPART — elle ne se transfère pas toujours in situ
    (la dynamique gestuelle déplace les formants). Toujours valider le
    résultat par ``setup_lang.py verify`` et affiner en conséquence.
    Avec ``--in-situ``, le raffinement est fait automatiquement :
    balayage de ρ par voyelle avec synthèse réelle + mesure LPC
    (cf. ``refine_in_situ``), le critère de ``verify``.
    """
    _ensure_jd3()   # garde-fou : calibrage in situ sur JD3 uniquement
    try:
        entries, display_name, _corners = calibrate_targets(
            lang, rho_step=0.01 if fine else 0.02)
    except ImportError:
        _die("language pack non installé — lancez d'abord : "
             "python setup_lang.py install")
    _info(f"Calibration mécanique de {lang} ({display_name}) sur VTL/JD3…")
    if in_situ:
        _info("Raffinement in situ (synthèse + LPC par voyelle)…")
        entries = refine_in_situ(lang, entries)
    block = render_calibrated_block(lang, entries, display_name,
                                    in_situ=in_situ)
    write_lang_section(lang, block)
    _info(f"Section langue réécrite avec les cibles calibrées : {lang}")
    _info("Rappel : vérifier in situ via  python setup_lang.py verify")
    report_current()


# ===========================================================================
# In-situ LPC measurement (shared by verify and the in-situ refinement)
# ===========================================================================

def _lpc_measure(x: np.ndarray, sr: int) -> list:
    """F1/F2 (and higher formants) of one vowel audio frame, by LPC.

    Same analysis chain as the original ``cmd_verify``: downsample to
    ~11 kHz, pre-emphasis 0.97, 40 ms Hamming window taken after the
    100 ms onset, order-16 LPC, roots of the prediction polynomial.
    """
    from scipy.linalg import solve_toeplitz
    from scipy.signal import lfilter as _lf, resample_poly
    x = x.astype(float)              # AVANT resample (int16 sinon perdu)
    if sr > 12000:
        x = resample_poly(x, 1, round(sr / 11025))
        sr = 11025
    x = x - x.mean()
    x = _lf([1., -0.97], [1.], x)
    w = int(0.040 * sr)
    trimmed = x[int(0.10 * sr):]
    if len(trimmed) >= w:
        x = trimmed
    i0 = max(0, (len(x) - w) // 2)
    frame = x[i0:i0 + w] * np.hamming(min(w, len(x) - i0))
    r = np.correlate(frame, frame, 'full')[len(frame) - 1:]
    coef = solve_toeplitz(r[:16], -r[1:17])
    roots = np.roots(np.r_[1., coef])
    return sorted(
        np.angle(rt) * sr / (2 * np.pi)
        for rt in roots
        if 0 < np.angle(rt) < np.pi and 0.80 < abs(rt) < 1.0
        and 150 < np.angle(rt) * sr / (2 * np.pi) < 4500)


def _measure_vowel(p, key: str, tmpdir: str):
    """Synthesize one vowel (SAMPA direct) and measure F1/F2 by LPC.

    Returns (f1, f2) or (None, None). ``p`` is a Pipeline instance.
    """
    import glob
    import tempfile
    import scipy.io.wavfile as wav
    d = tempfile.mkdtemp(prefix='vfy_')
    p.run(key, d, use_g2p=False, video=False, label=key)
    wavpath = glob.glob(f'{d}/*.wav')[0]
    sr, data = wav.read(wavpath)
    if data.ndim > 1:
        data = data[:, 0]
    freqs = _lpc_measure(data, sr)
    f1 = next((q for q in freqs if 150 <= q <= 1300), None)
    f2 = next((q for q in freqs if f1 and f1 < q <= 3500), None)
    return f1, f2


def refine_in_situ(lang: str, entries, coarse=0.1, fine_radius=0.08,
                   fine_step=0.02, tol=0.30, verbose=True):
    """Re-derive rho PER VOWEL by in-situ synthesis + LPC measurement.

    The static calibration (``calibrate_targets``/find_best_rho, tract
    figé) is only a starting point: the gestural dynamics displace the
    formants. For each vowel this sweeps rho (coarse grid, then a fine
    grid around the best), APPLIES each candidate rho to the live
    VOWEL_TARGETS (in-place mutation, shared dict), synthesizes the
    isolated vowel through the real pipeline (JD3) and keeps the rho
    whose MEASURED F1/F2 pass best against the language reference
    (re-read from language_vowel_sets). The selection criterion is
    ALIGNED WITH ``verify`` : minimize the number of formants outside
    the ±tol relative tolerance, then the max relative error — not the
    absolute Hz error (which over-weights F2 and accepts F1 collapses).
    Returns updated entries with the in-situ measured F1/F2.
    """
    from vtl_synth import Pipeline
    from vtl_synth.core.constants import VOWEL_TARGETS as _live_targets
    from vtl_synth.utils.language_vowel_sets import get_vowel_set
    refs = get_vowel_set(lang)['vowels']
    p = Pipeline(lang=lang)

    def _verdict_score(f1, f2, f1r, f2r):
        e1 = abs(f1 - f1r) / f1r
        e2 = abs(f2 - f2r) / f2r
        return ((e1 > tol) + (e2 > tol), max(e1, e2))

    out = []
    for key, rho, theta, f1s, f2s, errs, desc in entries:
        ref = refs.get(key)
        if not ref:                       # not a reference vowel
            out.append([key, rho, theta, f1s, f2s, errs, desc])
            continue
        f1r, f2r = float(ref[0]), float(ref[1])
        grid = list(np.arange(0.2, 1.45, coarse))
        best = None                       # (score, rho, (f1, f2))
        for round_grid in (grid, None):
            if round_grid is None:        # fine pass around the best
                if best is None:
                    break
                round_grid = np.arange(max(0.15, best[1] - fine_radius),
                                       min(1.5, best[1] + fine_radius),
                                       fine_step)
            for r in round_grid:
                # applique le rho candidat AVANT de synthétiser :
                # mutation en place — tous les modules partagent le dict
                _live_targets[key] = (float(r), theta)
                try:
                    f1, f2 = _measure_vowel(p, key, None)
                except Exception:
                    continue
                if f1 is None or f2 is None:
                    continue
                score = (_verdict_score(f1, f2, f1r, f2r), float(r),
                         (f1, f2))
                if best is None or score[0] < best[0]:
                    best = score
        if best is None:                  # LPC muet : garder le statique
            _live_targets[key] = (rho, theta)
            out.append([key, rho, theta, f1s, f2s, errs,
                        f"{desc} [in situ non mesurable — statique conservé]"])
        else:
            (n_out, max_rel), r, (f1, f2) = best
            _live_targets[key] = (r, theta)
            err = abs(f1 - f1r) + abs(f2 - f2r)
            out.append([key, r, theta, f1, f2, err, desc])
            if verbose:
                _info(f"  /{key}/ ρ {rho:.2f}→{r:.2f} : F1={f1:.0f} "
                      f"(réf {f1r:.0f}) F2={f2:.0f} (réf {f2r:.0f}) "
                      f"— max err rel {max_rel:.0%}")
    return out


def cmd_verify(lang: str | None = None, tol: float = 0.30) -> None:
    """Démonstration de fonctionnement : mesure LPC in situ des voyelles.

    Synthétise chaque voyelle de la langue active (SAMPA direct, JD3),
    mesure F1/F2 par LPC sur l'audio VTL produit, et compare aux
    formants de référence de la langue (language_vowel_sets).
    """
    try:
        import scipy.io.wavfile as wav  # noqa: F401 (import check)
    except ImportError:
        _die("scipy requis pour la vérification in situ")
    _ensure_jd3()   # garde-fou : mesure in situ sur JD3 uniquement
    from vtl_synth import Pipeline
    from vtl_synth.core.constants import ACTIVE_LANG, VOWEL_TARGETS
    from vtl_synth.utils.language_vowel_sets import get_vowel_set

    lang = lang or ACTIVE_LANG
    if lang != ACTIVE_LANG:
        _die(f"langue demandée {lang} != langue active {ACTIVE_LANG} "
             "(setlang d'abord)")
    refs = get_vowel_set(lang)['vowels']
    p = Pipeline(lang=lang)

    _info(f"Vérification in situ de {lang} ({_display(lang)}) — "
          "LPC sur audio VTL/JD3")
    print(f"{'voy':4s} {'F1 mes':>7s} {'F1 réf':>7s} | "
          f"{'F2 mes':>7s} {'F2 réf':>7s} | verdict")
    n_ok = n_tot = 0
    for key, target in VOWEL_TARGETS.items():
        ref = refs.get(key)
        if not ref:
            continue
        n_tot += 1
        f1r, f2r = float(ref[0]), float(ref[1])
        try:
            f1, f2 = _measure_vowel(p, key, None)
            ok1 = f1 is not None and abs(f1 - f1r) <= tol * f1r
            ok2 = f2 is not None and abs(f2 - f2r) <= tol * f2r
            ok = ok1 and ok2
            n_ok += ok
            print(f"{key:4s} "
                  f"{(f'{f1:7.0f}' if f1 else '    n/a'):>7s} {f1r:7.0f} | "
                  f"{(f'{f2:7.0f}' if f2 else '    n/a'):>7s} {f2r:7.0f} | "
                  f"{'OK' if ok else 'ÉCART'}")
        except Exception as e:
            print(f"{key:4s} {'erreur':>7s} {f1r:7.0f} | "
                  f"{'erreur':>7s} {f2r:7.0f} | {type(e).__name__}: "
                  f"{str(e)[:60]}")
    _info(f"Bilan : {n_ok}/{n_tot} voyelles dans la tolérance ±{tol:.0%}")
    report_current()
    return n_ok, n_tot


# ===========================================================================
# Commands
# ===========================================================================

def _install_lexicons(pack_dir: Path) -> dict:
    """Copy the pack lexicons into vtl_synth/data/ (never overwrite).

    Writes the data manifest {filename: sha256} of the data files OWNED
    by the pack: files this install copied (absent before), plus files
    already owned by a previous install that still byte-match the pack
    (ownership survives re-installs). Repository-tracked lexicons that
    simply match the pack copies are NOT claimed — ``restore --purge``
    must never delete files the pristine repo ships with.
    """
    src_dir = Path(pack_dir) / 'lexicons'
    dman = DATA_DIR / _DATA_MANIFEST
    previous = {}
    if dman.exists():
        try:
            previous = json.loads(dman.read_text(encoding='utf-8'))
        except ValueError:
            previous = {}
    manifest = {}
    if src_dir.is_dir():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            src = src_dir / name
            if not src.is_file():
                continue
            dst = DATA_DIR / name
            digest = _sha256(src)
            if not dst.exists():
                shutil.copy2(src, dst)
                _info(f"  copié : vtl_synth/data/{name}")
                manifest[name] = digest
            elif _sha256(dst) == digest:
                if name in previous:
                    # already owned by a previous install: keep ownership
                    manifest[name] = digest
                _info(f"  (déjà présent) : vtl_synth/data/{name}")
            else:
                _info(f"  (déjà présent, diffère du pack — conservé) : "
                      f"vtl_synth/data/{name}")
    for code, fname in _LEXICON_FILES:
        if not (DATA_DIR / fname).exists():
            _info(f"  AVERTISSEMENT : {fname} absent — le g2p {code} "
                  "fonctionnera sur les règles seules (téléchargement : "
                  "cf. lang_pack/lexicons/"
                  f"README_{code}_lexicon.md)")
    dman.write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    return manifest


def cmd_install(pack_dir: Path, lang: str, calibrate: bool = False) -> None:
    """Install the language-pack modules and activate ``lang``."""
    layout = _pack_layout(pack_dir)
    if layout is None:
        _die(f"pack de langues introuvable : {pack_dir} (option --pack ; "
             f"attendu : lang_pack/ à la racine, ou l'ancien layout "
             f"../modules)")
    blocks = _load_pack_blocks(pack_dir) if layout == 'lang_pack' else {}
    if not blocks:
        blocks = dict(_FALLBACK_BLOCKS)
        if layout == 'lang_pack':
            _info("AVERTISSEMENT : lang_blocks/blocks.py absent du pack — "
                  "blocs fr/en de secours")
        else:
            _info("Pack legacy (v1.0.0) : blocs intégrés fr/en "
                  "(lang_pack/lang_blocks/blocks.py requis pour es/de/it/pt)")
    if lang not in blocks:
        _die(f"langue {lang!r} inconnue; disponibles : "
             f"{', '.join(sorted(blocks))}")
    if blocks is not LANG_BLOCKS and blocks != LANG_BLOCKS:
        _info("NOTE : les blocs du pack --pack diffèrent de ceux du pack "
              "par défaut ; setlang continuera d'utiliser le pack par défaut")
    _info(f"Installation du language pack depuis : {pack_dir} "
          f"(layout {layout})")

    _info("Étape 1/4 : copie des modules de langue → vtl_synth/utils/")
    modules = _lang_module_names(layout)
    owned = []
    for name in modules:
        src = _module_source(pack_dir, layout, name)
        if not src.exists():
            _die(f"module absent du pack : {src}")
        dst = UTILS_DIR / name
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            _info(f"  mis à jour : vtl_synth/utils/{name}")
        elif not dst.exists():
            _info(f"  copié : vtl_synth/utils/{name}")
        shutil.copy2(src, dst)
        if name != 'g2p.py':     # g2p.py is native to the pipeline
            owned.append(name)
    # Manifest = every installed language module (except the native
    # g2p.py): a re-install refreshes it, so `restore --purge` always
    # performs a complete uninstall.
    (UTILS_DIR / _MANIFEST).write_text(
        '\n'.join(owned) + ('\n' if owned else ''), encoding='utf-8')

    _info("Étape 2/4 : intégration Pipeline (paramètre lang) + __init__")
    for pack_name, dst in PATCHED_FILES.items():
        src = _patched_source(pack_dir, layout, pack_name)
        if not src.exists():
            _die(f"fichier absent du pack : {src}")
        _backup(dst)
        shutil.copy2(src, dst)
        _info(f"  intégré : {dst.relative_to(PIPELINE_ROOT)}")

    _info("Étape 3/4 : lexiques de prononciation → vtl_synth/data/")
    _install_lexicons(pack_dir)

    _info("Étape 4/4 : section langue de constants.py")
    _ensure_jd3()   # garde-fou : cibles calibrées in situ sur JD3
    _backup(CONSTANTS)
    src = CONSTANTS.read_text(encoding='utf-8')
    current = get_current_lang()
    target = current if (current in blocks and LANG_SECTION_BEGIN in src) else lang
    if calibrate:
        entries, display_name, _corners = calibrate_targets(lang)
        block = render_calibrated_block(lang, entries, display_name)
        target = lang
    else:
        block = blocks[target]
    CONSTANTS.write_text(_replace_lang_section(src, target, block=block),
                         encoding='utf-8')
    _info(f"  section langue réécrite : {target}")

    verify_imports()
    report_current()


def cmd_setlang(lang: str) -> None:
    """Switch the active language by rewriting the LANG SECTION."""
    if lang not in LANG_BLOCKS:
        _die(f"langue {lang!r} inconnue; disponibles : {', '.join(sorted(LANG_BLOCKS))}")
    _ensure_jd3()
    src = CONSTANTS.read_text(encoding='utf-8')
    if LANG_SECTION_BEGIN not in src:
        # après une permutation de speaker (constants remplacé en
        # entier), la section a pu être perdue d'un dépôt sans garde —
        # ré-amorçable si le pack est installé (modules présents)
        if not (UTILS_DIR / 'setlang.py').exists():
            _die("language pack non installé — lancez d'abord : "
                 "python setup_lang.py install")
        _info("LANG SECTION absente (constants permuté par install_speaker ?) "
              "— ré-amorçage")
    previous = get_current_lang()
    if previous == lang:
        _info(f"Déjà en {lang} — rien à faire.")
        report_current()
        return
    CONSTANTS.write_text(_replace_lang_section(src, lang), encoding='utf-8')
    _info(f"Langue basculée : {previous or 'native'} → {lang}")
    report_current()


def cmd_list() -> None:
    """List the installable languages."""
    _info(f"Langues disponibles : {', '.join(sorted(LANG_BLOCKS))}")
    for code in sorted(LANG_BLOCKS):
        _info(f"  {code} — {_display(code)}")
    report_current()


def cmd_restore(purge: bool) -> None:
    """Restore the original pipeline files from the .bak backups."""
    _info("Restauration des fichiers originaux…")
    restored = False
    # constants.py : restauration SPEAKER-AWARE. Le .bak peut être
    # périmé (le speaker a pu changer depuis la première installation),
    # on réinjecte donc le bloc vocalique natif du speaker ACTIF
    # (source du registre multi-speakers) à la place de la LANG
    # SECTION. Sans registre (dépôts monospeaker), comportement
    # historique : copie du .bak.
    speaker = _active_speaker_name()
    src = CONSTANTS.read_text(encoding='utf-8')
    if LANG_SECTION_BEGIN in src or speaker is not None:
        if speaker is not None:
            reg = json.loads(
                (PIPELINE_ROOT / 'vtl_synth' / 'data' / 'speakers'
                 / 'registry.json').read_text(encoding='utf-8'))
            if speaker not in reg:
                _die(f"speaker actif {speaker!r} inconnu du registre")
            native_src = (PIPELINE_ROOT / 'vtl_synth' / 'data' / 'speakers'
                          / reg[speaker]['constants']).read_text(
                              encoding='utf-8')
            m = re.search(r'(?ms)^VOWEL_TARGETS:.*?^VOWEL_EFFORT_GAIN:.*?^\}\n',
                          native_src)
            if not m:
                _die(f"bloc vocalique natif introuvable dans la source du "
                     f"speaker {speaker}")
            if LANG_SECTION_BEGIN in src:
                section_re = re.compile(
                    re.escape(LANG_SECTION_BEGIN) + r'.*?'
                    + re.escape(LANG_SECTION_END) + r'[^\r\n]*\n', re.S)
                new_src = section_re.sub(lambda _m: m.group(0), src, count=1)
            else:
                new_src = src  # rien à désinstaller côté section
            if new_src != src:
                CONSTANTS.write_text(new_src, encoding='utf-8')
                _info(f"  section langue retirée : bloc vocalique natif du "
                      f"speaker {speaker} réinjecté")
                restored = True
            else:
                _info("  (aucune section langue dans constants.py)")
        else:
            bak = CONSTANTS.with_suffix(CONSTANTS.suffix + '.bak')
            if bak.exists():
                shutil.copy2(bak, CONSTANTS)
                _info(f"  restauré : constants.py ← {bak.name}")
                restored = True
            else:
                _info("  (pas de sauvegarde pour constants.py)")
    else:
        _info("  (constants.py sans section langue ni registre speaker)")
    for path in PATCHED_FILES.values():
        bak = path.with_suffix(path.suffix + '.bak')
        if bak.exists():
            shutil.copy2(bak, path)
            _info(f"  restauré : {path.relative_to(PIPELINE_ROOT)} ← {bak.name}")
            restored = True
        else:
            _info(f"  (pas de sauvegarde pour {path.name})")
    if purge:
        # Only remove modules that the install actually introduced
        # (manifest) — native pipeline modules like g2p.py are kept.
        manifest = UTILS_DIR / _MANIFEST
        if manifest.exists():
            for name in manifest.read_text(encoding='utf-8').split():
                p = UTILS_DIR / name
                if p.exists():
                    p.unlink()
                    _info(f"  supprimé : vtl_synth/utils/{name}")
            manifest.unlink()
        else:
            _info("  (manifeste absent — aucun module de langue à supprimer)")
        # Lexicon data files: remove only those that still byte-match
        # what the install put in place (user-modified files are kept).
        dman = DATA_DIR / _DATA_MANIFEST
        if dman.exists():
            recorded = json.loads(dman.read_text(encoding='utf-8'))
            for name, digest in sorted(recorded.items()):
                p = DATA_DIR / name
                if p.exists() and _sha256(p) == digest:
                    p.unlink()
                    _info(f"  supprimé : vtl_synth/data/{name}")
                elif p.exists():
                    _info(f"  conservé (modifié depuis l'installation) : "
                          f"vtl_synth/data/{name}")
            dman.unlink()
        _info("Modules de langue supprimés (--purge).")
    if not restored:
        _info("Rien à restaurer : le language pack n'avait rien modifié.")
    else:
        _info("Restauration terminée (fichiers .bak conservés).")
    report_current()


def verify_imports() -> None:
    """Import vtl_synth and check the language registry is operational."""
    code = (
        "import sys; sys.path.insert(0, r'%s'); "
        "import vtl_synth; from vtl_synth.utils import setlang as sl; "
        "langs = sl.list_languages(); "
        "assert 'en' in langs and 'fr' in langs, langs; "
        "print('OK: registre actif', langs)" % PIPELINE_ROOT
    )
    import subprocess
    res = subprocess.run([sys.executable, '-c', code],
                         capture_output=True, text=True)
    if res.returncode == 0:
        _info(f"Vérification : {res.stdout.strip()}")
    else:
        _info(f"AVERTISSEMENT — vérification import échouée :\n{res.stderr.strip()}")

# ===========================================================================
# CLI
# ===========================================================================

def main() -> None:
    ap = argparse.ArgumentParser(
        prog='setup_lang.py',
        description="Installation/bascule des langues du covtl-pipeline "
                    "(speaker JD3 conservé).")
    sub = ap.add_subparsers(dest='cmd')

    p_inst = sub.add_parser('install', help="installer le language pack")
    p_inst.add_argument('--lang', default='fr', choices=sorted(LANG_BLOCKS),
                        help="langue à activer après installation (défaut: fr)")
    p_inst.add_argument('--pack', default=None,
                        help="répertoire du pack (défaut: lang_pack/ à la "
                             "racine, sinon ../modules, ou $COVTL_LANG_PACK)")
    p_inst.add_argument('--calibrate', action='store_true',
                        help="dériver les cibles voc. sur VTL/JD3 au lieu du bloc intégré")

    p_set = sub.add_parser('setlang', help="basculer de langue")
    p_set.add_argument('lang', choices=sorted(LANG_BLOCKS))

    p_cal = sub.add_parser('calibrate',
                           help="dériver les cibles voc. d'une langue sur VTL/JD3 puis l'activer")
    p_cal.add_argument('lang')
    p_cal.add_argument('--fine', action='store_true',
                       help="pas de recherche rho fin (0.01, plus lent)")
    p_cal.add_argument('--in-situ', action='store_true',
                       help="raffiner chaque rho par synthèse réelle + "
                            "mesure LPC (lent mais auto-validé)")

    p_ver = sub.add_parser('verify',
                           help="mesure LPC in situ des voyelles (preuve de fonctionnement)")

    sub.add_parser('show', help="afficher la langue en cours")
    sub.add_parser('list', help="lister les langues disponibles")

    p_res = sub.add_parser('restore', help="restaurer les fichiers originaux")
    p_res.add_argument('--purge', action='store_true',
                       help="supprimer aussi les modules de langue installés")

    args = ap.parse_args()
    if args.cmd is None:
        report_current()          # no args: just report
        ap.print_help()
        return
    if args.cmd == 'install':
        pack = Path(args.pack or os.environ.get('COVTL_LANG_PACK')
                    or DEFAULT_PACK_DIR)
        cmd_install(pack, args.lang, calibrate=args.calibrate)
    elif args.cmd == 'setlang':
        cmd_setlang(args.lang)
    elif args.cmd == 'calibrate':
        cmd_calibrate(args.lang, fine=args.fine, in_situ=args.in_situ)
    elif args.cmd == 'verify':
        cmd_verify()
    elif args.cmd == 'show':
        report_current()
    elif args.cmd == 'list':
        cmd_list()
    elif args.cmd == 'restore':
        cmd_restore(purge=args.purge)


if __name__ == '__main__':
    main()
