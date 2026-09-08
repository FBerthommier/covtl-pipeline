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
│   └── tract_figure.py    plot-tract per-parameter figure
├── utils/g2p.py           English g2p (CMUdict -> connected SAMPA)
└── data/vtl_binaries/
    └── JD3.speaker        speaker file (package data)
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

## 8. Extension points

- **New phoneme**: add `(rho, theta, selector)` to
  `CONSONANT_TARGETS` / `VOWEL_TARGETS` in `core/constants.py`
  (tokenizers pick it up from `ALL_PHONEME_KEYS`).
- **Timing**: `--tcons/--tvoy/--tpause/--tpause-long` (CLI) map to
  `Pipeline` arguments; block schedule in `syltraj.py`.
- **Speaker**: `JD3.speaker` is parsed by `speaker_jd.py`; presets and
  orthogonal context maps come from the speaker file (JD2/JD3
  recalibration is a data problem, not a code change).
- **Tests**: 55 pytest tests in `tests/`, including end-to-end
  non-regression against `regression_baselines.json`.

See also `docs/CONVENTIONS.md` (naming, physical notation) and
`docs/manual.pdf` (user manual with the full model description).
