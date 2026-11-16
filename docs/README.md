# covtl-pipeline — Documentation (v1.1.0)

Five manuals, English (US), LaTeX sources + compiled PDFs.
Each manual is self-contained; they cross-reference each other by
file name.

| file | content |
|---|---|
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
