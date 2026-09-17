# Architecture — covtl-pipeline (`vtl_synth`)

This document describes the architecture of the synthesis engine: the
package layout, the data flow from text to audio/video, and the three
contributions that build every 400 Hz tract frame. The full user-facing
documentation is `docs/manual.pdf` (source: `docs/manual.tex`); this
file is the developer-oriented map.

## 1. Global model

Every synthesized frame is the sum of three contributions:

```
VTL(t) = B(t) + E_source(t) + E_ortho(t)
```

| Term | Content | Parameters | Main modules |
|---|---|---|---|
| `B(t)` | **Berthommier polar core** — phonetic targets in polar coordinates (rho, theta), arcs, superposition | 15 COVTL tract params | `core/polar.py`, `core/projection.py`, `core/syltraj.py`, `core/trajectory*.py` |
| `E_source(t)` | tag-driven extension: amplitude envelope E, voicing V, velum VO/VS, glottis trajectory (11 params), F0 | VO (1) + 11 glottis | `core/tag_system.py`, `core/amplitude_envelope.py`, `core/enveloppe.py`, `core/glottal_source.py`, `core/pulmonary_effort.py`, `core/timers.py`, `core/prosody_source.py` |
| `E_ortho(t)` | orthogonal branch: TS3 tongue-side shape + speaker-derived VS | TS3 (additive), VS (priority) | `core/orthogonal_params.py`, `core/speaker_jd.py` |

The assembly into VTL frames is `core/assemble_tract.py`
(`AssembleTract`), orchestrated phrase by phrase by
`core/build_phrase_tract.py` and end-to-end by `core/pipeline.py`
(`Pipeline`).

## 2. Package layout

```
vtl_synth/
├── __init__.py            public API (Pipeline, PipelineResult, ...)
├── core/                  the synthesis engine (26 modules)
│   ├── pipeline.py        Pipeline orchestrator: run / text_to_wav,
│   │                      F0 declination, WAV writing, video dispatch
│   ├── build_phrase_tract.py  7-step per-phrase assembly (B + E + ortho)
│   ├── assemble_tract.py  AssembleTract: 15->19 scattering, glottis,
│   │                      downstream corrections, 100->400 Hz up-sampling,
│   │                      .tract writer
│   ├── synth.py           VocalTractLab bindings (audio, SVG, analysis)
│   ├── text_to_tract.py   older single-phrase path (legacy chain)
│   ├── notation.py        Unicode/IPA normalization gateway
│   ├── parsing.py         longest-match tokenizer, phrase/syllable parse
│   ├── phonology.py       cluster rules (legacy), ART1 selectors
│   ├── phonemes.py        ARPAbet->SAMPA mapping, syllabification,
│   │                      SAMPA token tests
│   ├── constants.py       single source of constants: rates, CO_VTL
│   │                      coefficients, VOWEL_TARGETS, CONSONANT_TARGETS,
│   │                      parameter names, glottis presets
│   ├── polar.py           compute_P / arc_B / polar_arc (polar model)
│   ├── projection.py      COVTL projection, superposition, target
│   │                      resolution (voiceless->voiced, g_vel/g_pal,
│   │                      z_front)
│   ├── syltraj.py         ACTIVE syllabic trajectory engine ('syl')
│   ├── trajectory.py      refactored block builder (legacy chain)
│   ├── trajectory_legacy.py  superposition-graph engine (legacy)
│   ├── continuous.py      legacy continuous chain (tokens, syllabification,
│   │                      CV/CVC/CCV executors)
│   ├── gesture.py         gesture nodes and anchors (legacy chain)
│   ├── tag_system.py      three-level tag architecture (A/B/C)
│   ├── amplitude_envelope.py  token-based effort envelope E(t)
│   ├── enveloppe.py       TimedEnvelope + FeatureTimer (voicing, velum,
│   │                      F0, aspiration events indexed by anchors)
│   ├── glottal_source.py  glottis trajectory (presets, smoothing,
│   │                      pressure, pre-voicing)
│   ├── pulmonary_effort.py  subglottal pressure / relaxation coupling
│   ├── prosody_source.py  segment/syllable prosody structures
│   ├── timers.py          tau constants for nasality/laterality/voicing
│   ├── types.py           shared dataclasses (PolarTarget, ...)
│   └── speaker_jd.py      JD3.speaker XML parser (shapes, presets,
│                          orthogonal targets)
├── cli/main.py            vtl-synth entry point (run, text-to-wav,
│                          tract-to-mp4, inspect, plot-tract)
├── vtl/api.py             VocalTractLab API facade (re-exports core/synth)
├── video/
│   ├── renderer.py        read_tract, SVG->PNG frame rasterizer
│   ├── encoder.py         MP4 H.264/AAC via bundled ffmpeg
│   ├── polar_video.py     .polar builder + dual-panel polar MP4 (v1.1.0)
│   └── tract_figure.py    plot-tract per-parameter figure
├── utils/                 g2p (CMUdict) + language-pack modules
│                          (setlang, g2p_xx, lexicon_loader, chunking,
│                          prosody_f0, … — installed by setup_lang.py)
└── data/
    ├── vtl_binaries/
    │   └── JD3.speaker    speaker file (legacy fallback, package data)
    ├── speakers/          v1.1.0 multi-speakers registry: registry.json,
    │                      ACTIVE_SPEAKER marker, {jd3,s1,s2,m01,w02}.speaker
    │                      + *_constants.py (see §8)
    └── xx_lexicon.tsv     installed Wikipron lexicons (language pack)
```

## 3. Data flow (text -> .tract -> .wav -> .mp4)

```
raw text
  │  g2p (CMUdict, ARPAbet -> engine SAMPA, onset-maximization
  │  syllabification, words joined with '.' inside a phrase)
  ▼
engine SAMPA (e.g. Dis.iz.i.zi.fOR.@s)      [or --phonetic input]
  │  parse & normalize (notation.py, parsing.py), split on '|'
  ▼
per phrase: build_phrase_tract(...)
  ├─ B(t):   syltraj.build_phrase_pval — anchors, clusters, pauses
  │          (100 Hz gesture steps; t_cons=100 ms, t_voy=80 ms,
  │          pauses 200/320 ms by default)
  ├─ E(t):   amplitude_envelope (10 kHz -> 100 Hz) + TimedEnvelope
  │          events (voicing, VOT, velum, F0) + glottal_source
  ├─ ortho:  orthogonal_params (TS3 context map from JD3.speaker)
  └─ assemble_tract.assemble: 15 COVTL -> 19 VTL params (VS@6, VO@7,
             TS3 additive, TRX/TRY auto), glottis block, corrections,
             linear up-sampling 100 -> 400 Hz
  ▼
.tract file (400 Hz, 19 + 11 columns, header '# sample_rate: 400')
  │  apply_f0_declination (per-phrase, +3% onset / -15% final)
  │  synthesize_audio (vocaltractlab-cython, JD3, 110 samples/state)
  ▼
.wav (44 100 Hz, PCM 16-bit, peak-normalized to 0.9)
  │  video/renderer (SVG frames -> PNG, decimation 400/25) + encoder
  ▼
.mp4 (H.264 yuv420p + AAC, 960x840 @ 25 fps by default)
```

## 4. Sampling rates

| Rate | Value | Domain |
|---|---|---|
| Gesture/model | 100 Hz (1 step = 10 ms) | polar trajectory, envelopes |
| Envelope compute | 10 kHz, block-averaged to 100 Hz | effort envelope |
| Tract sequence | 400 Hz (`.tract`) | articulatory frames (2.5 ms hop) |
| Audio | 44 100 Hz (`.wav`) | 110 samples per tract state |
| Video | 25 fps (default) | every 16th tract frame |

## 5. The polar model in one page

- Every phoneme is a target `z = rho * exp(i*theta)`. Vowels live inside
  the unit circle (`rho <= 1`, anchors/plateaus); consonant closures
  beyond it (`rho` 1.0-1.45). Anchors: /a/ = 180 deg, /i/ = 300 deg,
  /u/ = 60 deg; schwa @ = centroid of the a-i-u triangle.
- Static projection (`polar.compute_P`):
  `P[p] = c1[p] + rho * c0[p] * cos(c2[p] - theta)` with the per-parameter
  coefficient table `CO_VTL` (see `constants.py`; documented calibration
  shifts for LD, TCY, TTY).
- Transition arcs (`polar.arc_B`): asymmetric S-curve blend
  `rk = cos(theta/2)**Pexp` over a half-turn sweep; the arrival term
  carries a phase offset `-(nu/K)*theta` that curves the path in the
  plane. Reference branches: `K_c = 10` (consonantal), `K_v = 30`
  (vocalic); the active `syl` engine runs `nu = -1`, `K = 1000`
  (quasi-straight).
- Consonant targets carry a **selector**: the list of parameters the
  consonant commands. Coarticulation is the **superposition** of the
  vocalic background arc (all non-selected parameters) with the
  consonantal excursion (selected parameters only) — lightened selectors
  (labials/fricatives without tongue params) let the tongue follow the
  vowel.
- The `syl` engine walks vowel anchors and emits typed blocks (plateau,
  background, cluster, pause, decay/attack, terminals); a cluster of m
  consonants is (m+1) sub-arcs of `T_cons` steps with per-parameter
  endpoint scoping (C0 continuity at boundaries). VV transitions that
  would close the tract are routed through the schwa (probe threshold
  0.18 cm^2).

## 6. The source model in one page

- Tags (phonetic A / articulatory B / control C) are compiled to JD3
  glottis presets at run time — no hard-coded VTL values.
- The effort envelope E(t) is built from a token reduction of the phrase
  (V/C/R/N/L/O/F/y) with raised-cosine transitions, then indexed on the
  block schedule; the source has **no timing of its own** — it inherits
  the coarticulation of B(t).
- Voicing V(t) is built per syllable from (V_o, V, V_e) triplets with
  place-dependent VOT (20-60 ms); nasality is the velum VO with a 20 ms
  carry-over; the glottis interpolates between JD3 presets, smoothed by a
  12 ms second-order Butterworth; pressure follows
  `P = P_min + min(E,1.5)^1.2 * (P_max - P_min)` (8 000 dPa max); F0 =
  102.216 Hz base + per-phrase declination (+3 %/-15 %) + micro-prosody
  (10 Hz per unit E).

## 7. Engines and compatibility

| Engine | Flag | Status | Modules |
|---|---|---|---|
| `syl` | `--engine syl` (default) | active | `syltraj.py` |
| `legacy` | `--engine legacy` | deprecated (DeprecationWarning, kept for non-regression) | `continuous.py`, `trajectory*.py`, `gesture.py`, `phonology.py` |

The VTL backend is the `vocaltractlab-cython` wheel (VocalTractLab 2.4,
Paul Krug's Cython binding); `vtl_synth.vtl.api` re-exports the facade
from `core/synth.py`. There is **no `.seg`/`.ges` stage** — unlike the
[vtl-pipeline](https://github.com/FBerthommier/vtl-pipeline) reference
repository, the tract sequence is synthesized directly by the COVTL
model (see manual, "Differences with the vtl-pipeline reference
repository").

## 8. v1.1.0 add-ons

### 8.1 Multi-speakers registry (add-on 1)

`core/speaker_registry.py` is the single source of truth; the registry
data ships as package data in `data/speakers/`:

| file | status |
|---|---|
| `jd3.speaker`, `jd3_constants.py` | reference (SynthVTL24b original; hash `75ae0ba837ed106d…`) |
| `s1.speaker`, `s2.speaker` | built from DVTD MRI (subject anatomies) |
| `s1_constants.py`, `s2_constants.py` | calibrated v3 (D15: 2D (ρ,θ) area-function occlusives, native TTY + apical bonus, multi-criteria `@`) |
| `m01.speaker`, `w02.speaker` | retouched from the official **VTL 2.4 ZIP** speaker files (pure option A + 2025→11-code glottal mapping, index 7 = PS) |
| `m01_constants.py`, `w02_constants.py` | native targets adapted to the mapping |
| `registry.json` | entries: speaker/constants file names, f0_default, SHA-256 hashes, `_meta.wheel_default_sha256` |

Three layers are driven by the active speaker (`ACTIVE_SPEAKER`
marker; **default jd3** when absent):

```
install_speaker.py install <name>
  ├─ geometry/glottis/f0 : core/constants.py  <- bit-exact copy of the
  │                        registry *_constants.py (LANG SECTION carried)
  ├─ orthogonal branch   : ACTIVE_SPEAKER marker -> speaker_registry
  │                        .active_speaker_file() resolved at EACH call
  │                        by speaker_jd.py / build_phrase_tract.py
  │                        (vtl_binaries/JD3.speaker never touched)
  └─ audio + SVG/video   : shared wheel resource site-packages/
                           vocaltractlab_cython/resources/JD3.speaker
                           (swapped with backup; effective in the NEXT
                           process — the DLL loads it at import; wheel
                           0.0.13 exposes no vtlInitialize/vtlClose)
```

`install_speaker.py` (`list|install|restore|status`) journals and
backs up into `.speaker_backups/` (first use), verifies hashes,
smoke-tests each install in a fresh subprocess and rolls back on
error. Per-speaker baselines: `regression_baselines_<name>.json`
(jd3 uses the reference `regression_baselines.json`);
`scripts/regen_baselines.py` regenerates the file of the active
speaker, `scripts/calibrate_fine_v2.py` is the s1/s2 calibration tool.

### 8.2 Language pack (add-on 2)

`setup_lang.py` + `lang_pack/` install a managed **LANG SECTION**
between the markers `# === LANG SECTION — BEGIN/END` over the native
`VOWEL_TARGETS..VOWEL_EFFORT_GAIN` block of `constants.py`
(`ACTIVE_LANG` recorded inside). The two installers are independent:
a speaker swap **carries** the section over the new constants, a
language switch re-edits it in place; coherence is checked on a
**canonical form** of the constants (vowel/lang region neutralized —
`speaker_registry.canonical_constants_text`). Installed modules are
tracked by `vtl_synth/utils/.lang_pack_manifest`, lexicons by
`vtl_synth/data/.lang_pack_data_manifest`; `setup_lang.py restore`
undoes everything.

**JD3-only calibration guard-rail**: the pack vowel targets are
calibrated in situ on JD3. `setup_lang.py::_ensure_jd3()` runs before
every `calibrate` / `install --calibrate`: if another speaker is
active it says so and reinstalls jd3 (constants + marker + wheel)
first — the recalibration can therefore never target s1/s2/m01/w02,
which keep their native vowel targets; `report_current`/`status` flag
a non-jd3 speaker + active language as « HYPOTHÈSE » (unverified
combination).

### 8.3 Expressive prosody (add-on 3)

`Pipeline(expressive=True)` / `--expressive`, default **OFF** with
bit-identical outputs. Two additions: syntactic breathing groups
(`utils/chunking.py`, per-language function-word dictionaries, 5-word
hard balance, 130 ms `%` breath pause in `syltraj`) and a sculpted F0
contour (`utils/prosody_f0.py`, per-language `ExpressivityProfile`
carried by `LangProfile`): declination + block re-attacks + pitch
accents (asymmetric gaussian bumps) + nuclear falls; lexical stress
travels **out-of-band** (`lexicon_loader.ipa_to_keys_stress`, never in
the SAMPA). Only the glottis f0 column and pause durations change —
never the tract. Full guide: `docs/expressive_prosody.pdf`.

### 8.4 Polar visualization (add-on 4)

`--polar` builds a `.polar` intermediate (100 Hz, **format v3**: two
dissociated trajectories `vocalic`/`consonantal` + phoneme timing;
v2 files stay readable) then renders the dual-panel MP4
(sagittal | polar) at 25 Hz — red vocalic branch, blue consonantal
branch, each with a fading trail. The branches are rebuilt from the
anchor pairs / consonant node targets recorded while the syl engine's
block helpers are monkeypatched during the build (the blended Pval
frames are off-manifold inside clusters — v2's single zigzag path is
kept only as the `polar_from_pval` diagnostic). The work directory is
purged and the frame count verified before encoding (stale-frame fix).
Module: `video/polar_video.py`; doc: `docs/polar_visualization.pdf`.

## 9. Extension points

- **New phoneme**: add `(rho, theta, selector)` to
  `CONSONANT_TARGETS` / `VOWEL_TARGETS` in `core/constants.py`
  (tokenizers pick it up from `ALL_PHONEME_KEYS`).
- **Timing**: `--tcons/--tvoy/--tpause/--tpause-long` (CLI) map to
  `Pipeline` arguments; block schedule in `syltraj.py`.
- **Speaker**: the active speaker comes from the registry
  (`data/speakers/`, §8.1); `*_constants.py` is a data problem, not a
  code change — add the files + a `registry.json` entry, then
  `python install_speaker.py install <name>`. `JD3.speaker` (legacy
  fallback) is parsed by `speaker_jd.py` exactly as before.
- **Language**: add a profile in `lang_pack/profiles/` + a vowel block
  in `lang_pack/lang_blocks/blocks.py`, then
  `python setup_lang.py install --lang <xx>` (calibration: JD3 only,
  §8.2).
- **Tests**: lightweight pytest suite (111 tests) in `tests/`,
  including end-to-end non-regression against the per-speaker
  `regression_baselines*.json`.

See also `docs/CONVENTIONS.md` (naming, physical notation) and
`docs/manual.pdf` (user manual with the full model description).
