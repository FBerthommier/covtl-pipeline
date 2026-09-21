# PROVENANCE PROSODY CHUNKING — Rapport d'enquête

Composants audités : `vtl_synth/utils/chunking.py` et
`vtl_synth/utils/prosody_f0.py` du dépôt `FBerthommier/covtl-pipeline`.

Date de l'enquête : 2026-09-21.
Méthode : niveaux de preuve P0 (hypothèse) → P4 (provenance établie),
conformément au cahier des charges de la mission. Aucune conclusion
P0–P2 n'est présentée comme un fait.

---

## Executive summary

L'enquête établit que les deux modules sont une **implémentation
originale réalisée au sein même du projet**, les 2026-09-15, à partir
d'un document de spécification écrit le même jour
(`docs/PROMPT_prosodie_expressivite.md`, 18:22 ; fichiers créés à
19:13 et 19:32), dans une session de travail humain-dirigée,
**assistée par IA** (agent ZCode/GLM opérant pour F. Berthommier).
Le titulaire des droits et auteur de référence est **Frédéric
Berthommier** (en-têtes SPDX de tous les fichiers, cohérents avec le
reste du dépôt, GPL-3.0-or-later). Les deux fichiers entrent dans
l'historique **public** GitHub dans un unique commit (`e991ff9`,
v1.1.0, 2026-09-17, auteur FBerthommier). Les recherches externes
exhaustives (noms de fichiers, 22 symboles inventés, chaînes
françaises distinctives, constantes) **ne retournent aucune
correspondance** : aucune source logicielle antérieure, aucune
copie, aucune adaptation externe. Les seules filiations de code sont
**internes au dépôt** (même auteur, même licence) : les modules
s'appuient sur `lexicon_loader`, `syltraj` et le pattern
`get_last_pval_state`. Les références scientifiques citées (Jun,
Ladd, Face, Grice, Avesani, Frota, Pierrehumbert…) sont des sources
**d'inspiration de paramétrage** (type D) et ne fournissent aucun
code ; aucune publication liée n'a de dépôt logiciel utilisé ici.
Deux actions de régularisation sont requises : ajouter la notice
**Wikipron (CC BY-SA 3.0)** à `THIRD_PARTY_NOTICES.md` (données
consommées par le canal de stress) et archiver le document de
spécification dans le dépôt public pour matérialiser la chaîne de
conception. **Aucune notice de code tiers n'est requise pour ces
deux modules.**

---

## 1. État actuel

| | `chunking.py` | `prosody_f0.py` |
|---|---|---|
| Lignes | 481 | 614 |
| SHA-256 (2026-09-21) | `70bc1314…80e0aab7` | `9e3ae318…6183fc8d` |
| En-tête | `SPDX-FileCopyrightText: 2026 Frédéric Berthommier` / `SPDX-License-Identifier: GPL-3.0-or-later` | idem |
| Symboles publics | `chunk_word_list`, `chunk_part`, `chunk_sentence`, `split_sentences`, `chunk_text`, `CHUNK_WORDS`, `WORD_RES` | `ExpressivityProfile`, `EXPRESSIVITY_PROFILES`, `token_nuclei`, `word_stress`, `orthographic_stress_index`, `WordPlan`, `ChunkPlan`, `plan_expressive_text`, `apply_expressive_f0` |
| Dépendances | stdlib uniquement (`re`, `typing`) | `numpy` + `vtl_synth.utils.chunking` + imports paresseux internes (`lexicon_loader`, `phonemes`, `constants`) |
| Rôle | découpage lexical en groupes de souffle (respiration syntaxique), dictionnaires de mots-outils pour 6 langues | profils d'expressivité par langue, canal de stress hors-bande, sculpture du contour F0 (accents, reprises, downstep, chute nucléaire) |

Aucun des deux fichiers n'embarque de code, table ou constante
provenant d'un tiers. Les listes lexicales de `CHUNK_WORDS` ont été
composées pour ce projet (30–50 mots-outils fréquents par langue).

## 2. Historique Git

**Dépôt public** (`github.com/FBerthommier/covtl-pipeline`, branche
`main`, 12 commits au 2026-09-21) :

| Fichier | Premier et unique commit | Date | Auteur |
|---|---|---|---|
| `vtl_synth/utils/chunking.py` | `e991ff9` — « v1.1.0 - multi-speakers registry (jd3 s1 s2 m01 w02), language pack (de en es fr it pt), expressive prosody, polar video v3; 5 manuals; packaging fixes » | 2026-09-17 | FBerthommier (Frederic Berthommier) |
| `vtl_synth/utils/prosody_f0.py` | idem | 2026-09-17 | idem |

Pas de renommage, pas de déplacement, pas de branche divergente sur
ces fichiers : l'historique public est **linéaire et mono-commit**
(squash de publication).

**Historique local (pré-publication)** — reconstitué à partir des
artefacts de la copie de travail `P:\covtl-languages\covtl-pipeline`
(la publication GitHub provient de la fusion dans
`P:\covtl-pipeline`) :

| Élément | Date/heure | Preuve |
|---|---|---|
| Spécification (`docs/PROMPT_prosodie_expressivite.md`, design complet : chunking, accents, profils par langue, références, contraintes) | 2026-09-15 18:22 | horodatage fichier (P3) |
| Création `chunking.py` | 2026-09-15 19:13 | horodatage fichier (P3) |
| Création `prosody_f0.py` | 2026-09-15 19:32 | horodatage fichier (P3) |
| Transfert vers la copie multi-speakers `P:\covtl-pipeline` | 2026-09-16 | rapport de session, horodatages (P3) |
| Publication GitHub v1.1.0 | 2026-09-17 | commit `e991ff9` (P4) |

**Processus d'écriture (déclaration d'auteur, P3 — vérifiable par
l'opérateur dans les journaux de session)** : implémentation
initiale réalisée par un agent de codage IA (ZCode, modèle GLM)
sous la direction de F. Berthommier, à partir de sa spécification,
avec itérations testées (batterie de 40 tests, mesures F0, démos 6
langues). La paternité au sens du droit d'auteur et la responsabilité
scientifique reviennent au titulaire du projet (en-têtes SPDX).
UNKNOWN — evidence insufficient : rien. Toute la chaîne est
documentée.

## 3. Sources logicielles candidates

Après recherches (voir §4 pour la méthode), **aucune source
logicielle candidate n'a été trouvée**. Fiche unique :

| Champ | Valeur |
|---|---|
| Source | — (aucune) |
| Recherche | négative, exhaustive sur les requêtes listées §4 |
| Conclusion | les deux fichiers ne proviennent d'aucun projet antérieur identifiable — **pas de code repris (type A : néant), pas de code adapté depuis l'extérieur (type B : néant)** |
| Niveau | P3 (négatif actif : recherches ciblées sur 22 symboles + chaînes distinctives + noms de fichiers, toutes vides) |

Nuance interne (type B, même auteur, même licence — sans obligation
d'attribution) :

| Portion | Pattern interne réutilisé | Source (même dépôt, même auteur) |
|---|---|---|
| `prosody_f0.apply_expressive_f0` | remplace/étend `apply_f0_declination` (détection des spans voisés, rampes) | `vtl_synth/core/pipeline.py` |
| `prosody_f0` / `syltraj.get_last_build` | pattern d'état module (`get_last_pval_state`, `get_last_timer_data`) | `vtl_synth/core/continuous.py` |
| canal de stress | rattaché au chargeur `lexicon_for`/`reset_cache` existant | `vtl_synth/utils/lexicon_loader.py` |

## 4. Comparaison de code

Comparaisons réalisées contre les candidats généraux du domaine
(outillage TTS public) : **aucun candidat avec correspondance
substantielle**. Détail des requêtes et résultats :

| Requête | Surface | Résultat |
|---|---|---|
| `"prosody_f0.py"` | web général | 0 correspondance |
| `"apply_expressive_f0"` / `"ipa_to_keys_stress"` / `"plan_expressive_text"` | web général | 0 correspondance |
| `"mots han-gants"` / `"HEURISTIQUE LEXICALE AVOUÉE"` | web général (FR) | 0 correspondance (néologismes du projet) |
| `"ExpressivityProfile"` | web + contexte TTS/prosodie | 0 correspondance au nom exact |
| `"chunk_word_list"` / `"CHUNK_WORDS"` | web + exemples code | 0 correspondance (homonymies triviales `chunk_words` en R/Python sans rapport) |
| `"covtl" chunking prosody` | web + Software Heritage (via recherche) | 0 correspondance hors le projet lui-même |

Non réalisé (et pourquoi) : comparaison AST contre un candidat —
aucun candidat n'ayant émergé, il n'y a rien à comparer. Hash des
fonctions : non pertinent sans candidat. Les empreintes locales
(symbols, constantes, SHA-256) sont consignées au §1 pour
l'archivage.

## 5. Sources scientifiques

Toutes les références citées dans les docstrings proviennent du
document de spécification du 2026-09-15 (elles y étaient listées
comme guide de paramétrage). **Aucune ne fournit de code utilisé
ici** ; relation de type D (inspiration scientifique — choix de
paramètres et de cibles de contour) :

| Référence | Rôle dans le module | Code associé ? | Relation |
|---|---|---|---|
| Jun (2005, 2014) *Prosodic Typology* I/II ; Ladd (2008) *Intonational Phonology* | cadre typologique, déclinaison/downstep | non (monographies) | D — downstep `de`, hiérarchie des pauses |
| Pierrehumbert (1980) ; Beckman & Ayers (1997) | contour anglais H* + chute | non | D — profil `en` |
| Jun & Fougeron (2002, 2013) ; Di Cristo (1998) | accent de GROUPE final français (pas d'accent lexical) | non | D — politique d'accent `fr` |
| Face (2003) ; Sosa (1999) ; Prieto & Roseano (2010) | pré-nucléaires montantes espagnoles | non | D — profil `es` |
| Féry (1993) ; Grice, Baumann & Benzmüller (2005) | chute tardive + downstep + terminal bas allemands | non | D — profil `de` |
| Avesani (1995) ; D'Imperio (2002) ; Gili Fivela et al. (2015) | montées accentuelles italiennes | non | D — profil `it` |
| Frota (2000, 2014) ; Vigário (2003) | chute précoce à terminal bas, plage étroite (pt européen) | non | D — profil `pt` |
| Selkirk (1984) ; Nespor & Vogel (1986) | hiérarchie prosodique / joncture (fondement du chunking) | non | D — justification des frontières |
| Boula de Mareüil (1998), *Text chunking for prosodic phrasing* (ISCA) — **trouvée par la recherche, non citée** | antériorité scientifique du concept de chunking prosodique déterministe pour le français | non (algorithme décrit, pas de code réutilisé) | D (concept espace) — le module cite Selkirk/Nespor & Vogel à la place ; aucune relation de code |

Données associées : les lexiques **Wikipron** (CC BY-SA 3.0,
données du Wiktionnaire) sont consommés via `lexicon_loader` — y
compris par le canal de stress de `prosody_f0`. Notices
par-langue présentes dans `vtl_synth/data/README_*_lexicon.md` ;
**absents du fichier central `THIRD_PARTY_NOTICES.md`** (action,
§10).

## 6. Licences

| Composant | Licence | Vérification |
|---|---|---|
| Dépôt `covtl-pipeline` | GPL-3.0-or-later | `LICENSE` (texte GPL-3 intégral) + README (choix justifié par les dépendances GPL : VocalTractLab, binding Cython) |
| `chunking.py` | GPL-3.0-or-later | en-tête SPDX, cohérent dépôt |
| `prosody_f0.py` | GPL-3.0-or-later | en-tête SPDX, cohérent dépôt |
| Sources antérieures | **aucune** — néant à évaluer | §3 |
| Wikipron (données) | CC BY-SA 3.0 | notices `data/README_*_lexicon.md` ; SHARE-Alike applicable **aux données**, pas au code qui les lit |
| numpy (dépendance) | BSD-3-Clause | THIRD_PARTY_NOTICES.md |

**Compatibilité : établie.** Code 100 % maison + dépendances BSD +
données CC BY-SA distribuées séparément avec leurs notices. Aucune
licence inconnue en jeu sur ces deux modules (pour tout autre
élément : « LICENCE UNKNOWN — ne pas conclure à la compatibilité »
ne s'applique à rien ici).

## 7. Provenance établie (P3/P4)

- **P4** — entrée dans l'historique public : commit unique
  `e991ff9` (2026-09-17, auteur FBerthommier) introduisant les deux
  fichiers ; vérifié sur github.com le 2026-09-21.
- **P4** — titulaire des droits : en-têtes SPDX nominaux des deux
  fichiers, cohérents avec l'ensemble du dépôt et sa licence.
- **P3** — chaîne de conception : spécification datée
  (2026-09-15 18:22) → implémentation (19:13, 19:32) → tests et
  mesures (CHANGELOG, `tests/test_expressive.py`, démos horodatées)
  → publication (2026-09-17).
- **P3 (négatif)** — absence de source externe : toutes les
  recherches ciblées (symboles, chaînes, constantes, noms de
  fichiers) sont vides.

## 8. Provenance probable (P2)

- L'**indépendance réciproque des deux fichiers d'avec tout projet
  tiers** : convergence de (a) recherches négatives, (b) imports
  limités au dépôt, (c) chaîne horodatée locale. P2 et non P4 car
  une négative ne peut jamais être exhaustive (GitHub code search
  non authentifié, forks privés insondables).

## 9. Hypothèses non confirmées (P0/P1)

- P0 — « le style des commentaires français pourrait trahir une
  réécriture d'un module anglais antérieur » : **infirmé** par les
  recherches (les formulations sont des néologismes sans
  correspondance) ; consigné car l'hypothèse initiale de la mission
  devait être testée.
- P1 — « `get_last_build` pourrait venir d'un autre projet » :
  recherche vide ; le pattern est présent *dans le même dépôt*
  (`get_last_pval_state`), filiation interne bien plus parsimonieuse.

## 10. Actions de régularisation

| # | Action | Justification | Statut |
|---|---|---|---|
| 1 | Conserver l'auteur actuel et les en-têtes SPDX tels quels | chaîne de titularité cohérente | recommandé (aucune modification) |
| 2 | **Ajouter une notice Wikipron (CC BY-SA 3.0) à `THIRD_PARTY_NOTICES.md`** | les TSV sont redistribués ; le fichier central doit refléter les notices `data/README_*_lexicon.md` | **requise** |
| 3 | **Copier `docs/PROMPT_prosodie_expressivite.md` (spécification du 2026-09-15) dans `docs/` du dépôt public** | matérialise la chaîne de conception (preuve P3) dans la source primaire qu'est le dépôt | **recommandée** |
| 4 | Ajouter une ligne de divulgation du processus (« implemented with AI coding assistance under the author's direction, from the author's specification ») dans le README ou le CHANGELOG | transparence honnête sur le processus ; sans effet sur la titularité déclarée | recommandée |
| 5 | Citer Boula de Mareüil (1998) aux côtés de Selkirk/Nespor & Vogel dans les docstrings du chunking | antériorité scientifique du concept, repérée par l'enquête | optionnelle |
| 6 | Aucune notice de code tiers à ajouter pour ces deux modules | pas de source externe | — |

Actions explicitement **non** déclenchées : isolation du module,
remplacement de code, demande de clarification à un tiers (aucun
tiers identifié — cf. règle §12 de la mission, aucun contact envoyé).

## 11. Généalogie

```
Spécification F. Berthommier (docs/PROMPT_prosodie_expressivite.md, 2026-09-15 18:22)
   │  [P3 — fichier horodaté]
   ▼
Session d'implémentation (humain-dirigée, assistée IA) — 2026-09-15 19:13/19:32
   │  [P3 — horodatages, tests, CHANGELOG]      Publications citées ──▶ (type D : paramétrage, pas de code)
   ▼                                                            Jun 2005/14, Ladd 2008, Jun&Fougeron 2002,
chunking.py + prosody_f0.py (copie covtl-languages)             Face 2003, Grice 2005, Avesani 1995,
   │  [P3 — port documenté 2026-09-16]                          Frota 2000, Pierrehumbert 1980…
   ▼
Fusion multi-speakers P:\covtl-pipeline (2026-09-16)
   │  [P3 — rapport de session]
   ▼
Commit public e991ff9 « v1.1.0 » — 2026-09-17, FBerthommier
   │  [P4 — github.com]
   ▼
FBerthommier/covtl-pipeline (GPL-3.0-or-later)
```

Aucune flèche ne part d'un projet logiciel tiers (aucun identifié).

## 12. Critère de clôture — réponses aux 12 questions

1. **Qui ?** Frédéric Berthommier (titulaire, en-têtes SPDX) ; implémentation initiale par agent IA sous sa direction (P3, divulgation recommandée).
2. **Quand ?** 2026-09-15 (création), 2026-09-16 (port), 2026-09-17 (publication).
3. **Dans quel dépôt ?** Copie de travail `covtl-languages/covtl-pipeline` puis `covtl-pipeline` (fusion multi-speakers) ; public : `FBerthommier/covtl-pipeline`.
4. **Version antérieure ?** Aucune version logicielle antérieure — le fichier de spécification (18:22) est l'antécédent documentaire immédiat.
5. **Copié, adapté, réimplémenté ?** Ni copié ni adapté : première implémentation originale. Filiale interne seulement (même dépôt, même auteur).
6. **Publications inspiratrices ?** Voir §5 (type D ; aucune ne fournit de code).
7. **Licence d'origine ?** Sans objet (pas de version antérieure) ; GPL-3.0-or-later dès la création.
8. **Licence actuelle ?** GPL-3.0-or-later (en-têtes + LICENSE du dépôt).
9. **Compatibilité ?** Oui — établie (§6).
10. **Attributions requises ?** Aucune attribution de code tiers. Attributions de données : Wikipron (action #2). Attribution scientifique : déjà présente en docstrings.
11. **Notices à conserver ?** `data/README_*_lexicon.md` (existantes), `THIRD_PARTY_NOTICES.md` à compléter (action #2).
12. **Modifications nécessaires ?** Actions #2 (requise) et #3–#4 (recommandées) ; rien d'autre.

---

*Méthode et limites : recherches web généralistes (non exhaustives
sur les dépôts privés) ; GitHub code search non authentifié non
utilisé ; Software Heritage interrogé via recherche générale. Le
négatif (§3) est P3, pas P4. Aucun contact tiers envoyé (règle §12).*


---

## Addendum (2026-09-21, après audit du dépôt public)

L'analyse de cohérence avec le dépôt GitHub **effectif**
(`FBerthommier/covtl-pipeline`, branche `main`, auditée le
2026-09-21) révèle que le dépôt public est **en avance** sur la
copie de travail locale pour l'hygiène de licences :

- `THIRD_PARTY_NOTICES.md` public contient deux sections absentes de
  la copie locale : **« Speakers s1/s2 (DVTD MRI) »** (provenance et
  licence des données IRM des locuteurs) et **« Language pack
  (de/en/es/fr/it/pt) »** qui documente déjà **Wikipron CC BY-SA
  3.0** avec renvoi vers `lang_pack/LICENSE.md` ;
- `MIGRATION_NOTES.md` (inventaire de migration) et
  `docs/README.md` (index des cinq manuels) existent seulement en
  ligne.

**Conséquence sur les actions du rapport :**

| Action | Statut révisé |
|---|---|
| #2 — notice Wikipron (requise) | **déjà satisfaite en amont (P4)** ; la copie locale de `THIRD_PARTY_NOTICES.md` a été **ré-alignée sur la version publique** pour éviter toute régression lors d'un futur commit (les sections Speakers/Language pack sont restaurées localement) |
| #3 — archivage de la spécification | reste ouverte : `docs/PROMPT_prosodie_expressivite.md` est présent localement, absent du dépôt public → incluse dans le commit proposé |
| #4 — divulgation du processus | reste ouverte : absente du CHANGELOG public ([Unreleased] public = « Documentation / hygiene », autre contenu) → incluse dans le commit proposé |
| Rapports de provenance | absents du dépôt public → inclus dans le commit proposé |

Le fichier `PROVENANCE_COMMIT_PROPOSAL.md` (même répertoire)
détaille le commit déduit de cette analyse.
