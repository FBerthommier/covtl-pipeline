# ARCHITECTURE — the covtl-pipeline language pack (v1.0.7)

Where every component comes from, what `install` does to the
pipeline tree, and how the switching/uninstalling machinery works.
Licensing per component: see `LICENSE.md`; user-facing usage:
see `README.md` and `manual/manual.tex`.

## 1. Sources and destinations

| Pack location | Content | Installed to | Notes |
|---|---|---|---|
| `profiles/g2p.py` | English g2p (CMUdict → engine SAMPA, homograph resolver) | `vtl_synth/utils/g2p.py` | replaces the native module in place (no `.bak`: the pack version is a superset, kept on purge) |
| `profiles/g2p_fr.py` | French g2p v2 (lexicon → exceptions → rules) | `vtl_synth/utils/` | delegates lexicon loading to `lexicon_loader` |
| `profiles/g2p_fr_legacy.py` | French g2p v1 (rules only), kept for reference/comparison | `vtl_synth/utils/` | not imported by the registry |
| `profiles/g2p_{es,de,it,pt}.py` | Wikipron-lexicon + rules g2p per language | `vtl_synth/utils/` | three-stage cascade on the g2p_fr v2 model |
| `profiles/lexicon_loader.py` | shared Wikipron TSV loader (`LexiconSpec`: file, env var `$COVTL_XX_LEXICON`, IPA→keys table, variant policy) | `vtl_synth/utils/` | lazy, fault-tolerant (missing lexicon → rules only), cached |
| `profiles/language_vowel_sets.py` | per-language vowel inventories with reference F1/F2 (literature) | `vtl_synth/utils/` | drives `calibrate` and `verify` |
| `profiles/calibrate_vowels.py` | `find_best_rho`: ρ derivation on the VTL transfer function + LPC | `vtl_synth/utils/` | |
| `profiles/chunking.py` | expressive prosody (v1.0.8, option — default OFF): syntactic breathing, per-language function-word lists | `vtl_synth/utils/` | lexical heuristic, no parsing; used by `prosody_f0` |
| `profiles/prosody_f0.py` | expressive prosody: `ExpressivityProfile` per language, out-of-band word stress, sculpted F0 (pitch accents, per-chunk reset, nuclear fall) | `vtl_synth/utils/` | glottis f0 column + `%` breath pauses only — never the tract; f0_base = the active speaker's f0 |
| `profiles/setlang.py` | `LangProfile` registry: g2p + F0 contour + timings + notation aliases + `expressivity` | `vtl_synth/utils/` | six built-in profiles; extensible at runtime |
| `integration/pipeline.py` | patched orchestrator: `Pipeline(lang=..., expressive=...)`, F0 declination per profile (monotone) or expressive prosody (option, default OFF), language-aware g2p dispatch | `vtl_synth/core/pipeline.py` | original backed up once as `.bak` |
| `integration/utils__init__.py` | patched package init re-exporting the multilingual API | `vtl_synth/utils/__init__.py` | original backed up once as `.bak` |
| `lexicons/*.tsv` | Wikipron pronunciation lexicons (CC BY-SA 3.0) | `vtl_synth/data/` | copied only if absent — never overwrites |
| `lexicons/README_xx_lexicon.md` | per-language provenance notices | `vtl_synth/data/` | must travel with the TSVs |
| `lang_blocks/blocks.py` | **single source of truth** for the per-language LANG SECTION fragments (ACTIVE_LANG + VOWEL_TARGETS (ρ, θ) + VOWEL_EFFORT_GAIN, with the in-situ proof comments: measured F1/F2, verdicts, HYPOTHÈSE flags) | — (read by `setup_lang.py` via importlib) | self-contained, no imports; markers must match `setup_lang.py` |
| `install_lang.bat` / `install_lang.sh` | one-command installers (deps check → install → verify → show) | — | see README §5 for the Windows encoding invariants |
| `manual/` | LaTeX user manual + `figures/make_figures.py` (figures generated **from** `lang_blocks/blocks.py`, so they cannot drift from the constants) | — | |

## 2. What `install` does (4 steps)

1. **Profile modules** — copies the thirteen `profiles/*.py` into
   `vtl_synth/utils/` and writes the module manifest
   `.lang_pack_manifest` listing every installed module except the
   native `g2p.py`. The manifest is the purge list: a re-install
   refreshes it, so `restore --purge` always uninstalls completely.
2. **Pipeline integration** — backs up (`*.bak`, one time only) then
   replaces `core/pipeline.py` and `utils/__init__.py` with the
   language-aware versions.
3. **Lexicons** — copies `lexicons/*` into `vtl_synth/data/` if
   absent (never overwrites). The data manifest
   `.lang_pack_data_manifest` records only the files the install
   itself brought in (or that a previous install owned and that still
   byte-match the pack): repository-tracked lexicons are never
   claimed, so `--purge` never deletes repo files.
4. **LANG SECTION** — backs up `constants.py` (once), then replaces
   the region between the `# === LANG SECTION` markers (or, on first
   intervention, the original static `VOWEL_TARGETS` /
   `VOWEL_EFFORT_GAIN` block) with the fragment of the target
   language from `lang_blocks/blocks.py`.

## 3. Switching and reversibility

- `setlang xx` re-renders the managed section from the block of `xx`:
  switching is a pure template rewrite, hence the byte-identical
  round trip (`fr → xx → fr` leaves `constants.py` unchanged —
  covered by `tests/test_multilang.py::test_lang_switch_roundtrip_no_residue`
  and by the CLI round-trip over the six languages).
- `restore` puts the `.bak` files back; `--purge` additionally
  removes the manifest-listed modules and pack-owned lexicons.
- Every `setup_lang.py` command prints the currently active language.

## 4. Engine-side touch points

The language machinery deliberately stays **outside** the engine
core. Two touch points exist:

1. **The managed LANG SECTION of `constants.py`** — the only engine
   file whose *content* changes per language (vowel targets + effort
   gains), between explicit markers.
2. **One bug fix in `core/syltraj.py`** (`_vv_waypoint`): when the
   active language has no `'@'` schwa target (Italian, Spanish), the
   closing vowel–vowel arcs fall back to the neutral anchor
   (`NEUTRAL_RHO/NEUTRAL_THETA` — which *is* the schwa by
   definition) instead of raising `KeyError '@'`. This fix is
   engine-level, applied once, and required by any schwa-free
   language; it is not reverted by `restore`.

The **JD3 speaker** and **`vtl_binaries/`** are never modified, and
the pack ships no binary; the full provenance boundary is defined
in `LICENSE.md` §2.

## 5. Pack resolution and the legacy layout

`setup_lang.py` resolves the pack in this order:

1. explicit `--pack DIR`;
2. `$COVTL_LANG_PACK`;
3. `lang_pack/` at the repository root (layout detected by
   `profiles/setlang.py` or `lang_blocks/blocks.py`);
4. legacy fallback `../modules` (flat layout of the
   covtl-language-pack 1.0.0 zip: five modules at the pack root, no
   lexicons, no blocks).

`LANG_BLOCKS` (the per-language fragments) are loaded at import time
from the resolved pack's `lang_blocks/blocks.py`; the legacy layout
has none, so `setup_lang.py` carries fr/en **fallback blocks** —
kept identical to the pack entries by
`tests/test_multilang.py::test_fallback_blocks_match_pack`. With the
legacy pack, the CLI therefore offers `fr`/`en` only, exactly like
the v1.0.0 zip pack did.

## 6. The g2p chain (shared by fr/es/de/it/pt)

```
orthographic text
   │
   ▼  lexicon (absolute priority: Wikipron TSV via lexicon_loader;
   │  $COVTL_XX_LEXICON overrides; auto-detect engine keys vs IPA;
   │  IPA→keys conversion, de-spacing of phones for diphthongs;
   │  variant policy: 'short' for fr, 'grapheme' for es/de/it/pt)
   ▼  exceptions (built-in dictionary of frequent irregulars)
   ▼  contextual rules (the language's grapheme rules)
   │
engine SAMPA  (conventions: '~' = nasal on the oral base,
   rhotic R, uvular X / palatal C fricatives, velar L;
   '|' = phrase break, '.' = syllable link)
```

Wikipron pitfalls handled once and for all in the loader: branch
**master** (not main); space-separated phones (de-spaced before
diphthong conversion); decomposed nasals (two-character entries);
Wiktionary clitic variants resolved by the variant policy; Tuscan
`ə` mapped to `e` (Italian has no `@` engine key); dialect splits
`spa_latn_ca`/`spa_latn_la` and `por_latn_po`/`por_latn_bz` (the
pack installs Castilian and European).

## 7. Calibration data flow

```
language_vowel_sets[xx]  (reference F1/F2, cardinal θ, corners, schwa)
   │
   ▼  find_best_rho   (static: ρ sweep on the VTL transfer function + LPC)
   ▼  refine_in_situ  (real synthesis per candidate ρ + LPC measurement;
   │                  criterion ALIGNED with verify: minimize the number
   │                  of formants outside ±30 %, then max relative error)
   ▼
LANG SECTION fragment (lang_blocks/blocks.py) — measured F1/F2 and
verdicts written as comments next to each target (the proof travels
with the constants); unmeasured targets flagged HYPOTHÈSE.
```

`verify` closes the loop on the installed tree: per vowel of the
active language, synthesize (SAMPA direct, JD3) → LPC → compare to
the reference formants at ±30 % → `Bilan : N/M`. Expected scores and
the documented LPC bias (F1 measured low on close/rounded vowels;
occasional instability on front-rounded vowels and the German
schwa): see `README.md` §3.
