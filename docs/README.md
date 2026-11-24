# covtl-pipeline — Documentation (v1.1.0)

Seven PDF documents (five manuals, the didactic manual and the reference manual), English (US), LaTeX sources + compiled PDFs. Note: `covtl-reference-manual.pdf` and `From_Phonetics_to_Articulatory_Phonology.pdf` have no .tex source in the repository (PDF + errata sheet).
Each manual is self-contained; they cross-reference each other by
file name.

| file | content |
|---|---|
| `From_Phonetics_errata.md` | Errata sheet of the didactic manual (2nd edition): production dental target 270 deg vs the article's 23*pi/16; .polar format v5. |
| `From_Phonetics_to_Articulatory_Phonology.pdf` | Didactic manual (2nd edition, 2026-11): the making of covtl, step by step - from the coordination function and the unit circle to the complete driving of VocalTractLab; implementation record corrected against covtl-synth 1.2.2 (speaker JD3). Entry point of the documentation family. |
| `manual.pdf` / `.tex` | Reference manual: the Berthommier COVTL model (polar targets, projection, coarticulation), source model, CLI/Python API, file formats, registry and language-pack overview, worked example, developer guide. |
| `speakers.pdf` / `.tex` | Multi-speaker registry: the five speakers (jd3, s1, s2, m01, w02), `install_speaker.py`, the four layers of a switch, provenance chains (DVTD construction, adaptation, Option A), defect catalogue D1–D21. |
| `language_pack.pdf` / `.tex` | Language pack: six languages (en, fr, es, de, it, pt), `setup_lang.py` (install/setlang/calibrate/verify/restore), vowel-target calibration, per-language profiles, JD3 guard, troubleshooting. |
| `expressive_prosody.pdf` / `.tex` | Expressive prosody option (`--expressive`): syntactic breathing, sculpted F0 contour, out-of-band stress channel, measurements, tests, interaction with speakers/languages. |
- `PROMPT_prosodie_expressivite.md` — design specification of the expressive-prosody add-on (2026-09-15, French; historical source document referenced by PROVENANCE_PROSODY_CHUNKING.md, not a manual)
| `polar_visualization.pdf` / `.tex` | Dynamic polar video (`--polar`): two-branch reconstruction (vocalic/consonantal), `.polar` intermediate format, dual-panel MP4, validation, demos. |

Shared developer docs at the repository root and in this folder:
`ARCHITECTURE.md` (engine map), `CONVENTIONS.md` (coding style),
`../CHANGELOG.md` (release history), `../MIGRATION_NOTES.md`
(packaging decisions, if present).

- **Coverage dossier (waves 1–4)** — `../COVERAGE_REPORT.md` and the
  wave-4bis addendum `../ADDENDUM_COVERAGE_REPORT.md`: measurement
  methodology, per-commit evidence, non-regression proofs, and the
  phonation redo with measured audio deltas. PDF synthesis in
  `wave4/synthesis/COVERAGE_SYNTHESIS_WAVE1-4.pdf`, commit log in
  `wave4/COMMIT_LOG_WAVE4.pdf`.
- **Coverage dossier, wave-5 addendum** —
  `../ADDENDUM_COVERAGE_REPORT_WAVE5.md`: the post-1.2.0 hardening
  audit — the CI-visible phonation tests, the wildcard tag override,
  and the console alignment (519 green tests, 76.7 % combined, honest
  ceiling 79.0 %).
- **Engine studies** — `schwa-position-audit-EN.md`: the schwa
  position change study (audit 2026-11-24; English translation of the
  French internal audit) — occlusion corner of the (ρ, θ) plane,
  dissimilarity law H = 1 − ρ_w, decision `'@'` = (0.580, 180°),
  measured impact, validation; every element classified by
  representation layer (layer 1 target / layer 2 mandatory routing /
  layer 2 display option).

## Building the PDFs

```bash
# manual.pdf (fontspec; uses the shipped IPA font docs/.l_10646.ttf)
xelatex manual.tex && xelatex manual.tex

# the four companion manuals (plain pdflatex)
pdflatex polar_visualization.tex && pdflatex polar_visualization.tex
pdflatex expressive_prosody.tex && pdflatex expressive_prosody.tex
pdflatex language_pack.tex && pdflatex language_pack.tex
pdflatex speakers.tex && pdflatex speakers.tex
```

Figures live in `figures/`. The manuals are transportable: standard
LaTeX packages only, no external tool dependencies.
