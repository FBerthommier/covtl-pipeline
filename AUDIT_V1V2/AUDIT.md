# AUDIT V1V2 — Coarticulation anomaly on V1.V2 hiatuses with nasal/oral toggle

**Audited engine:** `vtl-synth` (covtl-pipeline, Berthommier's COVTL articulatory model + VocalTractLab 2.4)
**Repository:** `github.com/FBerthommier/covtl-pipeline` — fresh clone, g2p workaround **removed** (revert commit `2a55b69`, reverting `dea71c6` + `f62f185`)
**Date:** October 31, 2026 · **Language tested:** French (fr pack, speaker `jd3`) · **Document intended for the agent in charge of fixing the engine.**

---

## 1. Executive summary

The syllabic synthesis engine (`syltraj`) **does not realize the coarticulated V1.V2 linkings when one of the two vowels is nasal and the other oral**. The defect was masked upstream by a recent change to the French g2p (commit `dea71c6`, completed by `f62f185` in expressive prosody) that inserts a **short pause** after any word ending in a nasal vowel. This workaround is partial: it only covers inter-word junctions ending in a nasal; it distorts the prosody (systematic pause); and it leaves the engine unable to handle the hiatus, including on manual SAMPA input — a limitation already recorded in the repository's CHANGELOG ("hand-written V~.V is still dropped by build_phrase_pval").

This audit, conducted on a **fresh clone where this workaround is removed**, demonstrates the defect on **all 4 requested situations** (nasal→oral and oral→nasal, intra-word and inter-word), with real French words:

| # | Situation | Audited example | SAMPA fed to the engine | Finding |
|---|-----------|----------------|------------------------|---------|
| S1 | inter-word, nasal→oral | "comment allez-vous" | `kOma~.a.le.vu` | BOTH the /a~/ and /a/ nuclei vanish from the plan; nasality lost |
| S2 | inter-word, oral→nasal | "il a envie" | `i.a.a~vi` | /a/ and /a~/ elided; "envie" denasalized |
| S3 | intra-word, oral→nasal | "néon", "éhonté", "paons" | `neO~`, `eO~.te`, `pao~` | /e/ and /O~/ elided; "néon" pronounced [neo] |
| S4 | intra-word, nasal→oral | "enhardir", "enhucher" | `a~aR.diR`, `a~y.Se` | /a~/ and /a/ elided; "enhardir" pronounced [anaʁdiʁ] |

**Formal proof**: the four hand-written minimal pairs `ta.ata`, `ta~.ata`, `ta.a~ta`, `ta~.a~ta` produce `.tract` and `.wav` files that are **identical byte for byte** (md5 `4f0698e3…` / `1c9c94b0…`). In other words, on a linked hiatus, **the engine completely ignores the nasality feature**: the velar opening (VTL parameter `VO`) stays at the floor −0.1 over the whole duration of the pair, whereas a healthy nasal plateau reaches +0.49 to +0.50 (`VO_NASALIZED_VOWEL = 0.5`).

**Note on "paon"** (word quoted in the order): the embedded Wikipron lexicon transcribes the singular "paon" as `p ɑ̃` — a **single** nasal vowel, no hiatus — and the g2p therefore produces `pa~`, which synthesizes correctly (healthy nasal plateau). It is the plural "paons", absent from the lexicon and transcribed by the rule-based path as `p a ɔ̃`, that produces the intra-word hiatus `pao~` (a.o~ junction) — item S3c, failing like the others.

The fix must be made **in the engine** (the `build_global_pval` walk + application of nasality in `build_phrase_tract`), not in the g2p: § 6 proposes an operational patch at two points, compatible with the coarticulation philosophy of the model (the hiatus remains a glided arc) and with the repository's non-regression requirements.

---

## 2. Context and scope

### 2.1 History of the problem

On October 30, 2026, commit `dea71c6` ("fix(g2p-fr): short pause instead of the linking dot after a nasal-vowel word ending") documents the anomaly observed on "comment allez-vous":

> "The syltraj walk cannot articulate the nasal/oral toggle across a linked boundary: on 'comment allez-vous' the G2P emitted `kOma~.a.le.vu` and the walk silently reduced `a~.a` to a background block, dropping BOTH the /a~/ and the /a/ from the articulation plan and from the audio (console compiler panel showed a '-' stretch; the polar display had no a label)."

The fix applied that day sits **in the g2p**: the inter-word junction switches from the linking dot (`.`) to a space (short pause) when the left-hand word ends in a nasal vowel. Commit `f62f185` extends the same rule to expressive prosody enrichment (`plan_expressive_text` was rebuilding the dotted junctions). The CHANGELOG keeps the known limitation: a `V~.V` hand-written at the engine's input is still elided, because the SAMPA guard cannot flag it (all symbols are valid).

### 2.2 Fresh audit clone

In accordance with the order, the audit is conducted on a clone where **this workaround is removed**, so as not to mask the engine defect:

- starting state: `41f6571` (HEAD of the repository on 10/30/2026, workaround present);
- audit commit: `2a55b69` — `git revert` of `dea71c6` and `f62f185`. The affected files are `vtl_synth/utils/g2p_fr.py`, `lang_pack/profiles/g2p_fr.py`, `vtl_synth/utils/prosody_f0.py`, `lang_pack/profiles/prosody_f0.py`; the unrelated fixes (integration-pipeline refresh `ff5090d`, utils synchronization `e50c348`) are **kept**;
- the g2p therefore again emits the linking dot everywhere: "comment allez-vous" → `kOma~.a.le.vu` (verified at runtime).

### 2.3 Audited processing chain

```
text ──> g2p_fr ──> SAMPA (linking dot '.') ──> build_phrase_tract
                                                ├─ tokenize_phrase (syltraj)
                                                ├─ build_flat / build_nodes / build_anchors
                                                ├─ build_global_pval  ──> blocks (plateau/cluster/background/pause…)
                                                ├─ E(t) (amplitude_envelope, from block_info)
                                                ├─ V(t), VO(t) (build_phrase_tract §3b, from block_info)
                                                └─ .tract 400 Hz (19 tract params incl. VO=col 7 + 11 glottis) ──> .wav 44.1 kHz
```

A vowel's nasality is not in its polar target (ρ, θ) — the target of a nasal is **its oral counterpart** ("nasality is the VO extension", `syltraj.py:694-696`) — but in the extension parameter `VO` (velar opening), driven by the blocks of the articulation plan. That is where the defect plays out.

---

## 3. Methodology

### 3.1 Corpus

Four situations × two or three items, with words **actually present in the embedded Wikipron lexicon** (the intra-word nasal→oral case, extremely rare, is covered by the "en-h" words with silent h: `enhardir` /ɑ̃.aʁ.diʁ/, `enhucher` /ɑ̃.y.ʃe/; the plural "paons", outside the lexicon, is added because the rule-based path produces the hiatus `a.ɔ̃` there), plus controls and hand-written minimal pairs injected directly as SAMPA at the engine's input (`use_g2p=False`):

| Id | Situation | Input | Type |
|----|-----------|--------|------|
| S1a/S1b | inter-word, nasal→oral | "comment allez-vous", "mon ami" | g2p |
| S2a/S2b | inter-word, oral→nasal | "il a envie" (requester's example), "la onzième" | g2p |
| S3a/S3b/S3c | intra-word, oral→nasal | "néon", "éhonté", "paons" (plural, rule-based path) | g2p |
| S4a/S4b | intra-word, nasal→oral | "enHardir", "enHucher" | g2p |
| T1/T2 | oral-oral hiatus controls | "aérer", "il a oublié" | g2p |
| T3/T4 | healthy nasal controls (VO reference) | "comment" (`kOma~`), "envie" (`a~vi`) | g2p |
| T5/T6 | nasal→nasal complements | "mon oncle", "un an" | g2p |
| H0–H3 | engine minimal pairs | `ta.ata`, `ta~.ata`, `ta.a~ta`, `ta~.a~ta` | direct SAMPA |
| H4 | case documented in the commit | `kOma~.a.le.vu` hand-written | direct SAMPA |

The full corpus is in `corpus_v1v2.json`; the `run_corpus.py` harness synthesizes each item (Pipeline `lang=fr`, engine `syl`, speaker `jd3`, default settings of the fr profile: `t_cons=140 ms`, `t_voy=120 ms`, `pause_short=200 ms`) and captures: the SAMPA string actually fed to the engine, the articulation plan (`syltraj.get_last_build()`: nodes, anchors, blocks), the `.tract` file, the `.wav`, and the logs.

### 3.2 Measurements

- **Articulation plan**: ordered list of blocks (`kind`, duration in steps at 100 Hz, `vowel_key`, `nasal`). A vocalic nucleus exists in the plan only as a `plateau` block; the `nasal` flag exists only on those plateaus.
- **Realized nasality**: maximum of the `VO` parameter (column 7 of the `.tract`) over the central half of the window of the `background` block that replaces the hiatus. Reference: maximum of `VO` over the nasal plateaus of controls T3/T4. Realized-nasality threshold: `VO ≥ 0.3`.
- **Audio**: RMS energy of the `.wav` over the same window (energy is present there — the defect is not a silence but a denasalized merger; see § 4.4).
- **Identity**: md5 of the `.wav` and `.tract` (evidence of indistinguishable outputs).
- **g2p comparison**: `compare_head_g2p.py` contrasts, for each text, the SAMPA of the fresh clone and that of the original HEAD (extracted from the git history), in order to measure exactly what the workaround masked.

---

## 4. Results

### 4.1 SAMPA strings fed to the engine (fresh clone, workaround removed)

| Id | Text | SAMPA fed to the engine | V1V2 junction |
|----|-------|------------------------|---------------|
| S1a | comment allez-vous | `kOma~.a.le.vu` | **a~.a** |
| S1b | mon ami | `mO~.a.mi` | **O~.a** |
| S2a | il a envie | `i.a.a~vi` | **i.a** then **a.a~** |
| S2b | la onzième | `la.O~zjEm` | **a.O~** |
| S3a | néon | `neO~` | **e.O~** |
| S3b | éhonté | `eO~.te` | **e.O~** |
| S3c | paons (plural, rule-based path) | `pao~` | **a.o~** |
| S4a | enhardir | `a~aR.diR` | **a~.a** |
| S4b | enhucher | `a~y.Se` | **a~.y** |
| T1 | aérer | `a.e.Re` | a.e (control) |
| T2 | il a oublié | `i.a.ub.li.je` | a.u (control) |
| T3 | comment | `kOma~` | — (healthy nasal) |
| T4 | envie | `a~vi` | — (healthy nasal) |
| T5 | mon oncle | `mO~.O~kl` | O~.O~ (complement) |
| T6 | un an | `9~.a~` | 9~.a~ (complement) |

Remark: intra-word linking dots sometimes disappear around nasals ("néon" → `neO~`, "envie" → `a~vi`) because `syllabify_keys` treats nasal keys as **consonants** (`SAMPA_VOWELS = frozenset(VOWEL_TARGETS.keys())`, `phonemes.py:38` — the nasal keys `a~`, `O~`… are not part of it). This is a second anomaly related to nasals (see § 5, defect no. 4): it has no effect on the defect under study — the linking dot is in any case a purely boundary marker for the engine, and the adjacency of the vowel **nodes** suffices to trigger the hiatus.

### 4.2 The exact mechanism of the defect (code reading)

Three converging defects, all on the engine side:

1. **Loss of the plateau.** `build_anchors` (`syltraj.py:641-646`): a vowel gets a "hold" anchor only if it is adjacent to **no** other vowel:
   ```python
   prev_v = i > 0 and nodes[i - 1].kind == 'V'
   next_v = i < n - 1 and nodes[i + 1].kind == 'V'
   anchors.append(SylAnchor(..., hold=not prev_v and not next_v))
   ```
   In a V1V2 hiatus (adjacent vowel nodes, with or without a dot), **both vowels lose their plateau**.

2. **Reduction to an anonymous background arc.** `build_global_pval`, branch `m == 0` (`syltraj.py:1019-1024`): between two vowel anchors with no consonant, the walk emits a single `background` block of `2·T_voy` steps — a glided arc from V1's target to V2's, **without `vowel_key` or `nasal` flag**. Yet the `nasal` flag is transmitted **only** by the `plateau` blocks (`syltraj.py:913-915` and `1046-1048`). Furthermore, since a nasal's polar target is its oral counterpart, a pair like `a~.a` produces a **static** arc (held [a]), with no glide at all.

3. **Nasality inapplicable on the background arc.** `build_phrase_tract.py:845`: the velar opening VO of nasal vowels is applied **only on `plateau` blocks**:
   ```python
   if _bi.kind == 'plateau' and getattr(_bi, 'nasal', False):
       ...  # VO ramp = 0.5 (VO_NASALIZED_VOWEL, constants.py:747)
   ```
   A `background` block never carries `nasal=True`, so the velum stays at the floor −0.1 (closed) over the whole hiatus duration: **the nasal vowel is fully denasalized**.

The energy, meanwhile, is present (`amplitude_envelope.py:386-387`: a `background` block gets E=1, voicing follows E): so there is no silence, but an unlabeled held **oral** vowel in place of the two expected nuclei — this is the perceptual "elision": "comment allez-vous" is realized [kɔmaːlely] with a long oral [aː] instead of [kɔmɑ̃.alely]. The "-" seen in the covtl console is the label timeline (no block carries the vowel keys).

### 4.3 Elision of the nuclei — articulation plans compared

Healthy control T3 "comment" (`kOma~`) — the final /a~/, not involved in a hiatus, has its nasal plateau:

```
offset dur  kind        vowel   nasal  content
     0  20  initial
    20  28  cluster                  cluster (1 cons.: k)
    48  12  plateau     O      False plateau of /O/
    60  28  cluster                  cluster (1 cons.: m)
    88  12  plateau     a      True  plateau of /a~/   <-- NASAL, VO≈0.49
   100  14  decay
   114  20  terminal
```

Failing item S1a "comment allez-vous" (`kOma~.a.le.vu`) — at the same offset 88, the nasal plateau has vanished, replaced by an anonymous background arc of 24 steps (2×T_voy):

```
offset dur  kind        vowel   nasal  content
     0  20  initial
    20  28  cluster                  cluster (k)
    48  12  plateau     O      False plateau of /O/
    60  28  cluster                  cluster (m)
    88  24  background  -      False UNLABELED background arc  <-- /a~/ AND /a/ elided
   112  28  cluster                  cluster (l)
   140  12  plateau     e      False plateau of /e/
   152  28  cluster                  cluster (v)
   180  12  plateau     u      False plateau of /u/
   192  14  decay
   206  20  terminal
```

The plan goes from 5 expected nuclei (O, a~, a, e, u) to 3 realized plateaus (O, e, u): **/a~/ and /a/ have been elided**. The 19 complete timelines are in `results/plans/`.

### 4.4 Measurements — summary table

`VO h. c.` = max of VO over the central half of the hiatus window; `VO ref.` = max of VO over a healthy nasal plateau. Nasality lost if `VO h. c. < 0.3`.

| Id | Engine SAMPA | Elided nuclei | VO h. c. | VO ref. | Nasality lost | Audio in the hiatus |
|----|--------------|----------------|-------------|---------|------------------|----------------------|
| S1a | `kOma~.a.le.vu` | a~, a | −0.085 | — | **YES** | present (RMS 0.24) |
| S1b | `mO~.a.mi` | O~, a | −0.085 | — | **YES** | present |
| S2a | `i.a.a~vi` | i, a, a~ | −0.100 | — | **YES** | present |
| S2b | `la.O~zjEm` | a, O~ | −0.100 | — | **YES** | present |
| S3a | `neO~` | e, O~ | −0.085 | — | **YES** | present |
| S3b | `eO~.te` | e, O~ | −0.100 | — | **YES** |
| S3c | `pao~` | a, o~ | −0.100 | — | **YES** | present |
| S4a | `a~aR.diR` | a~, a | −0.100 | — | **YES** | present |
| S4b | `a~y.Se` | a~, y | −0.100 | — | **YES** | present |
| T5 | `mO~.O~kl` | O~, O~ | −0.085 | — | **YES** | present |
| T6 | `9~.a~` | 9~, a~ | −0.100 | — | **YES** | present |
| T1 | `a.e.Re` | a, e (by design) | −0.100 | — | no (no nasal) | present |
| T2 | `i.a.ub.li.je` | i, a, u (by design) | −0.100 | — | no (no nasal) | present |
| T3 | `kOma~` | none | — | **0.495** | no | — |
| T4 | `a~vi` | none | — | **0.491** | no | — |
| H0 | `ta.ata` | a, a (by design) | −0.100 | — | no | present |
| H1 | `ta~.ata` | a~, a | −0.100 | — | **YES** | present |
| H2 | `ta.a~ta` | a, a~ | −0.100 | — | **YES** | present |
| H3 | `ta~.a~ta` | a~, a~ | −0.100 | — | **YES** | present |
| H4 | `kOma~.a.le.vu` | a~, a | −0.085 | — | **YES** | present |

Reading:

- **Situations S1–S4 fail on all their items (9/9)**: both members of the hiatus lose their nucleus, and the nasal member loses its nasality (VO at the floor −0.1, versus +0.49/+0.50 on a healthy nasal plateau — a difference of 0.6 in VTL units, huge).
- The small residual values (−0.085 instead of −0.100 on S1a, S1b, S3a, T5, H4) come from the decay tail of the anti-click smoothing (τ = 20 ms) after the preceding **nasal consonant** ([m] of `kOma~`, [n] of `neO~`): it is not the vowel that is nasalized, it is the nasal stop closing its velum late — further proof that the vowel itself contributes nothing.
- The V~.V~ complement (T5 "mon oncle", T6 "un an") shows that the nasal→nasal case is also affected: BOTH nasalities are lost.
- The audio is present in the hiatus window (RMS of the same order as the plateaus): the elision is **articulatory and perceptual** (merger into one held/glided oral vowel, unlabeled), not a silence.

### 4.5 Proof by byte identity — nasality is ignored

| Engine input | md5 `.wav` | md5 `.tract` |
|---------------|-----------|--------------|
| `ta.ata` (H0, oral control) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta~.ata` (H1, nasal→oral) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta.a~ta` (H2, oral→nasal) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta~.a~ta` (H3, nasal→nasal) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |

The four variants produce **exactly the same file**: the [nasal] feature has strictly no effect on a linked hiatus, in any direction. Moreover S1a (via g2p) and H4 (hand-written SAMPA) are likewise identical (`333c1d4e…`), confirming that g2p input and manual input converge to the same engine defect.

### 4.6 What the g2p workaround masked — and what it did not mask

`compare_head_g2p.py` (results in `results/sampa_frais_vs_head.txt`):

- **Masked by the patch** (space inserted instead of the dot): S1a, S1b ("comment allez-vous", "mon ami") and, incidentally, T5/T6 — i.e. all **inter-word junctions whose left-hand word ends in a nasal**. 4 items out of 14.
- **Not masked**: S2a/S2b (inter-word oral→nasal: "il a envie" → `i.a.a~vi` identical with or without the patch), S3a/S3b and S4a/S4b (intra-word: the patch only acts on between-word junctions) — **6 items out of 8 of the defect corpus**.

In other words: even **with** the workaround in place, the engine anomaly remained observable and audible on situations S2, S3 and S4. Only the engine fix covers all cases.

---

## 5. Root-cause analysis — four defects to enter in the register

1. **[Engine, critical] V1V2 hiatus without plateau or nasality** — the subject of this audit (§ 4.2, defects 1-3).
2. **[Front-end/g2p] Syllabification of nasal vowels as consonants** — `phonemes.py:38`: `SAMPA_VOWELS` contains only the oral keys; `syllabify_keys` treats `a~`, `O~`… as onsets/codas. Visible consequences in the produced SAMPA ("néon" → `neO~` without a dot; "envie" → `a~vi` monosyllable). Does not trigger defect no. 1 by itself, but distorts the syllabic segmentation and deserves to be fixed in the same pass (nasal keys must close a nucleus like the oral ones).
3. **[Workaround to remove] g2p pause after a final nasal** — `dea71c6`/`f62f185`: masks 1 case out of 4 situations, introduces a non-linguistic pause, and contradicts the documented invariant "the assembled SAMPA is identical to the language g2p's" as soon as one compares g2p and prosody. Once the engine is fixed, these two commits must be reverted again (back to the linking dot everywhere).
4. **[Guard] The SAMPA guard cannot flag the hand-written V~.V** — all symbols being valid, the silent reduction is undetectable at input. After the engine fix, this documented limitation disappears by itself; in the meantime, a dedicated warning ("V~.V detected — reduced by the walk") would be useful.

---

## 6. Proposed operational changes

> Goal: have the walk articulate the **nasal/oral toggle across a linked boundary**, while preserving the COVTL model's philosophy (the hiatus remains a coarticulated glided arc, cf. the treatment of oral V.V "handled by the walk") and the non-regression baselines.

### P1 — `syltraj.build_global_pval`: labeled background sub-blocks on the hiatus

In the `m == 0` branch (linked V.V boundary, `syltraj.py:1019-1024`), replace the single anonymous `background` block of `2·T_voy` with **two consecutive blocks of `T_voy`** covering the same arc (build the full arc, then split it, so as to preserve exactly the trajectory and the total duration), each carrying:

```python
SylBlock(n_steps=T_voy, kind='background',
         vowel_key=<oral key of V1>, nasal=<V1.nasal>)
SylBlock(n_steps=T_voy, kind='background',
         vowel_key=<oral key of V2>, nasal=<V2.nasal>)
```

Acceptable implementation variants: split **only when at least one member is nasal** (guarantees bit-for-bit behavior on purely oral hiatuses like `di.as`/T1/T2 — the safest option for non-regression), or split systematically (more homogeneous: every vowel of the hiatus regains a label and the per-vowel effort gain). The cumulative duration `2·T_voy` and the polar arc must remain unchanged.

Effects: both vowels regain a label in the plan (end of the "-" in the console and in the polar video), the per-vowel effort gain (`VOWEL_EFFORT_GAIN`, `build_phrase_tract.py:664-676`) applies, and the nasality hook point exists.

### P2 — `build_phrase_tract.py:845`: nasality applicable to background half-arcs

Extend the condition for applying the VO ramp of nasal vowels:

```python
# before:  if _bi.kind == 'plateau' and getattr(_bi, 'nasal', False):
# after:
if _bi.kind in ('plateau', 'background') and getattr(_bi, 'nasal', False):
```

The existing anti-click smoothing (first-order filter, τ = 20 ms, lines 867-873) handles the velar transition between the two halves: on `a~.a`, VO rises toward 0.5 on the first half then falls back toward −0.1 on the second — exactly the expected toggle. On `a.a~`, it is the reverse. On `a~.a~`, VO stays at 0.5 on both halves (with the 20 % ramps at the ends), which also fixes the T5/T6 case.

### P3 — Front-end cleanup (to be done after engine validation)

1. Re-revert `dea71c6` and `f62f185` (back to the linking dot everywhere): the g2p no longer has to mask the engine. Keep the CHANGELOG note, moving it to the past tense.
2. Fix `phonemes.py:38`: `SAMPA_VOWELS` must include the nasal keys (e.g. `{k for k in ALL_PHONEME_KEYS if _is_vowel_key(k)}` at the keys' source) so that `syllabify_keys` treats nasals as nuclei. Check the impact on the non-regression segmentation tests (some splits will change: `neO~` → `ne.O~`, `a~vi` → `a~.vi` — this is phonologically correct).
3. Optional: SAMPA guard warning on `V~.V` while P1/P2 are not in place.

### P4 — Non-regression and validation

1. **Unchanged baselines**: the reference corpora (regression_baselines*.json) must not move for entries without nasal hiatus — hence the value of the "split only if nasal" variant of P1. Check with the existing suite (the repository announces 207 passing engine tests).
2. **New unit tests** (to add to `tests/`):
   - `build_phrase_pval('ta~.ata')` → the plan contains a `background` block with `nasal=True` on the V1 side and `vowel_key='a'`;
   - same for `ta.a~ta` on the V2 side; `ta~.a~ta` → two nasal half-arcs;
   - `ta.ata` → bit-for-bit identical to the previous state (if the conditional variant is retained);
   - after synthesis: `max(VO) ≥ 0.4` on the first half of the hiatus of `ta~.ata`, `max(VO) ≤ 0.0` on the second;
   - the WAVs of `ta~.ata` and `ta.ata` must from now on **differ** (this is the inversion of the md5 proof of § 4.5).
3. **Perceptual validation protocol**: re-run `AUDIT_V1V2/run_corpus.py` — the 8 items S1–S4 must switch to "nasality lost: no" with `VO h. c. ≈ 0.5` on the nasal half(ves); compare the WAVs before/after the fix (archived in this folder).

### Scope deliberately excluded

The phonetic quality of the rendering (French liaison, nasalization durations, velar toggle speed — a 20 % ramp over T_voy=120 ms is phonetically debatable) and the expressive prosody engine are not audited here; the proposed patch is deliberately minimal and localized so as to remain reversible, in the spirit of the `covtl-lambda` repository (installable engine patch with an adjustable parameter).

---

## 7. Deliverables and reproduction

```
AUDIT_V1V2/
├── AUDIT.md                  ← this report
├── MISSION.md                ← mission note for the fixing agent
├── corpus_v1v2.json          ← test corpus (19 items)
├── run_corpus.py             ← harness: synthesis + plan/tract/wav capture + measurements
├── compare_head_g2p.py       ← SAMPA comparison fresh clone vs workaround HEAD
└── results/
    ├── results.json          ← complete machine-readable table (with verdicts)
    ├── results_g2p.json      ← fresh/HEAD g2p comparison
    ├── sampa_frais_vs_head.txt
    ├── plans/<id>.txt        ← 19 timelines of the articulation plan
    ├── wav/<id>.wav          ← 19 syntheses (44.1 kHz)
    ├── tract/<id>.tract      ← 19 VTL sequences 400 Hz (VO = column 7)
    └── logs/<id>.log         ← logs (incl. SAMPA guard: no flagging)
```

Reproduction (Linux):

```bash
python -m venv .venv && . .venv/bin/activate
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr
python AUDIT_V1V2/run_corpus.py            # ~2 min, writes results/
python AUDIT_V1V2/compare_head_g2p.py
```

*(Note: `pip install .` installs the engine; the harness inserts the repository root at the head of `sys.path`, so the local clone takes precedence over any installation. The "CONSTANTS INCONSISTENCY" warning after activating the fr pack is the known, documented constants.py hash — no effect on synthesis.)*

---

## Appendix A — Key raw data

- VO reference of a healthy nasal plateau: T3 = 0.495; T4 = 0.491 (`VO_NASALIZED_VOWEL = 0.5`, 20 % ramps included).
- Hiatus VO (central half): from −0.100 to −0.085 on all items with an elided nasal.
- Durations: `T_voy = 12` steps (120 ms); hiatus `background` block = `2·T_voy = 24` steps (240 ms); the RMS energy in this window is comparable to that of the plateaus (≈ 0.19–0.25 versus 0.11–0.22): no silence, an oral merger.
- Fingerprints: see § 4.5; `results.json` contains the md5 of each item.

## Appendix B — Files and lines concerned by the fix

| File | Line(s) | Role in the defect / fix |
|---------|----------|----------------------------------|
| `vtl_synth/core/syltraj.py` | 641-646 | `hold = not prev_v and not next_v` — loss of the hiatus plateaus (finding) |
| `vtl_synth/core/syltraj.py` | 1019-1024 | `m == 0` branch: anonymous background block — **P1 fix site** |
| `vtl_synth/core/syltraj.py` | 913-915, 1046-1048 | transmission of the `nasal` flag (plateaus only) |
| `vtl_synth/core/build_phrase_tract.py` | 839-854 | VO of nasal vowels — **P2 fix site** (line 845) |
| `vtl_synth/core/build_phrase_tract.py` | 867-873 | VO anti-click smoothing (τ = 20 ms) — reused as-is by P2 |
| `vtl_synth/core/amplitude_envelope.py` | 384-387 | E = 1 on background (why the audio survives) |
| `vtl_synth/core/phonemes.py` | 38 | `SAMPA_VOWELS` without nasal keys — defect no. 2 (P3.2) |
| `vtl_synth/core/constants.py` | 745-748 | `TAG_TO_VO_TARGET`: `nasalized = 0.5` |
| `vtl_synth/utils/g2p_fr.py` + `lang_pack/profiles/g2p_fr.py` | 249-279 | workaround removed by the audit revert (to be kept removed after the engine fix) |
