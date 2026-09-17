# pt_lexicon.tsv — provenance et licence

`pt_lexicon.tsv` est le lexique de prononciation du g2p portugais
(européen) : `mot<TAB>prononciation` (IPA Wikipron ou clés moteur),
consulté en priorité absolue par `vtl_synth/utils/g2p_pt.py`. Chargeur
commun : `vtl_synth/utils/lexicon_loader.py` (variable
d'environnement : `$COVTL_PT_LEXICON`).

## Source

* Fichier Wikipron : `data/scrape/tsv/por_latn_po_broad_filtered.tsv`
  — **portugais européen** (variante brésilienne :
  `por_latn_bz_broad_filtered.tsv`)
* Lien brut :
  <https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/por_latn_po_broad_filtered.tsv>
* Commande de téléchargement :

  ```bash
  curl -L -o vtl_synth/data/pt_lexicon.tsv \
    https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/por_latn_po_broad_filtered.tsv
  ```

* Taille attendue : ~59 000 lignes, ~1,6 Mo.

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
