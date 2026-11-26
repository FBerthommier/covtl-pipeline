# PROMPT — Rectification douce des arcs VV fermants : disparition de la pause schwa

> Prompt à donner à une session future (idle) pour achever la campagne
> « rectification douce VV » (audit 2026-11-26) : le moteur et les tests
> sont DÉJÀ implémentés et validés sur le clone de travail ; il reste à
> opérer la documentation (manuels LaTeX, SPEAKERS, erratas, doc de
> l'audit 24/11), la console (test_schwa_route.py + pin) et le round de
> release. Rédigé le 2026-11-26 à partir de l'état réel du dépôt
> (1.2.3 + patch moteur non publié).

---

## 1. Constat (le défaut corrigé)

Le routage des arcs VV fermants via le waypoint schwa (audit
2026-11-24) produisait une **pause non justifiée sur le schwa** lors
des diphtongues de type iu : chaque demi-arc `dep → @` puis `@ → arr`
est une sigmoïde `cos^Pexp` COMPLÈTE, à vitesse nulle aux deux
extrémités — à la jonction, l'état `P(@)` est atteint au ralenti puis
quitté au ralenti. Au D=4 de production (T_voy = 2, arc VV = 40 ms),
les états moteurs sont **[dep, @, @, arr]** : l'état exact du schwa
apparaît DEUX fois, soit 20 ms figés (la moitié de la diphtonge) —
audible comme un e-muet inséré (« buib » → « buiəb », plateau f2).

Mesures (sonde réelle VTL, JD3) : vitesse articulaire minimale dans
la fenêtre VV **0.000** (vs 0.051 après correction) ; 2 états
consécutifs identiques (dwell) ; l'arc direct non routé ferme à
**0.062 cm²** (iu) — c'est le défaut que le routage devait corriger.

## 2. Ce qui est implémenté (déjà validé — ne pas refaire)

Patch moteur sur `vtl_synth/core/syltraj.py` (audit 2026-11-26,
options 2+3 du rapport fusionnées) :

1. **Le trajet direct est conservé** (plus de jambes routées en
   régime nominal). L'arc VV fermant est **rectifié en douceur** :
   seules les colonnes du sélecteur `VV_RECTIFY_SELECTOR` = **TCY,
   TBY** (hauteur du corps et de la base de langue — les paramètres
   qui formment la constriction) sont tirées vers les valeurs du
   schwa par une **bosse sin²**, exactement nulle aux extrémités
   (ancrages bit-exacts), maximale au milieu :
   `P'(t)[p] = P(t)[p] + s·sin²(π·t/(D−1))·(P(@)[p] − P(t)[p])`.
2. **L'amplitude s est réglée par la sonde** (`VV_RECTIFY_STEPS` =
   0.1 … 1.0) : la plus petite valeur qui rouvre l'aire centrale ≥
   `SYL_VV_CLOSURE_THRESH` (0.18 cm²). iu : 0.062 → 0.229 cm² à
   s = 0.3 ; balayage des 132 paires ordonnées : 8 fermantes à D=4
   (10 à D=12), **toutes rectifiées à s ≤ 0.3, zéro fallback**.
3. **Fallback** : si aucune amplitude n'ouvre le corridor, le routage
   deux demi-arcs du 24/11 s'applique (bloc `vowel_key '@'`) — le
   comportement audité reste disponible.
4. `SylBlock.rectify_s` (0 = direct/fallback, > 0 = amplitude) ;
   commentaires `constants.py` + `jd3_constants.py` (rôle du @ :
   cible de rectification + waypoint du fallback) ; haches registry
   regénérées ; `CHANGELOG.md` « Unreleased » ; `DOC_SYNC_LOG.md`
   campagne 2026-11-26.

Validation effectuée : suite pipeline **534 passed / 3 skipped**
(sandhi optionnel, préexistants) ; **baselines 5 locuteurs vertes
sans régénération** (aucune paire VV fermante intra-mot dans le
corpus — « a i u » est en mots séparés, pas d'arc VV) ;
Hausdorff(buib, buaib) = **1.00** (critère ≥ 0.40) ; vitesse minimale
0.051 > 0 ; distance minimale à P(@) = 1.95 (le schwa n'est plus un
état de passage).

## 3. Ce qui reste à opérer (la mission de la session)

### 3.1 Documentation pipeline (doc-sync, cf. DOC_SYNC_LOG 2026-11-26)

| Fichier | Changement attendu |
|---|---|
| `docs/manual.tex` | §VV / § anti-fermeture : « routage obligatoire par le waypoint » → « rectification douce TCY/TBY sur le trajet direct (amplitude réglée par la sonde), routage deux demi-arcs en fallback » ; recompiler le PDF (xelatex, pagination à vérifier) |
| `docs/polar_visualization.tex` | sous-section « The schwa routing: mandatory in the engine, optional on display » → « The schwa rectification: direct path, probe-tuned TCY/TBY, display toggle shows the fallback routing » ; recompiler |
| `docs/SPEAKERS.md` | §6 : schéma schwa par locuteur — remplacer « routage obligatoire, tracé optionnel » par la sémantique rectification + fallback |
| `docs/From_Phonetics_errata.md`, `docs/reference-manual-errata.md` | errata #3 : compliquer — « routage effectif obligatoire » devient « rectification TCY/TBY (fallback : routage) » |
| `docs/schwa-position-audit-EN.md` | étiquettes [layer 2: mandatory routing] → [layer 1: rectification target / fallback route] ; mention explicite que les jambes routées ne subsistent que comme fallback |
| `docs/README.md`, `README.md` | phrases « routing mandatory » → rectification |
| `RELEASING.md` | statut du round 1.2.4 : engine change à embarquer + note « baselines sans régénération » |

Contrôle final : `grep -rn "routage obligatoire\|mandatory routing\|
routed legs" docs/ README.md` → 0 occurrence hors mention du fallback.

### 3.2 Console (covtl-console)

1. `tests/test_schwa_route.py` : `test_polar_routes_through_waypoint`
   — avec le moteur rectifié, « buib » NE PASSE PLUS par le méridien
   π (l'arc reste direct) : réécrire le test sur la nouvelle
   sémantique (ON = l'affichage montre la rectification/fallback
   comme le moteur ; pour buib : pas de croisement π, même payload
   que OFF). Le docstring « routing is mandatory and unconditional »
   → rectification.
2. `CHANGES_v3.md` : entrée du changement (le pin covtl-synth doit
   passer à la version qui embarque le patch).

### 3.3 Round de release

1. Bump 1.2.3 → 1.2.4 (`pyproject.toml` + `vtl_synth/__init__.py`,
   cohérence testée par `test_version_coherence`), datation du
   CHANGELOG « Unreleased » → [1.2.4].
2. Régénérer les démos HTML si elles contiennent des paires fermantes
   intra-mot (`make_html_demos.py` — audio resynthétisé) ; sinon
   simplement vérifier.
3. Chaîne publish-prod habituelle (cf. RELEASING.md), pin console.

## 4. Critères d'acceptation (à vérifier en fin de session)

1. Suite pipeline 534+ verts / 0 échec ; baselines 5 locuteurs SANS
   régénération ;
2. balayage 132 paires : 0 fallback (toutes paires rectifiées) ;
3. « buib » : 1 seul bloc background `rectify_s` ∈ (0, 1), ancrages
   exacts, vitesse minimale > 0, jamais d'état proche de P(@) ;
4. « buib » vs « buaib » : Hausdorff ≥ 0.40 ;
5. grep vocabulaire « routage obligatoire » = 0 occurrence dans docs
   (hors fallback) ;
6. console : suite verte avec le nouveau test_schwa_route.

## 5. Points de vigilance

- **Ne pas toucher aux baselines** : aucune paire VV fermante
  intra-mot dans le corpus — si une phrase en contient un jour, la
  régénération devient nécessaire (regen_baselines.py).
- Le sélecteur {TCY, TBY} est le choix de l'utilisateur (« idéalement
  tcy tby seulement ») ; le balayage montre que TCY seul suffit aussi
  (iu : 0.243 cm² à s = 0.3) — conserver les 2 colonnes pour la
  robust inter-locuteurs (m01/w02 ont leurs propres @).
- La sonde mesure sur l'état de repos 19 param ; la chaîne complète
  ajoute V/VO/TS3 — la marge 0.18 vs 0.15 (plateau /u/) est documentée
  dans `SYL_VV_CLOSURE_THRESH`.
- Option 1 (arc passant par @ sans s'y arrêter) : ÉCARTÉE mais
  documentée dans le rapport d'audit (PDF joint) — balayage intérieur
  240° à ρ quasi constant, excursion polaire 2× plus longue que le
  trajet direct, passage au territoire /y//2/ ; à rouvrir seulement si
  la rectification s'avérait insuffisante sur un nouveau locuteur.
