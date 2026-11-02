# Audit V1V2 — entry point (for the fixing agent)

> **STATUS 2026-10-31 — ENGINE FIX DELIVERED.** The fix is
> implemented according to the prescribed non-perturbing principle (syltraj intact,
> preprocessing layer `vtl_synth/core/nasal_preproc.py`, nasality
> reinjected into the existing orthogonal VO + 20 ms timer space): read
> first **`AUDIT_V1V2/IMPLEMENTATION_V1V2.md`** (architecture, results,
> non-perturbation proofs, re-verification commands).
>
> **NEW INSTRUCTIONS (2026-10-31, for the agent) — MISSION §6-§7:**
> - **P5 — definitively decommission the modifications that have become
>   unnecessary**: the g2p/prosody workarounds (`dea71c6`, `f62f185`)
>   must **never be re-applied** (the re-reversion clause of
>   P3 is cancelled); sweep the documentary residues; record the
>   definitive removal in the CHANGELOG.
> - **P6 — handle the other languages** (de, en, es, it, **pt
>   first** — the only other language of the pack with phonemic
>   nasal vowels): pt corpus on the same typology, harness parameterized by
>   language, inertia proof for es/it/de/en, `phonemes.py`
>   inventory covering all languages.
> - P3 residual: nasal keys `phonemes.py:38`, pre-existing SHA of
>   `test_syltraj_double_pause`.

This clone is the working state handed over for the fix of the synthesis
engine (covtl-pipeline). It contains, at the root, the full repository with its
git history; at the top are the audit commits and the fix:

- `2a55b69` — reverts the g2p/prosody workarounds (`dea71c6` + `f62f185`)
  that masked the engine defect: this removal is now **definitive**
  (MISSION §6 / P5);
- `1b81aef` — adds the `AUDIT_V1V2/` folder (the whole audit);
- `304f04c` — the engine fix (`nasal_preproc` layer + orthogonal VO
  injection), validated on the fr corpus 20/20.

**Start with:** `AUDIT_V1V2/MISSION.md` (objective, P1-P4 fix,
**new instructions P5 §6 and P6 §7**, acceptance criteria, verification
commands), then `AUDIT_V1V2/AUDIT.md` (full report; PDF version:
`AUDIT_V1V2/rapport_audit_V1V2.pdf`) and `AUDIT_V1V2/IMPLEMENTATION_V1V2.md`
(implementation report of the fix).

Defect in one line: on a linked V1.V2 hiatus with a nasal member, the
`syltraj` walk replaces the two nuclei with an anonymous background arc and
nasality (VO, velum) is never applied — measured: VO = −0.1 in the hiatus
versus +0.49 on a healthy nasal plateau; proof: `ta.ata`, `ta~.ata`,
`ta.a~ta`, `ta~.a~ta` used to produce identical byte-for-byte WAVs
(distinct since the fix).

**P6 — DONE (2026-11-02).** Validation extended to the full pack: dedicated Portuguese corpus (`corpus_v1v2_pt.json` → `results_pt/`, all nasalized typologies, VO >= 0.489), es/it/de/en inertia proven (`p6_multilingue.py` → `results_p6/inertie.json`: g2p without ~, lexicons without ~, bit-identical outputs with gate active/neutralized), engine inventory covering all languages, harness parameterized by language (`run_corpus.py --lang pt`). Details: `P6_MULTILINGUE.md`; extended tests (`TestP6Portuguese`, 38/38 green).

Reproduce the audit (Linux):

```bash
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr
python AUDIT_V1V2/run_corpus.py
```

> **DIDACTIC HTML — `correction_V1V2_avant_apres.html`** (root of this
> repository, self-contained: embedded CSS/JS/MP3 AUDIO, opens in any
> browser). Pedagogical page integrating the **twenty before/after examples**
> of the corpus (S1-S4, T controls, H pairs): clickable A→B audio per item,
> VO trajectories, before/after md5s, dashboard of the 20 items, principle of
> the fix (orthogonal factorization) and three demonstration listenings.
> Serves as the visual and audible demonstrator of the fix for review.
