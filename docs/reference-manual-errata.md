# covtl-reference-manual — Errata

Errata for `docs/covtl-reference-manual.pdf` (PDF without LaTeX source
in this repository; corrections are recorded here and not rewritten).

1. **.polar format — version 7** (sections 5.4 and 12.2): replace
   "version 4" with "version 7" — `POLAR_VERSION = 7`
   (`vtl_synth/video/polar_video.py`; v5 added the CV reduced-vowel
   approach anchoring, v6-v7 fixed the consonantal leg geometry:
   branchement on the full departure vowel, engine cos^2 sampling,
   mirrored release-leg phase).
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

3. **Schwa routing / VV closure** (sections describing the waypoint
   routing as unconditional): the effective treatment of closing VV
   arcs is now a SOFT RECTIFICATION — direct path kept, TCY/TBY pulled
   toward the schwa by a probe-tuned sin^2 bump; the two-leg waypoint
   routing remains as the fallback (`VV_RECTIFY_SELECTOR`,
   `VV_RECTIFY_STEPS`, 2026-11-26).
