# PROMPT — Prosodie expressive : contour de F0 et respiration syntaxique

> Prompt à donner à une session future (idle) pour améliorer le contour
> de F0 du covtl-pipeline dans les six langues (en, fr, es, de, it, pt)
> et casser les chaînes syllabiques inintelligibles par insertion de
> pauses courtes aux frontières syntaxiques. Fonction à conserver
> comme **option d'expressivité** (défaut : off). Rédigé le 2026-09-15
> à partir de l'état réel du dépôt (v1.0.7 + corrections 7 bis ; le
> packaging `lang_pack/` étant développé en parallèle — coordonner).

---

## 1. Constat (état actuel du code)

1. **Contour monotone** : `pipeline.apply_f0_declination`
   (`vtl_synth/core/pipeline.py`) applique une DÉCLINAISON LINÉAIRE par
   phrase — interpolation `onset_gain → final_gain` du profil de
   langue entre le début et la fin de chaque span voisé. Aucun accent
   local, aucune courbure, aucune variabilité : une phrase longue est
   une rampe plate, perçue comme monotone.
2. **Chaînes syllabiques inintelligibles** : le g2p relie TOUS les mots
   d'une phrase par `.` (coarticulation, v1.0.2) — une phrase sans
   virgule devient UNE seule chaîne de 5 s+ (ex. démo de : `IC.zu.X@.
   aj.n@.S2.n@.StRa.s@.In.k2.nICs.bE.ak` = 6 mots chaînés). Les pauses
   n'existent qu'après virgule (200 ms) et fin de phrase (320 ms) —
   il n'y a AUCUNE respiration aux frontières syntaxiques.
3. **Profil de langue sous-exploité** : `LangProfile` ne porte que
   `onset_gain`/`final_gain` (2 scalaires littéraires) + les timings.
   Les références d'intonation citées dans les docstrings (Face,
   Grice, Avesani, Frota…) ne sont pas implémentées au-delà des gains.
4. **Ac lost information** : le chargeur de lexiques
   (`lexicon_loader.ipa_to_keys`) **supprime** les marques d'accent de
   mot de Wikipron (`ˈ` primaire, `ˌ` secondaire) — c'est précisément
   l'information nécessaire pour placer des accents pitchés aux bonnes
   syllabes dans es/de/it/pt/en.

## 2. Objectif

Un mode **expressif** (option, défaut OFF) qui :

1. **Découpe** chaque phrase en blocs syntaxiques pertinents (chunking)
   et insère des pauses courtes entre eux, pour aucune chaîne
   ininterrompue ne dépasse ~4–6 mots (seuil paramétrable) ;
2. **Sculpte le F0** : déclinaison de base conservée, mais agrémentée
   d'**accents pitchés** positionnés sur les syllabes accentuées
   (conformes aux contours par langue, cf. §5), d'une reprise/montée
   d'attaque par bloc et d'une descente terminale par langue ;
3. **Ne change RIEN** quand il est désactivé : baselines, tests 90/90
   en `en`, sorties SAMPA et tract identiques bit à bit avec l'option
   off (l'expressivité agit uniquement sur le glottis : colonne f0 +
   pauses, jamais sur le tract).

## 3. Conception fonctionnelle proposée

### 3.1 Chunking syntaxique (respiration)

Nouveau module proposé : `vtl_synth/utils/chunking.py` (ou extension
des profils), appelé entre le g2p et `build_phrase_tract` :

* **Entrée** : le texte orthographique (avant g2p) — le chunking est
  grammatical, donc opère sur les mots, pas sur le SAMPA.
* **Règles par priorité** :
  1. frontières déjà marquées : virgules, points-virgules, deux-points
     (pause courte existante), tirets ;
  2. **mots fonctionnels de frontière** : conjonctions de coordination
     et subordination (en/and, but, because, that, which ; fr/et, mais,
     parce que, qui, que ; es/y, pero, porque, que ; de/und, aber, weil,
     dass ; it/e, ma, perché, che ; pt/e, mas, porque, que) et
     pronoms relatifs — pause AVANT le bloc introduit ;
  3. **limite dure de chaîne** : si un bloc sans frontière dépasse
     N mots (défaut 5), insérer une pause à la frontière la plus
     plausible : avant un groupe prépositionnel long, sinon au milieu
     du bloc (heuristique documentée comme approximation) ;
  4. jamais de pause : après déterminant/préposition, entre auxiliaire
     et participe, à l'intérieur d'un groupe nominal déterminant+nom.
* **Sortie** : les pauses deviennent des séparateurs courts (mêmes
  espaces que la virgule actuelle) dans le flux SAMPA — ou mieux, des
  marqueurs explicites portés jusqu'à `build_phrase_tract` si le
  refactoring permet de distinguer « pause virgule » et « pause
  respiratoire » (durée légèrement différente, ~120–150 ms, à
  régler à l'écoute).
* **Dictionnaires de mots fonctionnels par langue** dans le profil
  (`LangProfile.chunk_function_words`), extensibles — pas une grammaire
  complète : viser les 30–50 mots-outils les plus fréquents par langue,
  couverture typique 80 % des frontières utiles. Le dire tel quel :
  heuristique lexicale, pas un parseur.

### 3.2 Accents pitchés (F0 expressif)

Étendre `apply_f0_declination` (ou nouveau module `prosody_f0.py`)
avec, par span voisé (= bloc du chunking) :

* **cible de base + courbure** : déclinaison douce (conservée) +
  reprise d'attaque à chaque bloc (l'attaque actuelle ne se produit
  qu'à la première phrase) ;
* **accents locaux** : sur la syllabe accentuée du mot porteur,
  élévation locale du F0 (forme en bosse gaussienne ou interpolation
  S-courbe courte, ~120–200 ms, amplitude par langue) puis retour —
  PAS de saut discontinu (le synthétiseur glottal suit f0 par
  échantillon, la douceur est gratuite) ;
* **chute nucléaire terminale** par langue (§5) sur la dernière
  syllabe accentuée du dernier bloc ;
* **placement de l'accent** : cf. §4 (stress du lexique + règles par
  langue pour les mots hors lexique) ; en/fr : l'accent est de PHRASE
  (fr : finale de groupe accentuel — le dernier mot du bloc ; en :
  mot porteur, heuristique = dernier mot lexical du bloc).

### 3.3 Paramétrage et option

* `LangProfile` étendu (ou `ExpressivityProfile` séparé pour ne pas
  alourdir les profils validés) : `pause_breath_ms` (~130),
  `max_chain_words` (5), `accent_amplitude` (fraction de f0_base,
  ex. 0.12 fr → 0.18 de), `accent_shape/rate`, `nuclear_fall_depth`,
  `chunk_function_words` (dict par langue).
* **Option explicite** : `Pipeline(..., expressive=True)` + CLI
  `--expressive` (et `--no-expressive` en défaut documenté). Le
  bandeau SUCCESS affiche le mode (ex. « prosodie : expressive ») —
  cohérent avec l'affichage de la langue en cours.
* Le mode off doit produire des sorties **bit-identiques** à
  l'actuel : test de non-régression dédié (sha256 du tract/wav avec et
  sans l'option sur la suite existante).

## 4. Placement de l'accent (prérequis technique)

1. **Conserver le stress Wikipron** : modifier `lexicon_loader`
   (tables IPA→clés) pour convertir `ˈ`/`ˌ` en un marqueur porté par
   le token g2p (ex. préfixe `'` sur la voyelle : `'e` = accentuée,
   format à définir avec parsing.py — option minimale : liste d'index
   de syllabes accentuées par mot, hors flux SAMPA). Les clés moteur
   ne doivent PAS être polluées : faire voyager le stress en
   parallèle (dict mot → syllabe accentuée) plutôt que dans la
   chaîne SAMPA.
2. **Règles hors lexique par langue** (fautibles mais plausibles,
   documentées comme telles) : es/it : pénultième par défaut
   (exceptions accent écrite á/é/ì… déjà traitées par les g2p) ; de :
   première syllabe du radical ; en : CMUdict porte le stress (digits
   0/1/2 actuellement supprimés dans `phonemes.arpa_to_sampa` — même
   mécanisme de récupération que Wikipron) ; pt : pénultième (finales
   -l/-r/-i/-u/-im/-ns oxytones) ; fr : pas d'accent de mot — accent
   de GROUPE (finale du bloc).
3. **Fr cas particulier** : Jun & Fougeron — l'accent primaire tombe
   sur la FINALE du dernier groupe accentuel (≈ dernier mot non
   clitique du bloc) ; pas d'accent lexical interne.

## 5. Références d'accentuation par langue (à implémenter/citer)

* **Général** : hiérarchie prosodique et joncture — Selkirk (1984),
  Nespor & Vogel (1986) ; typologie des contours — Jun (2005, 2014),
  *Prosodic Typology* I/II (framework ToBI trans-langues) ; déclination
  et downstep — Ladd (2008, *Intonational Phonology*, 2e éd.).
* **en** : Pierrehumbert (1980) ; Beckman & Ayers (1997, guidelines
  ToBI) ; accent nucléaire H* + chute, deaccentuation des mots
  donnés (given/new) — heuristique simple : accentuer seulement la
  1re occurrence d'un mot dans l'énoncé.
* **fr** : Jun & Fougeron (2002, 2013) — groupe accentuel (AP),
  accent primaire sur la finale d'AP,_APB initial montant (LHi) ;
  Di Cristo (1998) pour la hiérarchie des accents.
* **es** : Sosa (1999) ; Face (2003) — pré-nucléaires H*+L montantes
  étroites, nucléaire H+L* ; Prieto & Roseano (2010, atlas
  intonatif).
* **de** : Féry (1993) ; Grice, Baumann & Benzmüller (2005, GToBI) —
  pré-nucléaires H* tardives, nucléaire H+L* avec terminal bas,
  downstep marqué.
* **it** : Avesani (1995) ; D'Imperio (2002) ; Gili Fivela et al.
  (2015, ITToBI) — montées accentuelles H+L* ou L*+H selon variété,
  terminal bas.
* **pt (européen)** : Frota (2000, 2014) ; Vigário (2003) — mot
  prosodique et groupes, nucléaire précoce H+L* à terminal bas,
  plage F0 plus étroite que l'espagnol.
* **Windows/encodage** : sans objet ici, mais rappeler l'invariant
  `chcp 65001` si un batch de démo prosodique est ajouté.

Ces références servent à CHOISIR les paramètres (amplitudes, cibles
H*/L*, timing de la chute nucléaire) — l'implémentation reste une
simplification à 2–3 paramètres par langue, documentée comme telle.

## 6. Livrables

1. `vtl_synth/utils/chunking.py` (respiration syntaxique) +
   `vtl_synth/utils/prosody_f0.py` (contour expressif) — ou fusion
   justifiée.
2. Extension `LangProfile`/`ExpressivityProfile` avec les paramètres
   du §3.3 et les dictionnaires de mots fonctionnels (6 langues).
3. Stress : conservation `ˈ`/`ˌ` (Wikipron) et digits CMUdict →
   position d'accent par mot (mécanisme hors-SAMPA), + règles de
   repli par langue.
4. Option `Pipeline(expressive=...)` + CLI `--expressive`, bandeau
   affichant le mode.
5. **Tests** : (a) mode off = sorties bit-identiques (sha256 tract/wav
   sur les fixtures existantes) ; (b) chunking : frontières attendues
   sur une batterie par langue (conjonctions, relatives, longues
   chaînes) ; (c) F0 expressif : présence mesurable des accents
   (max f0 local dans la fenêtre de la syllabe accentuée > base +X %),
   douceur (pas de saut > Y Hz/échantillon), chute terminale par
   langue ; (d) les 90 tests existants passent inchangés.
6. **Évaluations** : démos avant/après par langue (mêmes phrases que
   `out_demo/`), paire monotone/expressive, + une phrase longue
   sans ponctuation par langue montrant la respiration. Mesures
   objectives dans le compte-rendu : nb de chaînes > 5 mots (avant :
   nombreuses, après : 0), dynamique F0 (écart-type du contour en
   semi-tons), durée totale.
7. **Intégration lang_pack** : les nouveaux modules et paramètres vont
   dans `lang_pack/profiles/` (coordonner avec la session de packaging
   — elle est ACTIVE sur le dépôt, ne pas écraser `setup_lang.py`/
   `README` sans vérification préalable) ; mise à jour
   `docs/PROMPT_package_linguistique.md` §7 bis si des leçons moteur
   émergent.
8. Mise à jour `CHANGELOG.md` (option d'expressivité, défaut off) et
   mémoire projet.

## 7. Contraintes non négociables

1. **Défaut OFF** : c'est une option d'expressivité — rien ne change
   pour les usages existants (baselines, scripts, launch.bat).
2. **JD3 et `vtl_binaries/` intouchables** ; l'expressivité ne touche
   que f0 (colonne glottis) et les durées de pause — jamais le tract.
3. **Ne pas polluer le SAMPA** : le stress voyage hors bande (dict
   parallèle), les clés moteur restent l'inventaire actuel.
4. Heuristiques avouées : le chunking lexical et le placement hors
   lexique sont des approximations documentées (pas un parseur) — le
   signaler dans les docstrings et le manuel.
5. Chaque commande affiche toujours la langue en cours ; le bandeau
   affiche le mode prosodique.
6. Suite complète : 90/90 en `en` (ou plus, jamais moins) ; en `fr`
   seules les 6 baselines échouent par design.

## 8. Definition of done

* [ ] Mode expressif fonctionnel sur les 6 langues (chunking + accents
      + chute nucléaire) avec paramètres par langue justifiés par les
      références du §5.
* [ ] Mode off : bit-identique (test sha256 dédié).
* [ ] Batterie de chunking par langue (pauses aux frontières
      attendues, aucune chaîne > max_chain_words).
* [ ] Mesure objective des accents (pic F0 sur syllabe accentuée) et
      de la douceur du contour.
* [ ] Démos avant/après par langue + phrase longue respirée.
* [ ] Tests : 90/90+ ; stress Wikipron/CMUdict conservé hors bande.
* [ ] lang_pack à jour (coordination avec la session packaging),
      CHANGELOG + mémoire projet mis à jour.
