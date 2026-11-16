# COVERAGE_REPORT.md — Mesure de couverture n°4 : application des recommandations §7 de la vague 3 (refactorisation logicielle sur clone frais)

**Date de mesure** : 2026-11-14
**Dépôt mesuré** : https://github.com/fberthommier/covtl-pipeline — base HEAD `3903645d3f91862c49f934aee94e2b2cc09c4bd` (vtl-synth 1.1.3), **cloné à neuf** dans `covtl-wave4` (branche `wave4`)
**Objet de cette campagne** : appliquer les recommandations du §7 du rapport vague 3 — corriger les 2 bugs découverts, supprimer (et non plus seulement marquer) les 4 blocs morts, désambiguïser le canal E, couvrir les modes de phonation, verrouiller la composition sandhi en CI — avec cette fois des **modifications logicielles réelles** livrées comme **patch prêt à appliquer pour l'agent externe**, puis mesurer la couverture sous ces recommandations.
**Outils** : Python 3.12.16 · pytest 9.0.2 · pytest-cov 7.0.0 · Coverage.py 7.13.1 · numpy 2.1.3 · vocaltractlab-cython 0.0.17 (speaker JD3 actif) · covtl-sandhi v0.1.0 (activation Branch B par copie, pour la mesure)

---

## 1. Résumé exécutif

Les cinq recommandations du §7 du rapport vague 3 ont été appliquées comme **8 commits atomiques** sur un clone frais, avec preuve de non-régression à chaque étape où le comportement devait rester identique. La refactorisation des 4 cas morts (recommandation §7.2) est passée du stade « marquage pragma » (vague 3) à la **suppression effective** : les 27 lignes mortes ont été retirées de `build_global_pval`, avec preuve de bit-identité par hachage SHA-256 (brut + quantifié 1e-9 + structure de blocs) sur 22 phrases à pauses, et les 49 baselines de régression inchangées. La « prise en compte des consonnes » (§7.1) corrige la cause racine identifiée en vague 3 : `notation.ALL_K` dérive désormais du registre complet `ALL_PHONEME_KEYS` — les consonnes sourdes **p, t, k, f, s, S, T, tS** ne sont plus signalées à tort comme « caractères ignorés ». Deux bugs supplémentaires réparés : `parse_to_anchors` (kwarg renommé, TypeError systématique) et — découvert en cours de vague — les **overrides level-C du TagInterpreter n'atteignaient jamais les FeatureEvents** (les modes breathy/creaky/whisper étaient inopérants via l'API de tags). Le canal E est désambiguïsé (`E_fallback`). La CI gagne le job sandhi (recommandation §7.4).

**La campagne mesure 76,6 % de couverture combinée** (périmètre constant hors règles sandhi, vs 76,1 % en vague 3 et 74,5 % en vague 2), avec **501 tests verts, 0 échec**. La progression brute est modeste (+0,5 pt) mais c'est la structure qui change : `syltraj.py` passe à **95,5 %** (45→12 lignes manquantes), `enveloppe.py` à **85,3 %** (123→66), `notation.py` à **97,7 %**, `_make_phonation_mode_events` de 18 % à **96,3 %**, et le plafond honnête §7.5 (hors V1 déprécié + vidéo + g2p non-fr) atteint **78,6 %**. Tout l'essentiel du reliquat est désormais du code V1 déprécié par design ou de la couche vidéo volontairement légère.

**Livrable principal** : `download/covtl-wave4-patch/` — 8 `git format-patch` + diff cumulé + `bitident.py` (l'outil de preuve) + README d'application, **validé par application réelle sur un clone vierge** (`git am --keep-cr` → arbre byte-identique → 501 tests verts).

| Indicateur | Vague 3 | **Vague 4** | Δ |
|---|---|---|---|
| Couverture combinée (périmètre constant) | 76,1 % | **76,6 %** | +0,5 |
| Lignes couvertes | 6 521/8 177 (79,7 %) | **6 540/8 151 (80,2 %)** | +19 (et −26 statements morts retirés) |
| Branches couvertes | 2 084/3 130 (66,6 %) | **2 089/3 118 (67,0 %)** | +5 |
| Tests | 503 (501 pass · 0 fail) | **504** (501 pass · 0 fail · 3 skips attendus) | +1 (recodé) |
| `core/syltraj.py` | 92,9 % | **95,5 %** | +2,6 |
| `core/enveloppe.py` | 81,6 % | **85,3 %** | +3,7 |
| `core/notation.py` | ~91 % | **97,7 %** | fix consonnes |
| `_make_phonation_mode_events` | 18,5 %* | **96,3 %** | fix tags |
| `parse_to_anchors` | 0 % (cassé) | **100 %** | réparé |
| Bugs ouverts | 2 (+1 latent) | **0** | tous corrigés |
| Plafond honnête §7.5 | 78,2 %* | **78,6 %** | +0,4 |

\* valeurs re-mesurées en cours de vague 4 sur l'état vague 3 (le « 82 lignes » du §4.5 vague 3 était surestimé : le corps de `_make_phonation_mode_events` n'était en réalité jamais entré).

---

## 2. Méthodologie : clone frais, commits atomiques, preuve continue

1. **Clone frais** (`git clone covtl-pipeline covtl-wave4`, branche `wave4`) depuis HEAD `3903645` — aucun état résiduel des vagues précédentes ; le durcissement vague 3 (perdu au recyclage du sandbox) a été **re-recréé intégralement** (corpus 98 tests, pins SHA quantifiés, 26 tests ciblés, LEGACY §1bis, CI phonetic-fast, pyproject) et commité en premier.
2. **Empreintes pré-refactor** : `bitident.py` (livré dans le patch) hache 22 phrases avec pauses — SHA-256 brut, SHA-256 quantifié 1e-9, formes et structure de blocs — sur l'état avant modification.
3. **Un commit = une recommandation**, chaque message de commit documente la preuve (renvois au rapport vague 2 §4.4 pour les blocs morts, deltas mesurés pour les fixes).
4. **Vérification après chaque commit** : bit-identité (pour les refactors), suite de tests, baselines sha256.
5. **Validation du patch** : application par `git am --keep-cr` sur un clone vierge de `3903645`, comparaison byte-à-byte des diffs, exécution de la suite sur le dépôt patché.

---

## 3. Application des recommandations §7 du rapport vague 3

### 3.1 Correction des 2 bugs découverts (§7.1)

**Bug 1 — `notation.ALL_K` incomplet (la « prise en compte des consonnes »)**. Cause racine : `ALL_K = VOWELS_K | CONSONANTS_K` où `CONSONANTS_K` dérive de `CONSONANT_TARGETS` — qui ne porte que les **cibles articulatoires voisées**. Les sourdes (`constants._VOICELESS_KEYS = {p, t, k, f, s, S, T, tS}`) sont enregistrées dans `ALL_PHONEME_KEYS` (le registre des tokenizers) mais absentes du garde de la passerelle de notation. Correctif (commit `ec81a1a`) : `ALL_K = frozenset(ALL_PHONEME_KEYS)`. Vérifié : `preprocess_phrase('klinpan')` → ignorés `[]` (avant : `['k', 'p']`), `unknown_chars('stra ka pa fjuZ')` → `[]`, tokenisation inchangée (`build_flat('ka pa')` contient toujours k et p — le fix n'élargit que le jeu de caractères connus pour le signalement). Test nominal mis à jour.

**Bug 2 — `enveloppe.parse_to_anchors` cassé (API drift)**. Correctif (commit `7681cfe`) : passage du kwarg renommé `coarticulation_marker=` (et alignement des défauts sur `parse_ipa_with_markers` : 300 ms pause, 60 ms voyelle). La fonction retourne désormais la chaîne d'anchors `V_o / C_b / V / V_e` par syllabe — verrouillée par test nominal (8 anchors pour « ba da », temps chronologiques).

### 3.2 Suppression des 4 blocs morts — refactorisation réelle (§7.2, extends vague 2 §4.4)

Commit `971f2f2` : les 4 bras morts de `build_global_pval` sont **retirés du code** (remplaçant les `pragma: no cover` posés en vague 3) :

| Bras supprimé | Raison structurelle (preuve settrace vague 2) |
|---|---|
| `a_term` / else (cluster après pause à départ terminal) | `build_anchors` insère un anchor d'attaque vocalique après toute pause précédant un C → `m == 0` toujours ; le bras `m == 0` (arc + bloc `initial`) est le chemin vivant |
| `b_term` / `m > 0` (cluster terminal) | `build_anchors` insère un anchor de fin de mot avant toute pause suivant un C → `m == 0` toujours ; le `elif` (decay de V avant pause) est vivant |
| bloc pause médian (`pending_pt` consommé face à un anchor non terminal) | toujours consommé avant par la branche `a_term` |
| 2 blocs post-boucle (plateau V final, arc de pause final) | `build_anchors` termine toujours par un anchor `synth` → jamais de V final tenu ni de pending résiduel |

**Contrôle qualité décisif** : la première édition avait inversé les bras vivants/morts du `a_term`/`b_term` — la vérification `bitident.py` l'a **immédiatement détecté** (88 différences sur la structure des blocs : `['cluster', …]` au lieu de `['initial', …]`), la correction a été faite avant tout commit. Après correction : **22/22 phrases bit-identiques** (SHA brut + quantifié + structure), 110 tests syltraj/corpus et les 49 baselines verts. C'est la démonstration opérationnelle de la méthodologie : aucune suppression de code mort ne passe sans preuve d'équivalence.

### 3.3 Canal E désambiguïsé (§7.2/§2.2)

Commit `c02f482` : `TimedEnvelope.get_all_extensions()` exporte **`E_fallback`** au lieu de `E`. En l'état vague 3, l'E de la branche B était calculé puis **écrasé à la jonction** (`build_phrase_tract.py:751` : `extensions['E'] = E_100`, la branche A `amplitude_envelope`) — un calcul mort à l'arrivée. Le renommage rend l'architecture honnête : la branche B reste maîtresse de VO/V/f0/glottis, la branche A de l'E moteur ; l'affectation l.751 devient une création (commentaire mis à jour). Aucun consommateur interne ne lisait `ext['E']` en amont de la jonction ; `text_to_tract` (V1) et `assemble_tract` consomment l'E défini par le moteur. **Breaking change externe documenté** (clé renommée pour tout consommateur tiers de la branche B).

### 3.4 Modes de phonation — le 3e bug découvert en cours d'application

En voulant couvrir `_make_phonation_mode_events` (recommandation §7.3), la mesure a révélé que le corps de la fonction **n'était jamais entré** (18,5 %) malgré un test « breathy » qui passait : le delta glottis observé venait des presets, pas des FeatureEvents. Deux causes empilées :

1. `_schedule_segment_events` (enveloppe.py:390) lisait `DEFAULT_PHONEME_TAGS` seul, **ignorant les `tag_overrides` level-C du `TagInterpreter`** — l'override annotait le segment mais les événements (VOT, phonation) étaient construits sur les défauts. Correctif (commit `269b23a`) : fusion des défauts et des overrides, en miroir de `tag_system.TagInterpreter.apply`.
2. `TimedEnvelope(anchors=...)` re-dérive ses segments via `anchors_to_segments`, qui **re-étiquette les voyelles en `@`** : un override level-C ciblant la voyelle d'origine (« a ») ne matche jamais les segments reconvertis. Comportement documenté et verrouillé par le test (commit `bfc19bb`) : les jeux d'événements exacts des trois modes (breathy → {chink_area, x_bottom} ; creaky → {f0_offset, double_pulsing} ; whisper → {chink_area, x_bottom, x_top}) sont assertés sur la clé convertie (`@`) et sur une clé consonne (`b`), plus la baseline sans override (aucun événement de phonation).

Après correctifs : `_make_phonation_mode_events` **96,3 %**, et les trois modes de phonation sont **réellement pilotables** par l'API de tags.

### 3.5 CI sandhi (§7.4)

Commit `7d60b6e` : job `sandhi` dans `ci.yml` — clone de covtl-sandhi, activation Branch B par la procédure de copie officielle (`cp -r sandhi/. vtl_synth/utils/sandhi/`), assertion `SANDHI_FULL`, puis suite croisée (hook + composition V1V2×sandhi). La composition n'est plus jamais skippée en CI. Workflow YAML validé (4 jobs : `phonetic-fast`, `tests`, `baselines`, `sandhi`).

---

## 4. Mesures sous les recommandations vague 4

### 4.1 Conditions de mesure

Suite complète avec Branch B sandhi activée par copie (comme en vague 3) : `pytest tests/ --cov=vtl_synth --cov-branch --cov-report=term-missing --cov-report=xml:coverage_wave4.xml -q` → **501 passed, 3 skipped** (les skips croisés sandhi attendus par design : les tests stub-only se désactivent quand Branch B est installée), **194,6 s**. Le périmètre de comparaison inter-vagues exclut `utils/sandhi/` (règles du paquet compagnon, suite dans leur dépôt).

### 4.2 Résultats globaux et par module

| | Vague 2 | Vague 3 | **Vague 4** |
|---|---|---|---|
| Combiné (périmètre constant) | 74,5 % | 76,1 % | **76,6 %** |
| Lignes | 78,3 % | 79,7 % | **80,2 %** (6 540/8 151, miss 1 611, voir §4.4) |
| Branches | 64,5 % | 66,6 % | **67,0 %** |
| Statements mesurés | 8 227 | 8 177 | **8 151** (−26 : bras morts retirés) |

| Module (combiné) | Vague 2 | Vague 3 | **Vague 4** | Lignes manquantes |
|---|---|---|---|---|
| `core/syltraj.py` | 90,9 % | 92,9 % | **95,5 %** | 45 → 32 → **12** |
| `core/build_phrase_tract.py` | 81,7 % | 93,3 % | **93,3 %** | 63 → 20 → **20** |
| `core/enveloppe.py` | 75,2 % | 81,6 % | **85,3 %** | 123 → 88 → **66** |
| `core/continuous.py` | 84,4 % | 87,1 % | **87,1 %** | 65 → 51 → **51** |
| `core/notation.py` | — | ~91 % | **97,7 %** | **1** |
| `core/tag_system.py` | — | — | **86,2 %** | 6 |

Fonctions notables : `build_global_pval` (syltraj) **95,2 %** · `parse_to_anchors` **100 %** · `preprocess_phrase` **100 %** · `unknown_chars` **100 %** · `build_phrase_tract` 94,2 % · `_make_phonation_mode_events` **96,3 %** · `create_timed_envelope_from_segments` 79,1 %.

### 4.3 Le plafond honnête (§7.5)

Hors moteur V1 déprécié par design (`continuous`, `trajectory`, `prosody_source`, `parsing` — l'engine `'legacy'` n'est gardé que comme référence d'alignement), hors couche vidéo (LEGACY.md §3 : encodage ffmpeg non bit-stable) et hors g2p des langues non-françaises : **78,6 %** (5 266/6 395 lignes, 1 711/2 486 branches) — contre 78,2 % re-mesurés sur l'état vague 3. Le gap restant vers 100 % se concentre sur les branches de configuration et chemins d'erreur rares du chemin syl.

### 4.4 Lecture du reliquat (1 611 lignes, périmètre constant)

| Composant | Lignes | Statut après vague 4 |
|---|---|---|
| V1 déprécié (continuous 51, trajectory 65, prosody_source 25, timers 107 en partie) | ~250 | déprécié par design (DeprecationWarning) — candidat exclusion 2.0 |
| `enveloppe.py` restant | 66 | variantes de `envelope_from_anchors` (58 %, API de recherche désormais honnête avec `E_fallback`), restes breathy/whisper avancés |
| vidéo (polar_video, renderer) | ~230 | politique LEGACY.md §3 |
| g2p de/es/it/pt | ~180 | tables linguistiques non chargées par défaut |
| divers (polar, projection, prosody_f0, setlang, CLI…) | ~900 | branches de configuration, chemins d'erreur rares |

### 4.5 Timing du job rapide

`pytest tests/test_phonetic_model_inputs.py` : **97 tests en ~5,9 s** (wall clock) — conforme à l'objectif du job `phonetic-fast` (signal précoce à chaque push/PR).

---

## 5. Le patch pour l'agent externe

**Livrable** : `download/covtl-wave4-patch/`

```
covtl-wave4-patch/
├── README.md               # procédure d'application + impact + résultats
├── commits/                # 8 git format-patch (série à appliquer avec git am --keep-cr)
├── wave4_squashed.diff     # diff cumulé (1 442 lignes) pour application en un commit
└── bitident.py             # preuve bit-identité (22 phrases, save/check)
```

**Point technique important (fins de ligne)** : les fichiers moteur du dépôt sont des blobs git **CRLF**, les tests des blobs LF. La série de patches préserve ces fins de ligne ; l'application exige `git am --keep-cr` (documenté dans le README, avec le fallback `git apply --keep-cr` pour le diff cumulé). Une application sans cette option échoue sur `syltraj.py` — c'est le symptôme, pas un défaut du patch.

**Validation effectuée** : application sur clone vierge de `3903645` → arbre final **byte-identique** à la branche d'origine (`git diff` cumulé égal), 8 commits appliqués proprement, suite de tests verte sur le dépôt patché.

**Impact comportemental** (détaillé dans le README) : sorties moteur inchangées (bit-identité + baselines) ; suppression des faux avertissements de consonnes ignorées ; `parse_to_anchors` fonctionnel ; overrides level-C breathy/creaky/whisper opérationnels ; **breaking** : la clé `'E'` de `TimedEnvelope.get_all_extensions()` devient `'E_fallback'` (aucun consommateur interne affecté).

---

## 6. Commandes exactes et artefacts

```bash
# 1. appliquer le patch (agent externe)
git checkout -b wave4 main
git am --keep-cr download/covtl-wave4-patch/commits/*.patch

# 2. preuve bit-identité du refactor (optionnelle, avant/après commit 2)
python3 bitident.py save pre && python3 bitident.py check pre

# 3. campagne de couverture vague 4
pytest tests/ --cov=vtl_synth --cov-branch \
  --cov-report=term-missing:skip-covered \
  --cov-report=html:htmlcov_wave4 \
  --cov-report=xml:coverage_wave4.xml -q
# → 501 passed, 3 skipped in 194.64s

# 4. job rapide
pytest tests/test_phonetic_model_inputs.py -q     # 97 tests, ~5,9 s
```

| Artefact | Contenu |
|---|---|
| `COVERAGE_REPORT.md` (ce fichier) | rapport vague 4 |
| `coverage_wave4.xml` / `htmlcov_wave4/` | mesures brutes de la campagne |
| `download/covtl-wave4-patch/` | le patch pour l'agent externe (8 commits + diff + README + bitident) |
| `scripts/bitident.py` (dépôt racine) | outil de preuve, aussi livré dans le patch |

---

## 7. Recommandations (vague 5)

1. **Merger la branche `wave4`** (8 commits) après relecture — l'ordre des commits est conçu pour une relecture commit-par-commit avec vérification bit-identité au commit 2.
2. **Documenter le re-étiquetage `@` d'`anchors_to_segments`** dans la docstring du `TagInterpreter` : un override level-C doit cibler la clé du segment converti (voyelles → `@`), pas la clé d'origine — source de confusion pour tout utilisateur de l'API de tags.
3. **Exclure le V1 déprécié de la mesure** (ou le supprimer en 2.0) : ~250 lignes mesurées à jamais non couvertes par design ; avec cette exclusion, la couverture affichée du package atteindrait le plafond honnête de 78,6 % sans écrire une ligne de test supplémentaire.
4. **Reliquat enveloppe** : les 66 lignes restantes sont pour l'essentiel des variantes de `envelope_from_anchors` (API de recherche, désormais honnête grâce à `E_fallback`) — à couvrir seulement si l'API devient consommée.
