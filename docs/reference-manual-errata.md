# covtl-reference-manual — Errata

Errata for `docs/covtl-reference-manual.pdf` (PDF without LaTeX source
in this repository; corrections are recorded here and not rewritten).

1. **.polar format — version 5** (sections 5.4 and 12.2): replace
   "version 4" with "version 5" — `POLAR_VERSION = 5`
   (`vtl_synth/video/polar_video.py`, 2026-11-23; version 5 adds the CV
   reduced-vowel approach anchoring).
2. **User manual page count**: "covtl-pipeline User Manual (27 pp)" is
   to be read "(28 pp)" — two occurrences (chapter map and reference
   [1]); `pdfinfo docs/manual.pdf` reported 28 pages. Since the
   2026-11-24 schwa-audit documentation round (two-representation-layer
   section + VV waypoint update), the count is **(29 pp)**.
3. **Schwa target and VV waypoint** (§"vowel targets" table — the
   ρ̄ = 0.7167 centroid line — and §4.5 "Vowel-to-vowel coarticulation
   and the schwa waypoint"): the schwa target `'@'` is now the INTERIOR
   mid-central **(0.580, π)**, not the centroid of the calibrated
   triangle (0.7167 stayed one step only, 2026-09-04 → 2026-11-24
   audit; acoustic anchor F1 620 / F2 1463 Hz). The anti-closure
   routing of §4.5 is **mandatory and unconditional** in the engine
   (the waypoint follows `'@'`); only its DRAWN representation in the
   .polar plane is optional (`display_schwa_route`, default off =
   legacy direct arc). The new figure position for '@' is
   (ρ, θ) = (0.580, 180°). Cf. `docs/schwa-position-audit-EN.md`.
