# Changelog

All notable changes to this package are documented here.
Format: Keep a Changelog — https://keepachangelog.com/

## [Unreleased]

### Added (covtl-sandhi hook — 2026-11-02)

- **feat(sandhi): covtl-sandhi hook (Branch A) — cross-word sandhi as
  an option, default OFF** — `vtl_synth/utils/sandhi/` ships as an
  identity STUB (`SANDHI_FULL = False`) plus the
  `--sandhi` / `--sandhi-mode` options (`Pipeline(sandhi=...,
  sandhi_mode=...)`). Without the rule package the stub is the pure
  identity — **bit-identical outputs to the unpatched repository**
  (`tests/test_sandhi_hook.py`). The rule package (covtl-sandhi,
  Branch B — https://github.com/FBerthommier/covtl-sandhi) is
  installed either by copying its `sandhi/` folder over the stub
  (`cp -r sandhi/. vtl_synth/utils/sandhi/`) or via pip
  (`import sandhi`); it brings six languages — fr liaison
  (`faut il` → `fo.til`), en a→an + onset linking / linking-r
  (`far away` → `fa.R@.we`), it raddoppiamento + euphonic d
  (`a casa` → `a.kka.sa`), es enlace + y→e/o→u (`los amigos` →
  `lo.sa.mi.gos`), pt encadeamento + EP voicing (`os amigos` →
  `o.Z@.mi.guS`), de Glottalversatz (`ein Apfel` → `ajn a.pf@l`) —
  under four COVERAGE LEVELS: `off | minimal | standard | careful`
  (a monotone filter over each language's rule set, never a
  phonology change). The three implementations stay available as
  `--sandhi-mode g2p|post|pre`. The hook rewrites text/SAMPA only —
  never the engine — and the inserted key is never a syllable
  nucleus, so the expressive F0 plans stay aligned; no insertion
  across a `%` breath pause. This is the SINGLE sandhi dispatch of
  the pipeline: the historical 5-language liaison pack
  (fr/it/es/pt/de `liaison_*` modules, `--liaison`) was never
  merged to main and is superseded by the covtl-sandhi package
  (rule parity archived: 39/39 identical outputs on the shared
  battery).

### Added (mission P6 — 2026-11-02, execution)

- **fix(P6): V1V2 validation extended to the full language pack.**
  Dedicated Portuguese corpus `AUDIT_V1V2/corpus_v1v2_pt.json` (18
  items on the fr typology: S1 inter-word V~.V, S2 inter-word V.V~,
  S3 intra-word V.V~, oral/nasal/`cão` diphthong controls, H minimal
  pairs in direct SAMPA) — run through the parameterized harness
  (`run_corpus.py --lang pt` → `results_pt/`): all nasal halves reach
  VO >= 0.489 (threshold 0.3), oral controls at VO = -0.1,
  `nasalite_perdue` = false everywhere. Documented pt peculiarity:
  `g2p_pt` never emits intra-word V~.V (0/35690 words) — S4 is
  covered by the H items in direct SAMPA, as planned in §7.1.
  es/it/de/en inertness proven (`p6_multilingue.py` →
  `results_p6/inertie.json`): g2p without `~`, lexicons without `~`,
  bit-identical syntheses with the gate active/neutralized. Engine
  inventory: the nasal keys of every language are covered by
  `phonemes.SAMPA_VOWELS` (`tout_couvert = True`). Tests extended
  (`TestP6Portuguese`, 38/38). Harness parameterized per language
  (`--lang`/`--corpus`/`--results`/`--no-preproc`), fr remaining in
  `results/`. Details: `AUDIT_V1V2/P6_MULTILINGUE.md`.


### Added (V1V2 agent instructions — 2026-10-31, after the fix)

- **docs(mission): P5/P6 — new instructions for the fixing agent.**
  **P5 (MISSION §6)**: definitive decommissioning of the changes that
  became unnecessary — the g2p/prosody workarounds (`dea71c6`,
  `f62f185`) must never be re-applied (the P3 re-inversion clause is
  cancelled); the removal is final, superseded by fix `304f04c`.
  **P6 (MISSION §7)**: extending the fix to the pack's other
  languages (de, en, es, it, pt) — Portuguese first (corpus
  `corpus_v1v2_pt.json` on the fr typology, harness parameterized per
  language), inertness proof for es/it/de/en, `phonemes.py` inventory
  covering the nasal keys of every language. Added the self-contained
  tutorial HTML `correction_V1V2_avant_apres.html` (20 before/after
  examples, embedded audio). See `AUDIT_V1V2/MISSION.md` §6-§7.

### Added (V1V2 engine fix — 2026-10-31)

- **fix(engine): nasal/oral toggle across linked V1V2 hiatus via an
  orthogonal velar-port layer (nasal_preproc)** — syltraj's parametric
  elaboration is left untouched: hiatus-member nasal vowels are oralized
  in the motor chain by a new preprocessing gate
  (`vtl_synth/core/nasal_preproc.py`), so the background arc carries the
  base diphthong transition on oral targets, and nasality is re-injected
  downstream in the existing orthogonal VO control space (target 0.5,
  20% ramps) shaped by the existing 20 ms velar timer
  (build_phrase_tract step 3b-bis). Surgical scope: held nasal vowels
  keep the working plateau path; tokenizer round-trip verified with a
  conservative fallback (original chain, warning) so the gate can never
  produce an unexpected chain. Results (AUDIT_V1V2, 20 items): nasal
  halves reach VO 0.49-0.50 (healthy plateau reference), the audit's
  byte-identity `ta.ata ≡ ta~.ata ≡ ta.a~ta ≡ ta~.a~ta` is broken into
  4 distinct outputs, the 5 control items are bit-identical, and only
  the VO column of the .tract changes for the 15 corrected items.
  33 new unit tests (tests/test_nasal_preproc.py). See
  `AUDIT_V1V2/IMPLEMENTATION_V1V2.md`.

### Reverted (audit V1V2 — 2026-10-31)

- **revert(audit): remove the g2p-fr / prosody nasal-boundary workaround
  (commits `dea71c6` + `f62f185`)** — these two commits masked an engine
  defect instead of fixing it: the syltraj walk cannot articulate the
  nasal/oral toggle across a linked `V~.V` boundary and silently reduces
  the pair to an unlabeled background block (nasality lost, both vowel
  nuclei lost). The workaround (short pause after any word ending on a
  nasal vowel) is removed so that the engine defect is observable again,
  in view of fixing the walk itself. See `AUDIT_V1V2/` (audit report +
  reproduction harness) shipped with this clone.

### Fixed
- **fix(lang-pack): refresh the stale integration pipeline.py** —
  `lang_pack/integration/pipeline.py` shipped a pre-sampa_guard revision
  of the engine pipeline, and every `setup_lang.py install` copies it over
  `vtl_synth/core/pipeline.py` (PATCHED_FILES, backed up as `.bak`),
  silently regressing the engine: the console bridge and the CLI pass
  `sampa_guard=...`, which the stale pipeline rejects (TypeError). The
  integration copy is now the current v1.1.0 pipeline (expressive v1.1.0 +
  sampa_guard); installs no longer regress.
- **chore(lang): sync the installed `vtl_synth/utils/` copies with
  `lang_pack/profiles`** — the committed utils copies were a stale
  snapshot; installs now leave no spurious dirty state.

### Changed
- **fix(syltraj): preserve the pending anchor point across consecutive pause
  nodes (audit D-11)** — pause arcs now depart from the preceding vowel
  (paper §2.2 pause-diphthong V_e → V_o); max inter-step jump on `bi |`
  reduced from 0.908 to 0.106 VTL units; `bi |` and `bi | ba` are the only
  affected corpus sequences (90/92 corpus notations byte-identical; the
  console splits phrases on `|` and is unaffected).

### Added
- **Interactive HTML demos** (`docs/html/`): self-contained pages
  (no server or network, opened directly via `file://`) generated by
  `python docs/html/make_html_demos.py` — `index.html` + one page
  per phrase (`polar_demo_fr.html` "ba.da.ga",
  `polar_demo_en.html` "this is easy for us", same parameters as the
  MP4 demo). Each page embeds its data (`.polar` v4 trajectories at
  100 Hz, VTL sagittal SVG frames at 25 Hz, AAC audio as data URI)
  and renders on canvas the interactive counterpart of the
  dual-panel MP4: sagittal view, two-branch polar figure (rendering
  identical to `render_polar_frame` — K=30/ν=+1 vocalic,
  K=10/ν=−1 consonantal, 300 ms fading trail, transient phonemic
  labels, inventory), ρ/θ traces with phonemic bands, and full
  transport (play/pause, scrub, speed 0.25×–1×, loop, keyboard).
  Verified: geometric equivalence of the polar figures with the
  manual figures (`fig_frame_b`, `fig_frame_da`), exact round-trip
  from embedded data to pipeline outputs, no console errors.
  Repository assets only: never installed by pip (excluded from the
  wheel and sdist — pyproject `vtl_synth*` allowlist + MANIFEST.in
  `prune examples`, verified on built distributions).

### Changed
- **Polar video trail default raised to 300 ms**: the fading trail of
  each branch (red vocalic / blue consonantal) goes from
  $\approx$ 0.75 s to $\approx$ 0.30 s (`_TRAIL_S`) to shorten the
  visual afterglow — past trajectories fade faster and no longer
  mask brief gestures (clusters, views close to figure 4 of the
  paper). Display-only change: engine, `.tract`, audio, `.polar`
  format and branch geometry unchanged. **Polar manual figures
  regenerated** (`fig_branches_full`, `fig_frame_b`, `fig_frame_da` +
  demo `examples/polar_demo_en.mp4`): they dated from v1.1.0 and
  still showed the pre-fix geometry (symmetric lenses instead of the
  arcplot teardrops, vocalic branch diving toward the origin at the
  edges, dental /d/ angle at the pre-recalibration 23π/16); they now
  show the current v4 rendering (teardrops, periphery, 300 ms
  trail) and the captions are aligned
  (`docs/polar_visualization.tex` + recompiled PDF).
- **US English translation of the remaining comments, docstrings and
  displays**: core user-facing messages (active speaker announcement
  `describe()`/`announce()`, expressive prosody fallbacks in
  `Pipeline`, TSV warning of the lexicon loader, outputs of the
  vowel calibrator and its CLI), docstrings and comments of the
  multilingual g2p (de/es/it/pt + legacy fr) and of the common
  loader, COVTL calibration notes of the DVTD speakers
  (s1/s2/m01/w02 — `jd3_constants.py` deliberately untouched: its
  hash is doubly pinned (registry + test prefix) and already the
  subject of the known upstream inconsistency); `registry.json`
  limited to the mechanical refresh of the corresponding 4
  `constants_sha256`. Display-only change, proven by AST equality
  (normalized strings) on the 18 modified files; test suite
  unchanged (152 passed + identical jd3 upstream failure).
  Legitimately untranslated data: lexicons and g2p dictionaries,
  IPA symbols, native language names, legacy French dictionary
  entries annotated in French phonetic terminology.

### Documentation
- **Documentation aligned with the single trajectory path**:
  `docs/manual.tex` (and recompiled `manual.pdf`) — the "The legacy
  engine" section still described the old superposition-graph
  executor (`execute_superposition_segment`, explicit
  CV/CVC/CCV graphs); it now describes the actual chain
  (`gesture.py` nodes/anchors + `trajectory.py` block builder, fixed
  timing T_cons=T_voy=160 ms, not parameterizable); the "Key
  features" bullet wrongly claimed that a "legacy superposition-graph
  engine" remained selectable. `docs/ARCHITECTURE.md` —
  `core/trajectory*.py` → `core/trajectory.py` (B(t) and engine
  table), core/ tree raised to 28 modules (addition of
  `orthogonal_params.py`, `sampa_guard.py`, `speaker_registry.py`),
  test counter 111 → 153 with mention of the single-trajectory-path
  guards, clarification that `syltraj` embeds its own block builder.
  Stale code comments revised (`polar.py` ×2, `types.py`,
  `polar_video.py`: no active reference to `trajectory_legacy`
  left).

### Removed
- **Removal of the dual trajectory engine (trajectory_legacy)**: the
  superposition-graph engine `vtl_synth/core/trajectory_legacy.py`
  (1025 lines) and its cluster of dead executors in
  `continuous.py` (`_execute_syllable_element`, `_execute_*_diphthong*`,
  `_build_{cv,cccv,ccvc,cvc_extended}_graph`, `_build_transition_arc`,
  `_generate_pause` — 1189 lines) were removed. These functions were
  called by no production or test path (the active engine is
  `syltraj` via `engine='syl'` by default; the deprecated alignment
  path `engine='legacy'` already uses `trajectory.py`). Production
  synthesis now follows a single algorithmic path, proven by the
  guard `tests/test_single_trajectory_path.py` (module not
  importable, AST scan of imports, default engine = syltraj,
  deprecated path = trajectory.py). Default numeric outputs
  **bit-identical** on the reference corpus
  (16/16 `test_regression_baselines.py` unchanged).

### Fixed
- **Polar display teardrop**: the consonantal sub-arcs (blue branch)
  were drawn with the ν/K phase carried by the *arrival* point
  (`polar.polar_arc`) — on a V→C approach leg that point is the
  large-radius consonant, so the bulge occurred on the consonant
  side and a closed V→C→V loop rendered like a symmetric lens
  instead of the "teardrop" of the paper's planning figures
  (arXiv:2307.02299, Fig. 4). `polar_video.py` now draws the blue
  sub-arcs in the original *arcplot* anchor of Syllable_Synthesis
  (`_z_leg_arcplot`: phase carrier = the shortest-radius endpoint,
  ρ = cos(θ/2), first sample dropped; cf. the counterpart fix of
  big.bi-supplement): belly measured at 0.34–0.36 of the chord from
  the vowel (reference: 0.35), exact taper toward the consonantal
  target. `.polar` format bumped 3 → 4 (trajectory geometry
  changed); red branch unchanged; no engine test covers the
  rendering, validation is metric + visual (16/16 on
  `-k "video or pipeline or cli or polar"`).
- **BUG-001 (critical, external audit 09/25)**: `setup_lang.py` broke
  `constants.py` on a fresh clone — the old "rich" LANG SECTION
  (v1.1.0) contains the `VOWEL_TARGETS`; replacing them with the
  marker alone removed the definition and the `vtl_synth` import
  failed (`NameError`). The migration now extracts the vowel region
  from the old section and rewrites it after the marker.
- **BUG-002 (major)**: `install_speaker.py` — editable-pointer guard
  made portable (OS-neutral message, POSIX paths preserved).
- **BUG-009 (minor)**: `setup_lang.py restore` now invalidates the
  `__pycache__` (stale ACTIVE_LANG).
- **BUG-011 (minor)**: CLI default `-s/--speaker` = `jd3` (lowercase,
  consistent with the registry).
### Added
- **SAMPA guard (CORRECTIONS v2.1 s.2, engine fix)**: the parsers
  (`continuous.parse_ipa_with_markers`, `parsing._tokenize_word`,
  `syltraj.tokenize_phrase`) silently dropped unknown symbols
  (e.g. `klincan`: `c` is not an engine key and vanished without any
  diagnosis). New guard at the public frontiers
  (`vtl_synth/core/sampa_guard.py`): `build_phrase_tract`,
  `parse_to_segments`, `parse_input`, `build_phrase_pval`,
  `Pipeline.run`/`text_to_wav` and CLI `--sampa-guard {warn,error,off}`
  (+ environment variable `VTL_SAMPA_GUARD`). Default `warn`:
  `UnknownSegmentWarning` warning listing symbols and positions,
  bit-identical outputs; `error`: `SampaGuardError` before synthesis;
  `off`: previous behavior. Tests: `tests/test_sampa_guard.py`
  (bitwise neutrality included). One diagnosis per synthesis
  (internal 'off' plumbing).
- **g2p fixes (CORRECTIONS v2.1, de/pt synthesis leaks, 2026-10-23)**:
  two PRE-EXISTING leaks revealed by the SAMPA guard (which itself
  changed no output) — (a) g2p-de: the Wikipron lexicon (table
  `_DE_IPA_TO_KEYS`) and the exceptions emitted the keys
  `I`/`U`/`Y` (lax ɪ/ʊ/ʏ), absent from the engine inventory: vowels
  silently dropped ("Butter" -> /bt@/, "Mütter" -> /mt@/,
  "ist" -> /st/); now mapped to i/u/y (documented lax->tense
  approximation, consistent with "ö/ü always tense"); (b) g2p-pt:
  "qu" not covered by que/qui/qua/quo leaked `q` ("quente" ->
  /@~t@/); a "qu" -> "k" fallback rule added. en/fr/es/it outputs
  unchanged (non-regression tests); `lang_pack/profiles` mirrors
  synchronized. Tests: `tests/test_g2p_leaks.py`.
- **Expressive prosody option** (v1.0.8 — default OFF, outputs
  bit-identical to the monotone mode; carried over from
  covtl-languages into the multi-speakers branch, compatible with
  speaker switching): `Pipeline(expressive=True)` / CLI
  `--expressive` (banner "prosody: expressive") adds (a) *syntactic
  breathing* — lexical chunking into breath groups
  (`vtl_synth/utils/chunking.py`, function-word dictionaries for the
  6 languages, balanced hard limit of 5 words, unbreakable
  connectors "parce que"/"so that"/…) and a 130 ms breath pause `%`
  in the syl engine (`syltraj` `T_pause_breath`, bit-identical
  without the marker); (b) the *sculpted F0 contour*
  (`vtl_synth/utils/prosody_f0.py`): kept declination + per-block
  onset reset + pitch accents (asymmetric Gaussian bump, per-language
  amplitude 0.16-0.24 × f0_base, German downstep) + terminal nuclear
  fall per language (Jun 2005/2014, Ladd 2008; Pierrehumbert 1980 /
  Jun & Fougeron 2002 / Face 2003 / Grice et al. 2005 / Avesani 1995 /
  Frota 2000, cf. setlang.py). Lexical stress travels OUT OF BAND
  (never in the SAMPA): `lexicon_loader.ipa_to_keys_stress` keeps
  Wikipron ˈ/ˌ (`stress_for` channel), CMUdict digits for English,
  fallback orthographic rules es/it/pt/de. Acts only on the glottis
  f0 column and the pause durations — never on the tract (the
  speaker mechanics — per-speaker f0, register, .polar — is
  unchanged; the expressive contour's `f0_base` = the active f0,
  whatever the speaker). Per-language `ExpressivityProfile` carried
  by `LangProfile.expressivity`. Demos:
  `python examples/demo_prosody.py`; measurements:
  `python scripts/f0_report.py <tract...>`. Tests:
  `tests/test_expressive.py` (off bit-identity, per-language
  chunking, stress, measurable accents, smoothness, nuclear fall).
  `lang_pack/profiles/` enriched (`chunking.py`, `prosody_f0.py`;
  `setlang.py`, `lexicon_loader.py`, `integration/pipeline.py`
  synchronized; `setup_lang.LANG_MODULES` → 13 modules).
- **`docs/expressive_prosody.tex/.pdf`**: tutorial guide
  (US English, pure pdflatex, transportable) — quick start,
  syntactic breathing, F0 contour, out-of-band stress, measurements
  (`f0_report`), tests, limitations, and a detailed chapter on the
  interaction with the multi-speakers installation
  (registry, LANG SECTION transport, JD3 guard,
  language-first/speaker-first workflows, guarantees matrix).
- **`PROVENANCE_PROSODY_CHUNKING.md` / `.json`**: provenance report
  for the `chunking.py` / `prosody_f0.py` modules — original project
  implementation (specification of 2026-09-15, human-led session
  **assisted by AI**; no third-party software source found;
  scientific references = parameter sources, no code); public
  history: commit `e991ff9` (v1.1.0, 2026-09-17). Regularization
  actions applied: Wikipron notice (CC BY-SA 3.0) in
  `THIRD_PARTY_NOTICES.md`, specification archived in `docs/`.

### Changed
- **Vowel triangle of the 4 production speakers** (v1.2.0):
  CO_VTL matrices recalibrated at the parametric level (port of the
  jd3 gesture repertoire: c1_jd3, s_L·c0_jd3, c2_jd3 — s1 complete;
  s2 hybrid jd3 lips + tongue ×1.2; m01 kept after in-situ
  arbitration; w02 unchanged), jd3-referenced vowel targets re-fit
  per speaker, `SYL_THETA_DENTAL` fix 23π/16 → 3π/2 (270° — the
  d/t apical closure was open in all speakers, jd3 included:
  13/18 → 18/18 occlusives realized). a-i-u triangles:
  s1 4 → 70 %, s2 11 → 44 % of the jd3 area; registry and 5
  baselines regenerated.
- **Language pack: the LANG SECTION is a bare marker** (D24
  resolution): `setup_lang.py` no longer writes vowel targets —
  `VOWEL_TARGETS`/`VOWEL_EFFORT_GAIN` remain the property of the
  active speaker; `_ensure_jd3` becomes a no-op,
  `calibrate`/`--calibrate` deprecated, `install_speaker.py`
  transports the marker without touching the native region;
  canonical hash neutralizing section and region
  (`speaker_registry`).
### Changed
- **Polar video v3 — dissociated vocalic/consonantal branches**: the
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
  exactly on the consonant node targets. Each branch has its own
  fading trail (~0.75 s) and current position; inventory dots,
  orientation (θ=0 East, CCW), transient labels and the sagittal
  panel are unchanged. `.polar` format **version 3**: two 100 Hz
  trajectories `vocalic` / `consonantal` (null while a branch is
  inactive) + phoneme timing as before; v2 files remain readable by
  `read_polar`. `polar_from_pval` is kept as a diagnostic only.
  Demos regenerated: `out/polar_demo_en.mp4` ("this is easy for us",
  en/JD3, dissociation visible on /z/, /f/, /R/) and
  `out/polar_e2e.mp4` ("ba.da.ga").
- **Polar video fix — stale work-dir frames**: the dual-panel encoder
  silently appended leftover `frame_*.png` from a previous LONGER
  render in the persistent `temp_video` work directory (observed: a
  `polar_e2e.mp4` 0.64 s longer than its audio, ending with frames of
  an earlier "this is easy for us" render). `make_polar_video` now
  purges `frame_*.png` in the sagittal/polar/compo work
  subdirectories before rendering and verifies the composed frame
  count before encoding; the log reports the actual encoded count.
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
  /6/ 0.04 → 1.04; all ≥ 0.59), humps reduced. Baselines regenerated;
  previous constants in `data/speakers/sauvegarde/`.
- **Fine calibration v2 of s1/s2 (`s1_constants.py`, `s2_constants.py`)**:
  redone with `scripts/calibrate_fine_v2.py` implementing the D15
  corrections from the DVTD transfer report (covtl-speaker). Occlusive
  targets now come from a 2D (ρ, θ) area-function cost centered on the
  canonical JD3 place angle (exact closure + place margin when it exists,
  documented compromise otherwise — closure is not reachable on every
  vowel background for these anatomies); fricative gap windows are
  rescaled by s_L² (subglottal length ratio: s1 1.179, s2 0.887). New
  baseline files `regression_baselines_s1/s2.json`; reports under
  `out/fine/<spk>_fine_v2/`. Previous constants kept in
  `data/speakers/sauvegarde/*_pre_v2.py`.

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
