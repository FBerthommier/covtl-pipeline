# -*- coding: utf-8 -*-
r"""Registry integrity tests (install_speaker.py, 2026-09-11).

TestRegistry — pure checks on vtl_synth/data/speakers/ (files present,
hashes match registry.json, f0_default consistent with the constants
sources, s1/s2 differ from the JD3 102.216 Hz default).

NOTE (v1.1.0, tests allégés) : la classe TestInstallRestore du dépôt de
développement (idempotence install/restore en sous-processus réels,
swap de la ressource wheel partagée) n'est PAS migrée ici : elle est
lente (plusieurs installs + smoke de synthèse) et dépendait de backups
machine locaux. Elle reste disponible dans le dépôt de développement
P:\covtl-pipeline\tests\test_speaker_registry.py.
"""
import hashlib
import sys
from pathlib import Path

import pytest

from vtl_synth.core import speaker_registry as sr

PIPE_ROOT = Path(sr._PKG_ROOT).parent
INSTALL_TOOL = PIPE_ROOT / 'install_speaker.py'

JD3_CONSTANTS_HASH_PREFIX = '75ae0ba837ed106d'


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _load_constants_source(name):
    """Imports a registry constants source as an isolated module."""
    import importlib.util
    cpath = sr.constants_source_path(name)
    spec = importlib.util.spec_from_file_location(f'_chk_{name}', cpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses py3.9 need this
    spec.loader.exec_module(mod)
    return mod


class TestRegistry:
    def test_files_present(self):
        for name in sr.list_speakers():
            entry = sr.get_entry(name)
            assert (sr.REGISTRY_DIR / entry['speaker']).is_file(), name
            assert (sr.REGISTRY_DIR / entry['constants']).is_file(), name

    def test_hashes_match_registry(self):
        for name in sr.list_speakers():
            entry = sr.get_entry(name)
            assert sha256(sr.REGISTRY_DIR / entry['speaker']) \
                == entry['speaker_sha256'], name
            assert sha256(sr.REGISTRY_DIR / entry['constants']) \
                == entry['constants_sha256'], name

    def test_jd3_constants_is_the_reference(self):
        assert sr.get_entry('jd3')['constants_sha256'] \
            .startswith(JD3_CONSTANTS_HASH_PREFIX)

    def test_jd3_f0_is_102_216(self):
        assert sr.get_entry('jd3')['f0_default'] == pytest.approx(102.216)

    def test_s1_s2_f0_differ_from_jd3(self):
        # DVTD speakers are NOT JD3-derived on f0 (D14 was exactly this
        # hardcoded default staying at 102.216 for every speaker)
        assert sr.get_entry('s1')['f0_default'] == pytest.approx(114.908)
        assert sr.get_entry('s2')['f0_default'] == pytest.approx(181.008)
        for name in ('s1', 's2'):
            assert sr.get_entry(name)['f0_default'] \
                != pytest.approx(102.216), name

    def test_f0_default_matches_constants_source(self):
        for name in sr.list_speakers():
            mod = _load_constants_source(name)
            assert mod.SpeakerConfig().f0_default \
                == pytest.approx(sr.get_entry(name)['f0_default']), name

    def test_active_name_registered(self):
        assert sr.active_name() in sr.list_speakers()

    def test_announce_lists_all_layers(self):
        text = sr.describe()
        assert 'Speaker actif :' in text
        assert 'geometry:' in text and 'ortho:' in text
        assert 'audio wheel:' in text and 'video:' in text
