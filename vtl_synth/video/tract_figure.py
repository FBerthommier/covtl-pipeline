# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
tract_figure.py
===============
Figure rendering of a `.tract` file (400 Hz tract + glottis vectors).

This is the graphical counterpart of ``vtl-synth inspect``: instead of
printing per-parameter statistics in the terminal, it plots every
parameter trajectory over time and saves the figure as a PNG (or any
matplotlib-supported format)::

    vtl-synth plot-tract out/output.tract
    vtl-synth plot-tract out/output.tract -o out/tract.png --glottis
    vtl-synth plot-tract out/output.tract --params JX JA TTX TTY

The tract figure is one shared-time-axis subplot per parameter
(min/max envelope shading is not needed: a single line per curve, the
400 Hz sampling makes the trajectories fully resolved).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vtl_synth.core.constants import (
    GLOTTIS_PARAM_NAMES,
    N_GLOTTIS_PARAMS,
    N_TRACT_PARAMS,
    TRACT_PARAM_NAMES,
)
from vtl_synth.video.renderer import read_tract

# Glottis parameters worth plotting by default with --glottis (the
# remaining ones are constant presets in this engine).
PLOTTED_GLOTTIS = (0, 1)  # f0 (Hz), pressure (dPa)

_COLORS = ('#1f77b4', '#d62728', '#2ca02c', '#9467bd', '#ff7f0e')


def make_tract_figure(data: np.ndarray,
                      sr: float = 400.0,
                      which: str = 'tract',
                      params=None,
                      title: str | None = None):
    """Build the matplotlib figure of a .tract array.

    Parameters
    ----------
    data : (n_frames, >=19) array as returned by :func:`read_tract`.
    sr : sample rate in Hz (from the .tract header, default 400).
    which : 'tract' (19 vocal-tract parameters), 'glottis' (f0 +
        pressure), or 'all' (both blocks stacked).
    params : optional iterable of tract parameter names to restrict
        the tract block (e.g. ``['JX', 'JA', 'TTX']``).
    title : optional figure title.

    Returns
    -------
    (fig, axes) : the figure and its list of axes.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    t = np.arange(data.shape[0]) / sr

    blocks: list[tuple[str, list[str], np.ndarray]] = []
    if which in ('tract', 'all'):
        if params:
            missing = [p for p in params if p not in TRACT_PARAM_NAMES]
            if missing:
                raise ValueError(f'unknown tract parameters: {missing}')
            idx = [TRACT_PARAM_NAMES.index(p) for p in params]
            blocks.append(('vocal tract', [TRACT_PARAM_NAMES[i] for i in idx],
                           data[:, idx]))
        else:
            blocks.append(('vocal tract', list(TRACT_PARAM_NAMES),
                           data[:, :N_TRACT_PARAMS]))
    if which in ('glottis', 'all'):
        if data.shape[1] > N_TRACT_PARAMS:
            names = [GLOTTIS_PARAM_NAMES[i] for i in PLOTTED_GLOTTIS]
            cols = [N_TRACT_PARAMS + i for i in PLOTTED_GLOTTIS]
            blocks.append(('glottis', names, data[:, cols]))
        else:
            print('note: this .tract has no glottis columns; '
                  'skipping the glottis block')

    n_rows = sum(len(names) for _, names, _ in blocks)
    fig, axes = plt.subplots(n_rows, 1, figsize=(11, 1.35 * n_rows + 1.0),
                             sharex=True, squeeze=False)
    axes = [a for a in axes[:, 0]]

    k = 0
    for block_name, names, cols in blocks:
        for j, name in enumerate(names):
            ax = axes[k]
            ax.plot(t, cols[:, j], lw=0.9,
                    color=_COLORS[j % len(_COLORS)])
            ax.set_ylabel(name, rotation=0, ha='right', va='center',
                          fontsize=9, labelpad=8)
            ax.yaxis.set_label_coords(-0.06, 0.5)
            ax.grid(alpha=0.25, lw=0.5)
            ax.tick_params(labelsize=7, pad=2)
            if j == 0:
                ax.annotate(block_name, xy=(0.5, 1.35), xycoords='axes fraction',
                            ha='center', fontsize=10, fontweight='bold',
                            annotation_clip=False)
            k += 1

    axes[-1].set_xlabel('time (s)', fontsize=9)
    axes[-1].set_xlim(t[0], t[-1])
    if title:
        fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig, axes


def plot_tract_file(path, out_path=None, which: str = 'tract',
                    params=None, show_stats: bool = False) -> Path:
    """Read a .tract file, plot it, save the figure, return its path.

    With ``show_stats`` a compact min/max/mean table (same numbers as
    ``vtl-synth inspect --ranges``) is printed to the terminal.
    """
    path = Path(path)
    data, sr = read_tract(path)
    if out_path is None:
        out_path = path.with_suffix('.png')
    out_path = Path(out_path)
    if out_path.suffix.lower() == '':
        out_path = out_path.with_suffix('.png')

    fig, _ = make_tract_figure(
        data, sr=sr, which=which, params=params,
        title=f'{path.name}  —  {data.shape[0]} frames @ {sr:.0f} Hz '
              f'({data.shape[0] / sr:.2f} s)')
    fig.savefig(out_path, dpi=150)
    print(f'figure: {out_path}')

    if show_stats:
        tract = data[:, :N_TRACT_PARAMS]
        print(f'\n  {"param":<8s} {"min":>8s} {"max":>8s} {"mean":>8s}')
        for j, name in enumerate(TRACT_PARAM_NAMES):
            col = tract[:, j]
            print(f'  {name:<8s} {col.min():8.3f} {col.max():8.3f} '
                  f'{col.mean():8.3f}')
    return out_path
