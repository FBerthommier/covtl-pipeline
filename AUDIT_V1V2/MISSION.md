# MISSION — Correction du moteur : bascule nasal/oral sur les hiatus V1V2 liés

**ÉTAT (2026-10-31) : CORRECTION RÉALISÉE** — voir `IMPLEMENTATION_V1V2.md` :
le principe prescrit (syltraj intact + couche de pré-traitement + nasalité
dans l'espace orthogonal VO/timer existant) est implémenté et validé
(20/20 items, VO 0,49-0,50, témoins bit-identiques, 33 tests unitaires).
Le critère « blocs étiquetés » du §1 est supédité par l'architecture retenue
§6.1 du rapport d'implémentation. **Restent pour l'agent (consignes du
2026-10-31, après livraison du correctif)** : **P5** — décommissionner
définitivement les modifications devenues inutiles (§6 ci-dessous ; **annule
la clause de ré-inversion de P3**) ; **P6** — étendre le traitement aux autres
langues du pack (§7) ; et le résiduel de P3 (clés nasales `phonemes.py:38`,
SHA préexistant de `test_syltraj_double_pause`).

**Destinataire :** agent chargé de la modification du moteur de synthèse.
**Dépôt de travail :** ce clone `covtl-pipeline` (état : HEAD = `9cdc852` ; la correction est le commit `304f04c`, le dossier d'audit est `1b81aef`, le revert d'exposition du défaut est `2a55b69` — voir §6 pour le statut définitif des contournements `dea71c6` + `f62f185`).
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

---

## 6. P5 — Décommissionner définitivement les modifications devenues inutiles

**Motif.** La correction moteur `304f04c` rend obsolètes les contournements
d'époque qui existaient pour masquer le défaut. Ces modifications sont
devenues inutiles : elles doivent être **retirées définitivement** du livrable.

1. **Annulation de la clause de ré-inversion de P3.** La première partie de
   P3 (« ré-inverser les contournements g2p (`dea71c6`, `f62f185`) pour
   revenir au point de liaison partout ») est **annulée et remplacée par la
   présente section** : l'état « point de liaison partout » est déjà celui du
   tree (le revert `2a55b69` l'a rétabli) et doit rester **définitif**.
   Ne jamais ré-appliquer `dea71c6` (pause courte au lieu du point de
   liaison après mot fini par voyelle nasale, dans `g2p_fr`) ni `f62f185`
   (même règle dans l'enrichissement expressif de la prosodie).
2. **Statut du revert `2a55b69`.** Son message le motive par l'exposition du
   défaut (« jusqu'à correction du moteur ») — ce motif est périmé depuis
   `304f04c`. Consigner au CHANGELOG que le retrait du contournement est
   **définitif** (supersédé par la correction moteur), et non un état d'audit
   provisoire.
3. **Balayage des résidus** (docs et code) : entrées CHANGELOG de l'époque du
   contournement décrivant la « limitation connue » (hand-written V~.V dropped
   by build_phrase_pval) → marquer comme résolue par `304f04c` ; vérifier
   `MIGRATION_NOTES.md`, `PROVENANCE_PROSODY_CHUNKING.md`, les manuels
   (`lang_pack/manual/`) et les commentaires de code ; s'assurer qu'aucune
   copie du contournement ne survit (copies installées `vtl_synth/utils/` ↔
   sources `lang_pack/profiles/` — actuellement synchrones, le rester).
4. **Hors périmètre.** `g2p_fr_legacy.py` n'est PAS du code mort (source de
   données v1 importée par `g2p_fr.py`) — ne pas le supprimer. Le moteur
   `engine='legacy'` (déprécié) et `video/polar_video.py` sont des voies non
   couvertes documentées (IMPLEMENTATION_V1V2 §6.5) — ne pas les toucher ici.
5. **Historique git.** Aucune réécriture demandée : la chaîne
   `2a55b69` → `1b81aef` → `304f04c` documente le raisonnement (provenance).
   L'exigence porte sur le **tree livré** : il ne doit pas contenir le
   contournement, et aucun commit futur ne doit le réintroduire.
6. **Garde-fou.** Après nettoyage : re-vérifier la non-perturbation (témoins
   oraux bit-identiques avant/après) et la suite de tests (`pytest tests/ -q`).

## 7. P6 — Étendre le traitement aux autres langues (de, en, es, it, pt)

**Constat d'architecture.** La porte `split_nasal_hiatus` agit sur la chaîne
SAMPA à l'entrée de `build_phrase_pval` — elle est **agnostique de la
langue**. Mais toute la validation (corpus, harnais, tests) est française.
Étendre la validation au pack complet.

1. **Portugais — priorité 1** (seule autre langue du pack à voyelles nasales
   phonémiques : `@~ o~ e~ a~ u~ i~`, cf. `language_vowel_sets.py` et
   `g2p_pt.py` — « cão » `k @~ w`, « sem » `s e~ j`, « também »
   `t @~ b e~ j`, « axioma » `a k s j o~ m @`) :
   - construire `AUDIT_V1V2/corpus_v1v2_pt.json` sur la même typologie
     structurelle que le français (S1 inter-mot V~.V ; S2 inter-mot V.V~ ;
     S3 intra-mot V.V~ ; S4 intra-mot V~.V ; témoins T oraux et nasaux
     isolés ; paires H en SAMPA direct `ta~.ata`, `ta.a~ta`, …) ; items
     réels du portugais européen via `lang_pack/lexicons/pt_lexicon.tsv` et
     les règles `g2p_pt` ; **inclure un item dédié diphtongue nasale**
     (ex. « cão » seul → chemin plateau, VO ≈ 0,5 attendu, inchangé
     avant/après) ; quand la typologie n'a pas d'instanciation lexicale
     naturelle en pt, la couvrir par un item H (SAMPA direct) et le
     documenter ; vérifier la jonction inter-mot de `g2p_pt` (point de
     liaison ?) sur des items S1/S2 réels ;
   - paramétrer `run_corpus.py` par langue (`--lang`, corpus dédié) ou
     boucle sur les corpus présents ;
   - `python setup_lang.py install --lang pt && python setup_lang.py setlang pt`
     puis exécuter le harnais ;
   - critères identiques à fr : VO ≥ 0,4 sur les moitiés nasales ; témoins
     oraux **bit-identiques** avant/après ; md5 distincts pour les paires H.
2. **Espagnol, italien, allemand, anglais — preuve d'inertie** (aucune
   voyelle nasale phonémique ; pré-vérifié : `g2p_es`/`g2p_de` n'émettent
   jamais `~`, l'unique `~` de `g2p_it` est un commentaire de doc, l'anglais
   passe par ARPAbet sans `~`) :
   - balayer les sorties g2p d'un échantillon de textes par langue (et les
   lexiques `.tsv`) : prouver que `~` n'est jamais émis → la porte est
   structurellement inerte ;
   - non-perturbation bit à bit sur un échantillon oral par langue
   (sorties avant/après `304f04c` identiques) ;
   - documenter la couverture défensive : si un lexique futur ou du SAMPA
   manuel introduit `~`, le moteur gère la bascule au lieu de perdre la
   nasalité.
3. **Inventaire moteur.** Le résiduel de P3 (`phonemes.py:38`, clés nasales
   dans `SAMPA_VOWELS`) doit couvrir les clés émises par **toutes** les
   langues (fr : `a~ e~ i~ o~ u~ y~ 2~ 9~ O~ @~` ; pt : `@~ o~ e~ a~` …) —
   recouper `VOWEL_TARGETS` et `language_vowel_sets.py`.
4. **Tests.** Étendre `tests/test_nasal_preproc.py` : cas pt (diphtongues
   nasales, frontières inter-mot), identité de la porte sur entrées sans
   `~` (es/it/de/en).
5. **Livrables.** Résultats par langue dans `AUDIT_V1V2/results/` ; CHANGELOG
   à jour ; extension du rapport d'audit (tableau récapitulatif multilingue) ;
   le harnais ne doit pas écraser les résultats fr existants.
