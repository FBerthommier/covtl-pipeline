# IMPLEMENTATION V1V2 — Engine fix: nasal/oral toggle on linked hiatuses

**Date:** 2026-10-31 · **Repository:** `covtl-pipeline` clone (base: audit chain, HEAD `0f935b8`)
**Follows:** `AUDIT_V1V2/AUDIT.md` (findings) and `AUDIT_V1V2/MISSION.md` (specification)

---

## 1. Prescribed and adopted principle

> *Leave intact the elaboration of the parametric space by `syltraj`; convert
> the nasal vowels into non-nasal ones so as to obtain the base diphthong
> transitions; introduce the nasality information at the level of the existing
> orthogonal control space of the velar port and of its associated timer.*
> **Non-perturbing** implementation, by way of a **preprocessing layer**.

The adopted architecture factors nasality out of the formantic space:

```
SAMPA input (with '~') ──┬──────────────────────────────► segments / labels /
                         │                                timers / pulmonary effort
                         │                                (ORIGINAL chain, unchanged)
                         │
                 ┌───────▼────────┐        ┌──────────────────────────┐
                 |  nasal_preproc |  plan   │  syltraj (INTACT)        │
                 |  (preproc.)    │───────►│  ORALIZED engine chain   │
                 |  split          │        │  → Pval, block_info      │
                 └───────┬────────┘        └──────────┬───────────────┘
                         │  nasality events            │ background blocks
                         │  (vocalic runs,             │ (2·T_voy arcs)
                         │   positions, targets)       │
                         └───────────┬─────────────────┘
                                     ▼
                 ┌────────────────────────────────────────────────┐
                 │ build_phrase_tract — step 3b-bis (NEW)         │
                 │ VO ⊇ 0.5 ramp (20 %) over the nasal halves     │
                 │ then EXISTING TIMER: 1st-order smoothing τ=20ms│
                 └────────────────────────────────────────────────┘
```

Key points:

1. **`syltraj.py` is not modified** (empty diff). The hiatus background arc
   (`background`, 2·T_voy) **is** the base diphthong transition — it is
   built on the oral polar targets, which is already the engine's internal
   representation (a nasal = oral target + flag, cf. `build_nodes`:
   `base = key.rstrip('~')`).
2. **Preprocessing layer** (`vtl_synth/core/nasal_preproc.py`, new): the nasal
   vowels that are **members of a hiatus** (adjacent vocalic sequence of
   length ≥ 2, across or without a linking dot) are **oralized in the engine
   chain**; nasality is captured as an **event** (run,
   position, oral target). The oralization is **surgical**: held nasal
   vowels (outside a hiatus) keep the existing path (plateau + `nasal`
   flag) — they already work.
3. **Orthogonal reinjection** (`build_phrase_tract.py`, step 3b-bis, ~25
   lines): the nasality of hiatus members is applied in the existing **VO**
   extension — same target (`VO_NASALIZED_VOWEL` = 0.5), same symmetric
   20 % ramps (max 40 ms) as the nasal-plateau path — then
   **the existing velar timer** (first-order anti-click smoothing,
   τ = 20 ms) shapes the nasal↔oral toggles. No other channel is
   modified: B(t) (15 parameters), E(t), V(t), glottal source remain those
   of the oral base.

## 2. Files

| File | Nature | Content |
|---|---|---|
| `vtl_synth/core/nasal_preproc.py` | **new** | Preprocessing layer: `split_nasal_hiatus()` (split + plan), `nasal_hiatus_intervals()` (temporal localization), `vo_nasal_segment()` (ramp), `get_last_nasal_plan()` (state, `get_last_build` pattern) |
| `vtl_synth/core/build_phrase_tract.py` | modified (3 insertions) | (1) split before `build_phrase_pval` — the engine receives `ipa_motor`; (2) `nasal_plan = None` for the `legacy` engine; (3) step 3b-bis: VO overlay before the τ = 20 ms smoothing |
| `vtl_synth/core/syltraj.py` | **not modified** | — |
| `tests/test_nasal_preproc.py` | **new** | 33 tests: scope of the oralization, tokenizer round-trip, intervals (halves, V~.V~ fusion, VVV runs), ramp, nasality after synthesis, non-perturbation, parametric-space identity |
| `AUDIT_V1V2/run_corpus.py` | modified | verdict on the ORIGIN nodal view (true flags) + VO measurement on the **actual nasal halves** of the plan (the old "central half-window" metric did not see the last half of VVV runs) |
| `AUDIT_V1V2/compare_avant_apres.py` | **new** | before/after verification: VO the only modified column, bit-identical controls, inversion of the H0-H3 byte identity, WAV pairs for listening |
| `AUDIT_V1V2/results_avant/` | **new** | archive of the failing state ("before" reference) |
| `AUDIT_V1V2/results/` | regenerated | fixed state + `compare_avant_apres.json` |
| `AUDIT_V1V2/wav_compare/` | **new** | before/after WAV of each item for comparative listening |

## 3. Temporal localization (runs ↔ `background` blocks)

The mapping relies on a structural invariant of the engine, **verified at
every run** (otherwise conservative fallback — warning, no injection):

- each **internal pair** of a vocalic run emits exactly one
  `background` arc of 2·T_voy (the schwa split into two blocks preserves the
  total); runs of length k produce (k−1) **consecutive** arcs;
- two distinct runs are always separated by at least one non-`background`
  block (cluster, pause, decay…);

therefore: **g-th run ↔ g-th group of consecutive `background` blocks**,
expected total (k−1)·2·T_voy. Member j of the run owns the slot
[j·T, (j+1)·T) (first member of pair j), extended by [(2j−1)·T, 2j·T)
(second member of pair j−1) — medial vowels of VVV runs thus have
2·T_voy, in line with the time allocated by the engine.
**Adjacent nasal slots are merged**: the nasal/oral toggle only
occurs at true nasal↔oral boundaries (`9~.a~`: velum open from one
end of the arc to the other).

Effective T_voy: `t_voy` parameter replicated as in `build_phrase_pval`,
cross-checked with the step counts of the `plateau` blocks and the total of the groups (defense in
depth).

## 4. Measured results (full corpus, 20 items)

| Acceptance criterion (MISSION §1) | Result |
|---|---|
| Realized nasality: `max(VO)` over the nasal halves ≥ 0.4 | **0.491 – 0.500** (healthy reference 0.49-0.50) — S1a→S4b, T5, T6, H1-H4 |
| VO falls back on the oral half | descending ramp completed at the slot boundary + τ = 20 ms → −0.1 baseline |
| `ta~.ata` ≠ `ta.ata` (md5 .wav/.tract) | **4 distinct md5s** for H0/H1/H2/H3 (the audit's byte identity §4.5 is broken) |
| Non-regression | repository suite: **188 passing** (155 before + 33 new); the 3 failures pre-existing at the audit state (speaker hash + `test_syltraj_double_pause`: SHA locked to commit `48442aa9`, invalidated by the earlier D-11 fix `511cf2e`) are unchanged |
| Non-perturbation | **5 bit-identical controls** (T1, T2, T3, T4, H0); for the 15 fixed items, **only the VO column (7) of the `.tract` differs** — proof that the parametric space is intact |
| `nas.lost` | **20/20 "no"** (before: 15 "YES") |

Verification outputs: `AUDIT_V1V2/results/compare_avant_apres.json`
(machine-readable) and `AUDIT_V1V2/wav_compare/{avant,apres}/*.wav` (listening;
compare e.g. `avant/H1.wav` — denasalized "ta~.ata" — and `apres/H1.wav`).

## 5. Re-verification (commands)

```bash
python AUDIT_V1V2/run_corpus.py            # table: nas.lost = no everywhere
python AUDIT_V1V2/compare_avant_apres.py   # GLOBAL VERDICT: SUCCESS
pytest tests/test_nasal_preproc.py -q      # 33 passed
pytest tests/ -q                           # 188 passed, 3 pre-existing
```

## 6. Architecture choices worth noting (for the agent)

1. **The MISSION's "labeled blocks" criterion (P1) is superseded** by the
   prescribed principle: the background arc **remains** the realization of
   the hiatus nuclei (base diphthong, measured: energy and formants present);
   there is **no** split into two `T_voy` half-blocks. The mission
   asked for "one labeled block per member" as a means of transporting the
   nasal flag; the preprocessing layer now transports this
   information outside the engine, without modifying it.
2. **Surgical oralization (hiatus only).** Oralizing held vowels too would
   have redirected the plateau path (which works)
   toward the new layer: gratuitous perturbation. The adopted scope is
   the smallest set that covers the defect.
3. **Original chain preserved everywhere else**: `parse_to_segments`
   (glottal/velar labels, `TimedEnvelope`, pulmonary effort —
   "nasality requires continuous airflow") still sees the '~';
   only the input of `build_phrase_pval` is oralized.
4. **Guaranteed conservative fallback**: any deviation in the tokenizer
   round-trip or in the runs↔groups mapping disables the injection (warning
   `nasal_preproc`) and restores the previous behavior — the fix can
   never produce an unexpected chain or output.
5. **Uncovered paths** (documented, no effect on synthesis):
   `engine='legacy'` (deprecated) and the video instrumentation
   (`video/polar_video.py`, which calls `build_phrase_pval` directly)
   do not go through the gate. The repository's regression baselines do
   not change (no engine output outside a nasal hiatus is modified —
   verified bit by bit on the 5 controls).

## 7. Recommended follow-ups (carry over MISSION §2 P3/P4 and the new instructions §6-§7)

- **P3 (residual)** — after validation: fix `phonemes.py:38`
  (`SAMPA_VOWELS` must include the nasal keys — "néon" must come out
  syllabified as `ne.O~` and "envie" as `a~.vi`); record in the CHANGELOG.
  **The re-reversion clause for the g2p workarounds (`dea71c6`,
  `f62f185`) is CANCELLED**: see MISSION §6 (P5) — the removal is
  definitive, the "linking dot everywhere" state must be kept.
- **P5 — decommissioning** (MISSION §6): definitively remove the
  modifications that have become unnecessary (g2p/prosody workarounds), sweep
  the documentary residues, record the definitive character in the CHANGELOG.
- **P6 — other languages** (MISSION §7): extend validation to the full
  pack — Portuguese first (corpus `corpus_v1v2_pt.json`, harness
  parameterized by language), inertia proof for es/it/de/en,
  `phonemes.py` inventory covering the nasal keys of all languages.
- Update the outdated SHA of `test_syltraj_double_pause` (pre-existing,
  see §4) when regenerating the baselines
  (`scripts/regen_baselines.py`).
- Optional: physiological velar anticipations (lowering of the velum
  during the prevocalic nasalized consonant) — outside the scope of the
  present fix, which reproduces exactly the plateau path's dynamics.
