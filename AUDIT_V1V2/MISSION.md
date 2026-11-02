# MISSION — Engine fix: nasal/oral toggle on linked V1V2 hiatuses

**STATUS (2026-10-31): FIX DELIVERED** — see `IMPLEMENTATION_V1V2.md`:
the prescribed principle (syltraj intact + preprocessing layer + nasality
in the existing orthogonal VO/timer space) is implemented and validated
(20/20 items, VO 0.49-0.50, bit-identical controls, 33 unit tests).
The "labeled blocks" criterion of §1 is superseded by the adopted
architecture, §6.1 of the implementation report. **Remaining for the
agent (instructions of 2026-10-31, after delivery of the fix)**: **P5** —
definitively decommission the modifications that have become unnecessary
(§6 below; **cancels the re-reversion clause of P3**); **P6** — extend
the treatment to the other languages of the pack (§7); and the P3 residual
(nasal keys `phonemes.py:38`, pre-existing SHA of
`test_syltraj_double_pause`).

**Recipient:** agent in charge of modifying the synthesis engine.
**Working repository:** this `covtl-pipeline` clone (state: HEAD = `9cdc852`; the fix is commit `304f04c`, the audit folder is `1b81aef`, the revert that exposed the defect is `2a55b69` — see §6 for the definitive status of workarounds `dea71c6` + `f62f185`).
**Mandatory prerequisite reading:** `AUDIT_V1V2/AUDIT.md` (findings, mechanism, proofs) — especially § 4.2 (mechanism), § 6 (proposed fix), Appendix B (files/lines).

---

## 1. Objective

Make the `syltraj` engine **articulate the nasal/oral toggle across a linked V1.V2 boundary** (linking dot or direct adjacency), in the four situations:

1. inter-word V~.V (e.g. `kOma~.a.le.vu`);
2. inter-word V.V~ (e.g. `i.a.a~vi`);
3. intra-word V.V~ (e.g. `neO~`, `eO~.te`);
4. intra-word V~.V (e.g. `a~aR.diR`, `a~y.Se`).

Measurable acceptance criteria (carried over from the audit harness):

- [ ] For each item S1a→S4b of the corpus (`AUDIT_V1V2/corpus_v1v2.json`), the articulation plan contains, for each member of the hiatus, a labeled block (`vowel_key` defined) — no more anonymous `background` block of `2·T_voy`.
- [ ] Nasality is realized: `max(VO)` over the nasal half(ves) of the hiatus ≥ 0.4 (healthy reference: ≈ 0.49–0.50); VO falls back to ≤ 0 on the oral half (V~.V and V.V~ cases).
- [ ] `ta~.ata` and `ta.ata` produce **different** `.wav`s (the current byte identity — AUDIT.md § 4.5 — is the exact inverse of success).
- [ ] Non-regression: repository test suite at least as green as before the change (207 passing engine tests announced at `dea71c6`), and unchanged outputs for inputs without nasal hiatus if the conditional variant of P1 is adopted.

## 2. Proposed fix (minimal and reversible)

- **P1 — `vtl_synth/core/syltraj.py`, `m == 0` branch of `build_global_pval` (≈ lines 1019-1024)**: split the hiatus background arc into two `background` blocks of `T_voy` each (global arc preserved: build it whole, then cut it in two), carrying the `vowel_key` and `nasal` of V1 and V2 respectively. Conditional split ("at least one nasal member") recommended for non-regression; systematic split acceptable if the baselines are regenerated and documented.
- **P2 — `vtl_synth/core/build_phrase_tract.py`, line 845**: extend the application of the VO ramp to `background` blocks carrying the nasal flag (`kind in ('plateau', 'background')`). The existing anti-click smoothing (τ = 20 ms) handles the transition between halves.
- **P3 — after validation**: re-revert the g2p workarounds (`dea71c6`, `f62f185`) to return to the linking dot everywhere; fix `phonemes.py:38` (`SAMPA_VOWELS` must include the nasal keys — currently "néon" comes out as `neO~` without a dot and "envie" as the monosyllable `a~vi`); record in the CHANGELOG.
- **P4 — tests**: unit tests on `build_phrase_pval` (flags of the half-arcs), on VO after synthesis, and non-regression of the baselines (see AUDIT.md § 6/P4 for the exact list).

## 3. Verification protocol (commands)

```bash
# environment (Linux) — see AUDIT.md § 7 for details
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr

# before/after the change:
python AUDIT_V1V2/run_corpus.py            # regenerates results/ + summary table
python AUDIT_V1V2/compare_head_g2p.py      # accessory check (g2p SAMPA)
pytest tests/ -q                           # repository suite
```

The table produced by `run_corpus.py` must show `nas.lost = no` for S1a→S4b (and T5/T6), with `VO h.c. ≈ 0.4-0.5` on the nasal halves. The original WAVs (failing state) are archived in `AUDIT_V1V2/results/wav/` — do not overwrite them without saving them first (they serve as the before/after reference; copy the folder to `wav_avant/` before any regeneration).

## 4. Guardrails

- Do not modify the g2p to mask the engine (that is what the audit revert is about); do not touch the polar targets of the vowels (the nasal shares the target of its oral counterpart — nasality lives exclusively in the VO extension).
- Preserve the total duration (`2·T_voy`) and the trajectory of the arc (splitting, not recomposition).
- Any baseline drift must be justified and regenerated via `scripts/regen_baselines.py` with a CHANGELOG mention.
- Suggested delivery format, in the spirit of the repository: committed patch(es) with a detailed message + CHANGELOG update + tests.

## 5. Useful context, one line per file

`syltraj.py` = syllabic walk (nodes → anchors → blocks); `build_phrase_tract.py` = assembly of E/V/VO from the blocks; `amplitude_envelope.py` = E(t) per block (background → E=1); `phonemes.py` = inventory + syllabification; `constants.py` = targets, `TAG_TO_VO_TARGET['nasalized']=0.5`; `pipeline.py` = text→SAMPA→tract→wav orchestration. The `.tract` file has 30 columns (19 tract + 11 glottis), **VO = column 7**, frames at 400 Hz.

---

## 6. P5 — Definitively decommission the modifications that have become unnecessary

**Rationale.** The engine fix `304f04c` makes obsolete the
workarounds of that era that existed to mask the defect. These changes
have become unnecessary: they must be **definitively removed**
from the deliverable.

1. **Cancellation of the re-reversion clause of P3.** The first part of
   P3 ("re-revert the g2p workarounds (`dea71c6`, `f62f185`) to
   return to the linking dot everywhere") is **cancelled and replaced by
   this section**: the "linking dot everywhere" state is already that of
   the tree (the revert `2a55b69` restored it) and must remain
   **definitive**.
   Never re-apply `dea71c6` (short pause instead of the linking
   dot after a word ending in a nasal vowel, in `g2p_fr`) nor `f62f185`
   (same rule in the expressive prosody enrichment).
2. **Status of the revert `2a55b69`.** Its message motivates it by the
   exposure of the defect ("until the engine is fixed") — this rationale
   is obsolete since `304f04c`. Record in the CHANGELOG that the removal of
   the workaround is **definitive** (superseded by the engine fix), and not a provisional
   audit state.
3. **Sweep of the residues** (docs and code): CHANGELOG entries from the
   workaround era describing the "known limitation" (hand-written V~.V dropped
   by build_phrase_pval) → mark as resolved by `304f04c`; check
   `MIGRATION_NOTES.md`, `PROVENANCE_PROSODY_CHUNKING.md`, the manuals
   (`lang_pack/manual/`) and the code comments; make sure that no
   copy of the workaround survives (installed copies `vtl_synth/utils/` ↔
   sources `lang_pack/profiles/` — currently in sync, keep them so).
4. **Out of scope.** `g2p_fr_legacy.py` is NOT dead code (v1 data source
   imported by `g2p_fr.py`) — do not delete it. The
   `engine='legacy'` engine (deprecated) and `video/polar_video.py` are documented
   uncovered paths (IMPLEMENTATION_V1V2 §6.5) — do not touch them here.
5. **Git history.** No rewrite requested: the chain
   `2a55b69` → `1b81aef` → `304f04c` documents the reasoning (provenance).
   The requirement bears on the **delivered tree**: it must not contain the
   workaround, and no future commit must reintroduce it.
6. **Guardrail.** After cleanup: re-verify non-perturbation (oral
   controls bit-identical before/after) and the test suite
   (`pytest tests/ -q`).

## 7. P6 — Extend the treatment to the other languages (de, en, es, it, pt)

**Architectural finding.** The `split_nasal_hiatus` gate acts on the SAMPA
chain at the input of `build_phrase_pval` — it is **language-agnostic**.
But all the validation (corpus, harness, tests) is French.
Extend the validation to the full pack.

1. **Portuguese — priority 1** (the only other language of the pack with
   phonemic nasal vowels: `@~ o~ e~ a~ u~ i~`, cf. `language_vowel_sets.py` and
   `g2p_pt.py` — "cão" `k @~ w`, "sem" `s e~ j`, "também"
   `t @~ b e~ j`, "axioma" `a k s j o~ m @`):
   - build `AUDIT_V1V2/corpus_v1v2_pt.json` on the same structural
     typology as French (S1 inter-word V~.V; S2 inter-word V.V~;
     S3 intra-word V.V~; S4 intra-word V~.V; isolated oral and nasal
     T controls; H pairs in direct SAMPA `ta~.ata`, `ta.a~ta`, …); real
     items of European Portuguese via `lang_pack/lexicons/pt_lexicon.tsv` and
     the `g2p_pt` rules; **include a dedicated nasal diphthong item**
     (e.g. "cão" alone → plateau path, VO ≈ 0.5 expected, unchanged
     before/after); when the typology has no natural lexical instantiation
     in pt, cover it with an H item (direct SAMPA) and document it; check the inter-word junction of `g2p_pt` (linking
     dot?) on real S1/S2 items;
   - parameterize `run_corpus.py` by language (`--lang`, dedicated corpus) or
     loop over the available corpora;
   - `python setup_lang.py install --lang pt && python setup_lang.py setlang pt`
     then run the harness;
   - criteria identical to fr: VO ≥ 0.4 on the nasal halves; oral
     controls **bit-identical** before/after; distinct md5s for the H pairs.
2. **Spanish, Italian, German, English — inertia proof** (no
   phonemic nasal vowels; pre-checked: `g2p_es`/`g2p_de` never emit
   `~`, the only `~` of `g2p_it` is a doc comment, English
   goes through ARPAbet without `~`):
   - sweep the g2p outputs of a sample of texts per language (and the
     `.tsv` lexicons): prove that `~` is never emitted → the gate is
     structurally inert;
   - bit-for-bit non-perturbation on an oral sample per language
     (outputs before/after `304f04c` identical);
   - document the defensive coverage: if a future lexicon or manual SAMPA
     introduces `~`, the engine handles the toggle instead of losing
     nasality.
3. **Engine inventory.** The P3 residual (`phonemes.py:38`, nasal keys
   in `SAMPA_VOWELS`) must cover the keys emitted by **all** the
   languages (fr: `a~ e~ i~ o~ u~ y~ 2~ 9~ O~ @~`; pt: `@~ o~ e~ a~`
   …) — cross-check `VOWEL_TARGETS` and `language_vowel_sets.py`.
4. **Tests.** Extend `tests/test_nasal_preproc.py`: pt cases (nasal
   diphthongs, inter-word boundaries), gate identity on inputs without
   `~` (es/it/de/en).
5. **Deliverables.** Results per language in `AUDIT_V1V2/results/`; CHANGELOG
   up to date; extension of the audit report (multilingual summary table);
   the harness must not overwrite the existing fr results.
