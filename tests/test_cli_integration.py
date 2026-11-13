# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""CLI integration tests (P1 hardening) — vtl_synth.cli.main.main([...]).

Real end-to-end invocations of the subcommands with SHORT phonetic
inputs (one syllable): ``run`` / ``text-to-wav`` / ``inspect`` /
``plot-tract`` / ``polar-build``, plus the error paths of ``main``.

The video subcommands (tract-to-mp4, polar-video) are deliberately NOT
covered here: ffmpeg encoding is slow and non-deterministic — the video
layer is covered by the smoke tests and documented in LEGACY.md.
"""
import sys
from pathlib import Path

import pytest

from vtl_synth.cli.main import main


@pytest.fixture(scope='module')
def synth_out(tmp_path_factory):
    """One ``run`` synthesis shared by the file-inspecting subcommands."""
    out = tmp_path_factory.mktemp('cli_synth')
    rc = main(['run', '--phonetic', 'ba', '-o', str(out),
               '--no-video', '--sampa-guard', 'off'])
    assert rc == 0
    return out


def _find(out: Path, pattern: str):
    matches = sorted(out.glob(pattern))
    assert matches, f'no {pattern} under {out}'
    return matches[0]


class TestRun:
    def test_run_phonetic_success(self, synth_out):
        # prints were consumed by the fixture; assert on the artifacts
        tract = _find(synth_out, '*.tract')
        wav = _find(synth_out, '*.wav')
        assert tract.stat().st_size > 0
        assert wav.stat().st_size > 0
        # .tract is a VTL sequence: first data line = 19 tract + 11 glottis
        data = [l for l in tract.read_text().splitlines()
                if not l.startswith('#') and l.strip()]
        assert data and len(data[0].split()) == 30

    def test_run_with_lang_prints_language_line(self, tmp_path, capsys):
        rc = main(['run', '--phonetic', 'ba', '-o', str(tmp_path),
                   '--no-video', '--lang', 'fr'])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'language  : fr' in out


class TestTextToWav:
    def test_success_line_and_wav(self, tmp_path, capsys):
        rc = main(['text-to-wav', '--phonetic', 'ba', '-o', str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'SUCCESS' in out and 'monotone' in out
        assert _find(tmp_path, '*.wav').stat().st_size > 0

    def test_lang_in_success_line(self, tmp_path, capsys):
        rc = main(['text-to-wav', '--phonetic', 'ba', '-o', str(tmp_path),
                   '--lang', 'es'])
        assert rc == 0
        assert '(es,' in capsys.readouterr().out


class TestInspect:
    def test_inspect_states_and_ranges(self, synth_out, capsys):
        tract = _find(synth_out, '*.tract')
        rc = main(['inspect', str(tract), '--states', '2', '--ranges'])
        assert rc == 0
        out = capsys.readouterr().out
        assert 'shape' in out and 'rate' in out and 'duration' in out
        assert 'glottis cols' in out
        assert 'tract parameter ranges' in out
        assert 'HX' in out and 'TS3' in out

    def test_inspect_missing_file(self, capsys):
        rc = main(['inspect', 'no_such.tract'])
        assert rc == 1
        assert 'not found' in capsys.readouterr().out

    def test_inspect_ges_rejected(self, tmp_path, capsys):
        ges = tmp_path / 'x.ges'
        ges.write_text('dummy')
        rc = main(['inspect', str(ges)])
        assert rc == 1
        assert 'no .ges/.seg stage' in capsys.readouterr().out


class TestPlotTract:
    def test_plot_png_written(self, synth_out, tmp_path, capsys):
        tract = _find(synth_out, '*.tract')
        png = tmp_path / 'fig.png'
        rc = main(['plot-tract', str(tract), '--which', 'all',
                   '-o', str(png)])
        assert rc == 0
        assert png.stat().st_size > 0

    def test_plot_missing_file(self, capsys):
        assert main(['plot-tract', 'nope.tract']) == 1


class TestPolarBuild:
    def test_polar_file_written(self, tmp_path, capsys):
        polar = tmp_path / 'ba.polar'
        rc = main(['polar-build', 'ba', '-o', str(polar)])
        assert rc == 0
        assert polar.stat().st_size > 0
        assert 'steps @100 Hz' in capsys.readouterr().out


class TestMainErrorPaths:
    def test_unknown_speaker_returns_1(self, tmp_path, capsys):
        rc = main(['run', '--phonetic', 'ba', '-o', str(tmp_path),
                   '--no-video', '-s', 'no_such_speaker'])
        assert rc == 1
        err = capsys.readouterr().err
        assert err.startswith('ERROR:')

    def test_sampa_guard_error_aborts(self, tmp_path, capsys):
        # 'quack' is not engine SAMPA: the guard aborts before synthesis
        rc = main(['run', '--phonetic', 'quack', '-o', str(tmp_path),
                   '--no-video', '--sampa-guard', 'error'])
        assert rc == 1
        assert 'ERROR' in capsys.readouterr().err

    def test_debug_prints_traceback(self, tmp_path, capsys):
        # unknown speaker raises inside the pipeline: --debug shows the
        # full traceback, without it only the one-line ERROR
        rc = main(['--debug', 'run', '--phonetic', 'ba', '-o', str(tmp_path),
                   '--no-video', '-s', 'no_such_speaker'])
        assert rc == 1
        out = capsys.readouterr()
        assert 'Traceback' in out.err
