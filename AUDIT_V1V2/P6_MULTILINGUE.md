# P6 — Extension multilingue de la validation V1V2 (état 2026-11-02)

Mission §7 exécutée. La porte `nasal_preproc` est **agnostique de la
langue** ; la validation couvre désormais le pack complet.

## 1. Portugais — corpus dédié (`corpus_v1v2_pt.json`, résultats `results_pt/`)

Même typologie structurelle que le français, items réels du lexique et
des règles `g2p_pt` :

| id | situation | texte | SAMPA moteur | hiatus | VO nas. | nasalité perdue |
|----|-----------|-------|--------------|--------|---------|-----------------|
| S1a | inter-mot nasal→oral | acauã ele | `@.kaw@~.e.l@` | `@~.e` | 0.489 | non |
| S1b | inter-mot nasal→oral | atum a | `@tu~.a` | `u~.a` | 0.489 | non |
| S2a | inter-mot oral→nasal | ele um | `e.l@.u~` | `@.u~` | 0.489 | non |
| S2b | inter-mot oral→nasal | ele hã | `e.l@.@~` | `@.@~` | 0.489 | non |
| S3a | intra-mot oral→nasal | neon | `neo~` | `e.o~` | 0.489 | non |
| T1 | témoin intra V.V oral | país | `p@.is` | `@.i` | −0.1 | — (oral) |
| T2 | témoin inter V.V oral | ele ama | `e.l@.a.m@` | `@.a` | −0.1 | — (oral) |
| T3 | témoin nasale isolée (plateau final) | irmã | `iRm@~` | — | réf 0.495 | — |
| T4 | témoin nasale non-hiatus (diphtongue) | sem | `s@~j` | — | réf 0.489 | — |
| T5 | complément V~.V~ | afim um | `@fi~.u~` | `i~.u~` | 0.5 | non |
| T6 | complément V~.V~ | atum hum | `@tu~.u~` | `u~.u~` | 0.5 | non |
| T7 | témoin dédié diphtongue nasale | cão | `k@~w` | — | réf 0.489 | — (inchangé) |
| H0–H4 | paires minimales moteur | ta.ata … kOma~.a.le.vu | direct | typologie complète | 0.489–0.5 | non |

Critères fr respectés : VO ≥ 0.489 sur les moitiés nasales (seuil 0.3–0.4) ;
témoins oraux à VO = −0.1 ; `nasalite_perdue` = faux partout.

**Particularité pt documentée** : `g2p_pt` n'émet jamais V~.V intra-mot
(0 occurrence sur 35 690 mots du lexique — une voyelle nasale n'y est
jamais adjacente à une voyelle orale) ; la situation S4 intra-mot est
donc couverte par les items H en SAMPA direct (comme prévu §7.1). La
jonction inter-mot de `g2p_pt` est bien le point de liaison (`acauã ele`
→ `@.kaw@~.e.l@`).

## 2. Inertie es / it / de / en (`p6_multilingue.py`, `results_p6/inertie.json`)

| langue | g2p sans `~` | lexique sans `~` | bit-à-bit actif/neutre | inerte |
|--------|--------------|------------------|------------------------|--------|
| es | oui (2 textes) | oui | oui (wav + tract md5) | **oui** |
| it | oui | oui | oui | **oui** |
| de | oui | oui | oui | **oui** |
| en | oui (ARPAbet) | n/a (CMUdict) | oui | **oui** |

La porte est **structurellement inerte** sur les langues sans voyelle
nasale phonémique, et la couverture défensive est documentée : si un
lexique futur ou du SAMPA manuel introduit `~`, le moteur gère la
bascule (c'est l'objet du correctif) au lieu de perdre la nasalité.

## 3. Inventaire moteur

`phonemes.SAMPA_VOWELS` (= clés de `VOWEL_TARGETS`) couvre les clés
nasales de **toutes** les langues (fr : `a~ e~ i~ o~ u~ y~ 2~ 9~ O~ @~` ;
pt : `@~ o~ e~ a~ u~ i~`…) — vérifié par `p6_multilingue.py`
(`inventory_coverage`, `tout_couvert = True`), recoupé avec
`language_vowel_sets.py`.

## 4. Tests

`tests/test_nasal_preproc.py` étendu (`TestP6Portuguese`) : diphtongue
nasale `k@~w` (chemin plateau, porte inerte), hiatus inter-mots
`@~.e` / `@.u~` (oralisation + capture), plateau final `@tu~` inchangé,
inertie sur échantillons es/it/de/en normalisés moteur. 38/38 verts.

## 5. Harnais

`run_corpus.py` paramétré : `--lang` (Pipeline + dossier résultats
`results_<lang>`, le fr reste dans `results/`), `--corpus` (fichier JSON
dédié), `--no-preproc` (porte neutralisée — preuve d'inertie /
avant-après par item).
