# From Phonetics to Articulatory Phonology — Errata (2nd edition)

Errata for `docs/From_Phonetics_to_Articulatory_Phonology.pdf`
(2nd edition, 2026-11). The PDF has no LaTeX source in this repository
and is not rewritten; corrections are recorded here.

1. **Production dental target — 270 deg, not 23*pi/16** (sections 5.2,
   7.11-7.12 and table 6): the target /d/ written `23*pi/16` (258.75 deg)
   describes the state of the articles and of the monolithic engine
   (Timit-to-Maeda, `THETA_DENTAL`). The production state since v1.2.0 is
   `SYL_THETA_DENTAL = 3*pi/2` (270 deg) — cf. `syltraj.py:63`,
   `docs/SPEAKERS.md` (2026-09-23) and the CHANGELOG entry
   "SYL_THETA_DENTAL fix 23*pi/16 -> 3*pi/2 (270 deg...)". Table 5 of the
   same document (d = 1.10, 270 deg) is correct.
2. **.polar format — version 7** (chapter 7, .polar intermediate):
   `POLAR_VERSION = 7` (`vtl_synth/video/polar_video.py`). Version 5
   added the CV reduced-vowel approach anchoring; versions 6-7
   (2026-11-25, words 'oga'/'ago'/'bea.ba'/'a.ba') fixed the consonantal
   leg geometry: the branch departs from the FULL departure-vowel anchor
   (like the motor chain), leg sampling uses the engine's cos^2 profile
   (Pexp=2, legs meet on the consonant peak within ~2.4% of the chord),
   and the release-leg phase sign is mirrored so the pair closes as the
   reference lens. Readers of older v4 files keep v4 semantics.
3. **Schwa target — interior mid-central (0.580, 180°), not the polar
   centroid** (implementation record §"vowel radii" and appendix C,
   production table): the manual cites the centroid ρ̄ =
   (1 + 0.60 + 0.55)/3 = 0.7167 (re-centring of 2026-09-04). Since the
   2026-11-24 audit the production state is `'@' = (0.580, π)` — the
   INTERIOR mid-central, acoustically anchored (F1 620 / F2 1463 Hz
   measured, ref 600/1400). The centroid value stayed one step only
   (2026-09-04 → 2026-11-24): at 0.7167 the routed « buib » hugged the
   /a/ meridian and mimicked « buaib » (Hausdorff 0.283); at 0.580 the
   corridor crosses at quasi-constant aperture (H = 0.420, legs
   ≥ 0.170 cm²). The schwa remains the waypoint of the closing VV arcs
   (routing mandatory, unconditional); its display in the .polar plane
   is optional (`display_schwa_route`, default off). Cf.
   `docs/schwa-position-audit-EN.md`, `vtl_synth/core/constants.py`.

3. **.polar display — version 6, branchement on the full departure vowel**
   (2026-11-25 audit, words 'oga'/'ago'): the v5 'reduced arrival-vowel
   anchoring' applied only to full-vowel departures (rho > 0.7: a, o, O,
   e) and anchored the approach leg on a phantom REDUCED ARRIVAL vowel
   ('a réduit' for oga, 'o réduit' for ago) instead of the departure
   vowel. Since display v6 the consonantal branch departs from the FULL
   departure-vowel anchor — exactly like the motor chain — and the
   reduced anchoring of manual section 5.6 ('ba' lens) remains valid for
   INITIAL onsets only.
