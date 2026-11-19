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
