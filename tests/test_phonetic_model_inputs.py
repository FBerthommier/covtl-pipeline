# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Couverture du moteur par les entrées PHONÉTIQUES d'origine du modèle.

Corpus issu de la notation historique COVTL (cf. Timit-to-Maeda legacy
et la sémantique contrôlée par covtl-lambda) :

  - syllabes de toutes catégories : CV, CCV, VCV, VC.CV, CVC, CCVC…
  - séparateurs : espace (GAP inter-mots), ``|`` (pause longue),
    ``%`` (breath), ``.`` (séparateur de syllabe — C.C split,
    V.C/C.V/V.V merge), ``-`` (alias de ``.``)
  - clusters tautosyllabiques CC vs splits C.C (covtl-lambda : le dot
    désactive le flag cluster et les règles de cible cluster)
  - séquences longues CCCC→C.CCC et VVV→V.VV (règle schwa du
    timit_adapter, réimplémentée par ``_limit_long_sequences`` ; le
    DOT vocalique inséré est ensuite mergé par la règle V.V)
  - formes batch (``build_batch_tract``) reproduisant des phrases
    TIMIT du legacy (timit_ready.txt)

Chaque test valide : shapes finies, cohérence de la structure syllabique
(contre la sémantique covtl-lambda) et exécution sans erreur des deux
entrées du moteur (syltraj bas niveau + build_phrase_tract E2E).
"""
import re

import numpy as np
import pytest

from vtl_synth.core import syltraj
from vtl_synth.core.build_phrase_tract import build_phrase_tract, build_batch_tract
from vtl_synth.core.syltraj import tokenize_phrase, build_flat, build_nodes

TC = TV = 16  # pas de geste du harnais d'audit (rapide)


def _clusters_of(nodes):
    return [(nodes[i].key, nodes[i + 1].key) for i in range(len(nodes) - 1)
            if nodes[i].kind == 'C' and nodes[i + 1].kind == 'C'
            and getattr(nodes[i], 'in_cluster', False)]


def _nodes_of(phrase):
    """Même chaîne de normalisation que covtl-lambda plan_target_cluster."""
    from vtl_synth.core.syltraj import _normalize_word
    from vtl_synth.core.text_to_tract import _normalize_ipa
    ipa = _normalize_ipa(_normalize_word(phrase.strip()))
    flat, syllables, syl_bounds, boundary_info, word_starts = \
        syltraj.build_flat(ipa)
    return syltraj.build_nodes(flat, syllables, syl_bounds,
                               boundary_info, word_starts), syllables


# ----------------------------------------------------------------------
# 1. Catégories syllabiques élémentaires
# ----------------------------------------------------------------------

SYL_CATEGORIES = [
    # (forme, catégorie attendue)
    ('ba', 'CV'),
    ('pla', 'CCV'),
    ('sprü', 'CCCV'),
    ('aba', 'VCV'),
    ('ab', 'VC'),
    ('abba', 'VCCV'),          # cluster bb tautosyllabique
    ('ab.ba', 'VC.CV'),        # split C.C → 2 syllabes
    ('bab', 'CVC'),
    ('blab', 'CCVC'),
    ('plan', 'CCVC'),
    ('a', 'V'),
    ('aiu', 'VVV'),
    ('bla bra', 'CCV CCV'),
    ('tSa dZa', 'affriquées multi-caractères'),
    ('g_pal g_vel', 'alias velaire/palatal'),
]


@pytest.mark.parametrize('phrase,cat', SYL_CATEGORIES)
def test_syllable_category_builds(phrase, cat):
    """Chaque catégorie syllabique produit un Pval fini et non vide."""
    Pval, env, Vt, blocks = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert Pval.shape[0] > 0 and Pval.shape[1] == 15
    assert np.isfinite(Pval).all(), cat
    # env/blocks : liste de SylBlock ; Vt : liste de timers
    assert isinstance(env, list) and len(env) > 0, cat
    assert isinstance(blocks, list) and len(blocks) > 0, cat


# ----------------------------------------------------------------------
# 2. Séparateurs : espace, |, %, ., -
# ----------------------------------------------------------------------

@pytest.mark.parametrize('phrase,seps', [
    ('bi ba', ['GAP']),
    ('bi ba da', ['GAP', 'GAP']),
    ('bi | ba', ['GAP', 'PAUSE', 'GAP']),
    ('bi % ba', ['BREATH']),
    ('bi.ba', ['DOT']),         # le dot est un token à part entière
    # Recommandation vague 2 (écart documenté, décision mainteneur —
    # LEGACY.md §1bis) : '-' est préservé par notation.normalize_text
    # mais silencieusement consommé par la tokenisation syltraj (seul
    # '.' émet un DOT) — contrairement au parsing.py V1 qui traitait
    # '-' comme alias de '.'. Ce test verrouille le comportement
    # ACTUEL : si le mainteneur aligne le tiret sur le point, il
    # échouera et rappellera de mettre à jour la documentation.
    ('bi-ba', []),
    ('bi. ba', ['DOT', 'GAP']), # dot en fin de mot + espace
    ('bi .ba', ['GAP']),        # dot en début de mot : consommé par
                                # _normalize_word (normalisation)
])
def test_separators_tokenize(phrase, seps):
    """Espace→GAP, |→PAUSE (GAP conservés), %→BREATH, .→DOT, -→consommé."""
    toks = [t for t in tokenize_phrase(phrase) if not isinstance(t, tuple)]
    assert toks == seps, (phrase, toks)


@pytest.mark.parametrize('phrase', [
    'bi | ba',
    'bi | ba | da | ga',
    'bi % ba % da',
    'ba da ga | pa ta ka',
    'a | i | u',
])
def test_pauses_build(phrase):
    Pval, _, _, _ = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert np.isfinite(Pval).all() and Pval.shape[0] > 0


# ----------------------------------------------------------------------
# 3. Concaténation '.' : sémantique C.C / CC (contrôle covtl-lambda)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('dotted', ['klin.pan', 'min.bot', 'ab.ba', 'big.bi'])
def test_dotted_forms_disable_the_dotted_cluster(dotted):
    """C.C = split : le dot désactive le flag cluster pour la PAIRE
    pointée (covtl-lambda) — les autres clusters du mot restent légitimes."""
    nodes, syls = _nodes_of(dotted)
    # la paire autour du dot n'est PAS un cluster : au moins 2 syllabes
    assert any(len(w) > 1 for w in syls), (dotted, syls)


@pytest.mark.parametrize('plain,cluster', [
    ('klinpan', ('n', 'p')),
    ('minbot', ('n', 'b')),
    ('abba', ('b', 'b')),
    ('bigbi', ('g', 'b')),
])
def test_plain_forms_have_cluster(plain, cluster):
    """Sans dot : CC = cluster tautosyllabique (règles cluster actives)."""
    nodes, _ = _nodes_of(plain)
    assert cluster in _clusters_of(nodes), (plain, _clusters_of(nodes))


@pytest.mark.parametrize('phrase,syls_expect', [
    ('ab.ba', [[['a', 'b'], ['b', 'a']]]),
    ('big.bi', [[['b', 'i', 'g'], ['b', 'i']]]),
    ('bi.ba', [[['b', 'i', 'b', 'a']]]),      # V.C → merge
    ('abda', [[['a', 'b', 'd', 'a']]]),        # CC sans dot
])
def test_dot_split_merge_rules(phrase, syls_expect):
    """C.C → split ; V.C / C.V / V.V → merge (règle _should_split_at_dot)."""
    _, syls = _nodes_of(phrase)
    assert syls == syls_expect, (phrase, syls)


@pytest.mark.parametrize('phrase,nasal_cluster', [
    ('klinpan', ('n', 'p')),
    ('klinkan', ('n', 'k')),
    ('minbot', ('n', 'b')),
    ('Tinpakit', ('n', 'p')),
    ('klintan', ('n', 't')),
    ('mingot', ('n', 'g')),
])
def test_pouw_cluster_pairs(phrase, nasal_cluster):
    """Les paires CC des frames de Pouw (covtl-lambda) : 1 cluster nasal
    C1C2, et le dot le désactive."""
    nodes, _ = _nodes_of(phrase)
    cands = [(nodes[i].key, nodes[i + 1].key)
             for i in range(len(nodes) - 1)
             if nodes[i].kind == 'C' and nodes[i + 1].kind == 'C'
             and getattr(nodes[i], 'in_cluster', False)
             and nodes[i].key in 'mnN']
    assert cands == [nasal_cluster], (phrase, cands)


@pytest.mark.parametrize('dotted', ['klin.pan', 'min.bot'])
def test_dotted_pouw_forms_have_no_nasal_cluster(dotted):
    """covtl-lambda test_dotted_phrases_are_not_clusters : zéro cluster
    nasal dans les formes pointées."""
    nodes, _ = _nodes_of(dotted)
    cands = [(nodes[i].key, nodes[i + 1].key)
             for i in range(len(nodes) - 1)
             if nodes[i].kind == 'C' and nodes[i + 1].kind == 'C'
             and getattr(nodes[i], 'in_cluster', False)
             and nodes[i].key in 'mnN']
    assert cands == [], (dotted, cands)


def test_cluster_target_rules():
    """n cluster → cible stop alvéolaire (ρ 1.15, θ 3π/2) — covtl-lambda."""
    nodes, _ = _nodes_of('klinpan')
    n_cl = next(n for n in nodes if n.kind == 'C' and n.key == 'n'
                and getattr(n, 'in_cluster', False))
    assert n_cl.rho == pytest.approx(1.15)
    assert n_cl.theta == pytest.approx(3 * np.pi / 2)
    # hors cluster (klin.pan) : cible nasale standard, différente
    nodes2, _ = _nodes_of('klin.pan')
    n_free = next(n for n in nodes2 if n.kind == 'C' and n.key == 'n')
    assert n_free.rho != pytest.approx(1.15)


# ----------------------------------------------------------------------
# 4. Règle schwa du timit_adapter (séquences longues)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('phrase', [
    'Ekstr',       # kstR = 4 cons → DOT après k
    'abstRakt',    # bstR = 4 cons
    'ekstRakt',    # kstR = 4 cons
])
def test_long_consonant_sequences_get_schwa_split(phrase):
    """4+ C → C.CCC (règle timit_adapter) : le mot est scindé en 2
    syllabes par le DOT inséré (split C.C)."""
    from vtl_synth.core.syltraj import _limit_long_sequences
    toks = [t for t in tokenize_phrase(phrase) if t != 'GAP']
    lim = _limit_long_sequences(toks)
    assert 'DOT' in lim, phrase
    flat, syls, _, _, _ = build_flat(phrase)
    assert len(syls[0]) == 2, (phrase, syls)


def test_long_vowel_sequence_dot_is_merged():
    """3+ V → V.VV : le DOT est inséré puis MERGÉ par la règle V.V
    (la séquence vocalique reste une seule syllabe — comportement
    du moteur, cohérent avec _should_split_at_dot)."""
    from vtl_synth.core.syltraj import _limit_long_sequences
    toks = [t for t in tokenize_phrase('aaaa') if t != 'GAP']
    lim = _limit_long_sequences(toks)
    assert 'DOT' in lim
    flat, syls, _, _, _ = build_flat('aaaa')
    assert syls == [[['a', 'a', 'a', 'a']]]


def test_short_sequences_untouched():
    """3 cons ou 2 voyelles : pas de DOT (seuils 4+/3+)."""
    from vtl_synth.core.syltraj import _limit_long_sequences
    for w in ('splintE', 'tekst', 'strEts'):   # max CCC / CC
        toks = [t for t in tokenize_phrase(w) if t != 'GAP']
        lim = _limit_long_sequences(toks)
        assert 'DOT' not in lim, (w, lim)
    toks = [t for t in tokenize_phrase('aa') if t != 'GAP']
    assert 'DOT' not in _limit_long_sequences(toks)


def test_isolated_consonant_gets_schwa():
    """Mot sans voyelle avant pause → schwa @ (règle build_flat)."""
    flat, syls, _, _, _ = build_flat('b |')
    keys = [t[1] for t in flat if isinstance(t, tuple)]
    assert '@' in keys, (flat, syls)


@pytest.mark.parametrize('phrase', [
    'abstRakt',
    'ekstRakt',
    'aaaa',
    'baaa da',
])
def test_long_sequences_build(phrase):
    """Les formes à séquences longues synthétisent sans erreur."""
    Pval, _, _, _ = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert np.isfinite(Pval).all() and Pval.shape[0] > 0


# ----------------------------------------------------------------------
# 5. Entrées TIMIT du legacy (notation d'origine, é/è normalisés)
# ---------------------------------------------------------------------------

TIMIT_PHRASES = [
    # (timit_ready.txt, notation d'origine conservée — é/è sont
    #  normalisés par le moteur en e/E)
    'zis.waz.izi.fOr.as',
    'Si.iz.sinE.zEn.a.Em',
    'brat.sanSan.SimEz.an.za.oSan',
    'nasin.iz.Ez.afEnsiv.Ez.inasans',
    'wa.jEl.Or.wEi.ovE.sili.atamz',
    'swin.jOr.arm.Ez.fa.Ez.ju.kEn',
    'rimuv.za.splintE.wiz.a.pEr.av.twizEz',
    'za.drankEd.iz.a.soSal.atkEst',
    'a.fjuZ.tEpastri.fan.in.fE.fOlwE',
    'fiz.sadan.diparSE.Sakt.za.kEst',
    'klEsp.za.skru.in.jOr.lEft.fEnd',
    'trEspEsin.iz.fOrbidan.and.sabZEkt.tu.pEnalti',
    'artafiSal.intEl.aZans.iz.fOr.ril',
    'saantifik.pragrEs.kamz.fram.za.divElapmant.av.nu.tEkniks',
    'maskitoz.igzist.in.wOrm.fjumad.klamats',
]


@pytest.mark.parametrize('phrase', TIMIT_PHRASES)
def test_timit_legacy_phrases_build(phrase):
    """Les phrases TIMIT du legacy (timit_ready.txt) synthétisent sans erreur."""
    Pval, _, _, _ = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert np.isfinite(Pval).all() and Pval.shape[0] > 20


TIMIT_E2E = [
    'zis.waz.izi.fOr.as',
    'rimuv.za.splintE.wiz.a.pEr.av.twizEz',
    'klEsp.za.skru.in.jOr.lEft.fEnd',
]


@pytest.mark.parametrize('phrase', TIMIT_E2E)
def test_timit_legacy_e2e(phrase):
    """E2E : build_phrase_tract sur des phrases TIMIT du legacy."""
    tract, glottis = build_phrase_tract(
        phrase, phrase_id=None, label='timit', return_data=True, verbose=False)
    assert np.isfinite(tract).all() and np.isfinite(glottis).all()
    assert tract.shape[0] == glottis.shape[0]


# ----------------------------------------------------------------------
# 6. Mode batch : reproduction des phrases TIMIT (build_batch_tract)
# ---------------------------------------------------------------------------

def test_batch_timit_block():
    """Un bloc TIMIT (5 phrases) via build_batch_tract — mode batch du
    legacy timit_adapter (blocs de 5 séparés par |)."""
    block = [
        ('zis.waz.izi.fOr.as', 't1'),
        ('Si.iz.sinE.zEn.a.Em', 't2'),
        ('brat.sanSan.SimEz.an.za.oSan', 't3'),
        ('nasin.iz.Ez.afEnsiv.Ez.inasans', 't4'),
        ('wa.jEl.Or.wEi.ovE.sili.atamz', 't5'),
    ]
    results = build_batch_tract(block, **{'t_cons': 60, 't_voy': 60})
    assert set(results) == {'t1', 't2', 't3', 't4', 't5'}
    for label, (tract, glottis) in results.items():
        assert np.isfinite(tract).all(), label
        assert np.isfinite(glottis).all(), label
        assert tract.shape[0] == glottis.shape[0], label


def test_batch_timit_auto_labels():
    """Batch en labels automatiques (str simples, pas de tuples)."""
    phrases = ['ba di gu', 'pra kli spra', 'ba | da']
    results = build_batch_tract(phrases)
    assert len(results) == 3
    for tract, glottis in results.values():
        assert np.isfinite(tract).all()
        assert np.isfinite(glottis).all()


def test_batch_load_sanitize_label_uniqueness():
    """Test de charge batch (recommandation vague 2 §5.4) : un bloc
    TIMIT de 5 phrases + contrôle de _sanitize_label.

    Verrouille la fonction interne _sanitize_label : deux labels ne
    doivent JAMAIS collisionner après sanitation (sinon
    build_batch_tract écraserait silencieusement une entrée du dict
    de résultats), et la sanitation doit bien remplacer les
    caractères non mot par '_', compresser les underscore multiples
    et retirer les bords.
    """
    from vtl_synth.core.build_phrase_tract import _sanitize_label

    # unité : comportement de _sanitize_label sur les cas limites
    assert _sanitize_label('zis waz') == 'zis_waz'
    assert _sanitize_label('a  b__c!') == 'a_b_c'
    assert _sanitize_label('__x__') == 'x'
    assert _sanitize_label('é-è|à') == 'é-è_à'   # \w garde les accents
    assert _sanitize_label('') == ''

    # charge : bloc legacy de 5 phrases réelles + labels qui diffèrent
    # uniquement par des caractères que la sanitation remplace
    block = [
        ('zis.waz.izi.fOr.as', 'block one'),
        ('Si.iz.sinE.zEn.a.Em', 'block:two'),
        ('brat.sanSan.SimEz.an.za.oSan', 'block three'),
        ('nasin.iz.Ez.afEnsiv.Ez.inasans', 'BLOCK-FOUR'),
        ('wa.jEl.Or.wEi.ovE.sili.atamz', 'block five'),
    ]
    sanitized = [_sanitize_label(lbl) for _, lbl in block]
    # aucune collision : 5 labels distincts restent 5 clés distinctes
    assert len(set(sanitized)) == len(sanitized), sanitized
    # aucun résidu de caractère non mot
    for s in sanitized:
        assert re.fullmatch(r'[\w\-]+', s), s

    results = build_batch_tract(block, **{'t_cons': 60, 't_voy': 60})
    # 5 phrases → 5 clés distinctes → aucun écrasement silencieux
    assert len(results) == 5
    assert set(results) == set(sanitized)
    for label, (tract, glottis) in results.items():
        assert np.isfinite(tract).all(), label
        assert tract.shape[0] == glottis.shape[0], label


def test_batch_timit_pause_block():
    """Bloc legacy complet avec pauses longues '|' entre phrases (format
    timit_ready.txt : '1: | p1 | p2 | p3 | p4 | p5 |')."""
    phrase = ' | '.join([
        'zis.waz.izi.fOr.as',
        'Si.iz.sinE.zEn.a.Em',
        'brat.sanSan.SimEz.an.za.oSan',
    ])
    Pval, _, _, _ = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert np.isfinite(Pval).all() and Pval.shape[0] > 100


# ----------------------------------------------------------------------
# 7. Formes mixtes exhaustives (croisement séparateurs × catégories)
# ---------------------------------------------------------------------------

MIXED = [
    'pra kli spra spla',              # CCV×4 via espaces
    'pra.kli | spra.spla',            # CCV pointés + pause
    'ab.pra ab.pra',                  # VC.CV avec attaque CCV
    'bla | bra % bla',                # pause + breath mélangés
    'pra.ba da.ga',                   # dots + espaces
    'abstRakt | splintE % a',
    'klinpan | klin.pan',             # cluster vs split dans UNE phrase
    'bi.ba bi-ba bi.ba',              # '.' et '-' mélangés
    'a | e | i | o | u | y | 2 | 9',  # toutes les voyelles en pause
    'tSa dZa g_pal g_vel',            # multi-caractères
    '| ba',                           # pause INITIALE (anchor synth→pause)
    '| ba | ba',                      # pauses initiale + médiane
    '| ab ba',                        # pause initiale + attaque CC
    'ba | spra',                      # pause puis attaque CCC
    'abst |',                         # cluster consonantique final
    'klin | pan',                     # mot-C devant pause (word-end anchor)
]


@pytest.mark.parametrize('phrase', MIXED)
def test_mixed_separator_forms(phrase):
    Pval, _, _, _ = syltraj.build_phrase_pval(
        phrase, t_cons=TC, t_voy=TV, sampa_guard='off')
    assert np.isfinite(Pval).all() and Pval.shape[0] > 0
