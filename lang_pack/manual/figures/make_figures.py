# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Generate the figures of the language-pack manual (matplotlib).

Reads the ACTUAL vowel targets from ``lang_pack/lang_blocks/blocks.py``
(single source of truth — the figure can never drift from the shipped
constants) and renders:

  * ``vowel_triangle.pdf/.png`` — the a-i-u vocalic triangle in the
    (rho, theta) Maeda plane for French and Spanish, plus the overlay:
    same cardinal ANGLES, different calibrated RADII per language —
    the visual proof that targets do not transfer between languages;
  * ``pipeline_flow.pdf/.png`` — how the language pack is installed
    and switched (lang_pack/ -> vtl_synth/, LANG SECTION, verify).

Usage (from the repository root or from this directory)::

    python lang_pack/manual/figures/make_figures.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BLOCKS = ROOT / 'lang_pack' / 'lang_blocks' / 'blocks.py'

# French blue / Spanish orange (colour-blind friendly pair)
C_FR = '#1f77b4'
C_ES = '#d62728'
C_GRID = '#bbbbbb'


def load_targets() -> dict:
    """Exec each LANG SECTION block and return {lang: VOWEL_TARGETS}."""
    spec = importlib.util.spec_from_file_location('blocks', BLOCKS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = {}
    for lang, block in mod.LANG_BLOCKS.items():
        ns = {'np': np, 'Dict': dict, 'Tuple': tuple}
        exec(block, ns)
        out[lang] = ns['VOWEL_TARGETS']
    return out


def xy(rho, theta):
    return rho * np.cos(theta), rho * np.sin(theta)


def draw_axis(ax):
    """Light polar grid: unit circle + cardinal angle spokes."""
    for r in (0.2, 0.6, 1.0, 1.4):
        ax.add_patch(plt.Circle((0, 0), r, fill=False,
                                color=C_GRID, lw=0.5, ls=':'))
    for deg in (60, 90, 120, 180, 240, 270, 300, 330):
        t = np.radians(deg)
        ax.plot([0, 1.45 * np.cos(t)], [0, 1.45 * np.sin(t)],
                color=C_GRID, lw=0.5, ls=':')
        ax.text(1.52 * np.cos(t), 1.52 * np.sin(t), f'{deg}°',
                ha='center', va='center', fontsize=7, color='#777777')
    ax.set_xlim(-1.78, 1.78)
    ax.set_ylim(-1.45, 1.78)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines[:].set_visible(False)
    # x = rho axis label
    ax.annotate('', xy=(1.7, 0), xytext=(0, 0),
                arrowprops=dict(arrowstyle='->', color='#777777', lw=0.8))
    ax.text(0.85, -0.16, r'$\rho$', fontsize=10, color='#777777')


def plot_lang(ax, targets, color, label, label_fs=10):
    """One language: triangle a-i-u outline + every vowel point."""
    xs, ys = [], []
    for k in 'aiu':
        x, y = xy(*targets[k])
        xs.append(x)
        ys.append(y)
    ax.plot(xs + [xs[0]], ys + [ys[0]], '-', color=color, lw=1.2,
            alpha=0.85, zorder=2)
    ax.fill(xs, ys, color=color, alpha=0.06, zorder=1)
    for key, (rho, theta) in targets.items():
        x, y = xy(rho, theta)
        ax.plot([x], [y], 'o', color=color, ms=5, zorder=3)
        dx, dy = 0.05, 0.05
        if key in ('i', 'y', '2', 'e', 'E'):
            dx, dy = 0.06, 0.06
        ax.text(x + dx, y + dy, key, color=color, fontsize=label_fs,
                zorder=4)
    ax.set_title(label, fontsize=11, color=color)


def figure_triangle(all_targets):
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.8))
    for ax in axes:
        draw_axis(ax)
    plot_lang(axes[0], all_targets['fr'], C_FR, 'French (fr)')
    plot_lang(axes[1], all_targets['es'], C_ES, 'Spanish (es)')
    # overlay: same angles, different radii
    ax = axes[2]
    for key in 'aiu':
        rf, tf = all_targets['fr'][key]
        rs, ts = all_targets['es'][key]
        xf, yf = xy(rf, tf)
        xs_, ys_ = xy(rs, ts)
        ax.annotate('', xy=(xs_, ys_), xytext=(xf, yf),
                    arrowprops=dict(arrowstyle='->', color='#555555',
                                    lw=0.9))
    plot_lang(ax, all_targets['fr'], C_FR, 'fr vs es — same θ, ρ differs')
    plot_lang_overlay(ax, all_targets['es'], C_ES)
    fig.suptitle(
        'Vowel targets in the Maeda (ρ, θ) plane — calibrated per '
        'language on VTL/JD3',
        fontsize=12)
    fig.text(0.5, 0.015,
             'The cardinal angles θ are shared (a 180°, u 60°, i 300°); '
             'the radii ρ are NOT transferable between languages.',
             ha='center', fontsize=9, color='#444444')
    fig.tight_layout(rect=(0, 0.075, 1, 0.94))
    for ext in ('pdf', 'png'):
        fig.savefig(HERE / f'vowel_triangle.{ext}', dpi=200)
    plt.close(fig)


def plot_lang_overlay(ax, targets, color):
    """Second language on the overlay panel: points + labels only.

    Labels go below-right of the points (the first language's labels
    go above-right), with extra offsets where fr/es targets nearly
    coincide (E at 240°, u at 60°)."""
    extra = {'E': (0.10, -0.26), 'u': (0.10, -0.20), 'O': (0.10, -0.20)}
    for key, (rho, theta) in targets.items():
        x, y = xy(rho, theta)
        ax.plot([x], [y], 'o', color=color, ms=5, zorder=3,
                markeredgecolor='white', markeredgewidth=0.6)
        dx, dy = extra.get(key, (0.06, -0.15))
        ax.text(x + dx, y + dy, key, color=color, fontsize=10,
                zorder=4)


def figure_flow():
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 46)
    ax.axis('off')

    def box(x, y, w, h, text, fc='#eaf2fb', ec='#1f77b4', fs=8.5):
        ax.add_patch(plt.Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.2,
                                   zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
                fontsize=fs, zorder=3)

    def arrow(x1, y1, x2, y2, label='', dy=1.6):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='->', color='#333333',
                                    lw=1.1))
        if label:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label,
                    ha='center', fontsize=7.5, color='#333333')

    box(1, 30, 26, 13,
        'lang_pack/  (source package)\n'
        'profiles/  lexicons/  lang_blocks/\nintegration/  manual/',
        fc='#f2f2f2', ec='#888888')
    box(38, 34, 28, 9,
        'setup_lang.py install --lang xx\n'
        '(copies + integrates, .bak backups)')
    box(75, 30, 28, 13,
        'vtl_synth/\n'
        'utils/ (g2p + profiles)\n'
        'data/ (lexicons)   core/ (LANG SECTION)',
        fc='#eafbea', ec='#2e7d32')
    box(38, 18, 28, 9,
        'setup_lang.py setlang xx\n(rewrites the LANG SECTION\n'
        'of core/constants.py)')
    box(1, 14, 26, 10,
        'text --g2p--> engine SAMPA\n--> syltraj --> tract\n'
        '--> VTL/JD3 audio',
        fc='#fff8e1', ec='#f9a825')
    box(75, 14, 28, 10,
        'setup_lang.py verify\n(LPC on real audio,\n'
        '±30 % vs literature F1/F2)',
        fc='#fdeaea', ec='#c62828')

    arrow(27, 36.5, 38, 38.5)
    arrow(66, 38.5, 75, 36.5)
    arrow(52, 34, 52, 27)
    arrow(75, 19, 66, 22.5)
    arrow(38, 22.5, 27, 19)
    ax.text(52.5, 6,
            'JD3 speaker and vtl_binaries/ are never touched — '
            'restore [--purge] returns the tree to its pristine state',
            ha='center', fontsize=8.5, color='#555555')
    fig.tight_layout()
    for ext in ('pdf', 'png'):
        fig.savefig(HERE / f'pipeline_flow.{ext}', dpi=200)
    plt.close(fig)


if __name__ == '__main__':
    targets = load_targets()
    print('targets loaded for:', sorted(targets))
    figure_triangle(targets)
    print('vowel_triangle.pdf/png written')
    figure_flow()
    print('pipeline_flow.pdf/png written')
