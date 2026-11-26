# DOC_SYNC_LOG — Journal des modifications documentaires (2026-11-18)

Campagne doc-only suivant l'audit de cohérence inter-documents du
18 novembre 2026. **Aucune version n'a été modifiée, aucun paquet n'a été
publié, aucun tag n'a été créé.** Branche : `docs/sync-audit-2026-11`.

Chaque entrée : fichier, constat d'origine (numéro de l'audit), ancien →
nouveau. Les hashs SHA-256 des `.py` embarqués dans les sdists sont
identiques avant/après dans les trois dépôts (preuve en annexe du
`DOC_SYNC_VERIFICATION.md`).

---

## covtl-pipeline (branche docs/sync-audit-2026-11)

| Fichier | Constat | Modification |
|---|---|---|
| `docs/manual.tex` + `.pdf` | 1 | Cluster rules : `\rho_stop = 1.2` → **1.15** pour l/n (d/t et g/k inchangés à 1.2/1.1) + renvoi au test `test_cluster_target_rules` (contrat covtl-lambda). |
| `docs/manual.tex` + `.pdf` | 2, 7 | Nouveau paragraphe « Low-level API: always pass explicit timings » après `tab:blocks` : repli réel `T_voy = round(vowel_ms/10/3)` (2 pas / 20 ms avec le défaut 60 ms), mesure plateau `a~` 2 pas vs 12 (fr t14/v12) vs 8 (en t10/v8), valeurs VO lissées 0.491 / 0.470 / ≈0.14 (source AUDIT_V1V2, `VO_NASALIZED_VOWEL = 0.5`), recommandation timings explicites. |
| `docs/manual.tex` + `.pdf` | 4 | Sous la date (p. de titre) : bandeau « This manual documents engine v1.1.0. The engine has since evolved to 1.2.2 (2026-11-17)… ». `\fancyhead` v1.1.0 conservé (historique non falsifié). |
| `docs/manual.tex` + `.pdf` | 8, 3 | Inventaire : partenaires sourds exacts (p t k f s S T tS → b d g v z Z D dZ via `_normalize_consonant_key`, C et X sans partenaire) + note « X is a notational duplicate of R » (même cible ρ 1.28 / θ 234°, même sélecteur, durée 100 ms vs 70 ms). |
| `docs/manual.tex` + `.pdf` | 6 | Nouveau paragraphe « Where the base F0 comes from » : `f0_base=self.f0_hz` (locuteur) sur tous les chemins, `LangProfile.f0_base` = repli jamais lu, gains onset/final par langue (en 1.06/0.85, fr 1.03/0.85, es 1.08/0.85, it 1.06/0.85, pt 1.04/0.80, de 1.03/0.80). |
| `docs/speakers.tex` + `.pdf` | 6 | Note « Speaker F0 vs language profile » après l'annonce f0 default, renvoi au manuel principal. |
| `docs/wave4/synthesis/COVERAGE_SYNTHESIS_WAVE1-4.tex` + `.pdf` | 5 | Bandeau « Engine state at 2026-11-13 (v1.1.3) » : suite passée à 521 tests collectés, tableaux internes inchangés (état wave 1–4 : 504/501/3). |
| `README.md` | 12 | Retrait du lien vers `lang_pack/manual/manual.pdf` (dossier supprimé). Bandeau distribution covtl-synth / module vtl_synth / CLI vtl-synth vérifié complet (déjà conforme). |
| `lang_pack/manual/` (dossier) | 12 | **Supprimé** (`git rm -r`) : manuel v1.0.7 redondant avec `docs/language_pack.tex` v1.1.0 ; bandeaux divergents pour un même contenu. |
| `docs/language_pack.tex` | 12 | **Aucune modification nécessaire** : le bandeau rouge v1.20 mentionne déjà la garde JD3 retirée ET `calibrate` déprécié (vérifié). |

## covtl-sandhi (branche docs/sync-audit-2026-11)

| Fichier | Constat | Modification |
|---|---|---|
| `docs/covtl-sandhi-guide.tex` + `.pdf` | 10 | Section a→an : paragraphe « The rule is one-way » (jamais de retrait/déplacement d'un n existant ; `an one` inchangé ; seuls `('a','hour')` et `('a','apple')` insèrent — mesuré). |
| `docs/covtl-sandhi-guide.tex` + `.pdf` | 11 | Tableau ch. 1 : ligne « Glottalversatz (careful) / ein Ei / 1 front. → 2 » + section allemande : paragraphe discriminant « das ist ein Ei » (standard 1 frontière, careful 2 ; `std.count(' ')==1`, `careful.count(' ')==2`, test `test_de_careful_leve_exemption`). |
| `docs/covtl-sandhi-guide.tex` + `.pdf` | 13 | Liste h aspiré intégrale : 15 mots cités → **22 entrées** (ajout de heros, hauts, haute, hautes, hauteur, hauteurs, helas) avec note graphies accentuées/non accentuées et formes fléchies de haut. |
| `docs/covtl-sandhi-guide.tex` + `.pdf` | version | Titre et métadonnées v0.1.0 → **v0.1.1** (9 occurrences) ; en-tête de fichier et abstract précisent « facts measured on v0.1.0, re-verified against the 0.1.1 code » (0.1.1 = bump sans changement de règles ; 38/38 tests identiques). |
| `README.md` / `README.fr.md` | 11 | Ligne `de` du tableau des 6 langues : ajout de la paire discriminante « das ist ein Ei » (EN/FR). NB : ces README **sont** dans le sdist — modification de contenu .md uniquement, version inchangée (1.2.x suivante embarquera le README à jour). |

## covtl-console (branche docs/sync-audit-2026-11)

| Fichier | Constat | Modification |
|---|---|---|
| `docs/user-manual/user-manual.tex` + `.pdf` | 3 | Inventaire : liste consonnes complète du serveur (p b t d k g f v s z S Z T D tS dZ m n J l R j w h + turned-h U+0265) + note d'écart : le moteur accepte aussi L N C X (dark l, nasal dorsal, palatal, uvulaire duplicat de R), refusés volontairement par la garde console. |
| `docs/user-manual/user-manual.tex` + `.pdf` | 9 | Bandeau sous la date : « the engine has since evolved to 1.2.2; the console bridge pins covtl-synth==1.2.2 ». |
| `docs/tech-manual/tech-manual.tex` + `.pdf` | 3, 9 | Ligne `data.js` du tableau : note inventaire miroir = liste garde console, clés moteur L N C X délibérément absentes + même bandeau d'évolution moteur. |
| `docs/certificates/COVCONF-3SRC-3706f0c0.md` | 14 | §Deposit : « machine record `covconf-3src-verification.json` and predecessor certificate COVCONF-D11-511cf2e are **not deposited yet — pending from the certifier** » + même réserve dans les cross-references. Le **PDF signé reste intouché** (document externe ; on annote le .md compagnon). |
| `docs/certificates/README.md` | 14 | Ligne COVCONF-3SRC : statut du JSON manquant ; ligne D11 : « not deposited yet (pending from the certifier) » (harmonisation des formulations). |
| `covtl_console/ui/js/data.js` | C5 (bornée) | **Additif pur** (7 insertions, 0 suppression) : commentaire d'en-tête + export `INVENTORY_NOTE` (L N C X non offerts par la garde). `VOWELS`/`CONSONANTS`/logique intacts. |
| `covtl_console/ui/js/app.js` | C5 (bornée) | Import + passage de `INVENTORY_NOTE` à `renderInventory` (2 lignes). |
| `covtl_console/ui/js/render.js` | C5 (bornée) | Titre du popover corrigé « Engine inventory — ALL_PHONEME_KEYS » → « Console inventory (subset of ALL_PHONEME_KEYS) » + affichage de la note (3 insertions, 2 modifications de texte affiché ; aucun symbole ni logique). |
| `covtl-console-standalone.html` | C5 (conséquence) | Artefact construit régénéré automatiquement par `tests/test_standalone_build.py` lors de l'exécution de la suite : il embarque les trois modifications UI ci-dessus (note d'inventaire, titre du popover). Fichier tracké généré par `build_standalone.py` — régénérer le standalone après toute modification de `ui/` est la procédure normale du dépôt ; le fichier commité est fidèle au build (6/6 tests standalone passent, `git status` propre après rebuild). |

---

## Preuves d'innocuité (détail dans DOC_SYNC_VERIFICATION.md)

- sdists pipeline / sandhi / console reconstruits avant/après : **hashs
  SHA-256 des .py identiques**, listes de fichiers pipeline identiques ;
  seuls des fichiers de documentation diffèrent (README.md pipeline et
  sandhi sont embarqués dans le sdist ; docs/ ne l'est jamais).
- Tests : sandhi 38/38 ; pipeline 418 passed / 81 failed / 6 errors —
  **strictement identique avant/après** (échecs = moteur
  `vocaltractlab_cython` absent de l'environnement) ; console 34 passed /
  12 failed — **strictement identique avant/après** (échecs = 503,
  `vtl_synth` absent) ; test du contrat 1.15
  (`test_cluster_target_rules`) **PASS**.
- Workflows `publish-prod.yml` : déclenchement `workflow_dispatch`
  uniquement — aucune publication possible par un push.


## Campagne 2026-11-23 (12+1 constats, branche docs/sync-audit-2026-11-23)

Application des 13 corrections du rapport d'analyse de cohérence du
23/11/2026 (campagne doc-only, zéro code touché).

| F | Fichier(s) | Modification | Preuve |
|---|---|---|---|
| F1 | README.md | Exemples CLI polar-build/polar-video alignés sur cli/main.py | grep "polar-video out/x.tract" OK |
| F2 | README.md | `calibrate` marqué deprecated (D24) ; garde JD3 remplacée par la formulation marker-only | grep "reinstalls" vide ; "deprecated" présent |
| F3a | README.md | .polar format v4 → v5 + note CV reduced-vowel anchoring | grep "format v4" vide |
| F3b | docs/polar_visualization.tex | subsection (version 5), "version": 5, phrase v5 ; PDF recompilé (9 pp.) | grep '"version": 4' vide |
| F3c | docs/reference-manual-errata.md (nouveau) | errata §5.4/§12.2 version 5 | fichier présent |
| F4 | docs/manual.tex | note « deux mappings de pression » (actif E^1.2 vs legacy E^2, pulmonary_effort.py non importé) ; PDF recompilé (28 pp.) | grep "pulmonary\_effort" OK |
| F5 | docs/manual.tex | chronologie rayons /i,u/ : 1.00 → 0.60 / 0.55 (l'état 0.80 n'existe pas pour JD3 ; 0.80 = cible s2/glide j) | grep "0.80 \to 0.60" vide |
| F6 | docs/From_Phonetics_errata.md (nouveau) + docs/README.md | errata manuel didactique : /d/ production 270° (3π/2) vs 23π/16 des articles ; .polar v5 | docs/README.md référence l'errata |
| F7 | docs/language_pack.tex | bandeau aligné sur le PDF compilé : « v1.0.9 update » (résolution D24, 2026-09-23) ; PDF recompilé (12 pp.) | libellé identique .tex/.pdf |
| F8 | README.md | comptages : 153 → 529 tests collected ; 519 green → 529 collected (519 green wave-5 CI) ×2 | grep "153 tests" vide |
| F9 | lang_pack/README.md | 62 baselines → 40 pins (8 phrases × 5 speakers, schema 3) | grep "62 regression" vide |
| F10 | docs/README.md | « Five manuals » → « Seven PDF documents » + note PDFs sans source .tex | grep "Five manuals" vide |
| F11 | docs/reference-manual-errata.md | 27 pp → 28 pp (2 occurrences, reference manual) | errata point 2 |
| F12 | docs/speakers.tex + docs/SPEAKERS.md | renvoi croisé conventions L : 17.00 cm (moyenne voyelles tendues) vs 16.83 cm (statique Route A) ; speakers.pdf recompilé (14 pp.) | les deux fichiers se référencent |
| F13 | README.md | référence arXiv:2609.31508 ajoutée (EMA/CTW 2026) | grep "2609.31508" OK |

Déviation consignée : le comptage vérifié le 2026-11-24 est **529 tests
collected** (le rapport annonçait 521 au 23/11 ; 8 tests ont été ajoutés
entre-temps). Les corrections utilisent 529.
Invariants : `git diff -- vtl_synth/ tests/ scripts/` VIDE ; pages PDF
inchangées (polar 9 / language_pack 12 / speakers 14 / manual 28).

## Campagne 2026-11-24 (rework schwa — deux couches, toggle d'affichage)

Mission du propriétaire après l'audit schwa validé
(`docs/schwa-position-audit-EN.md`, traduction EN de l'audit FR du
24/11). Quatre commits : couches de représentation (B) → traduction EN
(A) → patch audit + flag display (C) → documentation complète (E).
**Cette campagne touche le CODE** (cible `'@'` + routage VV + toggle
display) : voir CHANGELOG.md « Changed » pour le détail moteur.

| Fichier | Modification |
|---|---|
| `docs/ARCHITECTURE.md` | section « Two representation layers » (layer 1 cibles / layer 2 f(P(t)) / toggle display) ; valeur schwa §5 : (0.580, 180°) ex-centroïde ; haché jd3 registry mis à jour |
| `docs/manual.tex` | sous-section « Two representation layers » (§ architecture) ; cible @ (table + TikZ + §voyelles) = (0.580, π) ; §VV : routage obligatoire + toggle ; §CLI polar-build/run : `--display-schwa-route` ; PDF recompilé (**29 pp.**, ex 28) ; + fix latent `\code` non défini (note F4 du 23/11, footnote silencieusement perdue) |
| `docs/polar_visualization.tex` | sous-section « The schwa routing: mandatory in the engine, optional on display » ; table events `bg` ; résidu « version = 4 » → 5 ; PDF recompilé (**10 pp.**, ex 9) |
| `docs/SPEAKERS.md` | §6 : schéma schwa par speaker — jd3/s1/s2 (0.580, 180°), m01 (0.750, 123°) / w02 (0.750, 234°) inchangés ; routage obligatoire, tracé optionnel ; hachés registry |
| `docs/From_Phonetics_errata.md` | errata #3 : schwa 0.580 (le manuel cite le centroïde 0.7167, annexe C + record d'implémentation) |
| `docs/reference-manual-errata.md` | errata #3 : schwa 0.580 + routage effectif obligatoire + toggle display (§ table voyelles + §4.5) |
| `docs/schwa-position-audit-EN.md` (nouveau) | traduction EN-US de l'audit FR, éléments étiquetés [layer 1: target] / [layer 2: mandatory routing] / [layer 2: display option] |
| `docs/README.md` | index : entrée « Engine studies » (étude schwa EN) |
| `README.md` | phrase « two representation layers » (intro) + §Polar video : routage obligatoire, toggle display-only |
| `CHANGELOG.md` | entrée « Changed » (cible, toggle display optionnel défaut OFF, tests) |
| `RELEASING.md` | « UNDER STUDY » → « IMPLEMENTED — routing mandatory, display toggle default OFF » + bullet livrable étude |
| `docs/DOC_SYNC_LOG.md` | la présente entrée |
| `vtl_synth/…` (code) | cible `'@'` (constants + jd3/s1/s2 constants, registry, hachés), commentaires syltraj, `_vv_probe` + toggle `display_schwa_route` (polar_video, pipeline, CLI), `tests/test_schwa_waypoint.py` (ON/OFF) — **moteur inconditionnel** |

Validation : 540 tests collectés (529 + 11 du patch) — 538 passed /
2 skipped / 0 échec (venv audit, editable sur le clone) ; baselines
5 speakers vertes sans régénération ; toggle vérifié ON (jonction
(0.580, π) à 1e-6) / OFF (identité au .polar de 6536f5a).


---

## Campagne « exclusion zone » (2026-11-25) — reformulation ensembliste

Retrait du notionnel « occlusion corner / coin d'occlusion / zone
d'exclusion autour de ρ = 0 » (entré le 24/11 par traduction verbatim
d'un rapport d'audit externe) : le point ρ = 0 est le NEUTRE du
modèle (0.277 cm² mesuré, sonde VTL JD3 au repos) et le disque central
ρ ≲ 0.10 est ouvert dans toutes les directions. Correction purement
documentaire (aucun code, aucun test moteur, aucune baseline). Le
vocabulaire de remplacement de la v1 (« mur de fermeture annulaire /
annular closure wall ») est RETIRÉ — aucun nom géométrique ne remplace
le notionnel : description strictement ensembliste (ensemble
sous-le-seuil {(ρ, θ) : A < 0.18 cm²}, frontière intérieure ρ*(θ) =
0.12 à θ = 0°, 0.36 à ±60°, rien au-delà de |θ| ≥ 70° sur le disque
unité ; continu avec la région ρ > 1 par les cibles consonantiques ;
contient les plateaux de /i/ (0.137) et /u/ (0.142)).

| Fichier | Constat | Correction |
|---|---|---|
| `docs/schwa-position-audit-EN.md` | 6 occurrences « occlusion corner » (résumé exécutif, titre §4.1, corps, légendes fig. 1 et 3, §4.2, §4.3, §8.2) | reformulation ensembliste : « sub-threshold sector of the layer-2 projection », frontière intérieure ρ*(θ), disque central ouvert (neutre 0.277 cm²), cordes fermées par les états de mélange mesurés (0.062-0.066 cm²), « open-corridor analysis » |
| `docs/README.md` | l. 36 « occlusion corner of the (ρ, θ) plane » | « sub-threshold sector of the layer-2 projection (the ρ ≈ 0 central disk is open, neutral) » |
| `docs/manual.tex` | § anti-fermeture « sweeps through the occlusion region » | « sweeps through occluded configurations (measured on the i-u pair) » — usage consonantique légitime l. 460 (constriction/occlusion region) INCHANGÉ |

Contrôle : grep notionnel + vocabulaire v1 (occlusion corner, coin
d'occlusion, exclusion zone, zone d'exclusion, annular closure wall,
mur de fermeture/annulaire) = 0 occurrence sur pipeline + console ;
usages légitimes conservés (occlusions consonantiques,
rho_min_occlusion, velar occlusion of /g/). manual.pdf recompilé
(xelatex, 29 pp., même pagination) ; suite tests inchangée.
Console : aucune occurrence (vérifié).


---

## Campagne « rectification douce VV » (2026-11-26) — moteur

Suite du rapport d'audit externe (diphtongues iu) : le détournement
du chemin vers le schwa donnait un mauvais résultat — pause non
justifiée sur le schwa (plateau f2). Cause : chaque demi-arc du
routage 24/11 est une sigmoïde cos^Pexp COMPLÈTE à vitesse nulle aux
extrémités ; à la jonction l'état P(@) est atteint puis quitté au
ralenti — au D=4 de production, les états moteurs sont
[dep, @, @, arr] : la moitié de la diphtonge figée sur le schwa
exact. Trois options étudiées (rapport) : (1) arc passant par @ sans
s'y arrêter (balayage intérieur 240° — écarté : excursion polaire
2× plus longue, passage au territoire /y/), (2) sélecteur minimal
TCY/TBY routés seuls (recouvert par (3) comme cas s=1), (3)
rectification douce des 2 paramètres sur le trajet direct, amplitude
réglée par la sonde — RETENUE et implémentée.

| Fichier | Modification |
|---|---|
| `vtl_synth/core/syltraj.py` | `VV_RECTIFY_SELECTOR` (TCY, TBY) + `VV_RECTIFY_STEPS` (0.1..1.0) ; `_rectify_vv_arc()` (bosse sin² nulle aux extrémités, amplitude minimale ouvrant ≥ 0.18 cm²) ; `_append_background` : rectification d'abord, routage deux demi-arcs en FALLBACK ; `SylBlock.rectify_s` ; commentaires VV réécrits |
| `vtl_synth/core/constants.py` | commentaire '@' : cible de rectification + waypoint du fallback |
| `vtl_synth/data/speakers/jd3_constants.py` | même commentaire (hache registry regénérée) |
| `vtl_synth/data/speakers/registry.json` | `constants_sha256` jd3 + note _meta |
| `tests/test_speaker_registry.py` | préfixe de hache jd3 épinglé |
| `vtl_synth/video/polar_video.py` | docstrings : l'affichage ON dessine l'arc direct unique des blocs rectifiés, les jambes dep→@→arr uniquement pour le fallback |
| `tests/test_schwa_waypoint.py` | réécrit : structure de rectification (1 bloc, colonnes TCY/TBY seules, ancrages exacts, jamais à l'arrêt), fallback deux jambes (stub tout-fermant), affichage ON/OFF, critères acoustiques (aire ≥ 0.15, pas de pause schwa, H(buib, buaib) ≥ 0.40) |
| `CHANGELOG.md` | entrée « Unreleased — Changed » |

Validation : suite complète 534 passed / 3 skipped (sandhi optionnel,
préexistants) ; baselines 5 speakers vertes SANS régénération (aucune
paire VV fermante intra-mot dans le corpus : « a i u » = mots séparés,
pas d'arc VV) ; balayage 132 paires ordonnées : 8 fermantes à D=4
(10 à D=12), toutes rectifiées à s ≤ 0.3, zéro fallback ; métriques
buib : aire 0.062 → 0.223 cm², vitesse minimale 0.051 > 0 (était
0.000), distance minimale à P(@) 1.95 (jamais approché), Hausdorff
(buib, buaib) 1.00 (critère ≥ 0.40).
Reste à opérer (voir `docs/PROMPT_SCHWA_RECTIFICATION.md`) : manuels
LaTeX (§VV « routage obligatoire » → rectification), SPEAKERS.md,
erratas, docs de l'audit 24/11 (mention du fallback), console
(test_schwa_route.py : plus de passage π pour buib), round de release.