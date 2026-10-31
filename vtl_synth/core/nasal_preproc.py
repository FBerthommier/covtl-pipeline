# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
nasal_preproc.py — porte nasalité/formant (couche de pré-traitement V1V2)
=========================================================================
Factorisation orthogonalisée de la nasalité pour les hiatus V1.V2 liés
(audit V1V2 / AUDIT.md §6 — variante « non perturbatrice » prescrite pour
la correction moteur).

Principe
--------
1. L'élaboration de l'espace paramétrique par ``syltraj`` est laissée
   INTACTE. Elle est déjà construite sur la base orale : une voyelle
   nasale partage la cible polaire de sa contrepartie orale
   (``syltraj.build_nodes`` : ``base = key.rstrip('~')`` — la nasalité
   n'y intervient que comme drapeau). L'arc de fond du hiatus
   (``background``, 2·T_voy) EST la transition diphtongue de base.
2. La présente couche de pré-traitement oralise UNIQUEMENT les voyelles
   nasales membres d'un hiatus (séquence vocalique adjacente de
   longueur ≥ 2) : le moteur ``syltraj`` reçoit une chaîne purement
   orale pour ces positions, et la nasalité est capturée comme
   ÉVÉNEMENT (règle vocalique d'appartenance + cible orale).
3. La nasalité est réinjectée en aval dans l'espace orthogonal de
   commande du port vélaire qui existe déjà (extension ``VO`` de
   ``build_phrase_tract`` : cible ``VO_NASALIZED_VOWEL`` = 0.5, rampes
   symétriques 20 %) et façonnée par le timer associé existant
   (lissage anti-clic du premier ordre, τ = 20 ms). Aucun autre canal
   n'est modifié : F1..F3/paramètres tract, enveloppe E, voisement V,
   source glottique restent ceux de la chaîne orale.

Non-perturbation
----------------
* sans voyelle nasale en hiatus, la chaîne moteur est IDENTIQUE à
  l'entrée (aller-retour tokenizer vérifié, sinon repli conservateur)
  → sorties bit-identiques ;
* les voyelles nasales hors hiatus (plateaux tenus) conservent le
  chemin moteur existant (drapeau ``nasal`` des blocs ``plateau``) ;
* ``syltraj.py`` n'est pas modifié ; la régression éventuelle de la
  correspondance runs↔blocs est détectée et désactivée proprement
  (repli sur le comportement antérieur, avertissement).

Le schéma d'état module (``get_last_nasal_plan``) suit le pattern du
dépôt (``syltraj.get_last_build``, ``continuous.get_last_pval_state``).
"""
from __future__ import annotations

import warnings

import numpy as np

# ---------------------------------------------------------------------------
# État du dernier passage (pattern get_last_build)
# ---------------------------------------------------------------------------

_LAST_PLAN: dict | None = None


def get_last_nasal_plan():
    """Plan de la dernière exécution de :func:`split_nasal_hiatus`.

    dict(original=..., motor=..., nodes_view=..., runs=..., events=...,
         intervals=...) — ``nodes_view`` reflète la chaîne d'ORIGINE
     (drapeaux ``nasal`` vrais), contrairement aux nœuds de
     ``syltraj.get_last_build()`` qui voient la chaîne oralisée.
    ``intervals`` est rempli par ``build_phrase_tract`` au moment de la
    réinjection VO (list de (t0, t1, clés) en pas @100 Hz).
    """
    return _LAST_PLAN


# ---------------------------------------------------------------------------
# Vue nodale de la chaîne (même tokenizer que le moteur, sans modification)
# ---------------------------------------------------------------------------

def _node_view(phrase: str):
    """Chaîne → (tokens, vue nodale kind/key/nasal).

    Reproduit la vue de ``syltraj.build_nodes`` : les '.' (DOT) ne sont
    pas des nœuds, GAP/PAUSE/BREATH sont des pauses. L'insertion du '@'
    des mots sans voyelle (build_flat) n'est pas reproduite : le '@'
    n'est jamais adjacent d'une autre voyelle, il n'affecte donc pas
    les séquences vocaliques (runs).
    """
    from .syltraj import _normalize_word, _is_vowel_key, tokenize_phrase
    norm = ' '.join(_normalize_word(w) for w in phrase.strip().split())
    tokens = tokenize_phrase(norm)
    nodes: list[dict] = []
    for tok in tokens:
        if tok == 'DOT':
            continue
        if isinstance(tok, tuple) and tok[0] == 'S':
            key = tok[1]
            if _is_vowel_key(key):
                nodes.append({'kind': 'V', 'key': key.rstrip('~'),
                              'nasal': key.endswith('~')})
            else:
                nodes.append({'kind': 'C', 'key': key, 'nasal': False})
        else:                       # GAP / PAUSE / BREATH
            nodes.append({'kind': 'pause', 'key': '', 'nasal': False})
    return tokens, nodes


def _vowel_runs(nodes: list[dict]) -> list[list[dict]]:
    """Séquences maximales de voyelles adjacentes (longueur ≥ 2)."""
    runs, cur = [], []
    for nd in nodes:
        if nd['kind'] == 'V':
            cur.append(nd)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def _rebuild_phrase(tokens: list, strip_marks: set) -> str:
    """Reconstruit la phrase depuis les tokens (aller-retour stable).

    ``strip_marks`` : indices de tokens ('S', …) dont le marqueur '~'
    doit être retiré (oralisation). Les séparateurs sont réémis à
    l'identique : GAP → espace, PAUSE → '|', BREATH → '%', DOT → '.'.
    """
    out: list[str] = []
    for i, tok in enumerate(tokens):
        if tok == 'GAP':
            out.append(' ')
        elif tok == 'PAUSE':
            out.append('|')
        elif tok == 'BREATH':
            out.append('%')
        elif tok == 'DOT':
            out.append('.')
        else:
            key = tok[1]
            if i in strip_marks:
                key = key.rstrip('~')
            out.append(key)
    return ''.join(out).strip()


# ---------------------------------------------------------------------------
# Couche de pré-traitement : scission nasalité / base orale
# ---------------------------------------------------------------------------

def split_nasal_hiatus(phrase: str) -> tuple[str, dict]:
    """Oralise les voyelles nasales membres d'hiatus, capture la nasalité.

    Returns
    -------
    (motor_phrase, plan)
        ``motor_phrase`` : chaîne pour ``syltraj`` (identique à
        ``phrase`` hors hiatus nasaux) ;
        ``plan`` : événements de nasalité pour la réinjection VO
        (voir :func:`get_last_nasal_plan`).

    Repli conservateur : si l'aller-retour du tokenizer ne reproduit
    pas exactement la chaîne attendue, la chaîne d'ORIGINE est
    renvoyée sans événement (comportement moteur antérieur) — la
    correction ne peut jamais produire une chaîne inattendue.
    """
    global _LAST_PLAN
    tokens, nodes = _node_view(phrase)
    runs = _vowel_runs(nodes)

    # indices de tokens à oraliser : voyelles nasales appartenant à un
    # run (membres d'hiatus). Les voyelles nasales tenues (hors run)
    # gardent le chemin moteur existant (plateau + drapeau nasal).
    node_tok: list[int] = []      # nœud -> indice du token dans `tokens`
    for ti, tok in enumerate(tokens):
        if tok == 'DOT':
            continue              # les '.' ne sont pas des nœuds
        node_tok.append(ti)       # (indice COMPLET, '.' compris)
    strip_marks: set[int] = set()
    runs_events: list[list[dict]] = []
    idx = 0
    for run in runs:
        # position du premier nœud du run dans la vue nodale (les runs
        # sont des tranches consécutives de `nodes`)
        while idx < len(nodes) and nodes[idx] is not run[0]:
            idx += 1
        members = []
        for j, member in enumerate(run):
            members.append({'key': member['key'],
                            'nasal': member['nasal']})
            if member['nasal']:
                tok_i = node_tok[idx + j]
                if tok_i is not None:
                    strip_marks.add(tok_i)
        runs_events.append(members)
        idx += len(run)
    events = [{'run': ri, 'member': j, 'key': m['key']}
              for ri, run in enumerate(runs_events)
              for j, m in enumerate(run) if m['nasal']]

    motor = _rebuild_phrase(tokens, strip_marks) if strip_marks else \
        ' '.join(_norm_word(w) for w in phrase.strip().split())
    # (sans oralisation, la chaîne renvoyée est la forme normalisée
    # mot à mot — exactement celle que build_phrase_pval calcule
    # lui-même avant tokenisation : sorties inchangées)

    plan = {
        'original': phrase,
        'motor': motor,
        'nodes_view': nodes,
        'runs': runs_events,
        'events': events,
        'intervals': None,
        'fallback': False,
    }

    if strip_marks:
        # aller-retour : le moteur doit voir exactement les tokens
        # attendus (originaux, '~' retiré aux positions marquées)
        expected = []
        for i, tok in enumerate(tokens):
            if isinstance(tok, tuple) and tok[0] == 'S' and i in strip_marks:
                expected.append(('S', tok[1].rstrip('~'), False))
            else:
                expected.append(tok)
        try:
            _, rt_nodes = _node_view(motor)
            rt_tokens = _tokenize(motor)
            ok = (rt_tokens == expected)
        except Exception:                                    # noqa: BLE001
            ok = False
        if not ok:
            warnings.warn(
                'nasal_preproc: aller-retour tokenizer impossible '
                f'({phrase!r} → {motor!r}) — repli sur la chaîne '
                'originale (nasalité de hiatus non réinjectée).',
                stacklevel=2)
            plan['motor'] = ' '.join(_norm_word(w)
                                     for w in phrase.strip().split())
            plan['events'] = []
            plan['fallback'] = True
    _LAST_PLAN = plan
    return plan['motor'], plan


def _norm_word(w: str) -> str:
    from .syltraj import _normalize_word
    return _normalize_word(w)


def _tokenize(phrase: str) -> list:
    from .syltraj import tokenize_phrase
    norm = ' '.join(_norm_word(w) for w in phrase.strip().split())
    return tokenize_phrase(norm)


# ---------------------------------------------------------------------------
# Localisation temporelle : runs ↔ groupes de blocs background
# ---------------------------------------------------------------------------

def _background_groups(block_info) -> list[tuple[int, int]]:
    """Groupes de blocs 'background' consécutifs → (début, total) pas."""
    groups: list[tuple[int, int]] = []
    off, start, total, inside = 0, 0, 0, False
    for b in block_info:
        if getattr(b, 'kind', '') == 'background':
            if not inside:
                start, total, inside = off, 0, True
            total += int(b.n_steps)
        elif inside:
            groups.append((start, total))
            inside = False
        off += int(b.n_steps)
    if inside:
        groups.append((start, total))
    return groups


def nasal_hiatus_intervals(block_info, plan: dict,
                           t_voy: int | None = None) -> list[tuple[int, int, str]]:
    """Événements de nasalité → intervalles VO (pas @100 Hz).

    Correspondance structurelle (vérifiée, sinon repli) : le g-ième run
    vocalique (longueur k ≥ 2) ↔ le g-ième groupe de blocs background
    consécutifs, totalisant (k−1)·2·T_voy pas — chaque paire interne du
    run émet exactement un arc de fond de 2·T_voy (découpage schwa
    possible en deux blocs, le total est préservé). Le membre j du run
    possède le créneau [j·T, (j+1)·T) en qualité de premier membre de
    la paire j, prolongé du créneau [(2j−1)·T, 2j·T) en qualité de
    second membre de la paire j−1 (les voyelles médianes de runs VVV
    disposent ainsi de 2·T_voy, conformément au temps alloué par le
    moteur). Les intervalles nasaux adjacents sont FUSIONNÉS : la
    bascule nasal/oral ne doit se produire qu'aux vraies frontières
    nasal↔oral (ex. 9~.a~ : vélum ouvert d'un bout à l'autre).
    """
    runs = plan.get('runs') or []
    if not any(m.get('nasal') for run in runs for m in run):
        return []
    groups = _background_groups(block_info)
    if len(groups) != len(runs):
        warnings.warn(
            f'nasal_preproc: {len(runs)} run(s) vocalique(s) mais '
            f'{len(groups)} groupe(s) background — correspondance '
            'non vérifiée, nasalité de hiatus non réinjectée.',
            stacklevel=2)
        return []

    # T_voy effectif : paramètre direct, sinon plateaux, sinon dérivation
    cands: list[int] = []
    if t_voy is not None:
        cands.append(int(t_voy))
    plateaus = [int(b.n_steps) for b in block_info
                if getattr(b, 'kind', '') == 'plateau']
    if plateaus:
        cands.append(plateaus[0])
    for (g0, gt), run in zip(groups, runs):
        if len(run) >= 2:
            cands.append(gt // (2 * (len(run) - 1)))
    if not cands:
        warnings.warn('nasal_preproc: T_voy indéterminable — '
                      'nasalité de hiatus non réinjectée.', stacklevel=2)
        return []
    T = cands[0]
    if any(c != T for c in cands):
        warnings.warn(
            f'nasal_preproc: T_voy incohérent {sorted(set(cands))} — '
            'nasalité de hiatus non réinjectée.', stacklevel=2)
        return []

    raw: list[tuple[int, int, str]] = []
    for (g0, gt), run in zip(groups, runs):
        k = len(run)
        for j, m in enumerate(run):
            if not m.get('nasal'):
                continue
            t0 = g0 + (0 if j == 0 else (2 * j - 1) * T)
            t1 = g0 + (gt if j == k - 1 else (2 * j + 1) * T)
            raw.append((t0, t1, m['key']))
    raw.sort(key=lambda x: (x[0], x[1]))

    merged: list[list] = []
    for t0, t1, key in raw:
        if merged and t0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], t1)
            merged[-1][2] = merged[-1][2] + '+' + key
        else:
            merged.append([t0, t1, key])
    return [(a, b, c) for a, b, c in merged]


# ---------------------------------------------------------------------------
# Rampe VO (même forme que le chemin plateau de build_phrase_tract)
# ---------------------------------------------------------------------------

def vo_nasal_segment(n: int, target: float, baseline: float = -0.1,
                     sr: int = 100) -> np.ndarray:
    """Segment VO nasalé : cible tenue + rampes 20 % (max 40 ms).

    Réplique exactement la forme du chemin existant des plateaux
    nasaux (build_phrase_tract, étape 3b) : rampes symétriques
    min(max(2, 0.04·sr), n//4), ancrées sur la baseline vélaire
    fermée (−0.1). Le lissage τ = 20 ms de build_phrase_tract
    (timer existant) s'applique en aval, sans modification.
    """
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    ramp = min(max(2, int(0.04 * sr)), max(1, n // 4))
    seg = np.full(n, float(target), dtype=np.float64)
    if ramp > 0:
        seg[:ramp] = np.linspace(baseline, target, ramp)
        seg[-ramp:] = np.linspace(target, baseline, ramp)
    return seg
