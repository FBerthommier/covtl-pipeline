# AUDIT V1V2 — Anomalie de coarticulation des hiatus V1.V2 avec bascule nasal/oral

**Moteur audité :** `vtl-synth` (covtl-pipeline, modèle articulatoire COVTL de Berthommier + VocalTractLab 2.4)
**Dépôt :** `github.com/FBerthommier/covtl-pipeline` — clone frais, contournement g2p **retiré** (commit de revert `2a55b69`, inversions de `dea71c6` + `f62f185`)
**Date :** 31 octobre 2026 · **Langue testée :** français (pack fr, speaker `jd3`) · **Document destiné à l'agent chargé de la correction du moteur.**

---

## 1. Résumé exécutif

Le moteur de synthèse syllabique (`syltraj`) **ne réalise pas les enchaînements coarticulés V1.V2 lorsqu'une des deux voyelles est nasale et l'autre orale**. Le défaut a été masqué en amont par une modification récente du g2p français (commit `dea71c6`, complété par `f62f185` en prosodie expressive) qui insère une **pause courte** après tout mot se terminant par une voyelle nasale. Ce contournement est partiel : il ne couvre que les jonctions inter-mots terminées par une nasale ; il dénature la prosodie (pause systématique) ; et il laisse le moteur incapable de traiter le hiatus, y compris en entrée SAMPA manuelle — limitation déjà consignée au CHANGELOG du dépôt (« hand-written V~.V is still dropped by build_phrase_pval »).

Le présent audit, réalisé sur un **clone frais où ce contournement est retiré**, démontre le défaut sur **les 4 situations** demandées (nasal→oral et oral→nasal, intra-mot et inter-mot), avec des mots français réels :

| # | Situation | Exemple audité | SAMPA en entrée moteur | Constat |
|---|-----------|----------------|------------------------|---------|
| S1 | inter-mot, nasal→oral | « comment allez-vous » | `kOma~.a.le.vu` | les DEUX noyaux /a~/ et /a/ disparaissent du plan ; nasalité perdue |
| S2 | inter-mot, oral→nasal | « il a envie » | `i.a.a~vi` | /a/ et /a~/ élidés ; « envie » dénasalisé |
| S3 | intra-mot, oral→nasal | « néon », « éhonté », « paons » | `neO~`, `eO~.te`, `pao~` | /e/ et /O~/ élidés ; « néon » prononcé [neo] |
| S4 | intra-mot, nasal→oral | « enhardir », « enhucher » | `a~aR.diR`, `a~y.Se` | /a~/ et /a/ élidés ; « enhardir » prononcé [anaʁdiʁ] |

**Preuve formelle** : les quatre paires minimales manuscrites `ta.ata`, `ta~.ata`, `ta.a~ta`, `ta~.a~ta` produisent des fichiers `.tract` et `.wav` **identiques octet par octet** (md5 `4f0698e3…` / `1c9c94b0…`). Autrement dit, sur un hiatus lié, **le moteur ignore totalement le trait de nasalité** : l'ouverture vélaire (paramètre VTL `VO`) reste au plancher −0,1 sur toute la durée de la paire, là où un plateau nasal sain atteint +0,49 à +0,50 (`VO_NASALIZED_VOWEL = 0,5`).

**Note sur « paon »** (mot cité dans la commande) : le lexique Wikipron embarqué transcrit le singulier « paon » en `p ɑ̃` — une voyelle nasale **unique**, sans hiatus — et le g2p produit donc `pa~`, qui se synthétise correctement (plateau nasal sain). C'est le pluriel « paons », absent du lexique et transcrit par la voie des règles en `p a ɔ̃`, qui produit le hiatus intra-mot `pao~` (jonction a.o~) — item S3c, défaillant comme les autres.

Le correctif doit être apporté **au moteur** (marche `build_global_pval` + application de la nasalité dans `build_phrase_tract`), pas au g2p : la § 6 propose un patch opérationnel en deux points, compatible avec la philosophie de coarticulation du modèle (le hiatus reste un arc glissé) et avec les exigences de non-régression du dépôt.

---

## 2. Contexte et périmètre

### 2.1 Historique du problème

Le 30 octobre 2026, le commit `dea71c6` (« fix(g2p-fr): short pause instead of the linking dot after a nasal-vowel word ending ») documente l'anomalie observée sur « comment allez-vous » :

> « The syltraj walk cannot articulate the nasal/oral toggle across a linked boundary: on 'comment allez-vous' the G2P emitted `kOma~.a.le.vu` and the walk silently reduced `a~.a` to a background block, dropping BOTH the /a~/ and the /a/ from the articulation plan and from the audio (console compiler panel showed a '-' stretch; the polar display had no a label). »

Le correctif appliqué ce jour-là se situe **dans le g2p** : la jonction inter-mots passe du point de liaison (`.`) à l'espace (pause courte) quand le mot de gauche finit par une voyelle nasale. Le commit `f62f185` étend la même règle à l'enrichissement prosodique expressif (`plan_expressive_text` reconstruisait les jonctions pointées). Le CHANGELOG conserve la limitation connue : un `V~.V` écrit à la main à l'entrée du moteur est toujours élidé, la garde SAMPA ne pouvant pas le signaler (tous les symboles sont valides).

### 2.2 Clone frais d'audit

Conformément à la commande, l'audit est mené sur un clone où **ce contournement est retiré** afin de ne pas masquer le défaut moteur :

- état de départ : `41f6571` (HEAD du dépôt au 30/10/2026, contournement présent) ;
- commit d'audit : `2a55b69` — `git revert` de `dea71c6` et `f62f185`. Les fichiers concernés sont `vtl_synth/utils/g2p_fr.py`, `lang_pack/profiles/g2p_fr.py`, `vtl_synth/utils/prosody_f0.py`, `lang_pack/profiles/prosody_f0.py` ; les correctifs non liés (rafraîchissement du pipeline d'intégration `ff5090d`, synchronisation utils `e50c348`) sont **conservés** ;
- le g2p émet donc à nouveau le point de liaison partout : « comment allez-vous » → `kOma~.a.le.vu` (vérifié à l'exécution).

### 2.3 Chaîne de traitement auditée

```
texte ──> g2p_fr ──> SAMPA (point de liaison '.') ──> build_phrase_tract
                                                       ├─ tokenize_phrase (syltraj)
                                                       ├─ build_flat / build_nodes / build_anchors
                                                       ├─ build_global_pval  ──> blocs (plateau/cluster/background/pause…)
                                                       ├─ E(t) (amplitude_envelope, depuis block_info)
                                                       ├─ V(t), VO(t) (build_phrase_tract §3b, depuis block_info)
                                                       └─ .tract 400 Hz (19 param. tract dont VO=col 7 + 11 glottis) ──> .wav 44,1 kHz
```

La nasalité d'une voyelle n'est pas dans sa cible polaire (ρ, θ) — la cible d'une nasale est **sa contrepartie orale** (« nasality is the VO extension », `syltraj.py:694-696`) — mais dans le paramètre d'extension `VO` (ouverture vélaire), piloté par les blocs du plan d'articulation. C'est là que se joue le défaut.

---

## 3. Méthodologie

### 3.1 Corpus

Quatre situations × deux ou trois items, avec des mots du français **réellement présents dans le lexique Wikipron embarqué** (le cas intra-mot nasal→oral, rarissime, est couvert par les mots en « en-h » à h muet : `enhardir` /ɑ̃.aʁ.diʁ/, `enhucher` /ɑ̃.y.ʃe/ ; le pluriel « paons », hors lexique, est ajouté car la voie des règles y produit le hiatus `a.ɔ̃`), plus des témoins et des paires minimales manuscrites injectées directement en SAMPA à l'entrée du moteur (`use_g2p=False`) :

| Id | Situation | Entrée | Type |
|----|-----------|--------|------|
| S1a/S1b | inter-mot, nasal→oral | « comment allez-vous », « mon ami » | g2p |
| S2a/S2b | inter-mot, oral→nasal | « il a envie » (exemple du demandeur), « la onzième » | g2p |
| S3a/S3b/S3c | intra-mot, oral→nasal | « néon », « éhonté », « paons » (pluriel, voie des règles) | g2p |
| S4a/S4b | intra-mot, nasal→oral | « enHardir », « enHucher » | g2p |
| T1/T2 | témoins hiatus oral-oral | « aérer », « il a oublié » | g2p |
| T3/T4 | témoins nasale saine (référence VO) | « comment » (`kOma~`), « envie » (`a~vi`) | g2p |
| T5/T6 | compléments nasal→nasal | « mon oncle », « un an » | g2p |
| H0–H3 | paires minimales moteur | `ta.ata`, `ta~.ata`, `ta.a~ta`, `ta~.a~ta` | SAMPA direct |
| H4 | cas documenté du commit | `kOma~.a.le.vu` écrit à la main | SAMPA direct |

Le corpus complet est dans `corpus_v1v2.json` ; le harnais `run_corpus.py` synthétise chaque item (Pipeline `lang=fr`, moteur `syl`, speaker `jd3`, réglages par défaut du profil fr : `t_cons=140 ms`, `t_voy=120 ms`, `pause_short=200 ms`) et capture : la chaîne SAMPA réellement entrée au moteur, le plan d'articulation (`syltraj.get_last_build()` : nœuds, ancrages, blocs), le fichier `.tract`, le `.wav`, et les journaux.

### 3.2 Mesures

- **Plan d'articulation** : liste ordonnée des blocs (`kind`, durée en steps à 100 Hz, `vowel_key`, `nasal`). Un noyau vocalique n'existe dans le plan que comme bloc `plateau` ; le drapeau `nasal` n'existe que sur ces plateaux.
- **Nasalité réalisée** : maximum du paramètre `VO` (colonne 7 du `.tract`) sur la moitié centrale de la fenêtre du bloc `background` qui remplace le hiatus. Référence : maximum de `VO` sur les plateaux nasaux des témoins T3/T4. Seuil de nasalité réalisée : `VO ≥ 0,3`.
- **Audio** : énergie RMS du `.wav` sur la même fenêtre (l'énergie y est présente — le défaut n'est pas un silence mais une fusion dénarisée ; voir § 4.4).
- **Identité** : md5 des `.wav` et `.tract` (mise en évidence des sorties indiscernables).
- **Comparaison g2p** : `compare_head_g2p.py` oppose, pour chaque texte, le SAMPA du clone frais et celui du HEAD d'origine (extrait de l'historique git), afin de mesurer exactement ce que le contournement masquait.

---

## 4. Résultats

### 4.1 Chaînes SAMPA en entrée du moteur (clone frais, contournement retiré)

| Id | Texte | SAMPA entré au moteur | Jonction V1V2 |
|----|-------|------------------------|---------------|
| S1a | comment allez-vous | `kOma~.a.le.vu` | **a~.a** |
| S1b | mon ami | `mO~.a.mi` | **O~.a** |
| S2a | il a envie | `i.a.a~vi` | **i.a** puis **a.a~** |
| S2b | la onzième | `la.O~zjEm` | **a.O~** |
| S3a | néon | `neO~` | **e.O~** |
| S3b | éhonté | `eO~.te` | **e.O~** |
| S3c | paons (pluriel, voie des règles) | `pao~` | **a.o~** |
| S4a | enhardir | `a~aR.diR` | **a~.a** |
| S4b | enhucher | `a~y.Se` | **a~.y** |
| T1 | aérer | `a.e.Re` | a.e (témoin) |
| T2 | il a oublié | `i.a.ub.li.je` | a.u (témoin) |
| T3 | comment | `kOma~` | — (nasale saine) |
| T4 | envie | `a~vi` | — (nasale saine) |
| T5 | mon oncle | `mO~.O~kl` | O~.O~ (complément) |
| T6 | un an | `9~.a~` | 9~.a~ (complément) |

Remarque : les points de liaison intra-mot disparaissent parfois autour des nasales (« néon » → `neO~`, « envie » → `a~vi`) car `syllabify_keys` traite les clés nasales comme des **consonnes** (`SAMPA_VOWELS = frozenset(VOWEL_TARGETS.keys())`, `phonemes.py:38` — les clés nasales `a~`, `O~`… n'en font pas partie). C'est une seconde anomalie liée aux nasales (voir § 5, défaut n° 4) : elle est sans effet sur le défaut étudié — le point de liaison est de toute façon un marqueur purement boundary pour le moteur, et l'adjacence des **nœuds** voyelles suffit à déclencher le hiatus.

### 4.2 Le mécanisme exact du défaut (lecture de code)

Trois défauts convergents, tous côté moteur :

1. **Perte du plateau.** `build_anchors` (`syltraj.py:641-646`) : une voyelle n'obtient un ancrage « à tenir » que si elle n'est adjacente à **aucune** autre voyelle :
   ```python
   prev_v = i > 0 and nodes[i - 1].kind == 'V'
   next_v = i < n - 1 and nodes[i + 1].kind == 'V'
   anchors.append(SylAnchor(..., hold=not prev_v and not next_v))
   ```
   Dans un hiatus V1V2 (nœuds voyelles adjacents, avec ou sans point), **les deux voyelles perdent leur plateau**.

2. **Réduction en arc de fond anonyme.** `build_global_pval`, branche `m == 0` (`syltraj.py:1019-1024`) : entre deux ancrages voyelles sans consonne, la marche émet un unique bloc `background` de `2·T_voy` steps — un arc glissé de la cible de V1 vers celle de V2, **sans `vowel_key` ni drapeau `nasal`**. Or le drapeau `nasal` n'est transmis **que** par les blocs `plateau` (`syltraj.py:913-915` et `1046-1048`). De surcroît, la cible polaire d'une nasale étant sa contrepartie orale, une paire comme `a~.a` produit un arc **statique** ([a] tenu), sans même de glissement.

3. **Nasalité inapplicable sur l'arc de fond.** `build_phrase_tract.py:845` : l'ouverture vélaire VO des voyelles nasales n'est appliquée **que sur les blocs `plateau`** :
   ```python
   if _bi.kind == 'plateau' and getattr(_bi, 'nasal', False):
       ...  # rampe VO = 0,5 (VO_NASALIZED_VOWEL, constants.py:747)
   ```
   Un bloc `background` ne portant jamais `nasal=True`, le velum reste au plancher −0,1 (fermé) sur toute la durée du hiatus : **la voyelle nasale est entièrement dénarisée**.

L'énergie, elle, est bien présente (`amplitude_envelope.py:386-387` : un bloc `background` reçoit E=1, le voisement suit E) : il n'y a donc pas de silence, mais une voyelle tenue **orale**, non étiquetée, à la place des deux noyaux attendus — c'est l'« élision » perceptuelle : « comment allez-vous » se réalise [kɔmaːlely] avec un [aː] oral long au lieu de [kɔmɑ̃.alely]. Le « - » constaté dans la console covtl est la timeline d'étiquettes (aucun bloc ne porte les clés des voyelles).

### 4.3 Élision des noyaux — plans d'articulation comparés

Témoin sain T3 « comment » (`kOma~`) — le /a~/ final, non impliqué dans un hiatus, a son plateau nasal :

```
offset dur  kind        voyelle nasal  contenu
     0  20  initial
    20  28  cluster                  cluster (1 cons. : k)
    48  12  plateau     O      False plateau de /O/
    60  28  cluster                  cluster (1 cons. : m)
    88  12  plateau     a      True  plateau de /a~/   <-- NASAL, VO≈0,49
   100  14  decay
   114  20  terminal
```

Item défaillant S1a « comment allez-vous » (`kOma~.a.le.vu`) — au même offset 88, le plateau nasal a disparu, remplacé par un arc de fond anonyme de 24 steps (2×T_voy) :

```
offset dur  kind        voyelle nasal  contenu
     0  20  initial
    20  28  cluster                  cluster (k)
    48  12  plateau     O      False plateau de /O/
    60  28  cluster                  cluster (m)
    88  24  background  -      False arc de fond NON étiqueté  <-- /a~/ ET /a/ élidés
   112  28  cluster                  cluster (l)
   140  12  plateau     e      False plateau de /e/
   152  28  cluster                  cluster (v)
   180  12  plateau     u      False plateau de /u/
   192  14  decay
   206  20  terminal
```

Le plan passe de 5 noyaux attendus (O, a~, a, e, u) à 3 plateaux réalisés (O, e, u) : **/a~/ et /a/ ont été élidés**. Les 19 timelines complètes sont dans `results/plans/`.

### 4.4 Mesures — tableau récapitulatif

`VO c. hiat.` = max de VO sur la moitié centrale de la fenêtre du hiatus ; `VO réf.` = max de VO sur un plateau nasal sain. Nasalité perdue si `VO c. hiat. < 0,3`.

| Id | SAMPA moteur | Noyaux élidés | VO c. hiat. | VO réf. | Nasalité perdue | Audio dans l'hiatus |
|----|--------------|----------------|-------------|---------|------------------|----------------------|
| S1a | `kOma~.a.le.vu` | a~, a | −0,085 | — | **OUI** | présent (RMS 0,24) |
| S1b | `mO~.a.mi` | O~, a | −0,085 | — | **OUI** | présent |
| S2a | `i.a.a~vi` | i, a, a~ | −0,100 | — | **OUI** | présent |
| S2b | `la.O~zjEm` | a, O~ | −0,100 | — | **OUI** | présent |
| S3a | `neO~` | e, O~ | −0,085 | — | **OUI** | présent |
| S3b | `eO~.te` | e, O~ | −0,100 | — | **OUI** |
| S3c | `pao~` | a, o~ | −0,100 | — | **OUI** | présent |
| S4a | `a~aR.diR` | a~, a | −0,100 | — | **OUI** | présent |
| S4b | `a~y.Se` | a~, y | −0,100 | — | **OUI** | présent |
| T5 | `mO~.O~kl` | O~, O~ | −0,085 | — | **OUI** | présent |
| T6 | `9~.a~` | 9~, a~ | −0,100 | — | **OUI** | présent |
| T1 | `a.e.Re` | a, e (par conception) | −0,100 | — | non (aucune nasale) | présent |
| T2 | `i.a.ub.li.je` | i, a, u (par conception) | −0,100 | — | non (aucune nasale) | présent |
| T3 | `kOma~` | aucun | — | **0,495** | non | — |
| T4 | `a~vi` | aucun | — | **0,491** | non | — |
| H0 | `ta.ata` | a, a (par conception) | −0,100 | — | non | présent |
| H1 | `ta~.ata` | a~, a | −0,100 | — | **OUI** | présent |
| H2 | `ta.a~ta` | a, a~ | −0,100 | — | **OUI** | présent |
| H3 | `ta~.a~ta` | a~, a~ | −0,100 | — | **OUI** | présent |
| H4 | `kOma~.a.le.vu` | a~, a | −0,085 | — | **OUI** | présent |

Lecture :

- **Les situations S1–S4 sont défaillantes sur tous leurs items (9/9)** : les deux membres du hiatus perdent leur noyau, et le membre nasal perd sa nasalité (VO au plancher −0,1, contre +0,49/+0,50 sur un plateau nasal sain — soit une différence de 0,6 en units VTL, énorme).
- Les petites valeurs résiduelles (−0,085 au lieu de −0,100 sur S1a, S1b, S3a, T5, H4) proviennent de la queue de décroissance du lissage anti-clic (τ = 20 ms) après la **consonne nasale** précédente ([m] de `kOma~`, [n] de `neO~`) : ce n'est pas la voyelle qui nasalisée, c'est l'occlusive nasale qui ferme son velum en retard — preuve supplémentaire que la voyelle elle-même ne contribue à rien.
- Le complément V~.V~ (T5 « mon oncle », T6 « un an ») montre que le cas nasal→nasal est également touché : les DEUX nasalités sont perdues.
- L'audio est présent dans la fenêtre du hiatus (RMS du même ordre que les plateaux) : l'élision est **articulatoire et perceptive** (fusion en une voyelle orale tenue/glissée, non étiquetée), pas un silence.

### 4.5 Preuve par identité octet — la nasalité est ignorée

| Entrée moteur | md5 `.wav` | md5 `.tract` |
|---------------|-----------|--------------|
| `ta.ata` (H0, témoin oral) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta~.ata` (H1, nasal→oral) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta.a~ta` (H2, oral→nasal) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |
| `ta~.a~ta` (H3, nasal→nasal) | `1c9c94b0cec9b99550ca2251a6e3e2a0` | `4f0698e3a77ae6d5816192dfe92e6f5a` |

Les quatre variantes produisent **exactement le même fichier** : le trait [nasal] n'a strictement aucun effet sur un hiatus lié, dans quelque direction que ce soit. Par ailleurs S1a (via g2p) et H4 (SAMPA manuscrit) sont eux aussi identiques (`333c1d4e…`), ce qui confirme que le g2p et l'entrée manuelle convergent vers le même défaut moteur.

### 4.6 Ce que le contournement g2p masquait — et ce qu'il ne masquait pas

`compare_head_g2p.py` (résultats dans `results/sampa_frais_vs_head.txt`) :

- **Masqués par le patch** (espace insérée au lieu du point) : S1a, S1b (« comment allez-vous », « mon ami ») et, incidemment, T5/T6 — soit toutes les jonctions **inter-mots dont le mot de gauche finit par une nasale**. 4 items sur 14.
- **Non masqués** : S2a/S2b (oral→nasal inter-mot : « il a envie » → `i.a.a~vi` identique avec ou sans patch), S3a/S3b et S4a/S4b (intra-mot : le patch n'agit que sur les jonctions entre mots) — **6 items sur 8 du corpus de défaut**.

Autrement dit : même **avec** le contournement en place, l'anomalie moteur restait observable et audible sur les situations S2, S3 et S4. Seule la correction du moteur couvre l'ensemble des cas.

---

## 5. Analyse des causes — quatre défauts à inscrire au registre

1. **[Moteur, critique] Hiatus V1V2 sans plateau ni nasalité** — le sujet du présent audit (§ 4.2, défauts 1-3).
2. **[Frontal/g2p] Syllabification des voyelles nasales comme consonnes** — `phonemes.py:38` : `SAMPA_VOWELS` ne contient que les clés orales ; `syllabify_keys` traite `a~`, `O~`… comme des attaques/codas. Conséquences visibles dans le SAMPA produit (« néon » → `neO~` sans point ; « envie » → `a~vi` monosyllabe). Ne déclenche pas le défaut n° 1 à elle seule, mais fausse la segmentation syllabique et mérite d'être corrigée dans la même passe (les clés nasales doivent fermer un noyau comme les orales).
3. **[Contournement à retirer] Pause g2p après nasale finale** — `dea71c6`/`f62f185` : masque 1 cas sur 4 situations, introduit une pause non linguistique, et contredit l'invariant documenté « the assembled SAMPA is identical to the language g2p's » dès qu'on compare g2p et prosodie. Une fois le moteur corrigé, ces deux commits doivent être à nouveau inversés (retour au point de liaison partout).
4. **[Garde] La garde SAMPA ne peut pas signaler le V~.V manuscrit** — tous les symboles étant valides, la réduction silencieuse est indétectable en entrée. Après correction moteur, cette limitation documentée disparaît d'elle-même ; en attendant, un avertissement dédié (« V~.V détecté — réduit par la marche ») serait utile.

---

## 6. Modifications opérationnelles proposées

> Objectif : que la marche articule la **bascule nasal/oral à travers une frontière liée**, tout en préservant la philosophie du modèle COVTL (le hiatus reste un arc glissé coarticulé, cf. le traitement des V.V orales « handled by the walk ») et les baselines de non-régression.

### P1 — `syltraj.build_global_pval` : sous-blocs de fond étiquetés sur le hiatus

Dans la branche `m == 0` (frontière liée V.V, `syltraj.py:1019-1024`), remplacer l'unique bloc `background` anonyme de `2·T_voy` par **deux blocs consécutifs de `T_voy`** couvrant le même arc (construire l'arc complet puis le scinder, afin de préserver exactement la trajectoire et la durée totale), chacun portant :

```python
SylBlock(n_steps=T_voy, kind='background',
         vowel_key=<clé orale de V1>, nasal=<V1.nasal>)
SylBlock(n_steps=T_voy, kind='background',
         vowel_key=<clé orale de V2>, nasal=<V2.nasal>)
```

Variantes d'implémentation acceptables : ne scinder **que lorsqu'au moins un membre est nasal** (garantit le bit-à-bit des hiatus purement oraux comme `di.as`/T1/T2 — option la plus sûre pour la non-régression), ou scinder systématiquement (plus homogène : chaque voyelle du hiatus retrouve une étiquette et le gain d'effort par voyelle). La durée cumulée `2·T_voy` et l'arc polaire doivent rester inchangés.

Effets : les deux voyelles retrouvent une étiquette dans le plan (fin du « - » dans la console et dans la vidéo polaire), le gain d'effort par voyelle (`VOWEL_EFFORT_GAIN`, `build_phrase_tract.py:664-676`) s'applique, et le point d'accroche de la nasalité existe.

### P2 — `build_phrase_tract.py:845` : nasalité applicable aux demi-arcs de fond

Étendre la condition d'application de la rampe VO des voyelles nasales :

```python
# avant :  if _bi.kind == 'plateau' and getattr(_bi, 'nasal', False):
# après :
if _bi.kind in ('plateau', 'background') and getattr(_bi, 'nasal', False):
```

Le lissage anti-clic existant (filtre du premier ordre, τ = 20 ms, lignes 867-873) prend en charge la transition vélaire entre les deux moitiés : sur `a~.a`, VO monte vers 0,5 sur la première moitié puis retombe vers −0,1 sur la seconde — exactement la bascule attendue. Sur `a.a~`, c'est l'inverse. Sur `a~.a~`, VO reste à 0,5 sur les deux moitiés (avec les rampes 20 % aux extrémités), ce qui corrige aussi le cas T5/T6.

### P3 — Nettoyage du frontal (à faire après validation moteur)

1. Ré-inverser `dea71c6` et `f62f185` (retour au point de liaison partout) : le g2p n'a plus à masquer le moteur. Conserver la note de CHANGELOG en la passant au passé.
2. Corriger `phonemes.py:38` : `SAMPA_VOWELS` doit inclure les clés nasales (p. ex. `{k for k in ALL_PHONEME_KEYS if _is_vowel_key(k)}` à la source des clés) afin que `syllabify_keys` traite les nasales comme des noyaux. Vérifier l'impact sur les tests de segmentation non-régression (certaines découpages changeront : `neO~` → `ne.O~`, `a~vi` → `a~.vi` — c'est phonologiquement correct).
3. Optionnel : avertissement de la garde SAMPA sur `V~.V` tant que P1/P2 ne sont pas en place.

### P4 — Non-régression et validation

1. **Baselines inchangées** : les corpus de référence (regression_baselines*.json) ne doivent pas bouger pour les entrées sans hiatus nasal — d'où l'intérêt de la variante « scission uniquement si nasal » de P1. Vérifier avec la suite existante (le dépôt annonce 207 tests moteur passants).
2. **Nouveaux tests unitaires** (à ajouter à `tests/`) :
   - `build_phrase_pval('ta~.ata')` → le plan contient un bloc `background` avec `nasal=True` côté V1 et `vowel_key='a'` ;
   - idem `ta.a~ta` côté V2 ; `ta~.a~ta` → deux demi-arcs nasals ;
   - `ta.ata` → bit-à-bit identique à l'état antérieur (si variante conditionnelle retenue) ;
   - après synthèse : `max(VO) ≥ 0,4` sur la première moitié de l'hiatus de `ta~.ata`, `max(VO) ≤ 0,0` sur la seconde ;
   - les WAV de `ta~.ata` et `ta.ata` doivent désormais **différer** (c'est l'inversion de la preuve md5 du § 4.5).
3. **Protocole de validation perceptif** : réexécuter `AUDIT_V1V2/run_corpus.py` — les 8 items S1–S4 doivent passer à « nasalité perdue : non » avec `VO c. hiat. ≈ 0,5` sur le(s) moitié(s) nasale(s) ; comparer les WAV avant/après correction (archivés dans ce dossier).

### Périmètre volontairement exclu

La qualité phonétique du rendu (liaison française, durées de nasalisation, vitesse de bascule vélaire — une rampe 20 % sur T_voy=120 ms est discutable phonétiquement) et le moteur prosodique expressif ne sont pas audités ici ; le patch proposé est volontairement minimal et localisé pour rester réversible, dans l'esprit du dépôt `covtl-lambda` (patch installable du moteur avec paramètre réglable).

---

## 7. Livrables et reproduction

```
AUDIT_V1V2/
├── AUDIT.md                  ← ce rapport
├── MISSION.md                ← note de mission pour l'agent correcteur
├── corpus_v1v2.json          ← corpus de test (19 items)
├── run_corpus.py             ← harnais : synthèse + capture plan/tract/wav + mesures
├── compare_head_g2p.py       ← comparaison SAMPA clone frais vs HEAD contourné
└── results/
    ├── results.json          ← tableau complet machine-lisible (avec verdicts)
    ├── results_g2p.json      ← comparaison g2p frais/HEAD
    ├── sampa_frais_vs_head.txt
    ├── plans/<id>.txt        ← 19 timelines du plan d'articulation
    ├── wav/<id>.wav          ← 19 synthèses (44,1 kHz)
    ├── tract/<id>.tract      ← 19 séquences VTL 400 Hz (VO = colonne 7)
    └── logs/<id>.log         ← journaux (dont garde SAMPA : aucun signalement)
```

Reproduction (Linux) :

```bash
python -m venv .venv && . .venv/bin/activate
pip install numpy scipy Pillow cmudict "vocaltractlab-cython>=0.0.10" .
python setup_lang.py install --lang fr && python setup_lang.py setlang fr
python AUDIT_V1V2/run_corpus.py            # ~2 min, écrit results/
python AUDIT_V1V2/compare_head_g2p.py
```

*(Note : `pip install .` installe le moteur ; le harnais insère la racine du dépôt en tête de `sys.path`, donc le clone local prime sur toute installation. L'avertissement « CONSTANTS INCONSISTENCY » après activation du pack fr est le hash de constants.py connu et documenté — sans effet sur la synthèse.)*

---

## Annexe A — Données brutes clés

- Référence VO plateau nasal sain : T3 = 0,495 ; T4 = 0,491 (`VO_NASALIZED_VOWEL = 0,5`, rampes 20 % incluses).
- VO hiatus (moitié centrale) : de −0,100 à −0,085 sur tous les items à nasale élidée.
- Durées : `T_voy = 12` steps (120 ms) ; bloc `background` d'hiatus = `2·T_voy = 24` steps (240 ms) ; l'énergie RMS dans cette fenêtre est comparable à celle des plateaux (≈ 0,19–0,25 contre 0,11–0,22) : pas de silence, une fusion orale.
- Empreintes : voir § 4.5 ; `results.json` contient les md5 de chaque item.

## Annexe B — Fichiers et lignes concernés par le correctif

| Fichier | Ligne(s) | Rôle dans le défaut / correctif |
|---------|----------|----------------------------------|
| `vtl_synth/core/syltraj.py` | 641-646 | `hold = not prev_v and not next_v` — perte des plateaux du hiatus (constat) |
| `vtl_synth/core/syltraj.py` | 1019-1024 | branche `m == 0` : bloc background anonyme — **site du correctif P1** |
| `vtl_synth/core/syltraj.py` | 913-915, 1046-1048 | transmission du drapeau `nasal` (plateaux uniquement) |
| `vtl_synth/core/build_phrase_tract.py` | 839-854 | VO des voyelles nasales — **site du correctif P2** (ligne 845) |
| `vtl_synth/core/build_phrase_tract.py` | 867-873 | lissage anti-clic VO (τ = 20 ms) — réutilisé tel quel par P2 |
| `vtl_synth/core/amplitude_envelope.py` | 384-387 | E = 1 sur background (pourquoi l'audio subsiste) |
| `vtl_synth/core/phonemes.py` | 38 | `SAMPA_VOWELS` sans clés nasales — défaut n° 2 (P3.2) |
| `vtl_synth/core/constants.py` | 745-748 | `TAG_TO_VO_TARGET` : `nasalized = 0,5` |
| `vtl_synth/utils/g2p_fr.py` + `lang_pack/profiles/g2p_fr.py` | 249-279 | contournement retiré par le revert d'audit (à maintenir retiré après correction moteur) |
