# Audit V1V2 — point d'entrée (pour l'agent correcteur)

> **ÉTAT 2026-10-31 — CORRECTION MOTEUR RÉALISÉE.** La correction est
> implémentée selon le principe non perturbateur prescrit (syltraj intact,
> couche de pré-traitement `vtl_synth/core/nasal_preproc.py`, nasalité
> réinjectée dans l'espace orthogonal VO + timer 20 ms existant) : lire en
> premier **`AUDIT_V1V2/IMPLEMENTATION_V1V2.md`** (architecture, résultats,
> preuves de non-perturbation, commandes de re-vérification). Restent à
> traiter par l'agent : P3 de la MISSION (ré-inversion g2p `dea71c6`+
`f62f185`, clés nasales dans `phonemes.py:38`) et le SHA préexistant de
> `test_syltraj_double_pause`.

Ce clone est l'état de travail remis pour la correction du moteur de synthèse
(covtl-pipeline). Il contient, à la racine, le dépôt complet avec son
historique git ; en tête se trouvent deux commits d'audit :

- `2a55b69` — inverse les contournements g2p/prosodie (`dea71c6` + `f62f185`)
  qui masquaient le défaut moteur : **ne pas les rétablir** avant correction ;
- `1b81aef` — ajoute le dossier `AUDIT_V1V2/` (tout l'audit).

**Commencer par :** `AUDIT_V1V2/MISSION.md` (objectif, correctif proposé P1-P4,
critères d'acceptation, commandes de vérification), puis `AUDIT_V1V2/AUDIT.md`
(rapport complet ; version PDF : `AUDIT_V1V2/rapport_audit_V1V2.pdf`).

Défaut en une ligne : sur un hiatus lié V1.V2 dont un membre est nasal, la
marche `syltraj` remplace les deux noyaux par un arc de fond anonyme et la
nasalité (VO, velum) n'est jamais appliquée — mesuré : VO = −0,1 dans l'hiatus
contre +0,49 sur un plateau nasal sain ; preuve : `ta.ata`, `ta~.ata`,
`ta.a~ta`, `ta~.a~ta` produisent des WAV identiques octet par octet.

Reproduire l'audit (Linux) :

```bash
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr
python AUDIT_V1V2/run_corpus.py
```
