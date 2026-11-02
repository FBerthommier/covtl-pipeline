#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p6_multilingue.py — Mission P6 : inertie de la porte nasal_preproc sur
es / it / de / en, balayage g2p + lexiques, inventaire moteur.

Pour chaque langue SANS voyelle nasale phonémique :
  1. balayage g2p : un échantillon de textes ne produit AUCUNE clé `~` ;
  2. balayage du lexique : le .tsv ne contient aucun signe `~` ;
  3. non-perturbation bit à bit : deux synthèses d'un échantillon oral —
     porte nasal_preproc ACTIVE puis NEUTRALISÉE — donnent des fichiers
     .wav / .tract IDENTIQUES (md5) ;
  4. inventaire : les clés nasales de `language_vowel_sets.py` (toutes
     langues) sont couvertes par `phonemes.SAMPA_VOWELS`.

Sorties : AUDIT_V1V2/results_p6/inertie.json + recapitulatif console.
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
    """Balayage g2p : aucune clé ~ n'est émise."""
    tilde = []
    for t in texts:
        sampa = profile.g2p_callable(t, warnings=[])
        if "~" in sampa:
            tilde.append((t, sampa))
    return {"texts": len(texts), "tilde_hits": tilde, "inerte": not tilde}


def lexicon_no_tilde(lang: str) -> dict:
    """Balayage du lexique .tsv : aucun signe ~ (l'anglais passe par
    CMUdict/ARPAbet — pas de lexique tsv à balayer)."""
    lex = REPO / "lang_pack" / "lexicons" / f"{lang}_lexicon.tsv"
    if not lex.exists():
        return {"lexicon": f"{lang}_lexicon.tsv (absent — ARPAbet)", "inerte": True}
    hits = [l.split("\t")[0] for l in
            lex.read_text(encoding="utf-8").splitlines()
            if "~" in l]
    return {"lexicon": lex.name, "tilde_lines": len(hits), "inerte": not hits}


def bit_identical(lang: str, texts) -> dict:
    """Deux synthèses (porte active / porte neutralisée) → md5 identiques."""
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
    """Clés nasales de language_vowel_sets ⊆ phonemes.SAMPA_VOWELS."""
    from vtl_synth.utils import language_vowel_sets as lvs
    sampa_vowels = set(phonemes.SAMPA_VOWELS)
    cover = {}
    for lang in ALL_LANGS:
        vs = getattr(lvs, f"VOWELS_{lang.upper()}", None)
        if vs is None:
            sets_map = getattr(lvs, "LANGUAGE_VOWEL_SETS", None)
            vs = (sets_map or {}).get(lang)
        if vs is None:
            cover[lang] = {"statut": "jeu de voyelles introuvable"}
            continue
        nasals = sorted(v for v in vs if v.endswith("~"))
        manquants = [v for v in nasals if v not in sampa_vowels]
        cover[lang] = {"nasales": nasals, "manquants_de_l_inventaire": manquants,
                       "couvert": not manquants}
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
        print(f"{lang}: g2p inerte={entry['g2p']['inerte']} "
              f"lexique inerte={entry['lexique']['inerte']} "
              f"bit-identique={entry['non_perturbation']['identique']} "
              f"→ INERTE: {entry['inerte']}")

    inv = results["inventaire"]
    print(f"inventaire: tout couvert = {inv['tout_couvert']}")
    out = HERE / "results_p6" / "inertie.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"écrit : {out}")

    inertes = all(e["inerte"] for e in results["langues"].values())
    ok = inertes and inv["tout_couvert"]
    print("P6 inertie + inventaire :", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
