#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figures of the V1V2 implementation (before/after engine fix).

fig_impl1: VO trajectory of S1a over the hiatus window — before (defect)
           vs after (nasal_preproc gate), with healthy band 0.49-0.50.
fig_impl2: minimal pairs H0-H3 — VO curves after the fix
           (4 distinct trajectories) vs H0 before (flat −0.1).
fig_impl3: summary — VO of the nasal halves before/after per item.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

fm.fontManager.addfont('/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf')
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['Noto Sans SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

HERE = Path(__file__).resolve().parent
AVANT = HERE / 'results_avant'
APRES = HERE / 'results'
FIGS = APRES / 'figs'
FIGS.mkdir(exist_ok=True)
TRACT_SR = 400
VO_COL = 7
C_AV, C_AP = '#c0392b', '#1a6fae'


def read_tract(path: Path):
    rows, started = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# ---'):
            started = True
            continue
        if not started or not line.strip() or line.startswith('# sample'):
            continue
        rows.append([float(x) for x in line.split()])
    return np.asarray(rows)


def vo(rid, state='apres'):
    base = APRES if state == 'apres' else AVANT
    return read_tract(base / 'tract' / f'{rid}.tract')[:, VO_COL]


# ---- fig 1: S1a, hiatus window -------------------------------------------
res = json.loads((APRES / 'results.json').read_text(encoding='utf-8'))
it = {r['id']: r for r in res['items']}['S1a']
t0, t1 = 0.30, 1.05                     # window around the a~.a hiatus
sr = TRACT_SR
w = slice(int(t0 * sr), int(t1 * sr))
tt = np.arange(w.stop - w.start) / sr + t0
v_av, v_ap = vo('S1a', 'avant')[w], vo('S1a', 'apres')[w]

fig, ax = plt.subplots(figsize=(7.2, 3.6), constrained_layout=True)
ax.axhspan(0.49, 0.50, color='#2e8b57', alpha=0.18,
           label='healthy reference (nasal plateau: 0.49–0.50)')
ax.axhline(0.4, color='#7f8c8d', ls=':', lw=1,
           label='acceptance threshold (0.4)')
ax.plot(tt, v_av, color=C_AV, lw=1.6, label='BEFORE (defect) — VO stuck at −0.1')
ax.plot(tt, v_ap, color=C_AP, lw=2.0,
        label='AFTER (nasal_preproc gate) — a~ → a switch')
for (i0, i1, k) in (it.get('intervalles_vo') or []):
    x0, x1 = i0 / 100.0, i1 / 100.0
    if x1 > t0 and x0 < t1:
        ax.axvspan(max(x0, t0), min(x1, t1), color=C_AP, alpha=0.12)
        ax.annotate('a~ (nasal creak)', xy=((max(x0, t0) + min(x1, t1)) / 2,
                    0.53), ha='center', fontsize=8, color=C_AP)
ax.set_xlabel('time (s)')
ax.set_ylabel('VO — velar opening')
ax.set_title('S1a "comment allez-vous" (kOma~.a.le.vu) — nasality of the a~.a hiatus\n'
             'only the velar-port command changes; the parameter space is identical',
             fontsize=9)
ax.legend(fontsize=7, loc='lower right')
ax.set_ylim(-0.2, 0.62)
fig.savefig(FIGS / 'fig_impl1_vo_S1a_avant_apres.png', dpi=200)
plt.close(fig)

# ---- fig 2: minimal pairs H0-H3 ------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 3.6), constrained_layout=True)
labels = [('H0', 'ta.ata', 'oral'), ('H1', 'ta~.ata', 'nasal→oral'),
          ('H2', 'ta.a~ta', 'oral→nasal'), ('H3', 'ta~.a~ta', 'nasal→nasal')]
colors = ['#7f8c8d', C_AP, '#8e44ad', '#2e8b57']
t0, t1 = 0.30, 1.15
w = slice(int(t0 * sr), int(t1 * sr))
tt = np.arange(w.stop - w.start) / sr + t0
ax.plot(tt, vo('H0', 'avant')[w], color='#e74c3c', lw=1.2, ls='--',
        label='BEFORE: H0≡H1≡H2≡H3 (4 byte-for-byte identical wav files)')
for (rid, lab, sit), c in zip(labels, colors):
    ax.plot(tt, vo(rid, 'apres')[w], color=c, lw=1.8,
            label=f'AFTER {lab} ({sit})')
ax.axhspan(0.49, 0.50, color='#2e8b57', alpha=0.15)
ax.set_xlabel('time (s)')
ax.set_ylabel('VO — velar opening')
ax.set_title('Engine minimal pairs — nasality now crosses the liaison boundary\n'
             '(the byte identity of audit §4.5 is inverted: 4 distinct outputs)',
             fontsize=9)
ax.legend(fontsize=7, loc='upper right')
ax.set_ylim(-0.2, 0.62)
fig.savefig(FIGS / 'fig_impl2_paires_H_apres.png', dpi=200)
plt.close(fig)

# ---- fig 3: VO nasal-halves summary --------------------------------------
cmpj = json.loads((APRES / 'compare_avant_apres.json').read_text(encoding='utf-8'))
rows = [r for r in cmpj['items'] if not r['identique']]
rows.sort(key=lambda r: r['id'])
x = np.arange(len(rows))
avant = [r['vo_avant'] if r['vo_avant'] is not None else -0.1 for r in rows]
apres = [r['vo_apres'] if r['vo_apres'] is not None else -0.1 for r in rows]
fig, ax = plt.subplots(figsize=(7.6, 3.8), constrained_layout=True)
ax.bar(x - 0.19, avant, 0.38, color=C_AV, label='BEFORE (defect)')
ax.bar(x + 0.19, apres, 0.38, color=C_AP, label='AFTER (fixed)')
ax.axhline(0.4, color='#7f8c8d', ls=':', lw=1, label='threshold 0.4')
ax.axhspan(0.49, 0.50, color='#2e8b57', alpha=0.15,
           label='healthy reference 0.49–0.50')
ax.set_xticks(x)
ax.set_xticklabels([r['id'] for r in rows], fontsize=8)
ax.set_ylabel('max(VO) over the nasal halves')
ax.set_title('Nasality realized on the nasal halves of the hiatuses — 15 items fixed\n'
             '(the 5 controls T1-T4, H0 are bit-identical and off the chart)',
             fontsize=9)
ax.legend(fontsize=7, loc='lower right')
ax.set_ylim(-0.15, 0.62)
fig.savefig(FIGS / 'fig_impl3_recap_avant_apres.png', dpi=200)
plt.close(fig)

print('Figures written:', FIGS)
for f in sorted(FIGS.glob('fig_impl*.png')):
    print('  -', f.name)
