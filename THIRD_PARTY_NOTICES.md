# Third-party notices

This package is licensed GPL-3.0-or-later. The following third-party
components are redistributed or relied upon; their licenses apply and
**may not** be removed.

> **LICENSE AUDIT — CLOSED (2026-11-06; committed upstream 2026-11-12).**
> This notice supersedes the earlier provisional text. Every fact below
> was verified against the artifacts actually distributed (installed
> distributions, wheel contents, bundled binaries), not against upstream
> declarations alone. The three previously open points are now closed:
> speakers s1/s2 (**CC0 1.0**, § below), the cmudict package/data split
> (§ below), and the bundled FFmpeg builds (**GPL**, both platforms,
> § below). Full evidence and methodology: `BUILD_REPORT.md` and
> `docs/license-scheme.md` of the covtl-console-testpypi integration
> project.

## VocalTractLab 2.4

- Author: Peter Birkholz (TU Dresden) — https://www.vocaltractlab.de
- Role: articulatory synthesizer producing the audio (`.wav`) and the
  sagittal SVG views used by the video renderer; the `JD3.speaker`
  file shipped in `vtl_synth/data/vtl_binaries/` is a VocalTractLab
  speaker definition, and the **M01/W02 speaker files** redistributed
  in `vtl_synth/data/speakers/` are derived from the official VTL 2.4
  ZIP (speaker definition retouched: glottal mapping 2025→11 codes,
  index 7 = PS — see `docs/ARCHITECTURE.md` §8.1).
- License: **GPL-3.0 (GPLv3)** — confirmed by the official channels,
  no inference from any "free for research" wording:
  1. the official site https://www.vocaltractlab.de (download page):
     the software "is open source under the GNU General Public License";
  2. the official VocalTractLab 2.4 user manual (P. Birkholz, 2025):
     "distributed as free and open source software under the GNU General
     Public License (GPL), available for download as a ZIP file from
     www.vocaltractlab.de" (the ZIP contains the program, the source,
     the license and the example files);
  3. the official development repository
     https://github.com/TUD-STKS/VocalTractLab-dev: `LICENSE` is the
     full GPLv3 text (it contains `resources/JD3.speaker` and the
     `VocalTractLabApi` source of which `vocaltractlab-cython` is the
     binding);
  4. the effective dependency chain of this project:
     `vocaltractlab-cython` 0.0.17 (PyPI) redistributes the native
     library, `VocalTractLabApi.c` and `resources/JD3.speaker` under
     GPL-3.0 (wheel METADATA + LICENSE).
  The Option-A transformation of M01/W02 (glottal mapping) creates no
  new rights: the files remain GPL-3.0 and are redistributed with the
  license text and these notices (GPL obligations satisfied by the
  GPL-3.0-or-later distribution of the whole).

- Provenance of the shipped copies (`vtl_synth/data/vtl_binaries/
  JD3.speaker` and `vtl_synth/data/speakers/jd3.speaker`): both are
  byte-identical (LF) to `resources/JD3.speaker` of the
  `vocaltractlab-cython` 0.0.13 wheel on PyPI
  (SHA-256 `e1e592da…418a503` LF-normalized; the wheel ships the file
  with CRLF endings, SHA-256 `a583bdaa…b571f00`). Unmodified upstream
  file; the registry hashes in `data/speakers/registry.json` refer to
  the LF form. `*.speaker` is excluded from git end-of-line
  normalization (`.gitattributes`) so checkouts preserve the hashed
  bytes.

## Speakers s1/s2 (DVTD MRI) — CONFIRMED REDISTRIBUTABLE, CC0 1.0

- Origin: MRI data of the DVTD subjects (male s1, female s2) from the
  **Dresden Vocal Tract Dataset**, converted to VTL speaker definitions
  with constants calibrated for this repository (v3).
- License of the underlying data: **CC0 1.0** — verified on the
  official dataset repository (figshare; license "CC0" confirmed via
  the figshare API on 2026-11-06;
  DOI [10.6084/m9.figshare.11897187.v1](https://doi.org/10.6084/m9.figshare.11897187.v1)).
  The derived measures and speaker definitions may be redistributed
  without license restriction.
- License of the conversion (calibrated constants v3, registry
  entries): GPL-3.0-or-later, as part of this project.
- Scientific citation (traceability requirement, **not** a license
  restriction — CC0 imposes none). Academic use of the s1/s2 speakers
  shall cite:

  > P. Birkholz, S. Kürbis, S. Stone, P. Häsner, R. Blandin,
  > M. Fleischer. *Dresden Vocal Tract Dataset* (complete archive).
  > Scientific Data 7:255 (2020).
  > DOI: [10.6084/m9.figshare.11897187.v1](https://doi.org/10.6084/m9.figshare.11897187.v1)
  > — license CC0 1.0.

## Language pack (de/en/es/fr/it/pt)

- Origin and per-component licensing:
  [`lang_pack/LICENSE.md`](lang_pack/LICENSE.md). Code (g2p profiles,
  installer, integration): GPL-3.0-or-later. Pronunciation lexicons
  `xx_lexicon.tsv` (fr/es/de/it/pt): **Wikipron** (CUNY-CL/wikipron,
  extracted from the English Wiktionary), **CC BY-SA 3.0** — the
  `README_xx_lexicon.md` notices must travel beside the TSV files and
  redistributed lexicons stay CC BY-SA 3.0
  (<https://creativecommons.org/licenses/by-sa/3.0/>). Share-Alike
  applies to the data files, not to the code that reads them; the
  expressive-prosody stress channel (`prosody_f0`) reads these TSVs
  through `lexicon_loader`. English g2p gateway: CMUdict (see below).
  Residual note (non-blocking): the exact extraction date of the TSV
  files is not recorded in the upstream sources; the CC BY-SA 3.0
  license and its obligations apply regardless.

## vocaltractlab-cython

- Author: Paul Krug — https://github.com/paul-krug/VocalTractLab-Python
  PyPI: https://pypi.org/project/vocaltractlab-cython/
- Role: Cython binding of the VocalTractLab API (`synth_block`,
  `tract_state_to_svg`, …); provides the VTL shared library.
- License: GPL-3.0 (wheel METADATA + LICENSE; the PyPI wheel also ships
  the sources `VocalTractLabApi.c` and `resources/JD3.speaker`).

## create_vtl_corpus (methodological reference — no file redistributed)

- Author: Konstantin Sering, Universität Tübingen — original source
  <https://github.com/quantling/create_vtl_corpus> (also referenced
  upstream as <https://github.com/serng/vtl-pipeline-related-work>).
- Role: methodological reference (seg → ges → tract pipeline) for the
  layout of the vtl-pipeline repository.
- License of the upstream project: GPL-3.0.
- **`phone_attributes.txt` — NOT redistributed.** An earlier notice
  documented `vtl_pipeline/data/phone_attributes.txt` (verbatim copy
  from create_vtl_corpus, GPL-3.0, modifications: none). This package
  does **not** include that file: no `phone_attributes.txt` exists in
  `vtl_synth/`, in the wheel nor in the sdist (verified 2026-11-05 and
  re-verified on the standalone bundle 2026-11-06). It is listed here
  only to record that it is absent, so the non-redistribution is
  explicit and auditable.

## cmudict Python package

- Version: 1.1.3 — <https://pypi.org/project/cmudict/>
- Use: grapheme-to-phoneme lookup for English (ARPAbet) in the g2p
  front-end.
- License: **GPL-3.0-or-later** (verified in the metadata of the
  installed distribution: `License: GPL-3.0-or-later`, GPLv3
  dist-info LICENSE, classifier GPLv3+).
- CORRECTED FROM THE EARLIER NOTICE: it stated `BSD-2-Clause` for
  "cmudict". That license applies to the **data** (next section), not
  to the Python package.

## CMU Pronouncing Dictionary data

- The CMU Pronouncing Dictionary data distributed with the cmudict
  package (`cmudict/data/cmudict.dict`, `.phones`, `.symbols`, `.vp`)
  are covered by their separate upstream BSD-style license
  (BSD-2-Clause; copyright 1993-2015 Carnegie Mellon University —
  `cmudict/data/LICENSE` in the installed distribution).
- The package license and the data license must not be conflated.

## Other Python dependencies

| package | license | role |
|---|---|---|
| numpy | BSD-3-Clause | parameter matrices |
| scipy | BSD-3-Clause | signal utilities |
| Pillow | HPND (MIT-CMU) | SVG→PNG rasterization for the video |
| imageio-ffmpeg | BSD-2-Clause (wrapper) | bundled ffmpeg binary (MP4/AAC encoding) |
| matplotlib (optional `plot` extra) | Matplotlib license (BSD-style) | `plot-tract` figures, polar/sagittal video views |

### Bundled FFmpeg — GPL builds on BOTH platforms (verified on the binaries)

The earlier notice described an "LGPL-compatible build". **Verified on
the binaries actually redistributed (2026-11-06, by execution): the
imageio-ffmpeg 0.8.1 wheel ships GPL builds.** They must be treated as
**GPL**, never as LGPL-compatible.

- **Linux** (`ffmpeg-linux-x86_64-v9.0.2`,
  `n9.0.2-17-g2a571b6068-20260930`, BtbN/FFmpeg-Builds family,
  172 692 552 bytes): configuration includes
  `--enable-gpl --enable-version3` → **GPL-3.0-or-later**. Proof that
  the bundled binary (not a system one) does the encoding: standalone
  smoke test with an **empty `PATH`** — the MP4 is still produced.
- **Windows** (`ffmpeg-win-x86_64-v9.0.2.exe`, executed on Windows):
  `ffmpeg version 9.0.2-essentials_build-www.gyan.dev`, configuration
  `--enable-gpl --enable-version3 --enable-static … --enable-libx264
  --enable-libx265 --enable-libxvid`; 105 423 872 bytes, SHA-256
  `3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec`;
  the binary's own `-L` statement: "GNU General Public License …
  either version 3 of the License, or (at your option) any later
  version" → **GPL-3.0-or-later** (gyan.dev "release essentials"
  build, <https://www.gyan.dev/ffmpeg/builds/>: "All builds are 64-bit,
  static and licensed as GPLv3").
- **Corresponding source (GPL §6 written offer):** for each
  redistributed FFmpeg binary the corresponding source is FFmpeg 9.0.2
  — commit `946fcce07b` (<https://github.com/FFmpeg/FFmpeg>), tarball
  <https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz>, plus the build
  scripts/page of the distributor (BtbN / gyan.dev). The
  covtl-console-testpypi integration project offers, on request and
  free of charge, for at least three years from distribution, the
  corresponding source of any FFmpeg binary it redistributes (contact:
  F. Berthommier, maintainer of the upstream repositories). The build
  identification above (version, configuration, SHA-256, provenance) is
  provided so the build can be reproduced.

## The Berthommier COVTL model

The synthesis engine (`vtl_synth/core`) implements the Berthommier
COVTL articulatory model coupled with VocalTractLab. The model is
described in the following publications (see also the References
section of the README):

- F. Berthommier, "A mathematical model of the vowel space",
  arXiv:2111.00868 [eess.AS], 2021.
- F. Berthommier, "Why can big.bi be changed to bi.gbi? A mathematical
  model of syllabification and articulatory synthesis",
  arXiv:2307.02299 [eess.AS], 2023.
- F. Berthommier, "Synthèse de syllabes avec un modèle de Maeda piloté
  par une représentation complexe", JEP 2024, pp. 541–550.
- F. Berthommier, "Articulatory modeling of the S-shaped F2
  trajectories observed in Öhman's spectrographic analysis of VCV
  syllables", Interspeech 2025 (HAL hal-05233039).

Academic use shall also cite VocalTractLab (author, version, site) and,
for the s1/s2 speakers, the Dresden Vocal Tract Dataset (§ above).
