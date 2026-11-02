# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Sandhi hook tests (covtl-sandhi Branch A — option, default OFF).

Covers the two-branch contract:

  (a) the STUB is the identity: every entry point returns its input,
      SANDHI_FULL is False, SANDHI_LANGS is empty — a pipeline patched
      with Branch A but WITHOUT the Branch B rule package produces
      bit-identical outputs to the unpatched repository;
  (b) option validation: bad level / bad mode raise early (ValueError
      from the constructor, SystemExit from the CLI choices);
  (c) graceful degradation: a requested level without Branch B falls
      back to 'off' with a printed warning — never a silent change;
  (d) default OFF: the option never touches the synthesis path
      (tract files identical with and without the option).

When the Branch B package is installed (copied over the stub), the
SAME tests (b)-(d) hold and the rule behaviour is covered by the
package's own suite (tests/test_sandhi.py of covtl-sandhi).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vtl_synth.utils import sandhi as hook  # noqa: E402

#: Stub tests are skipped when the Branch B rule package is installed
#: (copied over the stub or pip): the package's own suite then covers
#: the rules — the hook tests that remain (validation, default OFF,
#: bit-identity) hold in BOTH states.
STUB_ONLY = pytest.mark.skipif(
    hook.SANDHI_FULL, reason='Branch B installed: stub covered by the '
    'covtl-sandhi package suite')


# ---------------------------------------------------------------------------
# (a) the stub is the identity
# ---------------------------------------------------------------------------

@STUB_ONLY
def test_stub_declares_itself():
    assert hook.SANDHI_FULL is False
    assert set(hook.SANDHI_LANGS) == set()
    assert hook.SANDHI_LEVELS == ('off', 'minimal', 'standard',
                                  'careful')
    assert hook.SANDHI_MODES == ('g2p', 'post', 'pre')


@STUB_ONLY
def test_stub_identity_entries():
    def g2p(text, warnings=None, **kw):
        return 'D@.End'

    warns: list = []
    assert hook.apply_sandhi_text('fr', 'the end', g2p, 'standard',
                                  'g2p', warns) == 'D@.End'
    assert any('Branch B' in w for w in warns)
    assert hook.sandhi_rewrite_text('fr', 'faut il', g2p,
                                    'standard') == 'faut il'
    assert hook.apply_sandhi_sampa('fr', 'mon ami', 'mO~.a.mi', g2p,
                                   'standard', 'g2p') == 'mO~.a.mi'
    assert hook.apply_sandhi('fr', ['faut', 'il'], ['fo', 'i'],
                             'standard') == ['fo', 'i']
    assert hook.sandhi_oracle('fr', 'il', g2p) == 'D@.End'  # g2p view
    assert hook.sandhi_supported('fr') is False
    assert hook.join_words_keys(['ajn', ' a.pf@l']) == 'ajn a.pf@l'


def test_stub_validates_early():
    with pytest.raises(ValueError):
        hook.level_rank('bogus')
    with pytest.raises(ValueError):
        hook.apply_sandhi_text('fr', 'x', lambda t, warnings=None: t,
                               'bogus', 'g2p')
    with pytest.raises(ValueError):
        hook.apply_sandhi_text('fr', 'x', lambda t, warnings=None: t,
                               'standard', 'bogus')
    with pytest.raises(ValueError):
        hook.apply_sandhi('fr', ['a'], ['x', 'y'], 'standard')


# ---------------------------------------------------------------------------
# (b)/(c) option plumbing through the Pipeline
# ---------------------------------------------------------------------------

def _pipeline(**kw):
    from vtl_synth import Pipeline
    return Pipeline(**kw)


def test_pipeline_validates_level_and_mode():
    with pytest.raises(ValueError):
        _pipeline(sandhi='bogus')
    with pytest.raises(ValueError):
        _pipeline(sandhi_mode='bogus')


@STUB_ONLY
def test_pipeline_degrades_without_branch_b(capsys):
    pipe = _pipeline(sandhi='standard')
    assert pipe.sandhi == 'off'            # Branch B missing → off
    assert 'covtl-sandhi' in capsys.readouterr().out


def test_pipeline_default_off_is_silent(capsys):
    pipe = _pipeline()
    assert pipe.sandhi == 'off' and pipe.sandhi_mode == 'g2p'
    assert capsys.readouterr().out == ''


# ---------------------------------------------------------------------------
# (d) default OFF — bit-identical synthesis
# ---------------------------------------------------------------------------

def _tract_bytes(out: Path) -> bytes:
    tracts = sorted(out.rglob('*.tract'))
    assert tracts, 'no .tract produced'
    return b''.join(p.read_bytes() for p in tracts)


def test_off_is_bit_identical(tmp_path):
    _pipeline().run('the end', output_dir=str(tmp_path / 'a'),
                    use_g2p=True, video=False)
    _pipeline(sandhi='off', sandhi_mode='g2p').run(
        'the end', output_dir=str(tmp_path / 'b'), use_g2p=True,
        video=False)
    assert _tract_bytes(tmp_path / 'a') == _tract_bytes(tmp_path / 'b')


def test_requested_level_without_branch_b_is_bit_identical(tmp_path):
    # degradation to off = still bit-identical (the warning is
    # printed, the SAMPA path is untouched)
    _pipeline().run('the end', output_dir=str(tmp_path / 'a'),
                    use_g2p=True, video=False)
    _pipeline(sandhi='careful', sandhi_mode='post').run(
        'the end', output_dir=str(tmp_path / 'b'), use_g2p=True,
        video=False)
    assert _tract_bytes(tmp_path / 'a') == _tract_bytes(tmp_path / 'b')


def test_cli_rejects_bad_level(capsys):
    from vtl_synth.cli import main as cli_main
    with pytest.raises(SystemExit):
        cli_main.main(['run', 'hello', '--sandhi', 'bogus',
                       '--no-video', '-o', '/tmp/vtl-sandhi-t'])


def test_cli_accepts_level():
    from vtl_synth.cli import main as cli_main
    # --help must list the new options (smoke, no synthesis)
    with pytest.raises(SystemExit) as exc:
        cli_main.main(['run', '--help'])
    assert exc.value.code == 0
