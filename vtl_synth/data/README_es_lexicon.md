# es_lexicon.tsv — provenance et licence

`es_lexicon.tsv` est le lexique de prononciation du g2p espagnol
(castillan) : `mot<TAB>prononciation` (IPA Wikipron ou clés moteur),
consulté en priorité absolue par `vtl_synth/utils/g2p_es.py`. Chargeur
commun : `vtl_synth/utils/lexicon_loader.py` (variable
d'environnement : `$COVTL_ES_LEXICON`).

## Source

* Fichier Wikipron : `data/scrape/tsv/spa_latn_ca_broad_filtered.tsv`
  — **castillan** (avec distinción : c/z devant e,i → /θ/ ; variante
  latinos-américaine seseo : `spa_latn_la_broad_filtered.tsv`)
* Lien brut :
  <https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/spa_latn_ca_broad_filtered.tsv>
* Commande de téléchargement :

  ```bash
  curl -L -o vtl_synth/data/es_lexicon.tsv \
    https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/spa_latn_ca_broad_filtered.tsv
  ```

* Taille attendue : ~133 000 lignes, ~3,9 Mo.

Si le fichier est absent ou inexploitable, le g2p fonctionne quand même
(règles + exceptions intégrées) — dégradation douce.

## Licence — OBLIGATOIRE si le fichier est distribué

Les données Wikipron proviennent du **Wiktionnaire** (en) et sont
publiées sous licence **Creative Commons Attribution-ShareAlike
(CC BY-SA 3.0)**. Voir le README générique
[`README_fr_lexicon.md`](README_fr_lexicon.md) (section multilingue)
pour les conditions complètes : conserver la présente notice, citer la
source (« Prononciations extraites du Wiktionnaire anglais par
Wikipron (CUNY-CL/wikipron), CC BY-SA 3.0 ») et partager à l'identique.
Lien : <https://creativecommons.org/licenses/by-sa/3.0/>
