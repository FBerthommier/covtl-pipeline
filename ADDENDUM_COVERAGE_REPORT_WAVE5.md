# ADDENDUM AU RAPPORT DE COUVERTURE — Vague 5 (post-1.2.0 hardening)

**Date** : 2026-11-16
**Base** : moteur `94f01b1` (vague 4 déployée, vtl-synth 1.2.0 sur TestPyPI)
**Branche** : `improve/post-1.2.0-hardening` — 3 commits moteur + 2 commits console
**Périmètre** : recommandations P1 de l'audit post-1.2.0 + les 5 % de
remarques finales du déploiement vague 4 (métadonnées PyPI, guide
production, spéc Windows non rapporté).

---

## 1. Résumé exécutif

La vague 5 clôture les recommandations prioritaires de l'audit post-1.2.0.
Le diagnostic factuel a d'abord établi que **deux des trois items P1
étaient déjà réalisés** par la vague 4 (matrice baselines 5 speakers en
CI, pin glottal `glottis_sha256` schema 3) mais **non documentés** et,
pour la phonation, **invisible à la CI** (checker standalone non collecté
par pytest). La vague 5 documente, collecte et complète :

- **P1.1 (baselines multi-speakers)** : mécanisme déjà en place
  (`scripts/run_baselines_matrix.py`, job CI `baselines`) → **documenté**
  dans le README § Multi-speakers (vérifié vert sur cette machine :
  5/5 speakers green).
- **P1.2 (protection du signal glottal)** : `glottis_sha256` déjà pinné
  (schema 3, 8 phrases × 5 fichiers) → le checker full-path phonation
  (20 contrôles) est désormais **collecté par pytest** (17 tests) et
  donc **exécuté par la CI** ; conservation prouvée : baselines jd3
  49 passed après modification du code des tags.
- **P1.3 (alignement console ↔ moteur)** : écart réel — dépôt GitHub
  console à 3.1.5 / pin `vtl-synth==1.1.2` / zéro exposition de
  `tag_overrides` → **corrigé** : champ `phonation` exposé de bout en
  bout (SynthRequest → cache key → worker → `Pipeline(tag_overrides=
  {'*': …})` → UI), dépôt réaligné sur la 3.1.7 publiée, correctif
  spec Windows vague 4 rapporté dans l'arbre git.
- **Nouveau moteur** : clé joker `'*'` dans `tag_overrides` — la
  phonation de toute la phrase en une entrée (la forme qu'un
  sélecteur UI exige), avec priorité per-key > joker.

## 2. Chiffres de tests et de couverture

### 2.1 Moteur (clone frais de `94f01b1`, Python 3.12.16, Linux)

| | Vague 4 (réf.) | **Vague 5** |
|---|---|---|
| Suite complète | 501 passed, 3 skipped | **519 passed, 3 skipped, 0 failed** |
| dont nouveaux tests | — | +17 phonation full-path (pytest), +1 wildcard |
| Baselines jd3 | 49 passed | **49 passed** (inchangées — bit-identité) |
| Matrice 5 speakers | verte (CI) | **verte** (revérifiée localement : 5/5) |
| Couverture combinée (périmètre constant) | 76,6 % | **76,7 %** |
| Plafond honnête §7.5 | 78,6 % | **79,0 %** (5 lignes de mieux, le plafond reste réaliste) |

Conditions de mesure (identiques à §4.1 du rapport principal) :
`pytest tests/ --cov=vtl_synth --cov-branch --cov-report=xml` avec
Branch B sandhi activée par copie ; périmètre constant = hors
`utils/sandhi/`. Le XML est livré : `coverage_wave5.xml`.

Modules clés (lignes) : `syltraj.py` 98,0 % · `enveloppe.py` 88,6 % ·
`build_phrase_tract.py` 95,0 % · `tag_system.py` **96,9 %** (le
nouveau code joker est couvert par 2 tests dédiés + 5 tests
d'équivalence) · `notation.py` 97,4 %.

### 2.2 Console (clone frais de `a1566fc`, moteur vague 5 installé)

| | Avant vague 5 | **Après** |
|---|---|---|
| Suite (fast lane) | 94 passed (réf. CI) | **101 passed, 0 failed** (+7 alignement phonation) |
| Test packaging (pin) | `vtl-synth==1.1.2` | `vtl-synth==1.2.0` |

## 3. Détail des commits

### Moteur (base `94f01b1` → `wave5`)

| # | Commit | Contenu |
|---|---|---|
| 1 | `feat(tags): wildcard '*' tag overrides` | `TagInterpreter` honore la clé `'*'` (appliquée à chaque segment, avant toute entrée per-key) ; les fabricants d'événements (`enveloppe.py`) lisent le joker avec la même précédence. Test : interpréteur, précédence, spans, non-fuite (sans `'*'`, comportement par défaut bit-identique). |
| 2 | `test(phonation): collect the full-path phonation checks as pytest` | Portage pytest du checker standalone (17 tests) : résolution des presets, conversion en schedule, relabelling des blocs, glott400 distincts par mode, forwarding Pipeline, équivalences joker. Stub du probe vv-closure (dépendance tract, orthogonale). Le checker standalone reste. |
| 3 | `docs(packaging): wave-5 visibility` | README : matrice 5 speakers CI + pin tract/glottis documentés (§ Multi-speakers), joker dans l'exemple API (§ Python API) ; `examples/demo_phonation.py` (4 modes côte à côte, RMS affichés) ; `pyproject.toml` : description mentionnant phonation + sandhi, classifiers 3.13/3.14 ; CHANGELOG `[Unreleased]`. |

### Console (base `a1566fc` → `wave5`)

| # | Commit | Contenu |
|---|---|---|
| 1 | `feat(phonation): expose the engine's phonation modes` | `SynthRequest.phonation` (normal/breathy/creaky/whisper) ; mapping worker → `tag_overrides={'*': …}` par introspection de signature (moteur sans `tag_overrides` : ignoré silencieusement) ; clé de cache + echo enrichies ; `'normal'` → aucun override (chaîne nominale bit-identique) ; valeur inconnue → note de job, pas d'erreur moteur ; sélecteur UI « Phonation mode » (groupe Prosody, persisté, sans `convert()` — le mode ne change pas le SAMPA) ; 7 tests d'alignement. |
| 2 | `build: realign the repo with the published 3.1.7` | `pyproject.toml` 3.1.7 + pin `vtl-synth==1.2.0`, stamp `__init__`, assertion `test_packaging` ; **rapport du correctif spec Windows vague 4** dans l'arbre git : `collect_submodules("vtl_synth.utils.sandhi")` (chargement dynamique invisible à PyInstaller). |

## 4. P2/P3 — traitement et propositions

- **P2.4 (audit packaging production)** : réalisé — voir
  `publishing/PYPI_PRODUCTION.md` (audit complet des métadonnées,
  checklist, plan de release 1.2.1, guide écran par écran incluant
  l'édition de description TestPyPI et le scan TOTP).
- **P2.5 (visibilité tag_overrides)** : README § Python API montre le
  joker + l'exemple per-key ; `examples/demo_phonation.py` ;
  l'API est aussi exposée à la console (sélecteur).
- **P2.6 (LEGACY.md)** : relu — **aucune divergence** : les modules
  « kept » sont toujours importés (console/standalone), les omissions
  de couverture correspondent toujours aux fichiers listés ; le
  plafond honnête re-mesuré (79,0 %) confirme la politique (le
  reliquat = V1 déprécié + vidéo + g2p non-fr).
- **P3.7 (démos audio)** : 4 WAV produits depuis le moteur vague 5
  (`demos/`, « this is easy for us », RMS mesurés : normal 0,0760 /
  breathy 0,0844 / creaky 0,0810 / whisper 0,0627 — 4 fichiers
  distincts, empreintes SHA-256 dans SHA256SUMS.txt du zip).
  Placement proposé : page GitHub du projet (release suivante) et
  dossier `docs/demos/` du dépôt.
- **P3.8 (adoption/diffusion)** : état des lieux et 3 actions à faible
  coût dans `docs-upgrade/UPGRADE_README.md` § diffusion.

## 5. Risques restants et recommandations

1. **CI moteur Windows** : la suite 519 tests n'a tourné que sur Linux
   ici ; la CI GitHub (windows-latest) confirmera — les baselines
   étant générées/validées sous Windows, aucun changement de signal
   n'est attendu (aucune modification du chemin nominal : le joker
   n'agit que s'il est explicitement passé).
2. **Ordre de push** : pousser le moteur AVANT la console (la CI
   console installe le moteur depuis GitHub main ; le champ
   `phonation` est accepté mais sans effet jusqu'au push moteur).
3. **Version publiée** : les métadonnées corrigées (description,
   classifiers) ne peuvent PAS remplacer la 1.2.0 déjà sur TestPyPI —
   elles embarqueront la 1.2.1 (plan dans PYPI_PRODUCTION.md §5).
4. **Le joker s'applique aussi aux consonnes** : comportement voulu
   (une seule entrée = toute la phrase), documenté dans le test
   d'équivalence (`'*'` ≡ même override sur chaque phonème) ; pour
   ne moduler que les voyelles, garder la forme per-key.
