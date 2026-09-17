#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
#
# install_lang.sh — covtl-pipeline language pack installer
# (Linux/macOS). One command: install + in-situ verify + summary.
#
# Usage:   bash install_lang.sh [lang]     (default: fr)
# Example: bash install_lang.sh es
#
# What it does:
#   1. locates Python 3 (python3, else python);
#   2. installs the Python dependencies if missing, then the pipeline
#      itself (pip install -e .) if vtl_synth is not importable;
#   3. python setup_lang.py install --lang <lang>  (modules + lexicons
#      + LANG SECTION of constants.py; JD3 speaker untouched);
#   4. python setup_lang.py verify   (in-situ LPC proof on VTL/JD3);
#   5. python setup_lang.py show     (current language summary).
#
# Exit code: 0 on success, 1 on any installation error (a nonzero
# number of LPC deviations in `verify` is NOT an error — compare with
# the expected scores in lang_pack/README.md).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANGARG="${1:-fr}"

echo "[install_lang] Language requested: $LANGARG"

# --- locate Python 3 ------------------------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[install_lang] ERROR: Python 3 not found (need python3 >= 3.9)." >&2
    exit 1
fi
echo "[install_lang] Using interpreter: $PY"

cd "$ROOT"

# --- dependencies ---------------------------------------------------------
if ! "$PY" -c "import numpy, scipy, cmudict" >/dev/null 2>&1; then
    echo "[install_lang] Installing Python dependencies..."
    "$PY" -m pip install numpy scipy cmudict vocaltractlab-cython
fi

# --- the pipeline package itself ------------------------------------------
if ! "$PY" -c "import vtl_synth" >/dev/null 2>&1; then
    echo "[install_lang] Installing the pipeline (pip install -e .)..."
    "$PY" -m pip install -e .
fi

# --- 1/3: install the language pack, activate the language ----------------
"$PY" setup_lang.py install --lang "$LANGARG"

# --- 2/3: in-situ proof (LPC on real VTL/JD3 audio) ------------------------
echo
echo "[install_lang] In-situ verification — LPC measurement of the vowel"
echo "[install_lang] targets. Compare the 'Bilan' line with the expected"
echo "[install_lang] scores in lang_pack/README.md: deviations on"
echo "[install_lang] close/rounded vowels are the documented LPC measurement"
echo "[install_lang] bias, not a broken installation."
"$PY" setup_lang.py verify

# --- 3/3: summary ----------------------------------------------------------
"$PY" setup_lang.py show
echo
echo "[install_lang] Done. Next steps:"
echo "[install_lang]   switch language:  python setup_lang.py setlang en"
echo "[install_lang]   list languages :  python setup_lang.py list"
echo "[install_lang]   uninstall      :  python setup_lang.py restore --purge"
