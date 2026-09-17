# Lexiques de prononciation multilingues — provenance et licence

## Rôle des fichiers

Les lexiques `xx_lexicon.tsv` sont les lexiques de prononciation des
g2p multilingues du pipeline : un mot par ligne,
`mot<TAB>prononciation`, consultés en **priorité absolue** par les
modules `vtl_synth/utils/g2p_xx.py` — l'équivalent fonctionnel du
CMUdict pour l'anglais. Le chargement (détection de format, conversion
IPA, choix parmi les doublons, cache) est factorisé dans
`vtl_synth/utils/lexicon_loader.py`.

Deux formats de prononciation acceptés (détection automatique) :

| format  | exemple                |
|---------|------------------------|
| clés moteur SAMPA (séparées par espaces) | `attends	a t a~` |
| IPA (style Wikipron / Lexique)           | `attends	atɑ̃`    |

Si un fichier est absent ou inexploitable, le g2p de la langue
fonctionne quand même (règles + dictionnaire d'exceptions intégré) —
dégradation douce.

## Langues couvertes

| langue    | fichier            | source Wikipron (`data/scrape/tsv/`)        | g2p                  | env                   |
|-----------|--------------------|----------------------------------------------|----------------------|-----------------------|
| Français  | `fr_lexicon.tsv`   | `fra_latn_broad_filtered.tsv`                | `g2p_fr.py`          | `$COVTL_FR_LEXICON`   |
| Español   | `es_lexicon.tsv`   | `spa_latn_ca_broad_filtered.tsv` (castillan)| `g2p_es.py`          | `$COVTL_ES_LEXICON`   |
| Deutsch   | `de_lexicon.tsv`   | `deu_latn_broad_filtered.tsv`                | `g2p_de.py`          | `$COVTL_DE_LEXICON`   |
| Italiano  | `it_lexicon.tsv`   | `ita_latn_broad_filtered.tsv`                | `g2p_it.py`          | `$COVTL_IT_LEXICON`   |
| Português | `pt_lexicon.tsv`   | `por_latn_po_broad_filtered.tsv` (européen)  | `g2p_pt.py`          | `$COVTL_PT_LEXICON`   |

L'URL brute est de la forme
`https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/<fichier>`
(branche **master** du dépôt CUNY-CL/wikipron). Variantes notables :
espagnol latino-américain (seseo) `spa_latn_la_*`, portugais brésilien
`por_latn_bz_*`.

Commande de téléchargement générique :

```bash
curl -L -o vtl_synth/data/<xx>_lexicon.tsv \
  https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/<fichier_wikipron>
```

## Erreur classique : la page GitHub au lieu du fichier brut

Le fichier enregistré depuis l'interface GitHub (`<html …`) n'est PAS
le lexique. Il faut le TSV **brut** : ouvrir la page du fichier sur
GitHub puis cliquer le bouton **Raw** et enregistrer ce résultat
(ou la commande `curl -L -o …` ci-dessus). Un fichier beaucoup plus
petit que la taille attendue ci-dessous est suspect (page HTML,
réponse d'erreur…).

Tailles attendues (téléchargement de 2026-09-14) : fr ~2,6 Mo /
es ~3,9 Mo (133 k lignes) / de ~2 Mo (58 k) / it ~2,6 Mo (89 k) /
pt ~1,6 Mo (59 k).

## Notices par langue

Chaque lexique a sa notice de provenance détaillée à côté de lui :
[`README_es_lexicon.md`](README_es_lexicon.md),
[`README_de_lexicon.md`](README_de_lexicon.md),
[`README_it_lexicon.md`](README_it_lexicon.md),
[`README_pt_lexicon.md`](README_pt_lexicon.md).

## Licence — OBLIGATOIRE si les fichiers sont distribués

Les données Wikipron proviennent du **Wiktionnaire** (en) et sont
publiées sous licence **Creative Commons Attribution-ShareAlike
(CC BY-SA 3.0)** — le code du dépôt wikipron est sous Apache 2.0,
mais ce sont bien les données qui nous intéressent ici.

Si vous distribuez covtl-pipeline avec un `xx_lexicon.tsv` inclus
(GPL-3.0-or-later pour le code du pipeline), vous devez :

1. **Conserver la notice d'attribution** — le README_xx_lexicon.md
   présent à côté du lexique suffit ;
2. **Indiquer la source** : « Prononciations extraites du Wiktionnaire
   anglais par Wikipron (CUNY-CL/wikipron), CC BY-SA 3.0 » ;
3. **Partager à l'identique** : toute redistribution du lexique
   (modifié ou non) reste sous CC BY-SA 3.0 — licence compatible avec
   la GPL-3.0 du pipeline pour la distribution d'un ensemble ;
4. Lien de licence : <https://creativecommons.org/licenses/by-sa/3.0/>

Si la taille des TSV pose problème pour un dépôt, ne pas les
distribuer : les commandes de téléchargement ci-dessus permettent de
les reconstruire, et le pipeline fonctionne sans eux (règles seules).

Alternative sans contrainte de share-alike pour le français :
**Lexique 3** (<http://www.lexique.org>) est distribué sous licence
LGPL/LRLLL (voir la page du projet pour les conditions exactes d'usage
et de redistribution) — vérifier avant inclusion.

En résumé : usage **local/recherche** — aucune formalité.
Redistribution des fichiers — garder les README + mention
CC BY-SA 3.0 + Wiktionnaire.
