# P6 — Multilingual extension of the V1V2 validation (status 2026-11-02)

Mission §7 executed. The `nasal_preproc` gate is **language-agnostic**;
the validation now covers the full pack.

## 1. Portuguese — dedicated corpus (`corpus_v1v2_pt.json`, results `results_pt/`)

Same structural typology as French, real items from the lexicon and
from the `g2p_pt` rules:

| id | situation | text | engine SAMPA | hiatus | nasal VO | nasality lost |
|----|-----------|-------|--------------|--------|---------|-----------------|
| S1a | inter-word nasal→oral | acauã ele | `@.kaw@~.e.l@` | `@~.e` | 0.489 | no |
| S1b | inter-word nasal→oral | atum a | `@tu~.a` | `u~.a` | 0.489 | no |
| S2a | inter-word oral→nasal | ele um | `e.l@.u~` | `@.u~` | 0.489 | no |
| S2b | inter-word oral→nasal | ele hã | `e.l@.@~` | `@.@~` | 0.489 | no |
| S3a | intra-word oral→nasal | neon | `neo~` | `e.o~` | 0.489 | no |
| T1 | intra witness V.V oral | país | `p@.is` | `@.i` | −0.1 | — (oral) |
| T2 | inter witness V.V oral | ele ama | `e.l@.a.m@` | `@.a` | −0.1 | — (oral) |
| T3 | isolated nasal witness (final plateau) | irmã | `iRm@~` | — | ref 0.495 | — |
| T4 | non-hiatus nasal witness (diphthong) | sem | `s@~j` | — | ref 0.489 | — |
| T5 | complement V~.V~ | afim um | `@fi~.u~` | `i~.u~` | 0.5 | no |
| T6 | complement V~.V~ | atum hum | `@tu~.u~` | `u~.u~` | 0.5 | no |
| T7 | dedicated nasal-diphthong witness | cão | `k@~w` | — | ref 0.489 | — (unchanged) |
| H0–H4 | engine minimal pairs | ta.ata … kOma~.a.le.vu | direct | full typology | 0.489–0.5 | no |

French criteria met: VO ≥ 0.489 on the nasal halves (threshold 0.3–0.4);
oral witnesses at VO = −0.1; `nasalite_perdue` = false everywhere.

**Documented pt peculiarity**: `g2p_pt` never emits V~.V intra-word
(0 occurrences out of 35,690 lexicon words — a nasal vowel is never
adjacent to an oral vowel there); intra-word situation S4 is therefore
covered by the H items in direct SAMPA (as planned in §7.1). The
inter-word junction of `g2p_pt` is indeed the liaison point (`acauã ele`
→ `@.kaw@~.e.l@`).

## 2. Inertia for es / it / de / en (`p6_multilingue.py`, `results_p6/inertie.json`)

| language | g2p without `~` | lexicon without `~` | bit-exact active/neutral | inert |
|--------|--------------|------------------|------------------------|--------|
| es | yes (2 texts) | yes | yes (wav + tract md5) | **yes** |
| it | yes | yes | yes | **yes** |
| de | yes | yes | yes | **yes** |
| en | yes (ARPAbet) | n/a (CMUdict) | yes | **yes** |

The gate is **structurally inert** on languages without a phonemic nasal
vowel, and the defensive coverage is documented: if a future lexicon or
manual SAMPA introduces `~`, the engine handles the switch (that is the
purpose of the fix) instead of losing nasality.

## 3. Engine inventory

`phonemes.SAMPA_VOWELS` (= keys of `VOWEL_TARGETS`) covers the nasal keys
of **all** languages (fr: `a~ e~ i~ o~ u~ y~ 2~ 9~ O~ @~` ;
pt: `@~ o~ e~ a~ u~ i~`…) — verified by `p6_multilingue.py`
(`inventory_coverage`, `tout_couvert = True`), cross-checked with
`language_vowel_sets.py`.

## 4. Tests

`tests/test_nasal_preproc.py` extended (`TestP6Portuguese`): nasal
diphthong `k@~w` (plateau path, inert gate), inter-word hiatus
`@~.e` / `@.u~` (oralization + capture), final `@tu~` plateau unchanged,
inertia on engine-normalized es/it/de/en samples. 38/38 green.

## 5. Harness

`run_corpus.py` parameterized: `--lang` (Pipeline + results folder
`results_<lang>`, fr stays in `results/`), `--corpus` (dedicated JSON
file), `--no-preproc` (gate neutralized — inertia proof /
before-after per item).
