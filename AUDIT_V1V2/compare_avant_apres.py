#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
compare_avant_apres.py — verification of the V1V2 engine fix
============================================================
Compares the archived failing state (results_avant/, audit commit) and
the fixed state (results/, nasal_preproc gate) :

  1. table: VO nasal halves, nasality verdict, md5 (.tract/.wav) ;
  2. "parameter space intact" proof: columns of the .tract
     strictly identical before/after, EXCEPT the VO column (7) for
     the fixed items — and fully identical for the controls
     (T1-T4, H0: bit-for-bit non-perturbation) ;
  3. proof of the defect inversion: md5(ta~.ata) != md5(ta.ata) etc.
     (the byte identity H0≡H1≡H2≡H3 of audit §4.5 is broken) ;
  4. copy of the before/after WAV pairs for listening (wav_compare/).

Usage:  python AUDIT_V1V2/compare_avant_apres.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TRACT_SR = 400
VO_COL = 7
N_COLS = 30


def read_tract(path: Path):
    rows, started = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# ---'):
            started = True
            continue
        if not started or not line.strip() or line.startswith('# sample'):
            continue
        rows.append([float(x) for x in line.split()])
    return np.asarray(rows, dtype=np.float64)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    avant = json.loads((HERE / 'results_avant' / 'results.json')
                       .read_text(encoding='utf-8'))
    apres = json.loads((HERE / 'results' / 'results.json')
                       .read_text(encoding='utf-8'))
    items_avant = {it['id']: it for it in avant['items']}
    items_apres = {it['id']: it for it in apres['items']}

    wav_cmp = HERE / 'wav_compare'
    for sub in ('avant', 'apres'):
        (wav_cmp / sub).mkdir(parents=True, exist_ok=True)

    rows, n_corr, n_ident, problems = [], 0, 0, []
    for rid, it_a in items_avant.items():
        it_p = items_apres.get(rid)
        if it_p is None or 'erreur' in it_p or 'erreur' in it_a:
            problems.append(f'{rid}: synthesis error')
            continue
        t_av = read_tract(HERE / 'results_avant' / 'tract' / f'{rid}.tract')
        t_ap = read_tract(HERE / 'results' / 'tract' / f'{rid}.tract')
        if t_av.shape != t_ap.shape:
            problems.append(f'{rid}: different .tract shapes '
                            f'{t_av.shape} vs {t_ap.shape}')
            continue
        cols = [j for j in range(N_COLS)
                if not np.array_equal(t_av[:, j], t_ap[:, j])]
        v_av = it_a['verdict']
        v_ap = it_p['verdict']
        vo_av = v_av['vo_hiatus_centre']
        vo_ap = v_ap.get('vo_critere')
        corrige = v_av['nasalite_perdue'] and not v_ap['nasalite_perdue']
        identique = not cols
        if identique:
            n_ident += 1
        elif corrige and cols == [VO_COL]:
            n_corr += 1
        else:
            problems.append(f'{rid}: unexpected modified columns {cols}'
                            f' (fixed={corrige})')
        # WAV pairs for listening
        for tag, src in (('avant', HERE / 'results_avant' / 'wav' / f'{rid}.wav'),
                         ('apres', HERE / 'results' / 'wav' / f'{rid}.wav')):
            if src.exists():
                shutil.copy2(src, wav_cmp / tag / f'{rid}.wav')
        rows.append({
            'id': rid, 'situation': it_p['situation'],
            'vo_avant': vo_av, 'vo_apres': vo_ap,
            'nas_perdue_avant': v_av['nasalite_perdue'],
            'nas_perdue_apres': v_ap['nasalite_perdue'],
            'md5_tract_avant': it_a['md5_tract'],
            'md5_tract_apres': it_p['md5_tract'],
            'md5_wav_avant': it_a['md5_wav'],
            'md5_wav_apres': it_p['md5_wav'],
            'colonnes_diff': cols,
            'corrige': corrige, 'identique': identique,
        })

    # proof of the byte-identity inversion (audit §4.5)
    h = {r['id']: r['md5_tract_apres'] for r in rows}
    identite_cassee = len({h.get(k) for k in ('H0', 'H1', 'H2', 'H3')}) == 4

    # table
    print(f"{'id':<4} {'VO before':<9} {'VO after':<9} "
          f"{'before':<7} {'after':<7} {'tract':<11} {'state':<10}")
    print('-' * 66)
    for r in rows:
        etat = ('IDENTICAL' if r['identique']
                else 'VO only' if r['colonnes_diff'] == [VO_COL]
                else str(r['colonnes_diff']))
        print(f"{r['id']:<4} {str(r['vo_avant']):<9} {str(r['vo_apres']):<9} "
              f"{'YES' if r['nas_perdue_avant'] else 'no':<7} "
              f"{'YES' if r['nas_perdue_apres'] else 'no':<7} "
              f"{'=' if r['md5_tract_avant'] == r['md5_tract_apres'] else 'diff':<11} "
              f"{etat:<10}")

    print()
    print(f"Fixed (VO column only changed): {n_corr}")
    print(f"Bit-identical controls        : {n_ident}")
    print(f"H0-H3 byte identity broken    : "
          f"{'YES (4 distinct md5)' if identite_cassee else 'NO'}")
    if problems:
        print('PROBLEMS:')
        for p in problems:
            print('  -', p)

    out = {'items': rows,
           'n_corriges_vo_seule': n_corr,
           'n_temoins_identiques': n_ident,
           'identite_H0H3_cassee': identite_cassee,
           'problemes': problems}
    (HERE / 'results' / 'compare_avant_apres.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print("\nWritten : " + str(HERE / 'results' / 'compare_avant_apres.json'))
    print(f"Before/after WAVs for listening : {wav_cmp}")

    ok = (not problems and identite_cassee
          and all(not r['nas_perdue_apres'] for r in rows))
    print('\nOVERALL VERDICT :', 'SUCCESS' if ok else 'FAILURE')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
