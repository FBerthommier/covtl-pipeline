# vtl-synth — articulatory synthesis from text (COVTL + VocalTractLab)

`vtl-synth` turns English text (or phonetic input) into:

- a **`.tract`** file — the 400 Hz sequence of 19 tract + 11 glottis
  VocalTractLab parameters,
- a **`.wav`** waveform (44.1 kHz, synthesized by VocalTractLab 2.4,
  JD3 speaker),
- a **`.mp4`** video of the **sagittal cross-section** of the vocal
  tract, synchronized with the audio.

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

- **User manual** — [docs/manual.pdf](docs/manual.pdf)
  (LaTeX source: [docs/manual.tex](docs/manual.tex)): full model
  description with the polar-coordinate phonetic targets
  ($\rho, \theta$ plane, projection coefficients) and the
  coarticulation mechanisms (selector superposition, S-curve arcs,
  cluster scoping), CLI/API reference and worked example.
- **Architecture** — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):
  developer map of the engine (module layout, data flow, the
  B(t) + E_source(t) + E_ortho(t) decomposition).
- **Installation (Windows)** — [INSTALLATION.md](INSTALLATION.md):
  step-by-step CMD guide (Download ZIP, pip --user, PATH, Python 3.9
  note, troubleshooting); see also [INSTALL.md](INSTALL.md).
- **Coding conventions** — [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Quick start

```bash
pip install .            # or: pip install -e .
vtl-synth run "this is easy for us" -o ./out
```

Output: `out/this_is_easy_for_us.tract`, `.wav`, `.mp4` and `.txt`
(the SAMPA transcript produced by the g2p).

## Command line

```
vtl-synth run "this is easy for us" -o ./out      # tract + wav + mp4
vtl-synth run --phonetic "ba da ga | iowa a g" -o ./out   # direct SAMPA
vtl-synth text-to-wav "hello world" -o ./out      # audio only
vtl-synth tract-to-mp4 out/x.tract out/x.wav -o out/x.mp4
vtl-synth inspect out/x.tract --states 2 --ranges
vtl-synth plot-tract out/x.tract --which all -o out/x.png
```

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
| `-f0 HZ` | 102.216 | F0 (JD3 default); a French-style declination is applied |
| `--no-ortho` | off | disable the orthogonal branch (TS3/VS) |
| `--engine` | syl | trajectory engine (`syl` recommended, `legacy` = pre-syltraj) |
| `--fps`, `--scale`, `--no-video` | 25, 2 | video rendering |

## Python API

```python
from vtl_synth import Pipeline

pipe = Pipeline()                       # validated default settings
result = pipe.run("this is easy for us", output_dir="./out")
print(result.sampa)                     # "D i s i z i z i f O R @ s"
print(result.wav_path, result.duration_s)

# phonetic input, audio only
result = pipe.text_to_wav("ba da ga | iowa a g",
                          output_dir="./out/phon", use_g2p=False)
```

The full engine API (63 symbols: `build_phrase_tract`,
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
├── vtl_synth/
│   ├── core/                 # synthesis engine
│   │   ├── pipeline.py       # Pipeline orchestrator (run/text_to_wav)
│   │   ├── phonemes.py       # ARPAbet↔SAMPA tables
│   │   └── … 26 engine modules (constants, polar, syltraj, timers, …)
│   ├── cli/main.py           # vtl-synth entry point
│   ├── video/                # SVG/PNG renderer + MP4 encoder + tract figure
│   ├── vtl/api.py            # VocalTractLab API facade
│   ├── utils/g2p.py          # CMUdict g2p
│   └── data/vtl_binaries/JD3.speaker
├── tests/                    # 55 tests (engine non-regression + CLI/g2p)
├── examples/demo.py
├── docs/ARCHITECTURE.md      # developer architecture map
├── docs/CONVENTIONS.md       # coding conventions of the project
├── docs/manual.pdf|.tex      # user manual (US English, LaTeX)
└── regression_baselines.json # E2E non-regression baselines
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
