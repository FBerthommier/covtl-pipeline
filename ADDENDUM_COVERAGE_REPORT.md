# ADDENDUM_COVERAGE_REPORT.md — Vague 4bis : le redo du commit enveloppe (e5c0280)

**Date** : 2026-11-15
**Dépôt** : covtl-wave4 (branche `wave4`, commits `e5c0280` + `05ea4dc` sur la vague 4)
**Objet** : documenter la correction du **trou de lecture complet** des modes de
phonation découvert lors de la resynthèse de contrôle, et les mesures qui en
attestent l'effet réel sur l'audio. Cet addendum complète le COVERAGE_REPORT
vague 4 (§ 1–7) ; il fait partie intégrante du dossier de progression de
couverture transmis à testpypi covtl.

---

## 1. Contexte : la validation qui a révélé le second trou

La vague 4 avait corrigé le premier étage (commit `269b23a`) : les overrides
level-C du `TagInterpreter` atteignaient désormais les `FeatureEvents`
(`_make_phonation_mode_events` couvert à 96,3 %). La resynthèse de contrôle de
la phrase « this is easy for us » dans les 4 modes a produit **4 WAV
byte-identiques** : la modulation était lue, mais jamais entendue.

Mesure du trou (avant redo) sur « this is easy for us »
(`build_phrase_tract` avec `tag_overrides={'@': ...}`) :

- `compute_presets()` de `TimedEnvelope` portait bien la modulation
  (chink_area 15,0 sur 302–825 ms, Δ x_bottom/x_top/rel_amp importants) ;
- **mais** `glott400`, la trajectoire finale 400 Hz, restait **Δ = 0 sur les
  11 colonnes** quel que soit le mode.

Cause racine : `AssembleTract.assemble()` reconstruit la glottis depuis
`build_glottis_trajectory(shape_events, ...)` (moteur de règles
`glottal_source`), qui **ne lit jamais** `extension_data['glottis']` — le
travail du `TimedEnvelope` était jeté à l'assemblage. Un second défaut
connexe : le label `'creaky'` n'existe pas dans `JD3_GLOTTIS_PRESETS` (le
fichier speaker JD3 ne fournit pas cette forme), donc `_lookup_preset_vector`
l'effondrait silencieusement sur le preset modal.

## 2. Le correctif (commit `e5c0280`)

La voie retenue : porter la phonation par le **canal des shape_events** —
l'échelle des presets JD3 (unités natives du `.tract`), avec le même lissage
critique amorti 12 ms que tout autre changement de forme glottique.

| Fichier | Changement |
|---|---|
| `glottal_source.classify_block_events` | nouveau paramètre `phonation_schedule` : spans (mode, début, fin) qui relabellisent les événements intérieurs, **émettent** `(mode, span_start)` si aucun événement n'y tombe (bug trouvé en validation), restaurent la forme tenue en fin de span |
| `glottal_source.phonation_schedule_from_segments` | convertit les `glottal_tag` annotés (level-C) en frames alignées sur la timeline des blocs (même convention que `consonant_frames`) |
| `glottal_source._lookup_preset_vector` | les presets génériques indépendants du speaker servent de repli pour les labels de phonation absents du fichier speaker (`'creaky'` : f0 80, double_pulsing 0,3, pulse_skewness 0,5) — restreint aux labels de phonation pour préserver le fallback modal historique |
| `build_phrase_tract` | construit le schedule depuis les segments annotés et le passe à `classify_block_events` |
| `pipeline.Pipeline` | expose `tag_overrides` et le transmet à `build_phrase_tract` — les 4 modes enfin pilotables depuis l'API Pipeline (l'autre moitié du trou : rien en amont ne pouvait piloter les événements du premier fix) |

Verrouillage : `tests/check_phonation_full_path.py` (20 vérifications :
schedule, relabelling, résolution des presets, chemin complet glott400,
exposition Pipeline). L'override vide reste **bit-identique** à la baseline.

## 3. Mesures après correctif

### 3.1 Trajectoires glottiques (glott400, depuis les `.tract` du pipeline)

| Mode | max Δ vs normal (colonnes modifiées) |
|---|---|
| breathy | x_bottom 0,084 · x_top 0,072 · chink 0,054 · DP 0,004 |
| creaky | x_bottom 0,312 · x_top 0,208 · chink 0,104 · lag 1,17 · DP 0,264 · skew 0,520 |
| whisper | x_bottom 0,094 · x_top 0,084 · chink 0,209 · lag 0,356 · DP 0,052 |

### 3.2 Audio (synthèse C++ VocalTractLab, 44,1 kHz, WAV 16 bits)

« this is easy for us », 4 fichiers distincts (md5 tous différents), 2,37 s :

| Mode | RMS Δ vs normal | verdict |
|---|---|---|
| breathy | **0,0167** | audible |
| creaky | **0,0484** | audible |
| whisper | **0,0261** | audible |

Avant le redo, ces trois valeurs étaient **0,000** — les modes n'étaient
jamais sortis du moteur.

### 3.3 Tests

Suite complète du dépôt sous les 11 commits : **500 passed, 0 failed,
3 skipped** (Python 3.12, `vocaltractlab-cython` 0.0.17 installé —
l'installation du binaire répare aussi les 84 échecs préexistants des
environnements qui en sont dépourvus).

## 4. Impact sur la couverture

Le redo ajoute le code du schedule/relabelling (couvert par les 20
vérifications de `check_phonation_full_path.py`, exécutable standalone) et
étend la couverture effective du canal phonation de bout en bout :
tags → events → shape_events → glott400 → audio. La mesure de couverture
chiffrée de la vague 4 (76,6 % combiné, périmètre constant) demeure la
référence ; ce canal supplémentaire est désormais **exercé et vérifié** de
la contrainte level-C jusqu'au WAV.

## 5. Références

- WAV de contrôle : `vtl-this-is-easy-for-us-{normal,breathy,creaky,whisper}.wav`
  + `vtl-this-is-easy-for-us-REPORT.json` (mesures complètes).
- Commit `05ea4dc` (sandhi Branch B) : activation du jeu de règles complet —
  inclus dans la même série pour la CI `sandhi` du commit `7d60b6e`.
- Série complète : 11 `git format-patch` applicables par `git am --keep-cr`
  sur la base `3903645` (vtl-synth 1.1.3, main), arbre final byte-identique
  au dépôt de développement (vérifié sur clone vierge).
