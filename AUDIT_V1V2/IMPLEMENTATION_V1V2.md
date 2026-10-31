# IMPLEMENTATION V1V2 — Correction moteur : bascule nasal/oral sur les hiatus liés

**Date :** 2026-10-31 · **Dépôt :** clone `covtl-pipeline` (base : chaîne d'audit, HEAD `0f935b8`)
**Fait suite à :** `AUDIT_V1V2/AUDIT.md` (constats) et `AUDIT_V1V2/MISSION.md` (cahier des charges)

---

## 1. Principe prescrit et retenu

> *Laisser intacte l'élaboration de l'espace paramétrique par `syltraj` ; convertir
> les voyelles nasales en non nasales afin d'obtenir les transitions diphtongue de
> base ; introduire l'information de nasalité au niveau de l'espace orthogonal de
> commande du port vélaire et du timer associé qui existe déjà.*
> Implémentation **non perturbatrice**, moyennant une **couche de pré-traitement**.

L'architecture retenue factorise la nasalité hors de l'espace formantique :

```
entrée SAMPA (avec '~') ──┬──────────────────────────────► segments / étiquettes /
                          │                                timers / effort pulmonaire
                          │                                (chaîne ORIGINALE, inchangée)
                          │
                  ┌───────▼────────┐        ┌──────────────────────────┐
                  |  nasal_preproc |  plan   │  syltraj (INTACT)        │
                  |  (pré-trait.)  │───────►│  chaîne moteur ORALISÉE  │
                  |  scission       │        │  → Pval, block_info      │
                  └───────┬────────┘        └──────────┬───────────────┘
                          │  événements de nasalité     │ blocs background
                          │  (runs vocaliques,          │ (arcs 2·T_voy)
                          │   positions, cibles)        │
                          └───────────┬─────────────────┘
                                      ▼
                  ┌────────────────────────────────────────────────┐
                  │ build_phrase_tract — étape 3b-bis (NOUVELLE)   │
                  │ VO ⊇ rampe 0.5 (20 %) sur les moitiés nasales  │
                  │ puis TIMER EXISTANT : lissage 1er ordre τ=20ms │
                  └────────────────────────────────────────────────┘
```

Points clés :

1. **`syltraj.py` n'est pas modifié** (diff vide). L'arc de fond du hiatus
   (`background`, 2·T_voy) **est** la transition diphtongue de base — il est
   construit sur les cibles polaires orales, ce qui est déjà la représentation
   interne du moteur (une nasale = cible orale + drapeau, cf. `build_nodes` :
   `base = key.rstrip('~')`).
2. **Couche de pré-traitement** (`vtl_synth/core/nasal_preproc.py`, nouveau) :
   les voyelles nasales **membres d'un hiatus** (séquence vocalique adjacente
   de longueur ≥ 2, à travers ou sans point de liaison) sont **oralisées dans
   la chaîne moteur** ; la nasalité est capturée comme **événement** (run,
   position, cible orale). L'oralisation est **chirurgicale** : les voyelles
   nasales tenues (hors hiatus) gardent le chemin existant (plateau + drapeau
   `nasal`) — elles fonctionnent déjà.
3. **Réinjection orthogonale** (`build_phrase_tract.py`, étape 3b-bis, ~25
   lignes) : la nasalité des membres d'hiatus est appliquée dans l'extension
   **VO** existante — même cible (`VO_NASALIZED_VOWEL` = 0,5), mêmes rampes
   symétriques 20 % (max 40 ms) que le chemin des plateaux nasaux — puis
   **le timer vélaire existant** (lissage anti-clic du premier ordre,
   τ = 20 ms) façonne les bascules nasal↔oral. Aucun autre canal n'est
   modifié : B(t) (15 paramètres), E(t), V(t), source glottique restent ceux
   de la base orale.

## 2. Fichiers

| Fichier | Nature | Contenu |
|---|---|---|
| `vtl_synth/core/nasal_preproc.py` | **nouveau** | Couche de pré-traitement : `split_nasal_hiatus()` (scission + plan), `nasal_hiatus_intervals()` (localisation temporelle), `vo_nasal_segment()` (rampe), `get_last_nasal_plan()` (état, pattern `get_last_build`) |
| `vtl_synth/core/build_phrase_tract.py` | modifié (3 insertions) | (1) scission avant `build_phrase_pval` — le moteur reçoit `ipa_motor` ; (2) `nasal_plan = None` pour le moteur `legacy` ; (3) étape 3b-bis : overlay VO avant le lissage τ = 20 ms |
| `vtl_synth/core/syltraj.py` | **non modifié** | — |
| `tests/test_nasal_preproc.py` | **nouveau** | 33 tests : portée de l'oralisation, aller-retour tokenizer, intervalles (moitiés, fusion V~.V~, runs VVV), rampe, nasalité après synthèse, non-perturbation, identité de l'espace paramétrique |
| `AUDIT_V1V2/run_corpus.py` | modifié | verdict sur la vue nodale d'ORIGINE (drapeaux vrais) + mesure VO sur les **moitiés nasales réelles** du plan (l'ancienne métrique « demi-fenêtre centrale » ne voyait pas la dernière moitié des runs VVV) |
| `AUDIT_V1V2/compare_avant_apres.py` | **nouveau** | vérification avant/après : VO seule colonne modifiée, témoins bit-identiques, inversion de l'identité octet H0-H3, paires WAV pour écoute |
| `AUDIT_V1V2/results_avant/` | **nouveau** | archive de l'état défaillant (référence « avant ») |
| `AUDIT_V1V2/results/` | régénéré | état corrigé + `compare_avant_apres.json` |
| `AUDIT_V1V2/wav_compare/` | **nouveau** | WAV avant/après de chaque item pour écoute comparative |

## 3. Localisation temporelle (runs ↔ blocs `background`)

La correspondance repose sur un invariant structurel du moteur, **vérifié à
chaque exécution** (sinon repli conservateur — avertissement, pas d'injection) :

- chaque **paire interne** d'un run vocalique émet exactement un arc
  `background` de 2·T_voy (le découpage schwa en deux blocs conserve le
  total) ; les runs de longueur k produisent (k−1) arcs **consécutifs** ;
- deux runs distincts sont toujours séparés d'au moins un bloc non
  `background` (cluster, pause, decay…) ;

donc : **g-ième run ↔ g-ième groupe de blocs `background` consécutifs**,
total attendu (k−1)·2·T_voy. Le membre j du run possède le créneau
[j·T, (j+1)·T) (premier membre de la paire j), prolongé de [(2j−1)·T, 2j·T)
(second membre de la paire j−1) — les voyelles médianes de runs VVV disposent
ainsi de 2·T_voy, conformément au temps alloué par le moteur.
**Les créneaux nasaux adjacents sont fusionnés** : la bascule nasal/oral ne
se produit qu'aux vraies frontières nasal↔oral (`9~.a~` : vélum ouvert d'un
bout à l'autre de l'arc).

T_voy effectif : paramètre `t_voy` répliqué comme dans `build_phrase_pval`,
recoupé avec les pas des blocs `plateau` et le total des groupes (défense en
profondeur).

## 4. Résultats mesurés (corpus complet, 20 items)

| Critère d'acceptation (MISSION §1) | Résultat |
|---|---|
| Nasalité réalisée : `max(VO)` sur les moitiés nasales ≥ 0,4 | **0,491 – 0,500** (référence saine 0,49-0,50) — S1a→S4b, T5, T6, H1-H4 |
| VO retombe sur la moitié orale | rampe descendante achevée à la frontière de créneau + τ = 20 ms → baseline −0,1 |
| `ta~.ata` ≠ `ta.ata` (md5 .wav/.tract) | **4 md5 distincts** pour H0/H1/H2/H3 (l'identité octet §4.5 de l'audit est cassée) |
| Non-régression | suite du dépôt : **188 réussis** (155 avant + 33 nouveaux), les 3 échecs préexistants à l'état d'audit (hash speaker + `test_syltraj_double_pause` : SHA verrouillé au commit `48442aa9`, invalidé par le fix D-11 `511cf2e` antérieur) sont inchangés |
| Non-perturbation | **5 témoins bit-identiques** (T1, T2, T3, T4, H0) ; pour les 15 items corrigés, **seule la colonne VO (7) du `.tract` diffère** — preuve que l'espace paramétrique est intact |
| `nas.perdue` | **20/20 « non »** (avant : 15 « OUI ») |

Sorties de vérification : `AUDIT_V1V2/results/compare_avant_apres.json`
(machine-lisible) et `AUDIT_V1V2/wav_compare/{avant,apres}/*.wav` (écoute ;
comparer p. ex. `avant/H1.wav` — « ta~.ata » dénasalisé — et `apres/H1.wav`).

## 5. Re-vérification (commandes)

```bash
python AUDIT_V1V2/run_corpus.py            # tableau : nas.perdue = non partout
python AUDIT_V1V2/compare_avant_apres.py   # VERDICT GLOBAL : SUCCÈS
pytest tests/test_nasal_preproc.py -q      # 33 passed
pytest tests/ -q                           # 188 passed, 3 préexistants
```

## 6. Choix d'architecture à noter (pour l'agent)

1. **Le critère « blocs étiquetés » de la MISSION (P1) est supédité** par le
   principe prescrit : l'arc de fond **reste** la réalisation des noyaux de
   l'hiatus (diphtongue de base, mesurée : énergie et formants présents) ;
   il n'y a **pas** de scission en deux demi-blocs `T_voy`. La mission
   demandait « un bloc étiqueté par membre » comme moyen de transporter le
   drapeau nasal ; la couche de pré-traitement transporte désormais cette
   information hors du moteur, sans le modifier.
2. **Oralisation chirurgicale (hiatus seulement).** Oraliser aussi les
   voyelles tenues aurait redirigé le chemin des plateaux (qui fonctionne)
   vers la nouvelle couche : perturbation gratuite. La portée retenue est
   le plus petit ensemble qui couvre le défaut.
3. **Chaîne d'origine préservée partout ailleurs** : `parse_to_segments`
   (étiquettes glottales/vélaires, `TimedEnvelope`, effort pulmonaire —
   « nasality requires continuous airflow ») voit toujours les '~' ;
   seule l'entrée de `build_phrase_pval` est oralisée.
4. **Repli conservateur garanti** : tout écart de l'aller-retour tokenizer
   ou de la correspondance runs↔groupes désactive l'injection (avertissement
   `nasal_preproc`) et rend le comportement antérieur — la correction ne
   peut jamais produire une chaîne ou une sortie inattendue.
5. **Voies non couvertes** (documentées, sans effet sur la synthèse) :
   `engine='legacy'` (déprécié) et l'instrumentation vidéo
   (`video/polar_video.py`, qui appelle `build_phrase_pval` directement)
   ne passent pas par la porte. Les baselines de régression du dépôt ne
   changent pas (aucune sortie moteur hors hiatus nasal n'est modifiée —
   vérifié bit à bit sur les 5 témoins).

## 7. Suites recommandées (reprennent la MISSION §2 P3/P4 et les nouvelles consignes §6-§7)

- **P3 (résiduel)** — après validation : corriger `phonemes.py:38`
  (`SAMPA_VOWELS` doit inclure les clés nasales — « néon » doit sortir
  `neO~` syllabé et « envie » `a~.vi`) ; consigner au CHANGELOG.
  **La clause de ré-inversion des contournements g2p (`dea71c6`,
  `f62f185`) est ANNULÉE** : voir MISSION §6 (P5) — le retrait est
  définitif, l'état « point de liaison partout » doit être conservé.
- **P5 — décommissionnement** (MISSION §6) : retirer définitivement les
  modifications devenues inutiles (contournements g2p/prosodie), balayer
  les résidus documentaires, consigner le caractère définitif au CHANGELOG.
- **P6 — autres langues** (MISSION §7) : étendre la validation au pack
  complet — portugais prioritaire (corpus `corpus_v1v2_pt.json`, harnais
  paramétré par langue), preuve d'inertie pour es/it/de/en, inventaire
  `phonemes.py` couvrant les clés nasales de toutes les langues.
- Mettre à jour le SHA obsolète de `test_syltraj_double_pause` (préexistant,
  voir §4) lors de la régénération des baselines
  (`scripts/regen_baselines.py`).
- Optionnel : anticipations vélaire physiologiques (abaissement du voile
  pendant la consonne prévoclique nasalisée) — hors périmètre de la
  correction présente, qui reprend exactement la dynamique du chemin plateau.
