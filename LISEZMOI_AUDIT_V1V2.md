# Audit V1V2 — point d'entrée (pour l'agent correcteur)

> **ÉTAT 2026-10-31 — CORRECTION MOTEUR RÉALISÉE.** La correction est
> implémentée selon le principe non perturbateur prescrit (syltraj intact,
> couche de pré-traitement `vtl_synth/core/nasal_preproc.py`, nasalité
> réinjectée dans l'espace orthogonal VO + timer 20 ms existant) : lire en
> premier **`AUDIT_V1V2/IMPLEMENTATION_V1V2.md`** (architecture, résultats,
> preuves de non-perturbation, commandes de re-vérification).
>
> **NOUVELLES CONSIGNES (2026-10-31, pour l'agent) — MISSION §6-§7 :**
> - **P5 — décommissionner définitivement les modifications devenues
>   inutiles** : les contournements g2p/prosodie (`dea71c6`, `f62f185`)
>   ne doivent **jamais être réappliqués** (la clause de ré-inversion de
>   P3 est annulée) ; balayer les résidus documentaires ; consigner le
>   retrait définitif au CHANGELOG.
> - **P6 — traiter les autres langues** (de, en, es, it, **pt en
>   priorité** — seule autre langue du pack à voyelles nasales
>   phonémiques) : corpus pt sur la même typologie, harnais paramétré par
>   langue, preuve d'inertie pour es/it/de/en, inventaire `phonemes.py`
>   couvrant toutes les langues.
> - Résiduel de P3 : clés nasales `phonemes.py:38`, SHA préexistant de
>   `test_syltraj_double_pause`.

Ce clone est l'état de travail remis pour la correction du moteur de synthèse
(covtl-pipeline). Il contient, à la racine, le dépôt complet avec son
historique git ; en tête se trouvent les commits d'audit et le correctif :

- `2a55b69` — inverse les contournements g2p/prosodie (`dea71c6` + `f62f185`)
  qui masquaient le défaut moteur : ce retrait est désormais **définitif**
  (MISSION §6 / P5) ;
- `1b81aef` — ajoute le dossier `AUDIT_V1V2/` (tout l'audit) ;
- `304f04c` — la correction moteur (couche `nasal_preproc` + injection VO
  orthogonale), validée sur le corpus fr 20/20.

**Commencer par :** `AUDIT_V1V2/MISSION.md` (objectif, correctif P1-P4,
**nouvelles consignes P5 §6 et P6 §7**, critères d'acceptation, commandes de
vérification), puis `AUDIT_V1V2/AUDIT.md` (rapport complet ; version PDF :
`AUDIT_V1V2/rapport_audit_V1V2.pdf`) et `AUDIT_V1V2/IMPLEMENTATION_V1V2.md`
(rapport d'implémentation du correctif).

Défaut en une ligne : sur un hiatus lié V1.V2 dont un membre est nasal, la
marche `syltraj` remplace les deux noyaux par un arc de fond anonyme et la
nasalité (VO, velum) n'est jamais appliquée — mesuré : VO = −0,1 dans l'hiatus
contre +0,49 sur un plateau nasal sain ; preuve : `ta.ata`, `ta~.ata`,
`ta.a~ta`, `ta~.a~ta` produisaient des WAV identiques octet par octet
(distincts depuis le correctif).

**P6 — RÉALISÉ (2026-11-02).** Validation étendue au pack complet : corpus portugais dédié (`corpus_v1v2_pt.json` → `results_pt/`, toutes typologies nasalisees, VO >= 0.489), inertie es/it/de/en prouvée (`p6_multilingue.py` → `results_p6/inertie.json` : g2p sans ~, lexiques sans ~, sorties bit-identiques porte active/neutralisée), inventaire moteur couvrant toutes les langues, harnais paramétré par langue (`run_corpus.py --lang pt`). Détails : `P6_MULTILINGUE.md` ; tests étendus (`TestP6Portuguese`, 38/38 verts).

Reproduire l'audit (Linux) :

```bash
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr
python AUDIT_V1V2/run_corpus.py
```

> **HTML DIDACTIQUE — `correction_V1V2_avant_apres.html`** (racine de ce
> dépôt, autonome : CSS/JS/AUDIO MP3 embarqués, s'ouvre dans tout
> navigateur). Page pédagogique intégrant les **vingt exemples avant/après**
> du corpus (S1-S4, témoins T, paires H) : audio A→B cliquable par item,
> trajectoires VO, md5 avant/après, tableau de bord des 20 items, principe de
> la correction (factorisation orthogonale) et trois écoutes démonstratives.
> Sert de démonstrateur visuel et sonore de la correction pour revue.
