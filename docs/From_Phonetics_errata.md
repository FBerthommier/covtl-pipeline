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
2. **.polar format — version 5** (chapter 7, .polar intermediate):
   `POLAR_VERSION = 5` (`vtl_synth/video/polar_video.py`). Version 5 adds
   the CV reduced-vowel approach anchoring ("ventre" fix, 2026-11-23):
   post-vocalic onset consonants are drawn from the reduced arrival-vowel
   anchor (0.5*rho_V, theta_V), so the approach is the concave inner
   branch and the release rides the outer arc. Readers of older v4 files
   keep v4 semantics.
