# MIGRATION_NOTES — packaging GitHub v1.1.0 (2026-09-16)

Notes de migration de `P:\covtl-pipeline` (état intégré et testé,
validé 2026-09-16) vers `P:\covtl-github` (package
https://github.com/FBerthommier/covtl-pipeline v1.1.0). Toute décision
discutable est consignée ici plutôt qu'improvisée. Style : découvertes
numérotées à partir de D22 (D1-D21 appartiennent aux travaux
antérieurs, cf. `P:\covtl-speaker`).

## 1. Décision de version : **v1.1.0** (et non v2.0.0)

Inventaire diff v1.0.2 (GitHub, 2 commits) → pipeline : **0 fichier
supprimé, 34 modifiés, 512 ajoutés** (dont l'essentiel = artefacts
exclus du package). Justifications :

- **Fichiers noyau (`vtl_synth/core/`) modifiés : 7** —
  `build_phrase_tract.py`, `constants.py`, `orthogonal_params.py`,
  `phonemes.py`, `pipeline.py`, `speaker_jd.py`, `syltraj.py` (+ nouveau
  `speaker_registry.py`). Nature des modifications : **additive** —
  résolution dynamique du `.speaker` par le registre (fallback JD3
  inchangé), option `--expressive` **défaut OFF bit-identique**
  (marqueur de pause respiratoire `%` sans effet sans le mode),
  transport de la LANG SECTION (bloc marqué, section native conservée
  en repli).
- **Preuve chiffrée de rétrocompatibilité** : `regression_baselines.json`
  (JD3) est **bit-identique** v1.0.2 → pipeline sur la clé `phrases`
  (seule la clé `meta` gagne le champ `speaker` et une note) — les
  sorties par défaut du locuteur de référence n'ont pas changé.
- Aucune signature publique du noyau supprimée ; pas de rupture
  d'API/CLI (toutes les nouvelles fonctionnalités sont des options ou
  des outils additionnels : `install_speaker.py`, `setup_lang.py`,
  `--polar`, `--expressive`, `plot-tract`).

En cas d'ambiguïté résiduelle, on reste sur v1.1.0 « jusqu'à preuve du
contraire » (consigne §2-2 du cahier des charges).

## 2. Découvertes (D22… )

- **D22** — `P:\covtl-github` existait déjà (vide, créé 2026-09-16
  16:56) alors que la mission le décrivait « à créer ». Dossier vide =
  aucune perte possible ; utilisé tel quel comme destination.
- **D23** — `vtl_synth/data/vtl_binaries/JD3.speaker` du pipeline
  contient une coquille d'un caractère (ligne 1801 :
  `escription=` au lieu de `description=`, 91065 o) alors que la
  ressource originale de la wheel et le fichier publié en v1.0 sont
  sains (92938 o, SHA-256 `a583bdaaa7ffe216…`). Fichier dormant (le
  registre court-circuite `vtl_binaries/` dès que
  `registry.json` existe), mais le package GitHub embarque à nouveau
  **l'original de la wheel** (celui de la v1.0), pour un fallback
  sain. Le pipeline (verrouillé) n'a pas été touché.
- **D24** — Le garde-fou « calibrate JD3-only » demandé existe déjà en
  code, contrairement à la note du cahier des charges (« convention ») :
  `setup_lang.py::_ensure_jd3()` est appelé par `cmd_calibrate` et par
  `cmd_install --calibrate` ; il **signale et réinstalle jd3**
  (constants + marqueur + ressource wheel) avant toute calibration —
  sémantique plus forte qu'un simple refus : une calibration ne peut
  jamais s'exécuter sur s1/s2/m01/w02. `report_current()`/`status`
  affichent en outre l'avertissement « cibles calibrées JD3 —
  HYPOTHÈSE » quand un speaker ≠ jd3 est actif avec une langue
  installée. **Comportement conservé tel quel** (état intégré testé) ;
  rien réimplémenté.
- **D25** — `install_speaker.py` du pipeline ancre trois dépendances à
  la machine de développement, incompatibles avec un dépôt public :
  journaux/backups dans `P:\covtl-speaker\upgrade_speaker\`
  (répertoire hors dépôt, non versionné) ; garde-fou editable exigeant
  la sous-chaîne « covtl-pipeline » dans le pointeur site-packages ;
  garde `backup_originals` sur le hash brut du constants JD3 **sans
  section de langue** (casserait au premier install avec LANG SECTION
  active). **Adapté dans la copie GitHub uniquement** (cf. §3).
- **D26** — `pyproject.toml` ne déclarait pas les nouvelles données de
  package (`data/speakers/`, lexiques `data/*.tsv`) : un
  `pip install .` non éditable n'aurait pas embarqué le registre
  multi-speakers ni les lexiques installés. Corrigé dans la copie
  (`[tool.setuptools.package-data]` étendu).
- **D27** — Faux positif d'import lors du premier test du venv :
  `import vtl_synth` résolvait `P:\covtl-pipeline` parce que la
  commande tournait avec **cwd = P:\covtl-pipeline** (la chaîne vide
  en tête de `sys.path`). Depuis un cwd neutre, l'editable du venv
  résout correctement `P:\covtl-github`. Consigne de validation :
  toujours exécuter depuis un répertoire neutre.
- **D28** — Faux positif du garde-fou editable adapté : le scan
  cherchait aussi dans le user-site AppData (théorique), où traîne le
  finder editable de l'installation `--user` du Python système
  (covtl-pipeline) ; ce finder n'est PAS actif dans un venv
  (ENABLE_USER_SITE=False). Corrigé : seuls les répertoires
  **réellement présents dans `sys.path`** sont scannés, et la
  comparaison accepte la racine ou `vtl_synth/` (le mapping du finder
  pointe le dossier package), y compris via `os.path.samefile`
  (lettre de lecteur vs forme UNC).
- **D29** — `Stash` (rollback install_speaker) plantait sur un marqueur
  `ACTIVE_SPEAKER` **absent** — l'état neutre expédié (defaut jd3 sans
  marqueur) n'était pas couvert par le code de développement. Corrigé :
  le stash mémorise l'absence et le rollback supprime un marqueur
  éventuellement créé entre-temps.
- **D30** — Bug latent du `restore` quand le backup contient déjà une
  LANG SECTION (cas GitHub : état initial expédié = jd3 + section en) :
  `_carry_lang_section` substituait le bloc « natif »
  (`VOWEL_TARGETS..VOWEL_EFFORT_GAIN..^}`) dans un fichier où ce bloc
  est en fait une section — la borne `^}` déborde et corrompt le
  constants (INCOHERENCE détectée par l'annonce, rollback automatique,
  aucun état à moitié installé). Corrigé : quand la destination
  contient déjà une LANG SECTION, la substitution se fait **par les
  marqueurs de section** ; le chemin natif reste pour les constants
  natifs du registre. Re-validé par un `restore` complet OK.
- **D31** — Une **session de travail parallèle** (passe documentation
  §2-6) a écrit dans `P:\covtl-github\docs` PENDANT la validation
  (18:27-18:47) : retouches des 5 `.tex`, **nouveaux manuels**
  `speakers.tex/.pdf` et `language_pack.tex/.pdf`, `README.md`
  d'index, artefacts de compilation (`.aux/.log/.out/.toc/.ttf`,
  rendus d'essai `_render/`, logs `_b*/_m*`). Traitement : les
  manuels `.tex/.pdf` + `README.md` **intégrés** (c'est la passe de
  cohérence prévue) ; artefacts purgés ; `_render/` (non référencé
  par les `.tex`) mis en quarantaine dans
  `P:\covtl-tmp\quarantaine_docs\` avec les logs d'essai supprimés
  (régénérables). La même session a posé 3 fichiers dans
  `P:\covtl-pipeline\out\` (`_docpatch/`) — aucun outil de la mission
  n'a écrit dans le pipeline (cf. §8, manifestes).
- **D32** — `manual.tex` référence une fonte IPA locale
  `.l_10646.ttf` (Path=./) **jamais distribuée** — la v1.0 GitHub
  publiée est dans le même état (le .tex la référence, le dépôt ne
  l'embarque pas ; le PDF livré embarque la fonte). Le `.ttf` déposé
  temporairement par la session parallèle a été retiré (réalignement
  sur l'état public) et `docs/README.md` documente désormais comment
  recompiler sans elle. *(Complété par D34 : la fonte a été redéposée
  après coup par la session parallèle ; retirée à nouveau le
  2026-09-17.)*
- **D34** (2026-09-17, re-vérification à froid, cf. §9) — La fonte
  `.l_10646.ttf` (304 516 o, SHA-256
  `97226e81f19eff8c8fb191745748bab920472c005d3ec4e23d9a50a12c471d92`)
  était **à nouveau présente** dans `docs/` : créée à 19:02:11 le
  16/09, soit *après* le traitement D32 (README 18:56) et *avant* la
  recompilation finale de `manual.pdf` (19:16) — la session parallèle
  de documentation l'avait redéposée pour compiler, et la purge finale
  ne l'avait pas retirée une seconde fois. Dérive par rapport à la
  décision D32 et à l'état public v1.0 (vérifié : aucun `.ttf` dans
  `P:\covtl-tmp\v1.0-ref`). **Corrigé** : déplacée en quarantaine
  (pratique D31) dans `P:\covtl-tmp\quarantaine_docs\.l_10646.ttf`
  — aucune suppression irréversible ; `manual.pdf` livré embarque la
  fonte, la recompilation sans elle reste documentée dans
  `docs/README.md`.

## 3. Adaptations appliquées à la copie (et seulement à la copie)

1. `install_speaker.py` rendu portable (D25) : backups/journaux dans
   `.speaker_backups/` **à l'intérieur du dépôt** (créé au premier
   usage, exclu par `.gitignore`) ; le garde-fou editable compare
   désormais le pointeur à **la racine de ce dépôt** (toute
   installation editable pointant ailleurs reste une erreur — la
   cartographie editable est globale) ; `backup_originals` accepte le
   constants initial sous forme **canonique** jd3 (region
   vowel/langue neutralisée) en plus du hash brut ; l'aide
   `install` liste les 5 locuteurs.
2. `pyproject.toml` : version **1.1.0**, package-data étendu (D26).
3. `tests/test_speaker_registry.py` : la classe `TestInstallRestore`
   (cf. §5) est retirée ; en-tête documenté.
4. Messages « depuis P:\covtl-pipeline » générisés
   (`tests/test_regression_baselines.py`,
   `scripts/regen_baselines.py` docstring).
5. `vtl_binaries/JD3.speaker` = original wheel (D23).
6. `.gitignore` : ajout `ACTIVE_SPEAKER`, `.speaker_backups/`,
   `*.polar`, exception `!examples/*.mp4`.
7. `examples/polar_demo_en.mp4` (297 Ko < 5 Mo) recopié depuis
   `out/` comme unique artefact de démonstration.

## 4. État machine NEUTRE expédié

- `vtl_synth/core/constants.py` = **jd3 natif + LANG SECTION « en »**
  (reproduit exactement `install_speaker.py install jd3` sur l'état
  intégré : copie de `jd3_constants.py` du registre + transport de la
  section de langue ; vérifié par hash canonique `5166e7615ca50789` =
  jd3 et `ACTIVE_LANG = 'en'`).
- **Pas de `ACTIVE_SPEAKER`** dans le package : `active_name()`
  retombe sur `jd3` (défaut du registre). Documenté « reinstall avant
  toute synthèse » dans README/INSTALL : après clonage,
  `python install_speaker.py install jd3|s1|s2|m01|w02` (ou rien — jd3
  par défaut).
- La ressource wheel (`site-packages/vocaltractlab_cython/resources/
  JD3.speaker`) n'est **pas** embarquée : elle appartient à
  l'environnement Python de l'utilisateur ; `install_speaker.py`
  la permute avec backup/restore (journaux et manifestes locaux).
- Duplication assumée et conservée : `lang_pack/lexicons/*.tsv`
  (source du pack) **et** `vtl_synth/data/*.tsv` (état installé,
  suivi par `.lang_pack_data_manifest`) — l'état installé fait partie
  de l'état intégré testé ; `setup_lang.py restore` sait revenir en
  arrière. Coût : ~13 Mo.

## 5. Tests allégés — conservés / exclus

Conservés (moteur pur, sans synthèse audio/vidéo ni wheel VTL, suite
complète < 1 min) : `test_cli.py`, `test_expressive.py`,
`test_glottal_classification.py`, `test_notation.py`,
`test_parsing_equivalence.py`, `test_polar_model.py`,
`test_regression_baselines.py` (+ 5 fichiers baselines),
`test_speaker_registry.py` **réduit à `TestRegistry`**,
`test_syltraj_structure.py`, `test_tract_figure.py` (extra `plot`).

Exclus du package GitHub (non migrés, disponibles dans
`P:\covtl-pipeline\tests\`) :

| élément exclu | raison |
|---|---|
| `test_speaker_registry.py :: TestInstallRestore` | installs réels en sous-processus (plusieurs minutes, smoke de synthèse par install) + dépendance au manifeste de backups local `P:\covtl-speaker\upgrade_speaker\backup_install\backup_manifest.json` |

Les tests de génération audio/vidéo complètes ne figuraient déjà pas
dans la suite pytest (les rendus MP4 se font via les démos
`examples/`), seul le smoke `install_speaker.py` synthétise (hors
suite, commande utilitaire).

## 6. Licences — répartition des 4 add-ons

- **Speakers m01/w02** : issus du ZIP officiel **VocalTractLab 2.4**
  (fichiers `.speaker` du dossier speakers), retouchés (mapping glottal
  2025→11 codes, index 7 = PS) — licence VocalTractLab (GPL,
  usage recherche, cf. THIRD_PARTY_NOTICES.md §VocalTractLab 2.4).
- **Speakers s1/s2** : créés pour ce dépôt à partir d'IRM DVTD
  (constants calibrés v3) — GPL-3.0-or-later avec le dépôt, données de
  recherche du projet.
- **Pack de langues** : répartition détaillée dans
  `lang_pack/LICENSE.md` (code GPL-3.0-or-later ; lexiques Wikipron
  **CC BY-SA 3.0** avec notices `README_xx_lexicon.md` obligatoires à
  côté des TSV) — repris dans THIRD_PARTY_NOTICES.md.
- **Expressivité & polar** : code du dépôt, GPL-3.0-or-later.

## 7. Validation (venv frais Python 3.9) — RÉSULTATS

Venv : `P:\covtl-tmp\venv-github` (hors package), Python 3.9.13,
`pip install vocaltractlab-cython==0.0.13` puis
`pip install -e "P:\covtl-github[plot,dev]"` (numpy 2.0.2, scipy 1.13.1,
Pillow 11.3, imageio-ffmpeg 0.6, cmudict 1.1.3, matplotlib 3.9.4,
pytest 8.4.2). La wheel du venv est isolée : les swaps de speakers
n'ont touché que `venv-github\lib\site-packages\...resources\JD3.speaker`.

| # | test | résultat |
|---|---|---|
| 1 | `install_speaker.py list` | **PASS** — 5 speakers (jd3 m01 s1 s2 w02), actif jd3 (défaut sans marqueur), wheel = jd3 |
| 2 | `install_speaker.py install m01` | **PASS** — exit 0, garde-fou editable OK, LANG SECTION transportée (+ avertissement HYPOTHÈSE), wheel venv = m01, smoke sous-processus SUCCESS **656 frames @400 Hz**, annonce `Speaker actif : m01`, couches cohérentes |
| 3 | run manuel `--phonetic "a i u"` (m01) | **PASS** — SUCCESS, 656 frames, wav 1.64 s |
| 4 | `setup_lang.py list` | **PASS** — de/en/es/fr/it/pt + « Langue en cours : en [speaker: m01] !! cibles calibrées JD3 — HYPOTHÈSE » |
| 5 | garde-fou calibrate hors JD3 (`calibrate fr`, speaker m01 actif) | **PASS** — « garde-fou speaker : 'm01' est actif … réinstallation du speaker jd3… », calibration fr exécutée sur VTL/JD3 (jamais sur m01), langue fr active, speaker jd3 |
| 6 | run `--polar` (« ba da ga », jd3) | **PASS** — SUCCESS, `.polar` v3 + MP4 bi-panneau 61 frames @25 Hz (2.44 s ≈ wav 2.41 s), g2p fr + lexique 84 370 entrées |
| 7 | `install_speaker.py restore` (retour état d'origine) | **PASS** (après correctif D30) — constants fc779fae restauré, wheel originale a583bdaa, smoke jd3 SUCCESS 656 frames, zéro INCOHERENCE |
| 8 | pytest allégé (`tests/`) | **PASS — 111 passed, 0 failed, exit 0, 79.7 s** |

Remise en état après validation : constants.py = résultat du
`restore` + transport de section (canonical `5166e7615ca5` = jd3,
`constants_coherent() = True`, ACTIVE_LANG = en — vérifié par le
module `speaker_registry` ; le binaire `907eb9f0e0c4f288` diffère du
backup `fc779fae21dc8894` uniquement par la réécriture des fins de
ligne lors du transport de la section), marqueur/backups/`.bak`/
caches/`vtl_synth.egg-info` purgés.

**D35** (2026-09-17, inversion de décision) — La fonte
`docs/.l_10646.ttf` **est distribuée** avec le dépôt (décision
inverse de D32/D34) : elle est nécessaire pour recompiler
`manual.tex` et sa taille réelle est **309 516 octets** (et non
304 516 o comme consigné en D34) ; SHA-256 inchangé
(`97226e81…`). `docs/README.md` mis à jour en conséquence.

**D36** (2026-09-17) — `INSTALL.md` (guide pip rapide, 3,3 Ko) et
`INSTALLATION.md` (guide pas-à-pas CMD, 6,1 Ko) se recouvrent
partiellement mais restent tous deux référencés (README, notes de
release publiées) : décision de **conserver les deux** plutôt que de
supprimer `INSTALL.md`.

## 8. Intégrité (manifestes SHA-256 avant/après)

| dépôt | fichiers | verdict |
|---|---|---|
| `P:\SynthVTL24b` (verrouillé) | 274 | **IDENTIQUES** avant/après |
| `P:\vtl-pipeline` (verrouillé) | 91 | **IDENTIQUES** avant/après |
| `P:\covtl-pipeline` (source, intouchable) | 503 → 506 | **aucun fichier modifié ou supprimé** ; 3 AJOUTS dans `out/` (`_d19.txt`, `_docpatch/patch_docs.py` + `.pyc`) dus à la session parallèle D31, hors périmètre code (dossier d'artefacts `out/`, exclu du package) |

Manifestes : `P:\covtl-tmp\manifest_*_{AVANT,APRES}..tsv`.

## 9. Re-vérification à froid (2026-09-17)

Le packaging du 16/09 n'ayant pas été refait (livrable déjà validé,
source inchangée), une passe de vérification à froid a été exécutée :

- **Source inchangée** : aucun fichier de `P:\covtl-pipeline` modifié
  après la livraison (19:22) hormis `out\_docpatch\list_final.py`
  (19:23, artefact de travail de la session parallèle, hors package —
  `out/` est exclu). Dépôts verrouillés `P:\SynthVTL24b` (274 f.) et
  `P:\vtl-pipeline` (91 f.) : **zéro fichier modifié** depuis le
  16/09 12:00.
- **État machine neutre confirmé** via `speaker_registry` (venv de
  validation, cwd neutre) : `active_name() = jd3` (défaut, sans
  marqueur), hash canonique constants `5166e7615ca5` (= jd3, identique
  §7), `constants_coherent() = True`, LANG SECTION présente
  (`constants.py` lignes 295-327) avec `ACTIVE_LANG: str = 'en'`
  (ligne 300).
- **pytest allégé re-exécuté** (venv `P:\covtl-tmp\venv-github`,
  Python 3.9.13) : **111 passed, 0 failed, exit 0, 139,4 s**. La passe
  ayant régénéré `__pycache__/` et `out/phrases/*_pytest.tract`
  (couverts par `.gitignore`), ils ont été purgés après contrôle pour
  restaurer l'état expédié.
- **Correctif D34 appliqué** : fonte `.l_10646.ttf` retirée de `docs/`
  (mise en quarantaine, cf. §2-D34).
- **Inventaire final : 172 fichiers, 33 090 108 octets** (173 − la
  fonte D34). Aucun `ACTIVE_SPEAKER`, `.speaker_backups/`,
  `*.egg-info`, `*.bak`, cache ou artefact résiduel (scan `-Force`).
