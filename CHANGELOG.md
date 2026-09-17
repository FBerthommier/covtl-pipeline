# Changelog

All notable changes to this package are documented here.
Format: Keep a Changelog — https://keepachangelog.com/

## [Unreleased]

### Documentation / hygiene
- **Manual audit fixes (A/C/D/E)** — no functional change: glides
  documented as consonantal nodes anchored on the *reference* vowel
  tree, deliberately independent of the calibrated vowel plateaus
  (ρᵢ = 0.60, ρᵤ = 0.55); the spelled-`r` input alias removed from the
  engine-SAMPA inventory (only `R` exists, normalized in
  `notation.py`); the Fig. 1 caption corrected (m vs b: same target
  and selector, only the velum VO extension differs); the two
  constant sets explicitly split — reference curvature (Kc=10, Kv=30,
  ν=1) belongs to the deprecated `legacy` engine (plus the polar-video
  branch display), the `syl` engine runs ν=−1, K=1000,
  `SYL_COEFCEN=0.5`. The ARPAbet `NG → J` mapping is now documented as
  a compromise (the English velar nasal has no closure target); the
  `NG → N` alternative was left to a dedicated property test.
- **`constants.py`**: removed the shadowed duplicate `'j'` key (the
  former palatal entry (1.22, 1°) never took effect — the FIX-2 glide
  definition always won); effective targets unchanged (verified:
  j = 0.80/300°, w = 0.60/60°). Glide comment updated accordingly.
- **`docs/.l_10646.ttf`** is now shipped, so `manual.pdf` can be
  rebuilt from the repository (xelatex, two passes).

## [1.1.0] — 2026-09-16

Version decision (vs v2.0.0): **no file removed**; the 7 modified
`core/` files are **additive** changes (registry-driven speaker
resolution with unchanged JD3 fallback, `--expressive` default OFF with
bit-identical outputs, marked LANG SECTION carrying the native vowel
block), and the JD3 `regression_baselines.json` phrases are
**bit-identical to 1.0.2** (only the `meta` key gained a `speaker`
field) — the default-speaker behaviour did not change, so minor
version. Full inventory: `MIGRATION_NOTES.md` §1.

### Added — multi-speakers registry (add-on 1)
- **5-speaker registry** `vtl_synth/data/speakers/`
  (`registry.json` + `ACTIVE_SPEAKER` marker): `jd3` (reference,
  SynthVTL24b original), `s1`/`s2` (DVTD MRI subjects, constants v3)
  and `m01`/`w02` (official VTL 2.4 ZIP speakers, pure option A +
  2025→11-code glottal mapping, index 7 = **PS not DP**).
- **`install_speaker.py`** selector (`list|install|restore|status`):
  swaps `core/constants.py` (bit-exact copy of the registry source),
  the orthogonal branch (dynamic `ACTIVE_SPEAKER` resolution in
  `speaker_jd.py` / `build_phrase_tract.py` — `vtl_binaries/JD3.speaker`
  is never touched) and the shared `vocaltractlab_cython` wheel
  resource (audio + SVG/video layer; backup/restore, automatic
  rollback, per-install smoke test in a fresh subprocess).
- **Per-speaker regression baselines**
  `regression_baselines_{s1,s2,m01,w02}.json` (16/16 green per
  speaker; `scripts/regen_baselines.py` regenerates the file matching
  the active speaker), and `scripts/calibrate_fine_v2.py`
  (s1/s2 fine calibration, D15 corrections: 2D (ρ, θ) area-function
  occlusive targets, s_L² fricative-gap rescaling, native TTY rule +
  +0.15 apical bonus, multi-criteria `@` target).
- `tests/test_speaker_registry.py` — registry integrity (hashes,
  f0_default consistency with the constants sources).

### Added — language pack (add-on 2)
- **`setup_lang.py` + `lang_pack/`**: de/en/es/fr/it/pt with
  `install|setlang|calibrate|verify|restore`; a managed **LANG
  SECTION** (markers `LANG SECTION — BEGIN/END`) replaces the native
  `VOWEL_TARGETS..VOWEL_EFFORT_GAIN` block of `constants.py`, is
  transported across speaker swaps (canonical-form coherence), and is
  fully reversible. 13 g2p/profile modules land in `vtl_synth/utils/`
  (tracked by `.lang_pack_manifest`), Wikipron lexicons in
  `vtl_synth/data/` (CC BY-SA 3.0, notices beside each TSV).
- **JD3-only calibration guard-rail** (`setup_lang.py::_ensure_jd3`):
  the pack vowel targets are calibrated in situ on JD3 — any
  `calibrate` (or `install --calibrate`) first reinstalls speaker jd3
  (constants + marker + wheel) and says so; a non-jd3 speaker with an
  active language is flagged « cibles calibrées JD3 — HYPOTHÈSE ».
  s1/s2/m01/w02 keep their native vowel targets (only jd3 follows the
  pack). Per-component licensing: `lang_pack/LICENSE.md`.
- `lang_pack/manual/manual.pdf|.tex`, `lang_pack/ARCHITECTURE.md`.

### Added — expressive prosody (add-on 3)
- **Expressive prosody option** (défaut OFF, sorties
  bit-identiques au mode monotone; portée depuis covtl-languages dans
  la branche multi-speakers, compatible bascule de speakers):
  `Pipeline(expressive=True)` / CLI `--expressive` (bandeau
  « prosodie : expressive ») ajoute (a) la *respiration syntaxique* —
  découpage lexical en groupes de souffle (`vtl_synth/utils/chunking.py`,
  dictionnaires de mots-outils pour les 6 langues, limite dure 5 mots
  équilibrée, connecteurs insécables « parce que »/« so that »/…) et
  pause respiratoire `%` de 130 ms dans le moteur syl (`syltraj`
  `T_pause_breath`, bit-identique sans marqueur) ; (b) le
  *contour de F0 sculpté* (`vtl_synth/utils/prosody_f0.py`):
  déclinaison conservée + reprise d'attaque par bloc + accents de
  hauteur (bosse gaussienne asymétrique, amplitude par langue
  0.16-0.24 × f0_base, downstep allemand) + chute nucléaire terminale
  par langue (Jun 2005/2014, Ladd 2008 ; Pierrehumbert 1980 /
  Jun & Fougeron 2002 / Face 2003 / Grice et al. 2005 / Avesani 1995 /
  Frota 2000, cf. setlang.py). Le stress lexical voyage HORS BANDE
  (jamais dans le SAMPA) : `lexicon_loader.ipa_to_keys_stress`
  conserve ˈ/ˌ Wikipron (canal `stress_for`), digits CMUdict pour
  l'anglais, règles orthographiques de repli es/it/pt/de. N'agit que
  sur la colonne f0 du glottis et les durées de pause — jamais sur le
  tract (la mécanique speakers — f0 par locuteur, registre, .polar —
  est inchangée ; `f0_base` du contour expressif = le f0 actif,
  quel que soit le speaker). `ExpressivityProfile` par langue porté
  par `LangProfile.expressivity`. Démos :
  `python examples/demo_prosody.py`; mesures :
  `python scripts/f0_report.py <tract...>`. Tests :
  `tests/test_expressive.py` (bit-identité off, chunking par langue,
  stress, accents mesurables, douceur, chute nucléaire).
- **`docs/expressive_prosody.tex/.pdf`** : guide didactique
  (anglais US, pdflatex pur, transportable) — démarrage rapide,
  respiration syntaxique, contour F0, stress hors-bande, mesures
  (`f0_report`), tests, limitations, et un chapitre détaillé
  sur l'interaction avec l'installation multi-speakers
  (registre, transport de la LANG SECTION, garde-fou JD3,
  workflows langue-d'abord/locuteur-d'abord, matrice de
  garanties).

### Added — polar visualization (add-on 4)
- **Polar video v3** — CLI `--polar` on `run`: writes a `.polar`
  intermediate (100 Hz, format v3) and renders a **dual-panel MP4**
  sagittal cross-section | polar plane at 25 Hz, where the vocalic
  branch is drawn **red** and the consonantal branch **blue** (each
  with its fading trail and current position; inventory dots,
  orientation θ=0 East/CCW, transient labels). New module
  `vtl_synth/video/polar_video.py`; doc
  **`docs/polar_visualization.pdf`** (LaTeX source included) and
  `docs/figures/`. Short demo: `examples/polar_demo_en.mp4`.

### Added — packaging
- **`plot-tract` command**: graphical counterpart of `inspect` —
  draws the 400 Hz trajectory of every `.tract` parameter into a PNG
  figure (shared time axis; `--which all` adds the glottis f0 and
  pressure, `--params` selects a subset, `--ranges` prints the
  min/max/mean table). New module `vtl_synth/video/tract_figure.py`,
  optional `plot` extra (`pip install .[plot]`, matplotlib).
- `scripts/check_vowel_area.py`, `scripts/f0_report.py`.
- `MIGRATION_NOTES.md` — packaging decisions inventory
  (v1.1.0 justification, excluded tests, licensing map).

### Changed — polar video v3 engine
- **Dissociated vocalic/consonantal branches**: the
  polar figure is no longer an inversion of the blended Pval parameter
  frames (v2 `polar_from_pval`, which produced a single zigzag path:
  during a cluster the parameter frames are off-manifold so the two
  branches of the superposition model collapsed into one). The syl
  engine block helpers (`_append_arc`, `_append_background`,
  `_append_decay`, `_append_attack`, `build_cluster_pval`) are now
  temporarily monkeypatched during the `.polar` build to record the
  polar points the engine drives toward (anchor pairs, consonant node
  targets), and BOTH branches are rebuilt directly with
  `core.polar.polar_arc` / `stationary_point` at the reference-model
  curvature (**K=30**, ν=+1 vocalic / −1 consonantal — a display
  choice: not the quasi-rectilinear SYL_K=1000 parameter arcs):
  vocalic branch (red) = continuous anchor-to-anchor background +
  vowel plateaus, flowing under the clusters; consonantal branch
  (blue) = cluster sub-arcs anchor → C₁ → … → C_m → anchor, peaking
  exactly on the consonant node targets. `.polar` format **version 3**:
  two 100 Hz trajectories `vocalic` / `consonantal` (null while a
  branch is inactive) + phoneme timing as before; v2 files remain
  readable by `read_polar`. `polar_from_pval` is kept as a diagnostic
  only.
- **Polar video fix — stale work-dir frames**: the dual-panel encoder
  silently appended leftover `frame_*.png` from a previous LONGER
  render in the persistent `temp_video` work directory (observed: a
  `polar_e2e.mp4` 0.64 s longer than its audio, ending with frames of
  an earlier "this is easy for us" render). `make_polar_video` now
  purges `frame_*.png` in the sagittal/polar/compo work
  subdirectories before rendering and verifies the composed frame
  count before encoding; the log reports the actual encoded count.

### Changed — speakers s1/s2 (constants v3)
- **s1/s2 bunching fix (constants v3)**: root cause of the raised tongue
  tip / "bunch" (worst on schwa) found in the stage-2 TTY rule of the
  adapter — it substitutes c0 = (0.80−Va)/2.3, calibrated on JD3 only, which
  on the DVTD anatomies raises the tip at the anchors (s2: V(π) −1.299 →
  +0.394, i.e. an apical closure on /a/). `scripts/calibrate_fine_v2.py`
  now keeps the native analytic c0/c2 of TTY and only adds the +0.15 apical
  occlusion bonus (JD3 untouched). Full phase 1+2 rerun; the '@' target is
  additionally chosen by multi-criteria area-function cost instead of the
  a-i-u centroid (s1 (0.70, 160°), s2 (0.35, 170°)). Result: no vowel
  background has a lingual occlusion any more (s2 /a/ 0.00 → 0.71 cm²,
  /6/ 0.04 → 1.04; all ≥ 0.59), humps reduced. Baselines regenerated.
- **Fine calibration v2 of s1/s2 (`s1_constants.py`, `s2_constants.py`)**:
  redone with `scripts/calibrate_fine_v2.py` implementing the D15
  corrections from the DVTD transfer report. Occlusive targets now come
  from a 2D (ρ, θ) area-function cost centered on the canonical JD3 place
  angle (exact closure + place margin when it exists, documented
  compromise otherwise — closure is not reachable on every vowel
  background for these anatomies); fricative gap windows are rescaled by
  s_L² (subglottal length ratio: s1 1.179, s2 0.887).

### Fixed — packaging
- `vtl_synth/data/vtl_binaries/JD3.speaker`: restored the pristine
  wheel original (92938 o, SHA-256 `a583bdaaa7ffe216…`, identical to
  the 1.0.2 release) — the development tree carried a 1-character
  corruption (`escription=` line 1801) in this dormant fallback file.
- `pyproject.toml`: the new package data (`data/speakers/` registry,
  per-speaker `.speaker`/`*_constants.py`, Wikipron `data/*.tsv`
  lexicons) is now declared in `[tool.setuptools.package-data]` —
  a plain `pip install .` previously would not have shipped it.
- `install_speaker.py` is repository-portable: backups/journals live
  in `.speaker_backups/` inside the clone (created on first use,
  git-ignored); the editable-pointer guard now compares against the
  repository root instead of a hard-coded development path; the
  original-constants backup check accepts the canonical (LANG SECTION)
  form of the JD3 reference.

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
