# vtl-synth — articulatory synthesis from text (COVTL + VocalTractLab)

Version 1.1.0 adds a **multi-speaker registry**, a **6-language pack**
(de/en/es/fr/it/pt), **expressive prosody** and the **polar-coordinate
video** — with the default engine outputs unchanged (bit-identical
baselines).

`vtl-synth` turns English text (or phonetic input) into:

- a **`.tract`** file — the 400 Hz sequence of 19 tract + 11 glottis
  VocalTractLab parameters,
- a **`.wav`** waveform (44.1 kHz, synthesized by VocalTractLab 2.4),
- a **`.mp4`** video of the **sagittal cross-section** of the vocal
  tract, synchronized with the audio — and, with `--polar`, a
  **dual-panel video** adding the live (ρ, θ) **polar plane** (vocalic
  branch in red, consonantal in blue).

The synthesis engine is the **Berthommier articulatory model (COVTL)**:
place of articulation is computed in polar coordinates (ρ, θ) with
coarticulation, then projected onto the VocalTractLab parameters; a
tag-based extension engine drives voicing, nasality, laterality,
glottal effort and F0 (timed envelopes indexed by the segment events);
a syllabic trajectory engine (syltraj) shapes the
consonant/vowel arcs, inter-word pauses and phrase-final holds.

The package layout follows the
[vtl-pipeline](https://github.com/FBerthommier/vtl-pipeline)
reference repository (CLI, package data, video encoder, g2p).

Repository: <https://github.com/fberthommier/covtl-pipeline>

## Documentation

- **Documentation index** — [docs/README.md](docs/README.md): the five
  manuals (LaTeX sources + compiled PDFs, English US).
- **Reference manual** — [docs/manual.pdf](docs/manual.pdf): full model
  description with the polar-coordinate phonetic targets
  ($\rho, \theta$ plane, projection coefficients) and the
  coarticulation mechanisms (selector superposition, S-curve arcs,
  cluster scoping), CLI/API reference and worked example.
- **Speakers** — [docs/speakers.pdf](docs/speakers.pdf): the
  multi-speaker registry, `install_speaker.py`, the four layers of a
  switch, provenance chains and the defect catalogue (v1.1.0).
- **Language pack** --- [docs/language_pack.pdf](docs/language_pack.pdf), covering the six languages, `setup_lang.py` and the **marker-only LANG SECTION (v1.2.0)**: the language selects pronunciation modules, lexicons, G2P and notation, while vowel targets stay the active speaker’s own (the former per-language overrides and JD3 guard were removed, defect D24). Pack internals: [lang_pack/README.md](lang_pack/README.md), [lang_pack/manual/manual.pdf](lang_pack/manual/manual.pdf), [lang_pack/ARCHITECTURE.md](lang_pack/ARCHITECTURE.md). Speaker characteristics: [docs/SPEAKERS.md](docs/SPEAKERS.md).
- **Polar visualization** — [docs/polar_visualization.pdf](docs/polar_visualization.pdf):
  the (ρ, θ) plane, the dissociated vocalic/consonantal branches and
  the dual-panel video (v1.1.0).
- **Expressive prosody** — [docs/expressive_prosody.pdf](docs/expressive_prosody.pdf):
  breathing groups, F0 contour, out-of-band stress, and the
  interaction with the multi-speakers installation (v1.1.0).
- **Architecture** — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):
  developer map of the engine (module layout, data flow, the
  B(t) + E_source(t) + E_ortho(t) decomposition) — including the
  v1.1.0 add-ons (speakers registry, LANG SECTION, polar video).
- **Installation (Windows)** — [INSTALLATION.md](INSTALLATION.md):
  step-by-step CMD guide (Download ZIP, pip --user, PATH, Python 3.9
  note, troubleshooting); see also [INSTALL.md](INSTALL.md).
- **Coding conventions** — [docs/CONVENTIONS.md](docs/CONVENTIONS.md).
- **v1.1.0 packaging notes** — [MIGRATION_NOTES.md](MIGRATION_NOTES.md):
  version decision, excluded tests, licensing map.

## Quick start

```bash
pip install .            # or: pip install -e .
vtl-synth run "this is easy for us" -o ./out
```

Output: `out/this_is_easy_for_us.tract`, `.wav`, `.mp4` and `.txt`
(the SAMPA transcript produced by the g2p). The default speaker is
**jd3**; see [Multi-speakers](#multi-speakers) to install another
voice, and [Languages](#languages) for de/es/fr/it/pt input.

## Multi-speakers

Five speakers ship in the registry `vtl_synth/data/speakers/` and are
selected with the reversible tool `install_speaker.py` (constants +
orthogonal branch + wheel resource; backups and rollback automatic,
smoke-tested in a fresh subprocess):

| name | origin | f0 default |
|---|---|---|
| `jd3` | reference (SynthVTL24b original) | 102.2 Hz |
| `s1` | DVTD MRI subject 1 (male), calibrated constants v3 | 114.9 Hz |
| `s2` | DVTD MRI subject 2 (female), calibrated constants v3 | 181.0 Hz |
| `m01` | official VTL 2.4 ZIP (male), pure option A + 2025 glottal mapping | 120.0 Hz |
| `w02` | official VTL 2.4 ZIP (female), pure option A + 2025 glottal mapping | 232.5 Hz |

```bat
python install_speaker.py list            :: registered + active
python install_speaker.py install m01     :: swap speaker (reversible)
python install_speaker.py status          :: hashes / coherences
python install_speaker.py restore         :: back to jd3
```

Notes: the shared `vocaltractlab_cython` wheel resource (audio + SVG
layer) is swapped **for the next process** — relaunch your program
after an install. Per-speaker regression baselines
(`regression_baselines_<name>.json`) are picked automatically by the
test suite; regenerate them with `scripts/regen_baselines.py` after an
intentional signal change.

## Languages

`setup_lang.py` + `lang_pack/` add **German, English, Spanish, French,
Italian and Portuguese** (g2p, Wikipron lexicons, per-language vowel
sets and prosody profiles). The active language is a managed *LANG
SECTION* inside `constants.py`, transported across speaker swaps and
fully reversible:

```bat
python setup_lang.py list                 :: available + current
python setup_lang.py install --lang fr    :: install/activate French
python setup_lang.py setlang de           :: switch language
python setup_lang.py calibrate fr         :: re-derive vowel targets (JD3 only)
python setup_lang.py verify               :: integrity check
python setup_lang.py restore              :: back to native vowels
```

**Guard-rail**: the pack vowel targets are calibrated *in situ* on
**JD3** — `calibrate` (re)installs speaker jd3 first and says so; the
other speakers keep their native vowel targets (a non-jd3 speaker with
an active language is flagged as an unverified combination). Lexicons
are CC BY-SA 3.0 (Wikipron) — keep the `README_xx_lexicon.md` notices
beside the TSV files; details in `lang_pack/LICENSE.md`.

## Polar video

`vtl-synth run --polar "this is easy for us" -o ./out` also writes a
`.polar` intermediate (100 Hz, format v3: dissociated vocalic /
consonantal trajectories) and renders a **dual-panel MP4** — sagittal
cross-section (left) and polar (ρ, θ) plane (right) at 25 Hz, vowels in
**red**, consonants in **blue**, each branch with a fading trail. See
`docs/polar_visualization.pdf` and the short demo
`examples/polar_demo_en.mp4`.

## Expressive prosody

`vtl-synth run --expressive "…" -o ./out` (default **off**, outputs
bit-identical without it) adds syntactic breathing groups (per-language
function-word dictionaries, hard 5-word balance, inseparable
connectors, 130 ms `%` breath pauses) and a sculpted F0 contour
(declination + block re-attacks + pitch accents + per-language nuclear
fall; lexical stress travels out-of-band, never in the SAMPA). It only
touches the glottis f0 column and pause durations — never the tract,
so it composes with any speaker. Demo: `python examples/demo_prosody.py`;
measurements: `python scripts/f0_report.py <tract…>`. Guide:
`docs/expressive_prosody.pdf`.

## Command line

```
vtl-synth run "this is easy for us" -o ./out      # tract + wav + mp4
vtl-synth run --phonetic "ba da ga | iowa a g" -o ./out   # direct SAMPA
vtl-synth run -s m01 -l fr "bonjour" -o ./out     # speaker + language
vtl-synth run --expressive "this is easy for us" -o ./out
vtl-synth text-to-wav "hello world" -o ./out      # audio only
vtl-synth tract-to-mp4 out/x.tract out/x.wav -o out/x.mp4
vtl-synth inspect out/x.tract --states 2 --ranges
vtl-synth plot-tract out/x.tract --which all -o out/x.png
vtl-synth polar-build out/x.tract out/x.wav -o out/x.polar
vtl-synth polar-video out/x.polar out/x.tract out/x.wav -o out/x.mp4
```

Speaker/language options (`-s/--speaker`, `-l/--lang`,
`--expressive`/`--no-expressive`) act for the run: they switch the
registry entry / language section first (same machinery as
`install_speaker.py` / `setup_lang.py`). The timing defaults shown as
`None` in `--help` (100/80/200/320 ms) are resolved through the active
language profile.

`plot-tract` is the graphical counterpart of `inspect`: it draws the
400 Hz trajectory of each tract parameter (optionally the glottis f0
and pressure with `--which all`, or a subset with
`--params JX JA TTX TTY`) into a PNG figure; `--ranges` adds the
min/max/mean table of `inspect`. Requires the optional `matplotlib`
dependency (`pip install .[plot]`).

Engine options (COVTL model parameters) on `run`/`text-to-wav`:

| option | default | description |
|---|---|---|
| `--tcons MS` | 100 | consonant gesture duration |
| `--tvoy MS` | 80 | vowel gesture duration |
| `--tpause MS` | 200 | short inter-word pause (space) |
| `--tpause-long MS` | 320 | long pause (end of sentence, `\|`) |
| `-f0 HZ` | per speaker | F0 (jd3 default 102.216 Hz); a French-style declination is applied |
| `--no-ortho` | off | disable the orthogonal branch (TS3/VS) |
| `--engine` | syl | trajectory engine (`syl` recommended, `legacy` = pre-syltraj) |
| `--fps`, `--scale`, `--no-video` | 25, 2 | video rendering |

Note on the arc-shape constants (see `syltraj.py` and the CHANGELOG):
the `syl` engine uses the convention ν = −1, K = 1000,
`SYL_COEFCEN` = 0.5 — ν = 1 is recovered when the cosine is written
with the opposite sign (the published equation's form); the reference
curvatures K = 10/30 with ν = 1 belong to the `legacy` engine and the
polar-video display.

## Python API

```python
from vtl_synth import Pipeline

pipe = Pipeline()                       # validated default settings
result = pipe.run("this is easy for us", output_dir="./out")
print(result.sampa)                     # "Dis.iz.i.zi.fOR.@s"
print(result.wav_path, result.duration_s)

# phonetic input, audio only
result = pipe.text_to_wav("ba da ga | iowa a g",
                          output_dir="./out/phon", use_g2p=False)
```

The full engine API (72 symbols: `build_phrase_tract`,
`text_to_tract`, timers, envelopes, polar model, …) is available in
`vtl_synth.core`; the VTL bindings in `vtl_synth.vtl.api`.

## Input notation

- **English text** — converted to phonemes by the bundled g2p
  (CMUdict, ARPAbet → engine SAMPA). Words are **connected with '.'
  inside a phrase** (syllabified by onset maximization), so the
  engine coarticulates across word boundaries — no pause inside a
  phrase:
  `this is easy for us` → `Dis.iz.i.zi.fOR.@s`. A comma keeps a
  short inter-word pause (space) and sentence punctuation becomes
  `|` (long pause). Unknown words are passed through verbatim when
  they are already valid SAMPA.
- **SAMPA phonetic input** (`--phonetic`) — same engine notation,
  written directly: vowels `a e i o u y E O @ 2 6 9`, consonants
  `p b t d k g f v s z S Z T D tS dZ m n J l R j w h ɥ`;
  `.` syllable break, space short pause, `|` long pause.

## Repository layout

```
covtl-pipeline/
├── pyproject.toml            # package config (Python ≥ 3.9)
├── launch.bat                # Windows quick-launch script
├── install_speaker.py        # multi-speakers selector (add-on 1)
├── setup_lang.py             # language pack installer (add-on 2)
├── lang_pack/                # language pack source (g2p, lexicons, manual)
├── vtl_synth/
│   ├── core/                 # synthesis engine
│   │   ├── pipeline.py       # Pipeline orchestrator (run/text_to_wav)
│   │   ├── phonemes.py       # ARPAbet↔SAMPA tables
│   │   ├── speaker_registry.py  # multi-speakers registry access
│   │   └── … 27 modules incl. __init__ (constants, polar, syltraj, timers, …)
│   ├── cli/main.py           # vtl-synth entry point
│   ├── video/                # SVG/PNG renderer + MP4 encoder + polar
│   │                         # video (dual panel) + tract figure
│   ├── vtl/api.py            # VocalTractLab API facade
│   ├── utils/                # g2p (CMUdict) + language profiles
│   │                         # (chunking, prosody_f0, … — add-ons 2-3)
│   └── data/
│       ├── vtl_binaries/JD3.speaker     # legacy fallback speaker file
│       ├── speakers/                    # registry: 5 .speaker +
│       │                                # *_constants.py + registry.json
│       └── *_lexicon.tsv                # installed Wikipron lexicons
├── scripts/                  # regen_baselines, calibrate_fine_v2, f0_report…
├── tests/                    # lightweight suite (111 tests, engine
│                             # non-regression + CLI/g2p + registry)
├── examples/                 # demo.py, demo_prosody.py, polar_demo_en.mp4
├── docs/                     # manual, ARCHITECTURE, CONVENTIONS,
│                             # expressive_prosody.pdf, polar_visualization.pdf
├── regression_baselines*.json   # E2E non-regression baselines (5 speakers)
└── MIGRATION_NOTES.md        # v1.1.0 packaging decisions & inventory
```

## Differences with the vtl-pipeline reference repository

The reference repository chains VTL-native stages
(text → **.seg → .ges** → tract → wav/mp4) through a ctypes binding to
`libVocalTractLabApi`. This package instead synthesizes the 400 Hz
tract sequence **directly** with the Berthommier COVTL model — there
is no `.seg`/`.ges` stage, hence no such files in the output; the VTL
engine is the `vocaltractlab-cython` wheel (no manual DLL management).

## Installation

Windows: see [INSTALLATION.md](INSTALLATION.md) (step-by-step CMD guide,
pip-only, Git optional). Short version: `pip install .` — dependencies
`numpy`, `scipy`, `vocaltractlab-cython`, `Pillow`, `imageio-ffmpeg`
(bundled ffmpeg), `cmudict`. Optional extra `plot` (matplotlib) for
`plot-tract`.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This licensing is
mandatory: the three core components (VocalTractLab,
vocaltractlab-cython, create_vtl_corpus concepts) are GPL-3.0, so this
package may not be relicensed under a more permissive license
(MIT, Apache-2.0, BSD).

Copyright (C) 2026 Frédéric Berthommier. The synthesis engine
(`vtl_synth/core`) implements the Berthommier COVTL articulatory model
coupled with VocalTractLab, published under GPL-3.0-or-later. When
redistributing, keep the full `LICENSE` file and
`THIRD_PARTY_NOTICES.md` with all copyright notices intact.

## References

If you use this package in academic work, please cite the publications
of the Berthommier COVTL model:

1. F. Berthommier, "A mathematical model of the vowel space",
   arXiv:2111.00868 [eess.AS], 2021.
   DOI: 10.48550/arXiv.2111.00868 — <https://arxiv.org/abs/2111.00868>
2. F. Berthommier, "Why can big.bi be changed to bi.gbi? A mathematical
   model of syllabification and articulatory synthesis",
   arXiv:2307.02299 [eess.AS], 2023.
   DOI: 10.48550/arXiv.2307.02299 — <https://arxiv.org/abs/2307.02299>
3. F. Berthommier, "Synthèse de syllabes avec un modèle de Maeda piloté
   par une représentation complexe", in *Actes des 35èmes Journées
   d'Études sur la Parole (JEP)*, pages 541–550, ATALA and AFPC, 2024.
   <https://aclanthology.org/2024.jeptalnrecital-jep.55/>
4. F. Berthommier, "Articulatory modeling of the S-shaped F2
   trajectories observed in Öhman's spectrographic analysis of VCV
   syllables", *Interspeech 2025*, Rotterdam, Netherlands.
   HAL: hal-05233039, DOI: 10.5281/zenodo.17018832 —
   <https://hal.science/hal-05233039v1>

Please also cite VocalTractLab itself (see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
