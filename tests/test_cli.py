# -*- coding: utf-8 -*-
"""CLI and g2p unit tests (fast, no VTL synthesis)."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vtl_synth.utils.g2p import text_to_sampa, is_g2p_available
from vtl_synth.core.phonemes import (
    ARPA_TO_SAMPA,
    greedy_sampa_split,
    is_sampa_token,
)


# --------------------------------------------------------------------------
# phoneme tables
# --------------------------------------------------------------------------

def test_arpabet_table_covers_cmu_symbols():
    cmu = {'P', 'B', 'T', 'D', 'K', 'G', 'CH', 'JH', 'F', 'V', 'TH',
           'DH', 'S', 'Z', 'SH', 'ZH', 'HH', 'M', 'N', 'NG', 'L', 'R',
           'W', 'Y', 'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER',
           'EY', 'IH', 'IY', 'OW', 'OY', 'UH', 'UW'}
    assert cmu <= set(ARPA_TO_SAMPA)


def test_sampa_token_detection():
    assert is_sampa_token('ba')
    assert is_sampa_token('dZ')
    assert not is_sampa_token('quack')    # 'q' is not an engine key
    assert greedy_sampa_split('tSa') == ['tS', 'a']


# --------------------------------------------------------------------------
# syllabification (connected engine chains, g2p coarticulation fix)
# --------------------------------------------------------------------------

from vtl_synth.core.phonemes import keys_to_connected, sampa_to_connected


def test_syllabify_onset_maximization():
    # single intervocalic consonant -> onset of the next syllable
    assert keys_to_connected(['b', 'a', 'n', 'a', 'n', 'a']) == 'ba.na.na'
    # word-final consonants = coda of the last syllable
    assert keys_to_connected(['f', 'O', 'R']) == 'fOR'
    assert keys_to_connected(['@', 's']) == '@s'
    # multi-char keys stay atomic
    assert keys_to_connected(['tS', 'a', 'z']) == 'tSaz'
    assert keys_to_connected(['dZ', 'a', 'Z', 'a']) == 'dZa.Za'
    # clusters split coda/onset
    assert keys_to_connected(['a', 'l', 'b', 'E', 'R', 't']) == 'al.bERt'
    # no vowel at all: kept as a single group
    assert keys_to_connected(['s', 't']) == 'st'


def test_sampa_to_connected_strips_inner_spaces():
    assert sampa_to_connected('D i s') == 'Dis'
    assert sampa_to_connected('b a n a n a') == 'ba.na.na'
    # non-segmentable input unchanged
    assert sampa_to_connected('quack') == 'quack'


# --------------------------------------------------------------------------
# g2p
# --------------------------------------------------------------------------

@pytest.mark.skipif(not is_g2p_available(), reason='cmudict not installed')
def test_text_to_sampa_this_is_easy():
    out = text_to_sampa('this is easy for us', warnings=[])
    # adjacent words are CONNECTED with '.' so the engine
    # coarticulates across word boundaries: the whole phrase is one
    # chain, no inter-word pause inside it
    assert out == 'Dis.iz.i.zi.fOR.@s'
    assert ' ' not in out


@pytest.mark.skipif(not is_g2p_available(), reason='cmudict not installed')
def test_text_to_sampa_comma_keeps_word_pause():
    # comma = short inter-word pause (space); plain adjacent words
    # stay connected
    out = text_to_sampa('ab, cd', warnings=[])
    assert ' ' in out          # pause after the comma
    assert out.count(' ') == 1
    assert '.' in out.replace('|', '')


@pytest.mark.skipif(not is_g2p_available(), reason='cmudict not installed')
def test_text_to_sampa_phrase_separator():
    out = text_to_sampa('ba da. ga', warnings=[])
    assert '|' in out
    assert out.count('|') == 1


# --------------------------------------------------------------------------
# CLI plumbing (parser only, no synthesis)
# --------------------------------------------------------------------------

def test_cli_parser_requires_command():
    from vtl_synth.cli.main import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_cli_help_runs():
    res = subprocess.run(
        [sys.executable, '-m', 'vtl_synth.cli.main', '--help'],
        capture_output=True, text=True, cwd=str(ROOT))
    assert res.returncode == 0
    assert 'run' in res.stdout
