#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""V1V2 audit figures (200 dpi PNG, ready for ReportLab insertion).

fig1: VO (velum) trajectory of S1a "comment allez-vous" — hiatus window,
      measured value vs expected value.
fig2: summary — expected VO vs realized VO for the 8 defect situations.
fig3: minimal pairs H0-H3 — nasality is ignored (overlapping curves).
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
RES = HERE / 'results'
FIGS = RES / 'figs'
FIGS.mkdir(exist_ok=True)

# Cascade palette (design_engine.py palette-cascade, seed 42)
ACCENT = '#92761f'
ACCENT_2 = '#3aa0c2'
HEADER_FILL = '#4e4732'
CARD_BG = '#ebeae8'
BORDER = '#c5bfac'
TEXT_PRIMARY = '#151513'
TEXT_MUTED = '#7e7c74'
SEM_ERROR = '#a25b54'

TRACT_SR = 400
VO_COL = 7


def read_tract(path):
    rows, started = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# ---'):
            started = True
            continue
        if not started or not line.strip():
            continue
        rows.append([float(x) for x in line.split()])
    return np.asarray(rows)


def read_wav_rms(path, sr=44100):
    import wave
    with wave.open(str(path), 'rb') as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2')
    x = pcm.astype(np.float64) / 32768.0
    n = int(0.02 * sr)                       # 20 ms windows
    m = (len(x) // n) * n
    rms = np.sqrt((x[:m].reshape(-1, n) ** 2).mean(axis=1))
    return rms, np.arange(len(rms)) * 0.02 + 0.01


def style_ax(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(BORDER)
    ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=10)
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.25)
    ax.set_axisbelow(True)


results = json.loads((RES / 'results.json').read_text(encoding='utf-8'))
by_id = {r['id']: r for r in results['items']}

# ==========================================================================
# Figure 1 — VO(t) on S1a "comment allez-vous"
# ==========================================================================
rec = by_id['S1a']
tract = read_tract(RES / 'tract' / 'S1a.tract')
t = np.arange(tract.shape[0]) / TRACT_SR
vo = tract[:, VO_COL]

bg = [b for b in rec['blocks'] if b['kind'] == 'background'][0]
w0, w1 = bg['offset'] / 100.0, (bg['offset'] + bg['n_steps']) / 100.0
mid = (w0 + w1) / 2

fig, ax = plt.subplots(figsize=(8.0, 3.4), dpi=200, constrained_layout=True)
ax.axhspan(-0.2, 0.65, xmin=0, xmax=1, color='white')
ax.axhline(0.5, color=SEM_ERROR, linestyle=':', linewidth=1.2, alpha=0.9)
ax.axhline(-0.1, color=TEXT_MUTED, linestyle=':', linewidth=1.0, alpha=0.7)
ax.axvspan(w0, w1, color=ACCENT_2, alpha=0.12)
ax.plot(t, vo, color=ACCENT, linewidth=2.0, label='measured VO (engine)')

# expected: nasality on the 1st half of the window (20 % ramp)
tt = np.linspace(w0, mid, 80)
ramp = int(0.2 * len(tt))
attendu = np.full(len(tt), 0.5)
attendu[:ramp] = np.linspace(-0.1, 0.5, ramp)
attendu[-ramp:] = np.linspace(0.5, -0.1, ramp)
ax.plot(tt, attendu, color=SEM_ERROR, linewidth=1.8, linestyle='--',
        label='expected VO for /a~/ (20 % ramp)')

ax.annotate('a~.a hiatus collapsed into a background arc\n'
            '(background block, 240 ms)',
            xy=(mid, 0.05), xytext=(mid + 0.16, 0.34),
            fontsize=9.5, color=TEXT_PRIMARY,
            arrowprops=dict(arrowstyle='-', color=TEXT_MUTED, lw=0.8))
ax.text(1.42, 0.515, 'VO_NASALIZED_VOWEL = 0.5 (healthy nasal plateau)',
        fontsize=8.5, color=SEM_ERROR, va='bottom')
ax.text(1.42, -0.135, 'velum closed (floor −0.1)', fontsize=8.5,
        color=TEXT_MUTED, va='top')
ax.text(w0 + (w1 - w0) / 2, -0.185, 'no nasality on the vowel /a~/',
        fontsize=8.5, color=SEM_ERROR, ha='center', va='bottom')

ax.set_xlim(0, t[-1])
ax.set_ylim(-0.2, 0.65)
ax.set_xlabel('time (s)', fontsize=11, color=TEXT_PRIMARY)
ax.set_ylabel('VO — velar opening (VTL)', fontsize=11, color=TEXT_PRIMARY)
style_ax(ax)
ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.02), ncol=2,
          frameon=False, fontsize=9.5)
fig.savefig(FIGS / 'fig1_vo_S1a.png')
plt.close(fig)

# ==========================================================================
# Figure 2 — summary of expected / realized VO (8 defect situations)
# ==========================================================================
ids = ['S1a', 'S1b', 'S2a', 'S2b', 'S3a', 'S3b', 'S4a', 'S4b']
labels = ['S1a\ncomment\nallez-vous', 'S1b\nmon ami', 'S2a\nil a envie',
          'S2b\nla onzième', 'S3a\nnéon', 'S3b\néhonté',
          'S4a\nenhardir', 'S4b\nenhucher']
attendus, realises = [], []
for i in ids:
    v = by_id[i]['verdict']
    realises.append(v['vo_hiatus_centre'] if v['vo_hiatus_centre'] is not None else 0.0)
    attendus.append(0.5)                     # VO_NASALIZED_VOWEL reference

x = np.arange(len(ids))
w = 0.36
fig, ax = plt.subplots(figsize=(8.0, 3.6), dpi=200, constrained_layout=True)
b1 = ax.bar(x - w / 2, attendus, w, color=BORDER, edgecolor='none',
            label='expected VO on the nasal member (ref. 0.5)')
b2 = ax.bar(x + w / 2, realises, w, color=ACCENT, edgecolor='none',
            label='VO realized at the center of the hiatus (measured)')
ax.axhline(0.493, color=SEM_ERROR, linestyle=':', linewidth=1.2)
ax.text(len(ids) - 0.4, 0.505, 'healthy nasal plateaus T3/T4: 0.49–0.50',
        fontsize=8.5, color=SEM_ERROR, ha='right')
for xi, v in zip(x, realises):
    ax.text(xi + w / 2, v - 0.028, f'{v:+.2f}'.replace('-', '−'),
            ha='center', va='top', fontsize=8.5, color=HEADER_FILL)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=9, color=TEXT_PRIMARY)
ax.set_ylim(-0.2, 0.65)
ax.set_ylabel('VO — velar opening (VTL)', fontsize=11, color=TEXT_PRIMARY)
style_ax(ax)
ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.02), ncol=2,
          frameon=False, fontsize=9.5)
fig.savefig(FIGS / 'fig2_recap_vo.png')
plt.close(fig)

# ==========================================================================
# Figure 3 — minimal pairs H0-H3: overlapping curves
# ==========================================================================
trH = read_tract(RES / 'tract' / 'H0.tract')
tH = np.arange(trH.shape[0]) / TRACT_SR
voH = trH[:, VO_COL]
recH = by_id['H1']
bgH = [b for b in recH['blocks'] if b['kind'] == 'background'][0]
h0, h1 = bgH['offset'] / 100.0, (bgH['offset'] + bgH['n_steps']) / 100.0
mH = (h0 + h1) / 2

fig, ax = plt.subplots(figsize=(8.0, 3.3), dpi=200, constrained_layout=True)
ax.axhline(0.5, color=TEXT_MUTED, linestyle=':', linewidth=1.0, alpha=0.7)
ax.axhline(-0.1, color=TEXT_MUTED, linestyle=':', linewidth=1.0, alpha=0.7)
ax.axvspan(h0, h1, color=ACCENT_2, alpha=0.12)
ax.plot(tH, voH, color=ACCENT, linewidth=2.2,
        label='measured VO — ta.ata ≡ ta~.ata ≡ ta.a~ta ≡ ta~.a~ta (identical md5)')

for a, b, lab in [(h0, mH, 'expected H1 ta~.ata (nasal→oral)'),
                  (mH, h1, 'expected H2 ta.a~ta (oral→nasal)')]:
    tt = np.linspace(a, b, 60)
    ramp = int(0.2 * len(tt))
    att = np.full(len(tt), 0.5)
    att[:ramp] = np.linspace(-0.1, 0.5, ramp)
    att[-ramp:] = np.linspace(0.5, -0.1, ramp)
    ax.plot(tt, att, color=SEM_ERROR, linewidth=1.6, linestyle='--',
            label=lab)
tt = np.linspace(h0, h1, 80)
att = np.full(len(tt), 0.5)
att[:6] = np.linspace(-0.1, 0.5, 6)
att[-6:] = np.linspace(0.5, -0.1, 6)
ax.plot(tt, att, color=HEADER_FILL, linewidth=1.4, linestyle='-.',
        label='expected H3 ta~.a~ta (nasal→nasal)')

ax.set_xlim(0, tH[-1])
ax.set_ylim(-0.2, 0.65)
ax.set_xlabel('time (s)', fontsize=11, color=TEXT_PRIMARY)
ax.set_ylabel('VO — velar opening (VTL)', fontsize=11, color=TEXT_PRIMARY)
style_ax(ax)
ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.02), ncol=2,
          frameon=False, fontsize=8.8)
fig.savefig(FIGS / 'fig3_paires_H.png')
plt.close(fig)

print('Figures written:', *sorted(p.name for p in FIGS.glob('*.png')))
