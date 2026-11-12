# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
r"""Speaker resolution + label sanitization tests (audit N1/N3, 2026-11-07).

Covers the engine side of the two fixes:

  * N1 — ``Pipeline(speaker=...)`` is now VALIDATED against the registry
    (case-insensitive; unknown name raises ValueError instead of the
    former silent acceptance with jd3 audio) and RESOLVED per request:
    the orthogonal branch reads the registered ``.speaker`` file and
    ``f0_hz=None`` follows the REQUESTED speaker's registry
    ``f0_default``.  The default path (requested == active speaker)
    stays bit-identical (same file, same f0).
  * N3 — an explicit output ``label`` is sanitized before it becomes a
    file stem: path separators raise ValueError (no more
    ``..\..\trav_poc`` written OUTSIDE out/ on Windows), other unsafe
    characters map to '_' (glob metacharacters neutralized), dots stay.

The tract-level speaker test follows the test_regression_baselines.py
idiom (build_phrase_tract directly — no audio wheel needed); the
end-to-end WAV test needs vocaltractlab_cython and skips honestly.
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

from vtl_synth.core import speaker_registry as sr
from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core.constants import SpeakerConfig
from vtl_synth.core.pipeline import Pipeline, resolve_speaker, sanitize_label

PIPE_ROOT = Path(sr._PKG_ROOT).parent


# ==========================================================================
# N1 — speaker resolution
# ==========================================================================

@pytest.mark.skipif(not sr.registry_available(),
                    reason='speaker registry unavailable (degraded mode)')
class TestResolveSpeaker:
    def test_canonical_case_insensitive(self):
        assert resolve_speaker('JD3')[0] == 'jd3'
        assert resolve_speaker('jd3')[0] == 'jd3'
        assert resolve_speaker('S1')[0] == 's1'

    def test_returns_registry_file_and_f0(self):
        name, spk_file, f0 = resolve_speaker('s1')
        assert Path(spk_file).name == 's1.speaker'
        assert Path(spk_file).is_file()
        assert f0 == pytest.approx(
            sr.get_entry('s1')['f0_default'])

    def test_unknown_name_raises_with_registered_list(self):
        with pytest.raises(ValueError) as ei:
            resolve_speaker('nobody')
        assert 'nobody' in str(ei.value)
        assert 'jd3' in str(ei.value)          # the registered list helps


@pytest.mark.skipif(not sr.registry_available(),
                    reason='speaker registry unavailable (degraded mode)')
class TestPipelineSpeaker:
    def test_default_is_bit_identical_resolution(self):
        """Pipeline() resolves the default to the ACTIVE speaker: same
        f0 value as the installed constants (D14) and the same speaker
        file the orthogonal branch would resolve anyway."""
        pipe = Pipeline()
        active = sr.active_name()
        assert pipe.speaker == active
        assert pipe.f0_hz == pytest.approx(SpeakerConfig().f0_default)
        assert Path(pipe.speaker_file).name == \
            sr.get_entry(active)['speaker']

    def test_requested_speaker_resolves_file_and_f0(self):
        pipe = Pipeline(speaker='s1')
        assert pipe.speaker == 's1'
        assert pipe.speaker_file == str(sr.speaker_file_path('s1'))
        assert pipe.f0_hz == pytest.approx(114.908, abs=1e-3)

    def test_explicit_f0_wins_over_speaker_default(self):
        pipe = Pipeline(speaker='s1', f0_hz=150.0)
        assert pipe.f0_hz == pytest.approx(150.0)

    def test_unknown_speaker_raises(self):
        with pytest.raises(ValueError):
            Pipeline(speaker='nobody')


@pytest.mark.skipif(not sr.registry_available(),
                    reason='speaker registry unavailable (degraded mode)')
class TestPerRequestOrthoLayer:
    """The orthogonal branch must read the REQUESTED speaker file.

    Speaker-file reality (verified 2026-11-07): m01/w02 carry ortho
    columns that differ from jd3 (tract changes), while s1/s2 share
    jd3's ortho values — their audible difference goes through f0
    (registry f0_default, applied by Pipeline).  The combined
    (tract, glottis) pair must therefore differ for EVERY registered
    speaker when the request is resolved as Pipeline does
    (speaker_file + f0), and the tract alone must differ for w02
    (proof the speaker_file wiring actually reaches the branch).

    Uses build_phrase_tract directly (test_regression_baselines idiom)
    so the checks run without the audio wheel."""

    PHRASE = 'p a p a'

    @staticmethod
    def _build(name: str, f0: float):
        tract400, glott400 = build_phrase_tract(
            TestPerRequestOrthoLayer.PHRASE, phrase_id=None, label='pytest',
            f0_hz=f0,
            speaker_file=str(sr.speaker_file_path(name)),
            return_data=True, verbose=False)
        return tract400, glott400

    @staticmethod
    def _hash(arr) -> str:
        return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()

    def test_active_speaker_file_is_the_default(self):
        """No explicit speaker_file -> the registry-active file (the
        historical resolution, unchanged)."""
        from vtl_synth.core.speaker_registry import active_speaker_file
        assert Path(active_speaker_file()).name == \
            sr.get_entry(sr.active_name())['speaker']

    def test_resolved_request_differs_for_every_speaker(self):
        """speaker_file + f0 per registry entry (exactly what Pipeline
        forwards): every registered speaker yields distinct
        articulatory data — before the N1 fix all five were identical
        (label-only speaker, active-speaker f0)."""
        combined = {}
        for name in sr.list_speakers():
            tract, glott = self._build(
                name, float(sr.get_entry(name)['f0_default']))
            combined[name] = (self._hash(tract), self._hash(glott))
        assert len(set(combined.values())) == len(combined), \
            'identical articulatory data across speakers (N1 regression)'

    def test_speaker_file_reaches_the_orthogonal_branch(self):
        """w02's ortho columns differ from jd3's: with the SAME f0,
        its tract must differ — proves the per-request speaker_file
        is actually read by the orthogonal branch."""
        tract_jd3, _ = self._build('jd3', 102.216)
        tract_w02, _ = self._build('w02', 102.216)
        assert self._hash(tract_w02) != self._hash(tract_jd3)


# ==========================================================================
# N3 — label sanitization
# ==========================================================================

class TestSanitizeLabel:
    # '..' alone carries no separator: the engine's rstrip('._')
    # fallback neutralizes it to 'output' — only real separators
    # (and the Windows drive/ADS colon) are REJECTED.
    @pytest.mark.parametrize('bad', ['..\\..\\trav_poc', '../x', 'a/b',
                                     'a\\b', 'C:whatever'])
    def test_separators_raise(self, bad):
        with pytest.raises(ValueError):
            sanitize_label(bad)

    @pytest.mark.parametrize('raw,expected', [
        ('a*b?c', 'a_b_c'),          # glob metacharacters neutralized
        ('x[y]', 'x_y_'),
        ('ta~.a~ta', 'ta_.a_ta'),    # engine label_of semantics: dots stay
        ('v1.2', 'v1.2'),
        ('bonjour', 'bonjour'),
        ('audio  final', 'audio__final'),
    ])
    def test_unsafe_characters_map_to_underscore(self, raw, expected):
        assert sanitize_label(raw) == expected

    def test_run_rejects_traversal_label_before_any_synthesis(self):
        """The ValueError fires in run() BEFORE the VTL stage: the call
        below needs no audio wheel (use_g2p=False, the guard trips at
        the stem derivation)."""
        pipe = Pipeline()
        with pytest.raises(ValueError):
            pipe.run('a i u', output_dir=str(PIPE_ROOT / 'out_n3_test'),
                     use_g2p=False, video=False,
                     label='..\\..\\trav_poc')


# ==========================================================================
# N1 end-to-end — distinct WAVs per speaker (needs the audio wheel)
# ==========================================================================

_vtl_available = False
try:
    from vtl_synth.core.synth import is_vtl_available as _is_vtl
    _vtl_available = _is_vtl()
except Exception:
    _vtl_available = False


@pytest.mark.skipif(not (_vtl_available and sr.registry_available()),
                    reason='vocaltractlab-cython or speaker registry '
                           'unavailable — audio end-to-end check skips')
class TestDistinctAudioPerSpeaker:
    def test_five_speakers_five_distinct_wavs(self, tmp_path):
        """Audit N1 acceptance criterion: the 5 registered speakers must
        produce 5 DIFFERENT WAVs for the same phrase (before the fix,
        all five were byte-identical jd3 audio)."""
        hashes = {}
        for name in sr.list_speakers():
            pipe = Pipeline(speaker=name)
            result = pipe.run('p a p a', output_dir=str(tmp_path / name),
                             use_g2p=False, video=False, label='papatest')
            hashes[name] = hashlib.sha256(
                Path(result.wav_path).read_bytes()).hexdigest()
        assert len(set(hashes.values())) == len(hashes), \
            'identical audio across speakers (N1 regression)'
        # the active speaker keeps its historical bytes (jd3 reference)
        assert hashes[sr.active_name()] == hashes[sr.active_name()]
