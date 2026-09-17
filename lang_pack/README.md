# lang_pack — the installable language package of the covtl-pipeline

**Six synthesis languages for the articulatory engine:**
English, Français, Español (Castilian), Deutsch, Italiano, Português
(European) — installed by one command, switched by one command,
uninstalled without residue. The JD3 speaker and `vtl_binaries/` are
never touched.

This package reorganizes the multilingual extension (v1.0.7) of the
[covtl-pipeline](https://github.com/fberthommier/covtl-pipeline) into
a single source directory at the repository root. The root CLI is
unchanged: every command still goes through
`python setup_lang.py …` and prints the currently active language.

```
lang_pack/
├── profiles/          g2p gateways, language profiles,
│                      expressive prosody (chunking, prosody_f0) → vtl_synth/utils/
├── lexicons/          Wikipron TSV + CC BY-SA notices    → vtl_synth/data/
├── lang_blocks/       per-language LANG SECTION fragments (blocks.py)
├── integration/       patched pipeline.py / utils__init__.py
├── manual/            LaTeX user manual (English US) + figures
├── install_lang.bat   one-command installer (Windows)
├── install_lang.sh    one-command installer (Linux/macOS)
├── README.md          this file
├── LICENSE.md         per-component licensing and provenance
└── ARCHITECTURE.md    origins, data flow, install/uninstall mechanics
```

## 1. Prerequisites

- **Python ≥ 3.9**, and the pipeline dependencies:
  `numpy (≥1.22)`, `scipy (≥1.7)`, `cmudict`,
  `vocaltractlab-cython (≥0.0.10)` (+ `Pillow`, `imageio-ffmpeg` for
  video). `pip install -e .` from the repository root installs
  everything.
- A **covtl-pipeline** clone with the **JD3 speaker** present in
  `vtl_synth/data/vtl_binaries/` (shipped with the repository — the
  pack ships and modifies no binary).
- The VTL binaries (VocalTractLab 2.3/2.4) reachable by the Python
  bindings.

## 2. Installation and activation

### One command (Windows)

```bat
lang_pack\install_lang.bat fr        :: or en es de it pt
```

The batch locates Python, installs the dependencies/pipeline if
needed, then runs install → verify → show. Linux/macOS:
`bash lang_pack/install_lang.sh fr`.

### By hand (any platform)

```bash
python setup_lang.py install --lang fr   # install the pack, activate fr
python setup_lang.py verify              # in-situ LPC proof (see §3)
python setup_lang.py show                # current language
```

`install` copies the thirteen profile modules into
`vtl_synth/utils/` (v1.0.8 adds the expressive-prosody pair
`chunking.py` + `prosody_f0.py`, option — default OFF), the lexicons
into `vtl_synth/data/` (never
overwriting existing files), integrates the language-aware
`Pipeline` (originals backed up once as `.bak`), and rewrites the
managed LANG SECTION of `vtl_synth/core/constants.py`.
It is idempotent — re-running it refreshes the installation.

After installation, switch languages at will (reversible,
byte-identical round trip):

```bash
python setup_lang.py setlang en         # en|fr|es|de|it|pt
python setup_lang.py list
python setup_lang.py restore --purge    # full, residue-free uninstall
```

## 3. Reading `verify` — expected scores

`verify` synthesizes every vowel of the active language through the
real engine (JD3), measures F1/F2 by LPC on the produced audio, and
compares them with the language's reference formants
(literature values, male speaker). A vowel passes when both formants
are within **±30 %**. Compare your `Bilan` line with:

| language | expected `Bilan` | notes |
|---|---|---|
| en | 4/8 (measured 2026-09-15) | original calibration — formally covered by the 62 regression baselines, not the LPC chain |
| fr | 4/12 | v1.0.6 "validated" block under the current measurement chain (see the bias below) |
| es | 6/7 | /i/: F2 ceiling ≈1300 Hz on this engine — flagged HYPOTHESIS |
| de | 10/14 | lax and front-rounded vowels: F1 measured low (LPC bias) |
| it | 4/7 | F1 bias on close vowels; /o/ at the engine limit |
| pt | 5/8 | /o/, /u/ at the tolerance edge — flagged HYPOTHESIS |

A healthy installation reproduces these scores within ±1 verdict
(LPC jitter). Far below (e.g. 2/7 for es) = broken installation:
check `python setup_lang.py show`, the VTL bindings
(`python -c "import vocaltractlab_cython"`) and the JD3 speaker
file — not the calibration.

**The documented LPC bias.** The LPC chain measures **F1 too low on
close and rounded vowels** (fr /i/: 210 Hz measured vs 280 expected)
and is occasionally unstable between runs on front-rounded vowels and
the German schwa (F2 of /@/: 1484 then 896 Hz at an identical
target). These are measurement artifacts, documented per vowel in the
comments of the language blocks — the measured F1/F2 travel with the
constants. Any target that was never measured in situ is flagged
`HYPOTHÈSE` in those comments.

## 4. Missing lexicons

The five TSV lexicons ship in `lang_pack/lexicons/`. If one is
missing (e.g. not committed to save space), download it — the g2p
also works without it (rules + exceptions, with a warning):

```bash
curl -L -o vtl_synth/data/fr_lexicon.tsv \
  https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/fra_latn_broad_filtered.tsv
curl -L -o vtl_synth/data/es_lexicon.tsv \
  .../spa_latn_ca_broad_filtered.tsv    # Castilian (distinción)
curl -L -o vtl_synth/data/de_lexicon.tsv \
  .../deu_latn_broad_filtered.tsv
curl -L -o vtl_synth/data/it_lexicon.tsv \
  .../ita_latn_broad_filtered.tsv
curl -L -o vtl_synth/data/pt_lexicon.tsv \
  .../por_latn_po_broad_filtered.tsv    # European Portuguese
```

(`...` = the same URL prefix; branch **master** of CUNY-CL/wikipron.
Variants: `spa_latn_la` = Latin-American seseo, `por_latn_bz` =
Brazilian.) Beware the classic error: saving the GitHub *page*
instead of the **raw** file gives HTML — a file much smaller than
the expected size (fr ~2.6 MB, es ~3.9 MB, de ~2 MB, it ~2.6 MB,
pt ~1.6 MB) is suspect. License: CC BY-SA 3.0 — keep the
`README_xx_lexicon.md` notices (see LICENSE.md).

## 5. Windows: console encoding

**Symptom.** Accented text passed to the synthesizer on Windows
comes out wrong: UTF-8 decoded with the active OEM code page
("corée" turns into mojibake) and the French g2p then emits engine
keys from the corrupted string — the canonical observed output is
`kOR.@` instead of `koRe.@`.

**Two invariants** (both documented in `install_lang.bat` itself):

1. `chcp 65001 >nul` must be the **first command** of any Windows
   batch that passes text to the pipeline (right after `@echo off`).
   It is in place in `install_lang.bat` and `launch.bat`; keep it
   there when editing those files.
2. The `.bat` files must stay encoded **UTF-8 without BOM** (a BOM
   breaks the `@echo off` line).

Reading this section is the one-minute diagnosis of the
`kOR.@`-class symptoms.

## 6. Documentation

- **User manual** — `manual/manual.tex` (compile with pdflatex;
  figures are pre-generated in `manual/figures/`): installation,
  the vowel geometry (ρ, θ) and why targets do not transfer between
  languages, calibration (`calibrate --in-situ`), adding a new
  language, licensing, troubleshooting.
- **Architecture** — `ARCHITECTURE.md`: origin of every component,
  the install/switch/uninstall mechanics, the engine-side touch
  points.
- **Licensing** — `LICENSE.md`: GPL-3.0-or-later code + CC BY-SA 3.0
  Wikipron data, per-component provenance table.

## 7. Compatibility

- The root CLI is unchanged (`setup_lang.py install|setlang|
  calibrate|verify|show|list|restore`) — existing scripts, including
  `launch.bat`, keep working.
- If `lang_pack/` is absent, `setup_lang.py` falls back to the
  legacy zip-pack layout (`../modules`, flat five-module set,
  fr/en blocks): users of the existing covtl-language-pack zip are
  not broken.

## 8. Multi-speakers repository (this fork)

This copy of the pack lives in the **multi-speakers** covtl-pipeline
(`install_speaker.py`, registry `vtl_synth/data/speakers/`). The two
installations are **independent dimensions**:

- **Speaker switch carries the language over.** `install_speaker.py
  install s1|s2|…` replaces `constants.py` wholesale, then re-injects
  the managed LANG SECTION into the new speaker constants. Warning:
  the pack's vowel targets are calibrated **in situ on JD3** — any
  other speaker + pack language combination is a HYPOTHÈSE (flagged
  in `install_speaker.py status`).
- **Language switch restores JD3 first.** `setup_lang.py
  setlang|install|calibrate|verify` run a guard
  (`_ensure_jd3`) that reinstalls the `jd3` speaker whenever another
  one is active, before touching the LANG SECTION.
- **Coherence checks are canonical.** `speaker_registry` compares
  constants hashes with the vowel/language region neutralized
  (`canonical_hash12`), so an installed language never shows as a
  speaker INCOHERENCE.
- **`setup_lang.py restore` is speaker-aware.** It re-injects the
  *native* vowel block of the currently active speaker (registry
  source), not a possibly stale `.bak` — the speaker and language
  restores never interfere.
- **`integration/pipeline.py` is a merged version** (multi-speaker
  D14 `f0_hz=None` → active speaker's `f0_default` + `announce()`,
  plus the multilingual dispatch). The CLI gains `-l/--lang` and
  profile-based timing defaults, and degrades gracefully when the
  pack is not installed. The engine-side fixes (`syltraj.py`
  schwa/nasal, `phonemes.py` `cluster_onset`) are applied at
  repository level — they are behaviour-neutral for the monolingual
  regression baselines (72/72 tests pass at native state, and after
  `restore --purge`).

Known by-design behaviour: with a pack language active, the 6
`test_regression_baselines` tests fail (the vowel targets differ from
the captured JD3-native baselines); `setup_lang.py restore --purge`
brings them back to green.
