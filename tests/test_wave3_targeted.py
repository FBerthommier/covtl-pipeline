# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Tests ciblés vague 3 — lignes manquantes des 4 modules moteurs.

Chaque test documente la LIGNE exacte qu'il active (numéros au HEAD
3903645, état vague 2) et la raison :

  - syltraj.py (45 lignes → 13 activables) : variantes d'arc_B
    (D=0, opint -1/else), preprocess_phrase (API publique zéro
    appelant), fallback _c_target, _append_plateau.
  - build_phrase_tract.py (63 lignes) : phrase sans segments
    (ValueError), engine='legacy' (V1 : blocs kind='pause' →
    silencage background l.675, pulmonary aligné l.793 sur
    'b o Z u R', timer désaligné l.803 sur 'bi | ba'), hiatus nasal
    verbose ('ãa' → l.561 + VO l.899), speaker_file absent (l.969)
    ou corrompu (l.965-967), chemin d'écriture sans return_data
    (l.1088).
  - enveloppe.py (123 lignes) : la branche B (TimedEnvelope) via la
    voie V1 réelle — parse_to_segments → TagInterpreter → anchors →
    TimedEnvelope (schedule_from_anchors couvre
    _make_voicing_events/_make_phonation_mode_events), breathy via
    glottal_tag level C, add_vot_override, envelope_from_anchors
    (l'E de la branche B — écrasé par E_100 à la jonction
    build_phrase_tract l.751, cf. analyse croisée vague 3).
  - continuous.py (65 lignes) : chaîne V1 — parse_ipa_with_markers
    (List[ParseToken]), syllabify_continuous (onsets valides :
    _is_valid_onset(['s','t','R']) vrai, ['s','t'] faux),
    _chain_elements_to_pval, _extract_rho_from_anchors,
    _update_structure_type.

Découvertes structurelles (rapport vague 3, non couvertes à dessein) :
  - 5 lignes syltraj défensives (617, 660, 677, 689, 741) : le schwa
    inséré avant pause garantit un V dans les scans d'anchors ; la
    règle C.C ne produit jamais d'onset vocalique de syllabe.
  - build_phrase_tract 657-659 (interpolation E) : défensif,
    env_highres == n_steps*sps par construction.
  - build_phrase_tract 733/747-748 : extensions vides — non produites
    par TimedEnvelope.
"""
import contextlib
import io
import warnings as _w

import numpy as np
import pytest

from vtl_synth.core import syltraj
from vtl_synth.core.syltraj import (
    arc_B,
    _c_target,
    _append_plateau,
    preprocess_phrase,
)
from vtl_synth.core.build_phrase_tract import build_phrase_tract

TC = TV = 16


# ----------------------------------------------------------------------
# 1. syltraj — variantes d'arc et helpers (13 lignes)
# ----------------------------------------------------------------------

def test_arc_b_zero_steps():
    """l.204 : arc_B avec D=0 → matrice vide (0, N)."""
    z = arc_B([1.0, 0.0], [1.2, 0.5], list(range(15)), 0,
              [-np.pi, 0], 0, 2, 2.0, 2)
    assert z.shape == (0, 15)


def test_arc_b_opint_variants():
    """l.207-209 (opint=-1, points intérieurs) et l.211 (else :
    linspace direct, tout opint non nul non -1)."""
    a1 = arc_B([1.0, 0.0], [1.2, 0.5], list(range(15)), 5,
               [-np.pi, 0], -1, 2, 2.0, 2)
    a2 = arc_B([1.0, 0.0], [1.2, 0.5], list(range(15)), 5,
               [-np.pi, 0], 1, 2, 2.0, 2)
    for a in (a1, a2):
        assert a.shape == (5, 15)
        assert np.isfinite(a).all()
    # opint=0 (déjà couvert par la suite) vs les variantes : les
    # trajectoires diffèrent (échantillonnage theta différent)
    a0 = arc_B([1.0, 0.0], [1.2, 0.5], list(range(15)), 5,
               [-np.pi, 0], 0, 2, 2.0, 2)
    assert not np.allclose(a0, a1)


def test_preprocess_phrase_public_api():
    """l.261-265 : preprocess_phrase — normalisation + caractères
    ignorés (API publique documentée, zéro appelant interne).

    Wave 4 fix (COVERAGE_REPORT.md wave 3 §4.6-1, §7.1) :
    notation.ALL_K now derives from constants.ALL_PHONEME_KEYS, so
    the voiceless consonants (S, T, f, k, p, s, t) are recognized —
    no more false 'ignored characters' for phrases like 'klinpan'
    while the tokenizer synthesizes them."""
    normalized, ignored = preprocess_phrase('ba da é x')
    assert normalized == 'ba da e x'
    assert ignored == ['x']
    # the 7 previously missing consonants are now recognized
    normalized, ignored = preprocess_phrase('klinpan')
    assert normalized == 'klinpan'
    assert ignored == []
    normalized, ignored = preprocess_phrase('stra ka pa fjuZ')
    assert ignored == []


def test_c_target_unknown_key_fallback():
    """l.487 : consonne hors table → fallback neutre (1.1, π)."""
    rho, theta = _c_target('zz', 0.0)
    assert rho == pytest.approx(1.1)
    assert theta == pytest.approx(np.pi)
    # une vraie consonne passe par la projection (valeur distincte)
    rho2, theta2 = _c_target('b', 0.0)
    assert (rho2, theta2) != (1.1, np.pi)


def test_append_plateau_helper():
    """l.725-726 : _append_plateau — tuile compute_P et enregistre le
    bloc plateau."""
    blocks, binfo = [], []
    _append_plateau(blocks, binfo, [1.0, 0.0], 4)
    assert blocks[0].shape == (4, 15)
    assert binfo[0].kind == 'plateau' and binfo[0].n_steps == 4


# ----------------------------------------------------------------------
# 2. build_phrase_tract — chemins d'erreur, V1, hiatus, speaker
# ----------------------------------------------------------------------

def test_empty_phrase_raises_value_error():
    """l.492 : phrase sans segments phonémiques → ValueError explicite."""
    with pytest.raises(ValueError, match='No phonemic segments'):
        build_phrase_tract('| | |', return_data=True, verbose=False)


def test_legacy_engine_deprecation_and_pause_blocks():
    """engine='legacy' (l.565-577) : DeprecationWarning + chaîne V1.
    Le chemin V1 produit des blocs kind='pause' (trajectory.py l.510)
    → active le silencage des backgrounds après pause (l.675), absent
    du chemin syl (kinds initial/terminal uniquement)."""
    with pytest.warns(DeprecationWarning, match="engine='legacy'"):
        tract, glottis = build_phrase_tract(
            'ba da', engine='legacy', return_data=True, verbose=False)
    assert np.isfinite(tract).all()
    assert tract.shape[0] == glottis.shape[0]


def test_legacy_engine_pulmonary_aligned():
    """l.793-799 : pulmonary effort synthétisé quand les marks V1
    s'alignent sur la trajectoire (phrase 'b o Z u R' — l'exemple du
    CLI du module)."""
    with pytest.warns(DeprecationWarning):
        with contextlib.redirect_stdout(io.StringIO()):
            tract, glottis = build_phrase_tract(
                'b o Z u R', engine='legacy', return_data=True, verbose=True)
    assert np.isfinite(tract).all()
    assert tract.shape[0] == glottis.shape[0]


def test_legacy_engine_misaligned_timer_verbose():
    """l.802-803 : verbose + timer désaligné (phrase V1 multi-pause)."""
    with pytest.warns(DeprecationWarning):
        with contextlib.redirect_stdout(io.StringIO()):
            tract, glottis = build_phrase_tract(
                'bi | ba', engine='legacy', return_data=True, verbose=True)
    assert np.isfinite(tract).all()


def test_nasal_hiatus_verbose_plan():
    """l.561 + l.899-900 : hiatus nasal ('ãa' → moteur 'aa' + 1 event
    de nasalité) en verbose — trace du plan et des VO orthogonaux."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tract, glottis = build_phrase_tract(
            'ãa', return_data=True, verbose=True)
    assert np.isfinite(tract).all()
    log = out.getvalue()
    assert 'nasal_preproc' in log and 'nasality event' in log
    assert 'orthogonal VO' in log


def test_speaker_file_not_found_verbose():
    """l.969 : speaker_file inexistant + verbose → trace 'file not
    found', la synthèse continue sans branche orthogonale."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tract, glottis = build_phrase_tract(
            'ba', speaker_file='/tmp/inexistant_xyz.speaker',
            return_data=True, verbose=True)
    assert np.isfinite(tract).all()
    assert 'file not found' in out.getvalue()


def test_speaker_file_corrupted_orthobranch_abort():
    """l.965-967 : fichier speaker corrompu → OrthogonalBranch avorte
    proprement (exception attrapée, trace verbose)."""
    import pathlib
    bad = pathlib.Path('/tmp/vtl_synth_bad_speaker.speaker')
    bad.write_text("CECI N'EST PAS UN FICHIER SPEAKER VALIDE", encoding='utf-8')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tract, glottis = build_phrase_tract(
            'ba', speaker_file=str(bad), return_data=True, verbose=True)
    assert np.isfinite(tract).all()
    assert 'OrthogonalBranch aborted' in out.getvalue()
    bad.unlink()


def test_write_path_returns_none(tmp_path):
    """l.1088 : sans return_data, la fonction écrit le .tract et
    retourne None."""
    result = build_phrase_tract('ba', output_dir=str(tmp_path),
                                verbose=False)
    assert result is None
    files = list(tmp_path.rglob('*.tract'))
    assert len(files) == 1


# ----------------------------------------------------------------------
# 3. enveloppe.py — branche B (TimedEnvelope) via la voie V1 réelle
# ----------------------------------------------------------------------

def _v1_segments(phrase='ba da'):
    """segments + chain_elements + anchors par la voie V1 réelle
    (celle de build_phrase_tract engine='legacy')."""
    from vtl_synth.core.continuous import parse_to_segments
    from vtl_synth.core.tag_system import TagInterpreter
    from vtl_synth.core.enveloppe import chain_elements_to_anchors
    segments, chain = parse_to_segments(phrase, sampa_guard='off')
    segments = TagInterpreter().apply_all(segments)
    anchors = chain_elements_to_anchors(chain)
    return segments, chain, anchors


def test_timed_envelope_v1_extensions():
    """TimedEnvelope sur les anchors V1 : schedule_from_anchors couvre
    _make_voicing_events (l.523-528) et _make_phonation_mode_events
    (l.721-802 via le chemin des événements), get_all_extensions
    produit E/VO/VS/V/f0/glottis/aspiration finis."""
    segments, chain, anchors = _v1_segments('ba da ga')
    from vtl_synth.core.enveloppe import TimedEnvelope
    env = TimedEnvelope(anchors=anchors)
    ext = env.get_all_extensions()
    for key in ('E', 'VO', 'VS', 'V', 'f0', 'aspiration'):
        assert key in ext, key
        assert np.isfinite(np.asarray(ext[key], dtype=float)).all(), key
    g = np.asarray(ext['glottis'])
    assert g.shape[1] == 11 and np.isfinite(g).all()


def test_timed_envelope_breathy_phonation_mode():
    """_make_phonation_mode_events (l.721-802) : glottal_tag='breathy'
    (level C du TagInterpreter) sur un segment → mode de phonation
    non modal planifié."""
    segments, chain, anchors = _v1_segments('ba')
    # level C : override direct du tag glottal du premier segment
    voiced = [s for s in segments if getattr(s, 'is_voiced', False)]
    target = voiced[0] if voiced else segments[0]
    target.glottal_tag = 'breathy'
    from vtl_synth.core.enveloppe import TimedEnvelope
    env = TimedEnvelope(anchors=anchors)
    ext = env.get_all_extensions()
    g = np.asarray(ext['glottis'])
    assert g.shape[1] == 11 and np.isfinite(g).all()


def test_timed_envelope_add_vot_override():
    """add_vot_override (l.1625-1635) : override du VOT par phonème —
    l'exemple de la docstring du module (te2.add_vot_override)."""
    segments, chain, anchors = _v1_segments('ba da')
    from vtl_synth.core.enveloppe import TimedEnvelope
    env = TimedEnvelope(anchors=anchors)
    env.add_vot_override('t', 60.0)
    ext = env.get_all_extensions()
    assert np.isfinite(np.asarray(ext['V'], dtype=float)).all()


def test_create_timed_envelope_from_segments_v1():
    """create_timed_envelope_from_segments (l.1684-1744) : fabrique
    V1 d'un TimedEnvelope depuis les segments (parse_to_segments +
    TagInterpreter)."""
    from vtl_synth.core.enveloppe import create_timed_envelope_from_segments
    segments, _, _ = _v1_segments('ba da')
    env = create_timed_envelope_from_segments(segments)
    ext = env.get_all_extensions()
    for key in ('E', 'VO', 'VS', 'V', 'f0'):
        assert key in ext, key
        assert np.isfinite(np.asarray(ext[key], dtype=float)).all(), key


def test_envelope_from_anchors_syllabic_curve():
    """envelope_from_anchors (l.926-956) : E(t) syllabique indexée par
    les anchors V_o/V/V_e — montée, plateau à 1, chute.
    NB analyse vague 3 : cette E de la branche B est ÉCRASÉE par
    E_100 (amplitude_envelope, branche A) à la jonction
    build_phrase_tract l.751 — le test verrouille la fonction comme
    API indépendante, pas comme sortie moteur."""
    from vtl_synth.core.enveloppe import envelope_from_anchors
    segments, chain, anchors = _v1_segments('ba da')
    t_ms = np.linspace(0.0, 800.0, 800)
    E = envelope_from_anchors(t_ms, anchors, chain_elements=chain)
    assert E.shape == t_ms.shape
    assert np.isfinite(E).all()
    assert E.min() >= 0.0
    assert E.max() == pytest.approx(1.0, abs=0.1)


def test_envelope_from_anchors_empty():
    """l.926 : anchors vide → E nul partout (garde d'entrée)."""
    from vtl_synth.core.enveloppe import envelope_from_anchors
    t_ms = np.linspace(0.0, 100.0, 50)
    E = envelope_from_anchors(t_ms, [])
    assert E.shape == t_ms.shape and np.all(E == 0.0)


# ----------------------------------------------------------------------
# 4. continuous.py — chaîne V1 (parse, syllabification, Pval)
# ----------------------------------------------------------------------

def test_parse_ipa_with_markers_tokens():
    """parse_ipa_with_markers (l.355+) : entrée à espaces du CLI V1
    ('b o Z u R' — exemple de la doc build_phrase_tract) → liste de
    ParseToken."""
    from vtl_synth.core.continuous import parse_ipa_with_markers
    toks = parse_ipa_with_markers('b o Z u R', sampa_guard='off')
    assert isinstance(toks, list) and len(toks) >= 5
    keys = [t.key for t in toks if hasattr(t, 'key')]
    assert 'b' in keys and 'Z' in keys and 'R' in keys


def test_syllabify_continuous_onsets():
    """syllabify_continuous (l.892+) : ParseTokens → ChainElements ;
    les onsets sont validés par _is_valid_onset (['s','t','R'] oui,
    ['s','t'] non : 'str' est un onset à 3, 'st' seul est rejeté)."""
    from vtl_synth.core.continuous import (
        parse_ipa_with_markers, syllabify_continuous, _is_valid_onset,
    )
    assert _is_valid_onset(['s', 't', 'R']) is True
    assert _is_valid_onset(['s', 't']) is False
    assert _is_valid_onset(['b', 'l']) is True
    toks = parse_ipa_with_markers('ba da', sampa_guard='off')
    syls = syllabify_continuous(toks)
    assert len(syls) >= 3          # 2 syllabes + pauses
    kinds = {s.element_type for s in syls}
    assert 'syllable' in str(kinds).lower() or any(
        not s.is_pause for s in syls)
    non_pause = [s for s in syls if not s.is_pause]
    assert all(hasattr(s, 'nucleus_key') for s in non_pause)


def test_chain_elements_to_pval_v1():
    """_chain_elements_to_pval (l.135+) : Pval V1 depuis les chain
    elements — le B(t) du moteur legacy (parse_to_tract_trajectory
    s'appuie dessus). Retour (Pval, rho_theta, block_info)."""
    from vtl_synth.core.continuous import (
        parse_to_segments, _chain_elements_to_pval,
    )
    _, chain = parse_to_segments('ba da', sampa_guard='off')
    Pval, rho_theta, blocks = _chain_elements_to_pval(chain)
    assert Pval.ndim == 2 and Pval.shape[1] == 15
    assert np.isfinite(Pval).all()
    assert np.asarray(rho_theta).shape[1] == 2
    assert np.isfinite(np.asarray(rho_theta, dtype=float)).all()
    assert isinstance(blocks, list) and len(blocks) > 0


def test_extract_rho_from_anchors_v1():
    """_extract_rho_from_anchors (l.119+) : trajectoire (rho, theta)(t)
    depuis les anchors V1 (n_frames explicit, retour (N, 2))."""
    from vtl_synth.core.continuous import (
        parse_to_segments, _extract_rho_from_anchors,
    )
    from vtl_synth.core.enveloppe import chain_elements_to_anchors
    _, chain = parse_to_segments('ba da', sampa_guard='off')
    anchors = chain_elements_to_anchors(chain)
    rho_theta = _extract_rho_from_anchors(anchors, 200)
    assert rho_theta.shape == (200, 2)
    assert np.isfinite(rho_theta).all()


def test_update_structure_type():
    """_update_structure_type : classification de la structure de
    syllabe (CV, CVC, V…) d'un ChainElement."""
    from vtl_synth.core.continuous import (
        parse_ipa_with_markers, syllabify_continuous, _update_structure_type,
    )
    toks = parse_ipa_with_markers('ba da', sampa_guard='off')
    syls = [s for s in syllabify_continuous(toks) if not s.is_pause]
    for s in syls:
        _update_structure_type(s)
    # 'ba' : onset [b], noyau a, coda [] → structure CV
    st = getattr(syls[0], 'structure_type', None)
    assert st is not None


def test_align_trajectories_pad_and_truncate():
    """_align_trajectories (l.237-268) : réalignement des 3 branches —
    padding à droite (l.237-254) quand une branche est plus courte,
    troncature (l.256-268) quand elle est plus longue, pour les
    extensions 1D et 2D comme pour la branche orthogonale."""
    from vtl_synth.core.build_phrase_tract import _align_trajectories
    # pad : tract 50 < 60, extensions 1D/2D courtes, ortho court
    tract = np.ones((50, 15))
    ext = {'E': np.ones(40), 'glottis': np.ones((40, 11))}
    ortho = {'TS3_ortho': np.ones(45), 'VS_ortho': np.ones((45, 3))}
    t, e, o = _align_trajectories(tract, ext, ortho, 60)
    assert t.shape == (60, 15)
    assert e['E'].shape == (60,) and e['glottis'].shape == (60, 11)
    # le pad est bien à zéro
    assert np.all(t[50:] == 0.0) and np.all(e['E'][40:] == 0.0)
    # troncation : tout plus long que la cible
    ext2 = {'E': np.ones(80), 'glottis': np.ones((80, 11))}
    ortho2 = {'TS3_ortho': np.ones(90)}
    t2, e2, o2 = _align_trajectories(np.ones((75, 15)), ext2, ortho2, 60)
    assert t2.shape == (60, 15) and e2['E'].shape == (60,)
    assert o2['TS3_ortho'].shape == (60,)


def test_parse_to_anchors_nominal():
    """parse_to_anchors (enveloppe.py) — wave 4 fix (COVERAGE_REPORT.md
    wave 3 §4.6-2, §7.1): the function called parse_ipa_with_markers
    with the stale keyword ``pause_marker=`` (renamed
    ``coarticulation_marker=``), so every call raised TypeError. The
    keyword is fixed; the nominal path now returns the V_o / C / V /
    V_e anchor chain per syllable."""
    from vtl_synth.core.enveloppe import parse_to_anchors
    anchors = parse_to_anchors('ba da')
    assert len(anchors) == 8
    labels = [a.label for a in anchors]
    assert labels == ['V_o', 'C_b', 'V', 'V_e',
                      'V_o', 'C_d', 'V', 'V_e']
    # anchors carry absolute times in chronological order
    ts = [a.t_ms for a in anchors]
    assert ts == sorted(ts)
    # single syllable
    anchors_ba = parse_to_anchors('ba')
    assert len(anchors_ba) == 4
