# DOC_SYNC_VERIFICATION — Rapport de vérification de la campagne documentaire (2026-11-18)

Application du prompt `prompt-verification-docs-covtl.md` (Acte A :
corrections ; Acte B : vérifications). Toutes les commandes ci-dessous
ont été réellement exécutées le 18 novembre 2026 sur les clones
`covtl-pipeline` @ `8291d15`, `covtl-sandhi` @ `9a62ae3`,
`covtl-console` @ `2586ff8`, branche `docs/sync-audit-2026-11` créée
dans chaque dépôt.

---

## 1. Tableau des 14 constats — statut final

| # | Constat (audit) | Statut | Fichiers corrigés | Preuve (grep sur PDF extrait) |
|---|---|---|---|---|
| 1 | ρ l/n cluster : manuel dit 1.2, code/test/docstring 1.15 | **Corrigé** | pipeline `docs/manual.tex/.pdf` | `1.15` présent (§ Cluster rules) ; `test_cluster_target_rules` PASS |
| 2 | T_voy documenté 8 pas, repli réel vowel_ms/10/3 | **Corrigé (documenté)** | pipeline `docs/manual.tex/.pdf` | « always pass explicit timings » ×1 |
| 3 | Inventaire : partenaires sourds et symboles non décrits | **Corrigé** | pipeline `docs/manual.tex/.pdf`, console `user-manual.tex/.pdf`, `tech-manual.tex/.pdf`, `data.js`/`app.js`/`render.js` | « notational duplicate » / « intentionally » ×1 ; popover corrigé |
| 4 | Manuel v1.1.0 vs moteur 1.2.2 sans avertissement | **Corrigé** | pipeline `docs/manual.tex/.pdf` | bandeau « This manual documents engine v1.1.0… evolved to 1.2.2 » |
| 5 | Rapport wave4 figé à 501/504 sans état daté | **Corrigé** | pipeline `docs/wave4/…WAVE1-4.tex/.pdf` | « 521 tests » ×1 (bandeau Engine state) |
| 6 | f0_base : doc laisse croire que le profil pilote la base | **Corrigé** | pipeline `docs/manual.tex/.pdf`, `docs/speakers.tex/.pdf` | « Where the base F0 comes from » ×1 ; « Speaker F0 vs language » ×1 |
| 7 | Correctif V1V2 : plateau 0.49 suppose timings fr jamais dits | **Corrigé (documenté)** | pipeline `docs/manual.tex/.pdf` (§ Low-level API, valeurs 0.491/0.470/≈0.14 sourcées AUDIT_V1V2) | inclus dans le paragraphe timings |
| 8 | X doublon de R jamais documenté | **Corrigé** | pipeline `docs/manual.tex/.pdf` | « notational duplicate of R » (durées 100/70 ms) |
| 9 | Console : bandeau moteur v1.1.0 obsolète (pont=1.2.2) | **Corrigé** | console `user-manual.tex/.pdf`, `tech-manual.tex/.pdf` | « evolved to 1.2.2 » ×2 |
| 10 | a→an : sens unique non documenté | **Corrigé** | sandhi `docs/covtl-sandhi-guide.tex/.pdf` | « one-way » ×1 (comportement re-mesuré : `an one` inchangé) |
| 11 | Allemand : seul ein Apfel, pas de paire discriminante | **Corrigé** | sandhi guide (tableau + § allemand), `README.md`, `README.fr.md` | « das ist ein Ei » ×2 dans le PDF, ×1 par README |
| 12 | Doublon manuel lang_pack v1.0.7 vs v1.1.0 | **Corrigé (retrait)** | pipeline `lang_pack/manual/` supprimé, lien README retiré ; `docs/language_pack.tex` vérifié conforme (bandeau garde+calibrate déjà complet) | dossier absent ; 0 lien cassé |
| 13 | h aspiré : 15/22 entrées citées | **Corrigé** | sandhi `docs/covtl-sandhi-guide.tex/.pdf` | « hauteurs » ×1 (liste des 22 entrées) |
| 14 | Certificat : dépôt D11/JSON annoncé mais absent | **Corrigé (annotation .md)** | console `docs/certificates/COVCONF-3SRC-3706f0c0.md`, `docs/certificates/README.md` | « not deposited yet » ×2 + ×2 ; PDF signé intouché |

## 2. Décisions prises (aucune question restée ouverte)

| Décision | Justification factuelle (vérifiée au code) |
|---|---|
| Manuel passe à 1.15 (constat 1) | `syltraj.py:522` `return (1.15, np.radians(270))` ; docstring `syltraj.py:498` ; test `test_cluster_target_rules` (`approx(1.15)`, « covtl-lambda »). Trois sources contre une. |
| Repli T_voy documenté, pas corrigé (constat 2) | Contrainte doc-only ; code mesuré : plateau 2 pas (repli) vs 12 (fr) vs 8 (en). |
| f0_base de profil qualifié de « repli jamais lu » (constat 6) | `pipeline.py:626,637` passe toujours `self.f0_hz` ; `LangProfile.f0_base` (setlang.py) non consommé ; gains onset/final par langue relevés (1.03–1.08 / 0.80–0.85). |
| X documenté comme duplicat (constat 8) | `constants.py:404,422` même cible (1.28, 234°) et sélecteur ; `continuous.py:155` durées 100 vs 70 ms. |
| Garde console : bandeau d'écart, pas d'import moteur (C5) | Import JS impossible ; comportement garde inchangé (L N C X toujours refusés — testé) ; note affichée dans le popover. |
| Liste h aspiré intégrale (constat 13) | `fr_h_aspire.txt` = 22 entrées (recomptées : héros, heros, haut, hauts, haute, hautes, hauteur, hauteurs, hache, haie, haine, hall, halle, harpe, hasard, hélas, helas, hectare, homard, huche, hoyau, hamburger). |
| Retrait lang_pack/manual (constat 12) | Diff 85 lignes avec docs/language_pack.tex ; bandeaux divergents v1.0.7/v1.1.0 ; dossier repository-only (absent du sdist vérifié). |
| Guide sandhi v0.1.1 | `pyproject.toml` 0.1.1 ; 0.1.1 = bump sans entrée CHANGELOG ; 38/38 tests identiques → faits du guide inchangés, version citée corrigée. |

## 3. Gardes « zéro impact version » (B.1, B.6) — sorties réelles

```
$ git diff -- CHANGELOG.md pyproject.toml '*/__init__.py'   (3 dépôts)
  0 ligne dans les trois dépôts
$ git tag | wc -l                                          (3 dépôts)
  0
$ # hashs SHA-256 des .py embarqués dans le sdist, avant/après :
$ diff /tmp/pipe_py_before.txt /tmp/pipe_py_after.txt   -> identiques (94 fichiers)
$ diff /tmp/sandhi_py_before.txt /tmp/sandhi_py_after.txt -> identiques (9 fichiers)
$ diff /tmp/cons_py_before.txt /tmp/cons_py_after.txt   -> identiques
$ diff /tmp/pipe_files_before.txt /tmp/pipe_files_after.txt -> identiques
  (retrait de lang_pack/manual ne change pas le sdist : repository-only)
```

Les seuls fichiers du sdist dont le contenu change : `README.md`
(pipeline : lien retiré ; sandhi : ligne de tableau enrichie) — fichiers
de documentation, sans bump de version ; les wheels `vtl_synth`/`sandhi`
sont inchangés octet pour octet (aucun .py touché).

## 4. Compilations (B.3)

| Document | Warnings Overfull/Underfull | vs baseline main | Placeholders |
|---|---|---|---|
| pipeline `manual.pdf` | 29 | identiques (29) | 0 |
| pipeline `speakers.pdf` | 2 | identiques (2) | 0 |
| pipeline `COVERAGE_SYNTHESIS_WAVE1-4.pdf` | 13 | identiques (13) | 0 |
| sandhi `covtl-sandhi-guide.pdf` | 31 | identiques (31) | 0 |
| console `user-manual.pdf` | 8 | identiques (8) | 0 |
| console `tech-manual.pdf` | 40 | identiques (40) | 0 |

Deux dépassements introduits puis corrigés pendant la campagne (ligne de
tableau sandhi trop large, liste consonnes console trop longue) — les
comptes finaux égalent les baselines. `language_pack.pdf` non recompilé
(source inchangée). Le glyphe ɥ (U+0265) absent de la police mono du
manuel console est décrit textuellement (« turned h ») — zéro
« Missing character ».

## 5. Tests (B.4, B.7)

```
sandhi    : 38 passed, 0 failed                        (avant = après)
pipeline  : 418 passed, 81 failed, 4 skipped, 6 errors (avant = après ;
            échecs = moteur vocaltractlab_cython absent de l'environnement)
console   : 34 passed, 12 failed, 32 skipped           (avant = après ;
            échecs = 503 vtl_synth absent ; liste des FAILED diff-à-diff vide)
contrat 1.15 : test_cluster_target_rules PASSED
```

`node --check` sur `data.js`, `app.js`, `render.js` : OK.
Diff numstat `data.js` : 7 insertions / 0 suppression. Les deux autres
fichiers UI ne touchent que du texte affiché et un paramètre de fonction.
L'exécution de la suite a régénéré `covtl-console-standalone.html`
(artefact construit, tracké) via `tests/test_standalone_build.py` —
il reflète les trois modifications UI ; rebuild propre (`git status`
vide), 6/6 tests standalone passent, hashs `.py` du sdist toujours
identiques avant/après.

## 6. Ce qui n'a PAS été fait (bornes respectées)

- Aucune publication TestPyPI/PyPI, aucun tag, aucun workflow déclenché
  (les `publish-prod.yml` exigent un `workflow_dispatch` manuel).
- Aucune modification de `vtl_synth/`, `sandhi/`, `covtl_console/server.py`,
  des tests, des données `sandhi/data/*.txt`.
- Le PDF signé `COVCONF-3SRC-3706f0c0.pdf` n'a pas été régénéré.
- Aucun push : les branches `docs/sync-audit-2026-11` restent locales.

## 7. Déclaration finale

**Aucune version n'a été modifiée, aucun paquet n'a été publié, aucun
code du paquet n'a changé** — à l'exception des trois fichiers UI de la
console (`data.js` additif pur, `app.js`/`render.js` : texte affiché et
paramètre), dont l'innocuité est prouvée par les tests identiques
avant/après et les hashs `.py` du sdist inchangés.
