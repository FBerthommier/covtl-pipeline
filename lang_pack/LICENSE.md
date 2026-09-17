# LICENSE — provenance and licensing of the covtl-pipeline language pack

The covtl-pipeline repository is licensed **GPL-3.0-or-later**
(see the repository root `LICENSE`). The language pack stacks code
and data of several origins; this file is the per-component
attribution, `ARCHITECTURE.md` carries the same information from the
data-flow point of view.

## 1. Per-component provenance

| Component | Origin | License / citation |
|---|---|---|
| COVTL engine, Berthommier model, JD3 speaker, `vtl_binaries/` | covtl-pipeline repository (vtl-pipeline reference) | GPL-3.0-or-later — **JD3 and `vtl_binaries/` are untouched by this pack** (it ships no binary) |
| English g2p (CMUdict gateway) | CMUdict (Carnegie Mellon University) | public domain / BSD-like; source credited |
| g2p fr/es/de/it/pt, shared lexicon loader, language profiles, LANG blocks, installer scripts, manual | written for the covtl-pipeline repository | GPL-3.0-or-later |
| Pronunciation lexicons `xx_lexicon.tsv` (fr, es, de, it, pt) | **Wikipron** (CUNY-CL/wikipron, branch master), extracted from the **English Wiktionary** | **CC BY-SA 3.0** — keep the `README_xx_lexicon.md` notices next to the files, cite the source |
| Reference formants (vowel inventories) | Fant (1973); Peterson & Barney (1952); Quilis (1981); Jørgensen (1969); Ferrero et al. (1978); Delgado-Martins (1999); Escudero et al. (2009) | academic citation |
| Prosodic contours (F0 profiles) | Jun & Fougeron (2002); Face (2003); Grice et al. (2005); Avesani (1995); Frota (2000); Beckman & Ayers (1997, ToBI guidelines) | academic citation |

## 2. Provenance boundary

Everything in this pack originates from the sources listed in the
table above and from no other program, dataset or external project.
Nothing outside that table may be cited as a component, origin or
dependency of the pipeline — including in derived documentation.
The only binaries of the pipeline are the `vtl_binaries/`
VTL 2.3/2.4 (VocalTractLab) and the JD3 speaker.

## 3. Overall compatibility and redistribution

- **Code** (profiles, integration, installers, manual, tests):
  GPL-3.0-or-later, same as the repository.
- **Data** (Wikipron `xx_lexicon.tsv`): CC BY-SA 3.0. The
  share-alike clause applies to the data files; it is compatible
  with the GPL-3.0 of the code **for the distribution of the whole**,
  provided the attribution notices travel with the data:
  1. keep the `README_xx_lexicon.md` notice beside each TSV;
  2. state the source: « Pronunciations extracted from the English
     Wiktionary by Wikipron (CUNY-CL/wikipron), CC BY-SA 3.0 » ;
  3. redistributed lexicons (modified or not) stay CC BY-SA 3.0
     (link: <https://creativecommons.org/licenses/by-sa/3.0/>).
- **Local / research use** of the pack carries no formality.
- If the size of the TSV files is a problem for a repository, do not
  commit them: the download commands in `README.md` §4 rebuild them,
  and every g2p degrades gracefully to its rules + exceptions when
  the lexicon is absent.
