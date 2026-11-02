#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p6_multilingual.py — Mission P6: inertness of the nasal_preproc gate on
es / it / de / en, g2p + lexicon sweeps, engine inventory.

For each language WITHOUT phonemic nasal vowels:
  1. g2p sweep: a sample of texts produces NO `~` key;
  2. lexicon sweep: the .tsv contains no `~` sign;
  3. bit-level non-perturbation: two syntheses of an oral sample —
     nasal_preproc gate ACTIVE then NEUTRALIZED — give IDENTICAL
     .wav / .tract files (md5);
  4. inventory: the nasal keys of `language_vowel_sets.py` (all
     languages) are covered by `phonemes.SAMPA_VOWELS`.

Outputs: AUDIT_V1V2/results_p6/inertie.json + console recap.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from vtl_synth import Pipeline                       # noqa: E402
from vtl_synth.core import phonemes                  # noqa: E402
from vtl_synth.utils.setlang import get_profile      # noqa: E402

SAMPLES = {
    "es": ["el perro verde", "la casa azul"],
    "it": ["il gatto nero", "la casa bianca"],
    "de": ["das grune Haus", "ein gruner Baum"],
    "en": ["the green tree", "hello world"],
}
ALL_LANGS = ["fr", "pt", "es", "it", "de", "en"]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def g2p_no_tilde(profile, texts) -> dict:
    """g2p sweep: no `~` key is emitted."""
    tilde = []
    for t in texts:
        sampa = profile.g2p_callable(t, warnings=[])
        if "~" in sampa:
            tilde.append((t, sampa))
    return {"texts": len(texts), "tilde_hits": tilde, "inerte": not tilde}


def lexicon_no_tilde(lang: str) -> dict:
    """Sweep of the .tsv lexicon: no `~` sign (English goes through
    CMUdict/ARPAbet — no tsv lexicon to sweep)."""
    lex = REPO / "lang_pack" / "lexicons" / f"{lang}_lexicon.tsv"
    if not lex.exists():
        return {"lexicon": f"{lang}_lexicon.tsv (absent — ARPAbet)", "inerte": True}
    hits = [l.split("\t")[0] for l in
            lex.read_text(encoding="utf-8").splitlines()
            if "~" in l]
    return {"lexicon": lex.name, "tilde_lines": len(hits), "inerte": not hits}


def bit_identical(lang: str, texts) -> dict:
    """Two syntheses (gate active / gate neutralized) -> identical md5s."""
    import vtl_synth.core.nasal_preproc as npre
    original = npre.split_nasal_hiatus
    md5s = {}
    pipe = Pipeline(lang=lang)
    for mode in ("actif", "neutralise"):
        if mode == "neutralise":
            npre.split_nasal_hiatus = (lambda phrase: (phrase, {
                "original": phrase, "motor": phrase, "nodes_view": [],
                "runs": [], "events": [], "intervals": None,
                "fallback": False}))
        hashes = []
        for i, t in enumerate(texts):
            out = HERE / "_p6_tmp" / f"{lang}_{mode}_{i}"
            pipe.run(t, output_dir=str(out), use_g2p=True, video=False,
                     label=f"p6_{i}")
            wav = out / f"p6_{i}.wav"
            trt = out / f"p6_{i}.tract"
            hashes.append(md5(wav) + ":" + md5(trt))
        md5s[mode] = hashes
    npre.split_nasal_hiatus = original
    import shutil
    shutil.rmtree(HERE / "_p6_tmp", ignore_errors=True)
    return {"md5": md5s, "identique": md5s["actif"] == md5s["neutralise"]}


def inventory_coverage() -> dict:
    """Nasal keys of language_vowel_sets ⊆ phonemes.SAMPA_VOWELS."""
    from vtl_synth.utils import language_vowel_sets as lvs
    sampa_vowels = set(phonemes.SAMPA_VOWELS)
    cover = {}
    for lang in ALL_LANGS:
        vs = getattr(lvs, f"VOWELS_{lang.upper()}", None)
        if vs is None:
            sets_map = getattr(lvs, "LANGUAGE_VOWEL_SETS", None)
            vs = (sets_map or {}).get(lang)
        if vs is None:
            cover[lang] = {"statut": "vowel set not found"}
            continue
        nasals = sorted(v for v in vs if v.endswith("~"))
        missing = [v for v in nasals if v not in sampa_vowels]
        cover[lang] = {"nasales": nasals, "manquants_de_l_inventaire": missing,
                       "couvert": not missing}
    return {"sampa_vowels": sorted(sampa_vowels), "langues": cover,
            "tout_couvert": all(c.get("couvert", True)
                                for c in cover.values())}


def main() -> int:
    results = {"langues": {}, "inventaire": inventory_coverage()}
    for lang in ("es", "it", "de", "en"):
        profile = get_profile(lang)
        texts = SAMPLES[lang]
        entry = {
            "g2p": g2p_no_tilde(profile, texts),
            "lexique": lexicon_no_tilde(lang),
            "non_perturbation": bit_identical(lang, texts),
        }
        entry["inerte"] = (entry["g2p"]["inerte"] and entry["lexique"]["inerte"]
                           and entry["non_perturbation"]["identique"])
        results["langues"][lang] = entry
        print(f"{lang}: g2p inert={entry['g2p']['inerte']} "
              f"lexicon inert={entry['lexique']['inerte']} "
              f"bit-identical={entry['non_perturbation']['identique']} "
              f"-> INERT: {entry['inerte']}")

    inv = results["inventaire"]
    print(f"inventory: all covered = {inv['tout_couvert']}")
    out = HERE / "results_p6" / "inertie.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"written: {out}")

    inert = all(e["inerte"] for e in results["langues"].values())
    ok = inert and inv["tout_couvert"]
    print("P6 inertness + inventory:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
