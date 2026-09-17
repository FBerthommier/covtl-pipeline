@echo off
chcp 65001 >nul
rem ============================================================
rem  install_lang.bat -- covtl-pipeline language pack installer
rem  (Windows). One command: install + in-situ verify + summary.
rem
rem  Usage:   install_lang.bat [lang]     (default: fr)
rem  Example: install_lang.bat es
rem
rem  INVARIANTS -- do not break (see lang_pack/README.md, section
rem  "Windows: console encoding"):
rem   1. "chcp 65001 >nul" MUST stay at the top of this file, right
rem      after @echo off. Without it, UTF-8 text is decoded with the
rem      active OEM code page: accented characters get corrupted
rem      ("coree" with an accent becomes "corA(c)e"-style mojibake)
rem      and the g2p then emits wrong engine keys (observed symptom:
rem      kOR.@ instead of koRe.@ on the French demo phrase).
rem   2. This file must stay encoded UTF-8 WITHOUT BOM (a BOM would
rem      break the "@echo off" line at execution).
rem ============================================================
setlocal EnableExtensions

rem ---- repository root (this script lives in <root>\lang_pack) ----
set "ROOT=%~dp0.."
pushd "%ROOT%"
if errorlevel 1 (
    echo [install_lang] ERROR: cannot enter repository root: %ROOT%
    exit /b 1
)

rem ---- language argument (default: fr) ----
set "LANGARG=%~1"
if "%LANGARG%"=="" set "LANGARG=fr"
echo [install_lang] Language requested: %LANGARG%

rem ---- locate Python (py -3 launcher first, then python) ----
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [install_lang] ERROR: Python not found.
    echo [install_lang]        Install Python 3.9+ so that "py -3" or
    echo [install_lang]        "python" works, then run this again.
    popd
    exit /b 1
)
echo [install_lang] Using interpreter: %PY%

rem ---- dependencies (numpy/scipy/cmudict/VTL bindings) ----
%PY% -c "import numpy, scipy, cmudict" >nul 2>&1
if errorlevel 1 (
    echo [install_lang] Installing Python dependencies...
    %PY% -m pip install numpy scipy cmudict vocaltractlab-cython
    if errorlevel 1 (
        echo [install_lang] ERROR: dependency installation failed ^(pip^).
        popd
        exit /b 1
    )
)

rem ---- the pipeline package itself (pip install -e .) ----
%PY% -c "import vtl_synth" >nul 2>&1
if errorlevel 1 (
    echo [install_lang] Installing the pipeline ^(pip install -e .^)...
    %PY% -m pip install -e .
    if errorlevel 1 (
        echo [install_lang] ERROR: "pip install -e ." failed -- run it
        echo [install_lang]        manually from the repository root.
        popd
        exit /b 1
    )
)

rem ---- 1/3: install the language pack, activate the language ----
%PY% setup_lang.py install --lang %LANGARG%
if errorlevel 1 (
    echo [install_lang] ERROR: language pack installation failed.
    popd
    exit /b 1
)

rem ---- 2/3: in-situ proof (LPC on real VTL/JD3 audio) ----
echo.
echo [install_lang] In-situ verification -- LPC measurement of the
echo [install_lang] vowel targets. Compare the "Bilan" line with the
echo [install_lang] expected scores in lang_pack/README.md: deviations
echo [install_lang] on close/rounded vowels are the documented LPC
echo [install_lang] measurement bias, not a broken installation.
%PY% setup_lang.py verify

rem ---- 3/3: summary ----
%PY% setup_lang.py show
echo.
echo [install_lang] Done. Next steps:
echo [install_lang]   switch language:  python setup_lang.py setlang en
echo [install_lang]   list languages :  python setup_lang.py list
echo [install_lang]   uninstall      :  python setup_lang.py restore --purge
popd
endlocal
exit /b 0
