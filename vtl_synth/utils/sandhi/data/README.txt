covtl-sandhi — vues éditables des tables
=============================================

Chaque fichier de ce dossier est une VUE ÉDITABLE d'une table du
package : une entrée par ligne, minuscules, commentaires « # »,
lignes vides permises. Au chargement, le module lit le fichier et
REPLACE sa table embarquée si le fichier existe et n'est pas vide ;
sinon il garde la table par défaut (le package reste toujours
importable et testable — ces fichiers ne sont PAS une dépendance).

  fr_h_aspire.txt      mots à h aspiré bloquant la liaison (fr)
  it_rs_triggers.txt   mots-outils déclencheurs du raddoppiamento (it)
  pt_function_words.txt  mots-outils : encadeamento minimal (pt)
  de_glottal_exempt.txt   mots-outils exemptés de frontière glottale (de)

NIVEAUX : un mot AJOUTÉ à une table prend le niveau de sa règle —
it_rs_triggers.txt → standard ; les déclencheurs MINIMAL (fr, it)
sont des sous-classes embarquées du module (voir la docstring de
chaque langue). Le niveau d'une règle existante ne change jamais :
le niveau est un filtre de COUVERTURE, pas de phonologie (base.py).
