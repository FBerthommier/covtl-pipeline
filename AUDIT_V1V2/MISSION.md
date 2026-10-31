# MISSION — Correction du moteur : bascule nasal/oral sur les hiatus V1V2 liés

**Destinataire :** agent chargé de la modification du moteur de synthèse.
**Dépôt de travail :** ce clone `covtl-pipeline` (état : HEAD = commit d'audit `2a55b69`, qui inverse les contournements g2p `dea71c6` + `f62f185` — **ne pas les rétablir**, le défaut doit rester exposé jusqu'à correction du moteur).
**Lecture préalable obligatoire :** `AUDIT_V1V2/AUDIT.md` (constats, mécanisme, preuves) — en particulier § 4.2 (mécanisme), § 6 (correctif proposé), § Annexe B (fichiers/lignes).

---

## 1. Objectif

Faire en sorte que le moteur `syltraj` **articule la bascule nasal/oral à travers une frontière liée V1.V2** (point de liaison ou adjacence directe), dans les quatre situations :

1. inter-mot V~.V (ex. `kOma~.a.le.vu`) ;
2. inter-mot V.V~ (ex. `i.a.a~vi`) ;
3. intra-mot V.V~ (ex. `neO~`, `eO~.te`) ;
4. intra-mot V~.V (ex. `a~aR.diR`, `a~y.Se`).

Critères d'acceptation mesurables (repris du harnais d'audit) :

- [ ] Pour chaque item S1a→S4b du corpus (`AUDIT_V1V2/corpus_v1v2.json`), le plan d'articulation contient, pour chaque membre du hiatus, un bloc étiqueté (`vowel_key` défini) — fini le bloc `background` anonyme de `2·T_voy`.
- [ ] La nasalité est réalisée : `max(VO)` sur la (ou les) moitié(s) nasale(s) du hiatus ≥ 0,4 (référence saine : ≈ 0,49–0,50) ; VO retombe ≤ 0 sur la moitié orale (cas V~.V et V.V~).
- [ ] `ta~.ata` et `ta.ata` produisent des `.wav` **différents** (l'identité octet actuelle — AUDIT.md § 4.5 — est l'inversion exacte de la réussite).
- [ ] Non-régression : suite de tests du dépôt au moins aussi verte qu'avant modification (207 passants moteur annoncés à `dea71c6`), et sorties inchangées pour les entrées sans hiatus nasal si la variante conditionnelle de P1 est retenue.

## 2. Correctif proposé (minimal et réversible)

- **P1 — `vtl_synth/core/syltraj.py`, branche `m == 0` de `build_global_pval` (≈ lignes 1019-1024)** : scinder l'arc de fond du hiatus en deux blocs `background` de `T_voy` chacun (arc global préservé : le construire entier puis le couper en deux), portant `vowel_key` et `nasal` de V1 et V2 respectivement. Scission conditionnelle (« au moins un membre nasal ») recommandée pour la non-régression ; scission systématique acceptable si les baselines sont régénérées et documentées.
- **P2 — `vtl_synth/core/build_phrase_tract.py`, ligne 845** : étendre l'application de la rampe VO aux blocs `background` porteurs du drapeau nasal (`kind in ('plateau', 'background')`). Le lissage anti-clic existant (τ = 20 ms) gère la transition entre moitiés.
- **P3 — après validation** : ré-inverser les contournements g2p (`dea71c6`, `f62f185`) pour revenir au point de liaison partout ; corriger `phonemes.py:38` (`SAMPA_VOWELS` doit inclure les clés nasales — actuellement « néon » sort `neO~` sans point et « envie » `a~vi` monosyllabe) ; consigner au CHANGELOG.
- **P4 — tests** : unitaires sur `build_phrase_pval` (drapeaux des demi-arcs), sur VO après synthèse, et non-régression des baselines (cf. AUDIT.md § 6/P4 pour la liste exacte).

## 3. Protocole de vérification (commandes)

```bash
# environnement (Linux) — voir AUDIT.md § 7 pour le détail
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr

# avant/après modification :
python AUDIT_V1V2/run_corpus.py            # régénère results/ + tableau récapitulatif
python AUDIT_V1V2/compare_head_g2p.py      # contrôle accessoire (SAMPA g2p)
pytest tests/ -q                           # suite du dépôt
```

Le tableau produit par `run_corpus.py` doit afficher `nas.perdue = non` pour S1a→S4b (et T5/T6), avec `VO c.hiat. ≈ 0,4-0,5` sur les moitiés nasales. Les WAV d'origine (état défaillant) sont archivés dans `AUDIT_V1V2/results/wav/` — ne pas les écraser sans les avoir sauvegardés (ils servent de référence avant/après ; recopier le dossier en `wav_avant/` avant toute régénération).

## 4. Garde-fous

- Ne pas modifier le g2p pour masquer le moteur (c'est l'objet du revert d'audit) ; ne pas toucher aux cibles polaires des voyelles (la nasale partage la cible de sa contrepartie orale — la nasalité est exclusivement dans l'extension VO).
- Préserver la durée totale (`2·T_voy`) et la trajectoire de l'arc (scission, pas recomposition).
- Toute dérive des baselines doit être justifiée et régénérée via `scripts/regen_baselines.py` avec mention au CHANGELOG.
- Format de livraison suggéré, dans l'esprit du dépôt : patch commité(s) avec message détaillé + mise à jour du CHANGELOG + tests.

## 5. Contexte utile en une ligne par fichier

`syltraj.py` = marche syllabique (nœuds → ancrages → blocs) ; `build_phrase_tract.py` = assemblage E/V/VO depuis les blocs ; `amplitude_envelope.py` = E(t) par bloc (background → E=1) ; `phonemes.py` = inventaire + syllabification ; `constants.py` = cibles, `TAG_TO_VO_TARGET['nasalized']=0.5` ; `pipeline.py` = orchestration texte→SAMPA→tract→wav. Le fichier `.tract` a 30 colonnes (19 tract + 11 glottis), **VO = colonne 7**, frames à 400 Hz.
