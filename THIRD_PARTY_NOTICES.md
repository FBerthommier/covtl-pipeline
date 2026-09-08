# Third-party notices

This package is licensed GPL-3.0-or-later. The following third-party
components are redistributed or relied upon; their licenses apply and
**may not** be removed.

## VocalTractLab 2.4

- Author: Peter Birkholz (TU Dresden) — https://www.vocaltractlab.de
- Role: articulatory synthesizer producing the audio (`.wav`) and the
  sagittal SVG views used by the video renderer; the `JD3.speaker`
  file shipped in `vtl_synth/data/vtl_binaries/` is a VocalTractLab
  speaker definition.
- License: GPL-3.0 (Ursache/usage: research). See
  https://www.vocaltractlab.de

## vocaltractlab-cython

- Author: Paul Krug — https://github.com/paul-krug/VocalTractLab-Python
  PyPI: https://pypi.org/project/vocaltractlab-cython/
- Role: Cython binding of the VocalTractLab API (`synth_block`,
  `tract_state_to_svg`, …); provides the VTL shared library.
- License: GPL-3.0.

## create_vtl_corpus

- Author: Konstantin Sering —
  https://github.com/serng/vtl-pipeline-related-work
- Role: methodological reference (seg → ges → tract pipeline) for the
  layout of the vtl-pipeline repository this package mirrors.
- License: GPL-3.0.

## cmudict

- The CMU Pronouncing Dictionary (ARPAbet), used by the g2p front-end.
- License: BSD-2-Clause (permissive); attribution retained here.

## Other Python dependencies

| package | license | role |
|---|---|---|
| numpy | BSD-3-Clause | parameter matrices |
| scipy | BSD-3-Clause | signal utilities |
| Pillow | HPND (MIT-CMU) | SVG→PNG rasterization for the video |
| imageio-ffmpeg | BSD-2-Clause | bundled ffmpeg binary (MP4/AAC encoding) |

The bundled ffmpeg binary is licensed LGPL-2.1+ / GPL depending on
build; the imageio-ffmpeg wheel ships an LGPL-compatible build (see
https://github.com/imageio/imageio-ffmpeg).

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
