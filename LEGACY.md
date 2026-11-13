# Legacy code, dead code and the coverage policy

This document records the decisions taken on 2026-11-13 (branch
`fix/coverage-hardening`) about the modules that stayed behind the
production path. The production engine is the **syllabic trajectory
chain**: `build_phrase_tract` / `Pipeline(engine='syl')` — syltraj →
glottal_source rule engine → assemble_tract.

The combined coverage target is set on the code that this chain (and
its public API surface) actually uses; everything excluded from the
measure is listed here with the reason. Nothing listed as "kept" was
deleted — external users (covtl-console, covtl-lambda, standalone
scripts) depend on this package's import surface.

## 1. Legacy V1 synthesis chain — KEPT (public API) + smoke tests

| Module | Role | Decision |
|---|---|---|
| `core/text_to_tract.py` | V1 chain (continuous parsing → tags → trajectory → assemble); exported as `vtl_synth.text_to_tract` | kept, entry-point contract locked by `tests/test_legacy_v1_api.py` (shapes, finiteness, empty-input error) |
| `core/synth.py` (VTL facade part) | `is_vtl_available`, `get_vtl_info`, `synthesize_to_wav`, `render_tract_svg`, `svgs_to_video`, the `get_*` introspection family | kept (`__all__` + the `vtl_synth.vtl.api` facade mirror it); smoke-tested; `synthesize_audio` is the production audio path used by `Pipeline` |
| `vtl/vtl/api.py` | compatibility re-export facade of the reference repository layout | kept, re-export identity locked by test |
| `core/gesture.py`, `core/trajectory.py`, `core/enveloppe.py`, `core/continuous.py`, `core/prosody_source.py` | V1 chain internals | kept, exercised through the `text_to_tract` smoke path (no dedicated unit tests — they are not on the production path) |
| `core/polar.py`, `core/projection.py` | polar representation / projection of the V1 display model | kept, partially exercised via the V1 smoke path |
| `utils/g2p_fr_legacy.py` | v1 French g2p DATA (single source) | **not** dead: `utils/g2p_fr.py` imports its tables (see `g2p_fr.py` header); stays measured, no omit |

The V1 **signal** is deliberately not pinned by baselines: the
acoustically validated reference is the syl engine (see
`regression_baselines.json`, `engine: 'syl'`).

## 2. Dead code — omitted from the coverage measure

| Module | Evidence | Decision |
|---|---|---|
| `core/pulmonary_effort.py` | zero importers anywhere (grep over `vtl_synth/`, `tests/`, `scripts/`); its role moved to `glottal_source.compute_pulmonary_effort` (2026-09); only stale comments mention it | **omitted** from coverage (`[tool.coverage.report] omit`), file kept in the package for import compatibility; candidate for removal in 2.0 |
| `utils/calibrate_vowels.py` | zero importers; a research/calibration tool (interactive per-speaker vowel calibration), shipped in `utils/` for reproducibility of the 2026-09 calibrations | **omitted** from coverage; kept as a repo tool — it is not part of the import surface used at runtime |

## 3. Video layer — deliberately light testing

| Module | Decision |
|---|---|
| `video/encoder.py` | **omitted** from coverage: MP4 encoding shells out to ffmpeg (via imageio-ffmpeg); slow, and the encoded bytes are not deterministic across ffmpeg builds — a coverage percentage here measures nothing |
| `video/polar_video.py` | measured: `build_polar`/`write_polar` (the deterministic .polar intermediate, 100 Hz) are covered via the `vtl-synth polar-build` CLI test; `make_polar_video` (encoding) is not |
| `video/renderer.py` | measured: `read_tract` covered via `vtl-synth inspect`; frame rendering runs only as part of MP4 jobs |
| `video/tract_figure.py` | measured, covered (`tests/test_tract_figure.py`) |

Rationale: an ffmpeg encode costs seconds per test, is non-bit-stable,
and the sagittal rendering geometry is exercised through the SVG path
of the engine. The cheap, deterministic part of the video pipeline
(polar intermediate + tract figure) IS tested.

## 4. Where the decisions live

- coverage omissions: `pyproject.toml` → `[tool.coverage.report] omit`
  (each entry with a pointer to this file)
- baseline corpus & anti-drift guard: `scripts/regen_baselines.py`
- 5-speaker permutation: `scripts/run_baselines_matrix.py` (+ the CI
  baseline job in `.github/workflows/ci.yml`)
