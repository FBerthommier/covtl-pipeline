# Changelog

All notable changes to this package are documented here.
Format: Keep a Changelog — https://keepachangelog.com/

## [Unreleased]

### Added
- **`plot-tract` command**: graphical counterpart of `inspect` —
  draws the 400 Hz trajectory of every `.tract` parameter into a PNG
  figure (shared time axis; `--which all` adds the glottis f0 and
  pressure, `--params` selects a subset, `--ranges` prints the
  min/max/mean table). New module `vtl_synth/video/tract_figure.py`,
  optional `plot` extra (`pip install .[plot]`, matplotlib).

## [1.0.2] — 2026-09-08

### Changed
- **Inter-word coarticulation**: adjacent words inside a phrase are
  now connected with '.' (`Dis.iz.i.zi.fOR.@s`) instead of being
  separated by an inter-word pause — the chopped-listening defect
  (a silence at every word boundary) is gone. A comma still inserts
  the short inter-word pause (space); `|` remains the long phrase
  pause.
- **Timing rebalance** (defaults of `Pipeline` and the CLI):
  `--tcons` 60 → **100 ms**, `--tvoy` 60 → **80 ms**,
  short pause stays **200 ms**.

### Audit (on "this is easy for us", v1.0.1 → v1.0.2)
- pause runs ≥ 100 ms: 6 → 4; silence fraction: 69.7 % → 45.5 %
  (−24.2 pts); longest voiced run: 0.25 s → 0.65 s (×2.6);
  RMS +21 %; duration 2.87 s → 2.37 s.

## [1.0.1] — 2026-09-08

### Fixed
- **g2p broke coarticulation**: the ARPAbet→SAMPA conversion emitted
  a space-separated phoneme list (`D i s i z i ...`), so the engine
  treated every phoneme as its own word and inserted an inter-word
  pause after each one. Words are now emitted as **connected engine
  tokens** syllabified by onset maximization with '.' separators
  (`Dis iz i.zi fOR @s`). Added `phonemes.syllabify_keys`,
  `keys_to_connected`, `sampa_to_connected`.
- Quantified on "this is easy for us": pause runs (≥100 ms silence)
  drop from **14 to 6** (exactly the structural ones: onset, 4 word
  boundaries, offset), duration from 5.0 s to 2.6 s — the 8 spurious
  intra-word pauses are gone and intra-word coarticulation is
  restored. Inter-word short pauses and `|` long pauses unchanged.

## [1.0.0] — 2026-09-07

First packaged release: the Berthommier COVTL synthesis engine
(articulatory model coupled with VocalTractLab) packaged as the
installable `vtl_synth` package, with the layout aligned on the
vtl-pipeline reference repository.

### Added
- Installable package `vtl_synth` (`pip install .` / `-e .`),
  console script `vtl-synth` with subcommands `run`, `text-to-wav`,
  `tract-to-mp4`, `inspect`.
- `vtl_synth.core.pipeline`: `Pipeline` orchestrator (text → tract →
  wav → mp4), port of the former root `synthesize_tract.py` (F0
  declination included) plus integrated video rendering.
- `vtl_synth.core.phonemes` + `vtl_synth.utils.g2p`: English g2p
  (CMUdict ARPAbet → engine SAMPA) with verbatim passthrough of
  already-phonetic tokens.
- `vtl_synth.video`: `renderer` (tract → SVG → PNG, ported from
  `make_video.py`) and `encoder` (MP4 H.264/AAC via imageio-ffmpeg).
- `vtl_synth.vtl.api`: VocalTractLab API facade.
- Package data: `JD3.speaker` under `vtl_synth/data/vtl_binaries/`.
- `examples/demo.py`, `launch.bat`, README/INSTALL/LICENSE
  (GPL-3.0-or-later)/THIRD_PARTY_NOTICES.
- Tests: 49 engine non-regression tests migrated unchanged (except
  import paths) + 6 new CLI/g2p tests.

### Changed
- Package `pipeline` → `vtl_synth.core` (156 import statements
  rewritten; module code otherwise untouched).
- Speaker file resolution: `vtl_synth/data/vtl_binaries/JD3.speaker`
  (package data) instead of the repository root.
- Default debug output dir of `build_phrase_tract`: `./out/phrases`
  (cwd-based) instead of `<repo>/output/phrases`, so an installed
  package never writes into site-packages.

### Fixed / compatibility
- `synth.py`: the four analysis bindings added in
  vocaltractlab-cython 0.0.16 (`active_speaker`, `get_cross_sections`,
  `get_centerline`, `get_outlines`) are now optional — older wheels
  (0.0.13, the last installable under Python 3.9 on Windows) load
  with the full synthesis path available; the matching getters raise
  a clear error. Previously one missing symbol disabled the whole VTL
  layer.
