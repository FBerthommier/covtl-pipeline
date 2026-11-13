# Known issue (Windows): `vocaltractlab_cython` crashes on non-ASCII installation paths

**Status:** open upstream — root cause identified, fix proposed, workaround shipped in COVTL Console 3.1.4+ builds.
**Audience:** Windows users, packagers, and downstream maintainers. Linux/macOS are not affected (POSIX paths are byte-transparent to `fopen`).

## Symptom

The host process dies with a silent fast-fail **0xC0000409** (Windows Event Log ID 1000, no traceback, no console output) when it is installed or extracted in a directory whose path contains **any non-ASCII character** (`é`, `à`, `ω` — with or without spaces, in the final segment or a parent). ASCII paths with spaces work. A non-ASCII *current working directory* with an ASCII executable path works. Any `pip`/`venv` install of the same sources is unaffected or fails gracefully with a handled return code.

Observed in frozen applications (PyInstaller 6.22.3 onedir, CPython 3.14.7), during the import of `vocaltractlab_cython` (the extension module of this project), which **auto-initializes** with the bundled `resources/JD3.speaker` at import time (since 0.0.14.dev1).

## Root cause (static analysis, source + binary)

End-to-end chain, verified against `vocaltractlab_cython` 0.0.17 and `VocalTractLabBackend-dev` @ df30392 (identical to `main` on 2026-11-12, i.e. the bug is present in current upstream):

1. The Cython binding encodes the speaker path as **UTF-8** (`path.encode()` — the documented `str → char*` conversion) and calls `vtlInitialize(const char*)`.
2. `vtlInitialize` → `vtlLoadSpeaker` → `Speaker::read` → `xmlParseFile` → **`XmlNode.cpp:122`: `ifstream file(fileName.c_str());`** — a *narrow* `char*` path.
3. On Windows, `std::ifstream`/`fopen` with a narrow path decode the bytes using the **ANSI code page (CP_ACP)**, not UTF-8 (MSVC STL `stl/src/fiopen.cpp`; Microsoft Learn, `fopen`/`_wfopen`: "a narrow filename string is interpreted using the ANSI codepage"). The UTF-8 bytes of `é` (`0xC3 0xA9`) decode as `Ã©` in CP1252 → the file is not found → `xmlParseFile` returns NULL → `Speaker::read` throws `XmlException`.
4. **No `try`/`catch`** exists between `vtlInitialize()` and `Speaker::read()`, so the C++ exception escapes the `extern "C"` API boundary and the Cython module init → `std::terminate` → `abort()` → `__fastfail` ⇒ **0xC0000409 (FAST_FAIL_FATAL_APP_EXIT) with no handler and no traceback**.

Binary evidence (PE import tables of the published wheel): `VocalTractLabApi.dll` imports the narrow `std::_Fiopen(const char*)` overload from MSVCP140.dll plus `_CxxThrowException`/`__std_terminate`/`abort` from VCRUNTIME140; no wide-char path API is used anywhere in the chain. The PyInstaller bootloader is exonerated (fully wide-char in 6.22.3; minimal numpy/scipy/matplotlib onedir bundles run fine from the same non-ASCII path — the failing file open is the only ANSI-path operation in the initialization chain).

Same-family precedents: HDF5 #5037 (resolved 2025 by trying UTF-8 first), llama.cpp #18571 (model loading on non-ASCII paths, fixed by Unicode APIs), ParaView (VTK/HDF5 `é`-in-path). **No existing issue tracks this on either repository** — this document will become the upstream issue.

## Workaround shipped in COVTL (application side)

`covtl-console` frozen builds (3.1.4+) detect a non-ASCII executable path at startup and **relocate the whole application to `%TEMP%\covtl-console-ascii`** (incremental robocopy, re-executed from there in a new console). %TEMP% under the user profile is ASCII and private; subsequent launches reuse the staged copy (incremental copy is near-instant). If staging is impossible (e.g. accented %TEMP%), the startup guard refuses politely with a bilingual message and exit code 80 instead of crashing. A structural complement is an `activeCodePage=UTF-8` manifest on the host executable (Windows 10 1903+), which makes CP_ACP equal UTF-8 for the process.

## Upstream fix proposed

1. **Backend (`VocalTractLabBackend-dev`)** — in `xmlParseFile` (`XmlNode.cpp`), on Windows convert the narrow path from UTF-8 to UTF-16 (`MultiByteToWideChar` with `CP_UTF8`) and open via `_wfsopen`, making UTF-8 the API-wide path convention (same resolution HDF5 chose in 2025). Apply the same treatment to the other narrow call sites (`Synthesizer.cpp`, `SegmentSequence.cpp`, `GesturalScore.cpp`).
2. **Backend, defense in depth** — wrap `vtlLoadSpeaker()` / `Speaker::read()` in `try { … } catch (std::exception&)` inside `vtlInitialize()` and return an error code instead of letting a C++ exception escape the `extern "C"` boundary (any future failure becomes a handled `VtlApiError` instead of a process kill).
3. **Binding (`paul-krug/vocaltractlab-cython`)** — document/enforce the path encoding contract, and make the import-time auto-initialization tolerant (catch `VtlApiError`, retry from an ASCII copy) or refuse with a clear message.

## References

Full root-cause report (FR) and the ready-to-file upstream issue draft (EN): COVTL integration workspace, `download/Rapport_vocaltractlab_cython_chemins_non-ASCII.pdf` and `download/draft_issue_VocalTractLabBackend-dev_EN.md`.
