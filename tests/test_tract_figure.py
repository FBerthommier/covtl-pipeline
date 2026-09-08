# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Tests of the plot-tract utility (tract_figure)."""

import numpy as np
import pytest

from vtl_synth.core.constants import N_TRACT_PARAMS, TRACT_PARAM_NAMES
from vtl_synth.video.tract_figure import make_tract_figure, plot_tract_file


@pytest.fixture
def tract_array():
    rng = np.random.default_rng(0)
    # 400 frames @ 400 Hz = 1 s; 19 tract + 11 glottis columns
    data = rng.uniform(-1, 1, size=(400, N_TRACT_PARAMS + 11))
    data[:, N_TRACT_PARAMS] = 100.0  # glottis f0
    return data


def test_make_tract_figure_all(tract_array):
    fig, axes = make_tract_figure(tract_array, sr=400.0, which='all')
    # 19 tract + 2 glottis (f0, pressure) rows
    assert len(axes) == 21
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_make_tract_figure_params_filter(tract_array):
    fig, axes = make_tract_figure(tract_array, which='tract',
                                  params=['JX', 'JA'])
    assert len(axes) == 2
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_make_tract_figure_unknown_param(tract_array):
    with pytest.raises(ValueError, match='unknown tract parameters'):
        make_tract_figure(tract_array, params=['NOPE'])


def test_plot_tract_file(tract_array, tmp_path):
    src = tmp_path / 'x.tract'
    np.savetxt(src, tract_array, comments='')
    out = plot_tract_file(src)
    assert out == src.with_suffix('.png')
    assert out.exists() and out.stat().st_size > 0
