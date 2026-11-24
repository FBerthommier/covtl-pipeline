# covtl-reference-manual — Errata

Errata for `docs/covtl-reference-manual.pdf` (PDF without LaTeX source
in this repository; corrections are recorded here and not rewritten).

1. **.polar format — version 5** (sections 5.4 and 12.2): replace
   "version 4" with "version 5" — `POLAR_VERSION = 5`
   (`vtl_synth/video/polar_video.py`, 2026-11-23; version 5 adds the CV
   reduced-vowel approach anchoring).
2. **User manual page count**: "covtl-pipeline User Manual (27 pp)" is
   to be read "(28 pp)" — two occurrences (chapter map and reference
   [1]); `pdfinfo docs/manual.pdf` reports 28 pages.
