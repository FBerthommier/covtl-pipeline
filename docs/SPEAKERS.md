# Caractéristiques des locuteurs du registre covtl-pipeline

**Version :** 1.0.9 (état du 24/09/2026) · **Source :** missions
triangle/consonnes 22-23/09/2026 + audit croisé de l'étude externe
(`vowel_spaces_covtl_pipeline.pdf`, `vowel_spaces_rho_refit_report.pdf`).
Mesures : statique Route A (solveur tube sans perte, normalisation par
longueur L : jd3 16,83 · s1 18,64 · s2 16,18 · m01 17,59 · w02 15,74 cm)
et réalisation in-situ (LPC sur audio synthétisé, 145 runs VCV + phrases).

## 1. Tableau récapitulatif

| | jd3 | s1 | s2 | m01 | w02 |
|---|---|---|---|---|---|
| Type | référence | DVTD s1 ♂ (IRM) | DVTD s2 ♀ (IRM) | officiel VTL 2.4 ♂ | officiel VTL 2.4 ♀ |
| Longueur tract (cm) | 16,8–18,6 | 18,3–19,8 | 15,6–17,3 | 16,6–19,7 | 15,1–16,7 |
| f0 (Hz) | 102,2 | 114,9 | 181,0 | 120,0 | 232,5 |
| Triangle a-i-u (vs jd3) | **100 %** | **70 %** | **44 %** | 46 % (stat.) | **53 %** |
| Occlusives réalisées (VCV) | 18/18 | 12/18 (d/t quasi, **g/k ouvertes**) | 16/18 + 2 quasi | **18/18** | **18/18** |
| /i/ réalisée (F1, F2) Hz | (585, 1454)* | **(116, 1923)** | (331, 2167) | (175, 1988) | (392, 2026) |
| /a/ réalisée | (757, 1298) | (569, 1104) | (688, 1137) | (591, 1303) | (654, 1115) |
| /u/ réalisée | (160, 795)* | (199, 784) | ≈(350, 1080) | (232, 790) | (625, 1034)* |
| Viabilité | référence | **viable sauf vélaires** | **viable** | **viable** | **viable** |

\* LPC instable sur ces tokens chez jd3 (documenté) ; w02 /u/ réalisé haut
(trait court). Valeurs F1/F2 en Hz, médianes LPC phrase 10 voyelles.

## 2. Verdicts par locuteur

### jd3 — référence
Trapèze vocalique calibré (12 voyelles, accord tube-VTL ≤ 10 %), 18/18
occlusives (d/t réparé par le correctif `SYL_THETA_DENTAL` 270°).
Intouché depuis l'origine.

### s1 — viable sauf vélaires
La plus grande progression : triangle 4 % → 70 % (port complet du
répertoire gestuel jd3 dans la matrice CO_VTL : c1_jd3, 0,9067·c0_jd3,
c2_jd3) + cibles jd3 recalées (ρ_i = 1,20 — la constriction palatale de
cette anatomie exige le double d'excursion de jd3 ; ρ_y = 1,10 ;
ρ_2 = 0,60) + correctif c1(TTY) +0,75 (arbitrage in-situ). Série frontale
complète i > y > e > 2 > E. **Réserves** : vélaires g/k ouvertes
(0,114 cm² — la fermeture n'est atteinte qu'à ρ 3,0 ; lever recommandé :
`clamp_tongue_params=True`) ; apicales quasi-fermées (iti 0,009, ada
0,062 cm²) ; F1 de /i/ statique très bas (fermeture forte, réalisation
conforme).

### s2 — viable
Défaut historique **labial** (directions LP/LD propres fermant les lèvres
sur les voyelles avant : lèvres /i/ 0,061 cm², /e/ fermée) corrigé par
hybride : LP/LD ← jd3, langue propre ×1,2 en c0, cibles jd3 (ρ_i = 0,80).
Triangle 11 % → 44 %. 16/18 occlusives + 2 quasi (udu/utu 0,042 cm²).
**Vigilance** : F1 de /i/ à la marge haute de la bande ; paire o/u serrée
(trait court) ; les « limites anatomiques » /i/ et /e/ du refit externe
(à angles JD2 figés) sont résolues par les angles jd3 portés.

### m01 — viable
Matrice propre conservée (le port jd3, meilleur en statique 57 % contre
46 %, dégradait la /i/ réalisée [459, 1316] — arbitrage D25) + correctif
c1(TTY) 22/09 (−0,149467). 18/18 occlusives. /i/ au point de convergence
de trois voies indépendantes ((178, 2040) fit anatomique = refit externe =
réalisation [175, 1988]). **Améliorations possibles** : /u/ trop frontale
(normalisé +53 % ; le refit externe ρ 0,66 donne +17 % — essai
recommandé) ; nasale /n/ 0,12-0,19 cm² ; glide /w/ ouvert (0,86 cm²) ;
famille e≈E (D26).

### w02 — viable
Matrice inchangée (déjà conforme : 53 %, /i/ sain) ; cibles arrière
réalignées sur les angles jd3 : o (0,80, 104,7°), O (0,85, 149,9°) —
chaîne arrière ordonnée a 1070 > O 977 > u 940 > o 873. 18/18
occlusives. **Limites** : e≈E persistant (Δ 6-38 Hz — D26, seul θ
sépare) ; /o/ à F1 excessif (trait court, confirmé limite anatomique par
les deux études — meilleure configuration externe ρ 0,84 : (452, 738),
essai optionnel) ; paire u/o serrée.

## 3. Ce que « viable » signifie

Un locuteur est déclaré **viable en production** lorsque :
1. toutes ses occlusives orales ferment (aire ≤ 0,005 cm² au lieu du
   geste, réalisées en VCV sur /a i u/) — sauf exceptions documentées
   ci-dessus ;
2. son espace vocalique couvre le triangle a-i-u avec l'ordre phonémique
   français correct et les voyelles de production dans les bandes
   jd3-normalisées (ratio F1 ∈ [0.5, 1.45], |ΔF2| ≤ 25 %), à l'exception
   des marges documentées ;
3. le tout est vérifié **in-situ** (pipeline complet, contexte de
   phrase), pas seulement en projection statique — la réalisation étant
   seule autorité (D25).

## 4. Historique de calibration (résumé)

| Date | Mission | Effet |
|---|---|---|
| 11/09 | registre multi-speakers, baselines relatives | infrastructure |
| 21/09 | recalage ρ polaire (m01 e/y/i, w02 e/y/2/i), D24 identifié | espaces in-situ réparés |
| 22/09 | occlusives : c1(TTY) m01 Δ+1,11 / w02 Δ+1,05 ; clamps vérifiés | 18/18 occlusives m01+w02 |
| 23/09 | triangle : port gestuel s1, hybride s2, cibles w02, m01 conservé ; `SYL_THETA_DENTAL` 270° ; pack langue marqueur seul (D24) | triangle 70/44/46/53 % ; jd3 18/18 |
| 24/09 | audit croisé étude externe | convergences documentées ; essais ρ_u(m01), ρ_o(w02) proposés |

## 5. Speaker characteristics (English summary)

The five registered speakers were recalibrated (matrix level: gesture
repertoire port; target level: jd3-referenced per-speaker radii; pipeline
level: 270° dental override) and validated in-situ. Corner-triangle areas
vs jd3: s1 70 %, s2 44 %, m01 46 %, w02 53 %. Realized oral stops close
on jd3/m01/w02 (18/18) and s2 (16/18 + 2 near-closed); **s1 is viable
except velars** (g/k 0.114 cm²; three remedial levers documented, nearest:
`clamp_tongue_params=True`). All four production speakers are **viable
for synthesis**, with documented residuals: s2 high-F1 /i/ and tight o/u
pair; m01 frontal /u/ (external re-fit candidate), /n/ and /w/; w02 e≈E
merger and short-tract /o/ F1. The external study's four "anatomical
limits" are resolved for three vowels by the current c2-ported matrices;
only w02 /o/ is confirmed as a true limit. See
`audit_rapports_externes.md` and `rapport_triangle_vocalique.md` in the
working archive for the full measurements.
