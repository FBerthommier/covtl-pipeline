# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
pipeline.py
===========
High-level orchestration: text -> SAMPA -> tract -> WAV -> MP4.

This module is the ``vtl-synth`` counterpart of the reference
repository's ``vtl_pipeline.core.pipeline``.  It keeps the
COVTL synthesis chain (Berthommier COVTL place model,
syltraj syllabic engine, TimedEnvelope source, orthogonal branch,
inter-word pauses) and adds:

  * an optional English g2p front-end (CMUdict -> engine SAMPA);
  * the F0 declination applied by the former ``synthesize_tract.py``;

Usage
-----
    from vtl_synth import Pipeline
    pipe = Pipeline()
    result = pipe.run("this is easy for us", output_dir="./out")

Equivalent command line::

    vtl-synth run "this is easy for us" -o ./out
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from vtl_synth.core.assemble_tract import AssembleTract
from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core.constants import TRACT_SR, SpeakerConfig
from vtl_synth.core.synth import synthesize_audio
from vtl_synth.utils.g2p import text_to_sampa
from vtl_synth.utils.setlang import (
    get_active_profile as _get_active_lang_profile,
    get_profile as _get_lang_profile,
    setlang as _setlang,
    text_to_sampa as _text_to_sampa_lang,
)

# Expressive prosody (v1.1.0, option — défaut OFF). Import non
# critique : indisponible → Pipeline(expressive=True) retombe sur la
# déclinaison monotone avec un avertissement.
try:
    from vtl_synth.core.syltraj import get_last_build as _get_last_build
    from vtl_synth.utils.prosody_f0 import (
        apply_expressive_f0 as _apply_expressive_f0,
        plan_expressive_text as _plan_expressive_text,
    )
    _EXPRESSIVE_OK = True
except Exception:                                        # pragma: no cover
    _EXPRESSIVE_OK = False


# ==========================================================================
# Result container
# ==========================================================================

@dataclass
class PipelineResult:
    """Artifacts produced by one Pipeline.run()."""
    sampa: str
    phrases: List[str]
    tract_path: Path
    wav_path: Path
    mp4_path: Optional[Path] = None
    transcript_path: Optional[Path] = None
    polar_path: Optional[Path] = None
    n_frames: int = 0
    duration_s: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def audio(self) -> np.ndarray:
        """The synthesized audio signal (read back from the WAV)."""
        import wave
        with wave.open(str(self.wav_path), 'rb') as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2')
        return pcm.astype(np.float64) / 32768.0


# ==========================================================================
# Helpers (ported verbatim from the former root synthesize_tract.py)
# ==========================================================================

def label_of(phrase: str) -> str:
    """Short label for a phrase."""
    keep = ''.join(ch if (ch.isalnum() or ch == '.') else '_'
                   for ch in phrase)
    return keep[:30].strip('_') or 'phrase'


def apply_f0_declination(glott400: np.ndarray,
                         f0_base: float = 102.216,
                         onset_gain: float = 1.03,
                         final_gain: float = 0.85,
                         ) -> np.ndarray:
    """Applies a declarative declination to the glottis F0 contour.

    French declarative F0 contour (reference: Jun & Fougeron 2002):
      1. Initialization at the base level
      2. Slight initial peak (+3%)
      3. Progressive declination across the phrase
      4. Low final fall (-15%)

    Detects phrase boundaries from the silences in rel_amp
    (rel_amp < 0.1 for > 80 frames = 200 ms @400 Hz).

    Modifies glott400 in place (column 0 = f0).
    """
    n = len(glott400)
    if n < 40:
        return glott400
    voiced = glott400[:, 6] > 0.1  # rel_amp > 0.1 = voiced

    # --- detect phrases: voiced spans separated by silences ---
    phrase_starts = []
    phrase_ends = []
    in_voice = False
    voice_start = 0
    gap = 0
    for t in range(n):
        if voiced[t]:
            if not in_voice:
                in_voice = True
                voice_start = t
            gap = 0
        else:
            if in_voice:
                gap += 1
                if gap > 80:  # 200 ms of silence = end of phrase
                    if voice_start < t - gap:
                        phrase_starts.append(voice_start)
                        phrase_ends.append(t - gap)
                    in_voice = False
    if in_voice:
        phrase_starts.append(voice_start)
        phrase_ends.append(n)

    for ps, pe in zip(phrase_starts, phrase_ends):
        if pe - ps < 40:
            continue
        # contour: linear declination onset -> final
        progress = np.linspace(0, 1, pe - ps)
        decl = onset_gain + (final_gain - onset_gain) * progress
        # smooth the onset (contour attack, no jump)
        ramp_len = min(10, len(decl) // 5)
        if ramp_len > 0:
            decl[:ramp_len] = np.linspace(1.0, decl[ramp_len - 1], ramp_len)
        glott400[ps:pe, 0] = f0_base * decl

    return glott400


def _write_wav_09(audio: np.ndarray, wav_path: Path) -> float:
    """Write a 44.1 kHz 16-bit mono WAV, normalized to 0.9 (legacy
    behaviour of synthesize_tract.py)."""
    audio = np.asarray(audio, dtype=np.float64)
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio / peak * 0.9
    pcm = (audio * 32767).astype('<i2')
    import wave
    with wave.open(str(wav_path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(pcm.tobytes())
    return len(audio) / 44100.0


# ==========================================================================
# Pipeline
# ==========================================================================

class Pipeline:
    """Text -> tract -> audio (+ video) orchestrator.

    Parameters
    ----------
    f0_hz, speaker, engine, use_orthogonal :
        Engine configuration, passed through to
        :func:`build_phrase_tract` (defaults = validated
        settings: JD3 speaker, syl engine, orthogonal branch on).
        ``f0_hz=None`` (default) resolves to ``f0_default`` of the
        installed constants — i.e. the active speaker of the registry
        (see vtl_synth.core.speaker_registry).
    lang :
        Active language profile (language pack; default ``en`` =
        the CMUdict gateway, i.e. the historical behaviour).
    t_cons_ms, t_voy_ms :
        Consonant / vowel gesture duration (ms).
    pause_short_ms, pause_long_ms :
        Inter-word (space) and end-of-sentence ('|') pause duration.
    expressive : bool
        Prosodie expressive (v1.1.0) : respiration syntaxique
        (pauses courtes aux frontières de blocs — aucune chaîne de
        mots coarticulés > ``max_chain_words``) et contour de F0
        sculpté (accents de hauteur sur les syllabes accentuées,
        reprise d'attaque par bloc, chute nucléaire). DÉFAUT OFF :
        sorties bit-identiques au mode monotone. N'agit que sur la
        colonne f0 du glottis et les durées de pause — jamais sur le
        tract. Requiert ``use_g2p=True`` (l'entrée phonétique n'a
        pas de structure syntaxique).
    """

    def __init__(self,
                 f0_hz: Optional[float] = None,
                 speaker: str = 'JD3',
                 engine: str = 'syl',
                 use_orthogonal: bool = True,
                 t_cons_ms: Optional[float] = None,
                 t_voy_ms: Optional[float] = None,
                 pause_short_ms: Optional[float] = None,
                 pause_long_ms: Optional[float] = None,
                 lang: str = 'en',
                 expressive: bool = False):
        # None -> f0_default of the installed constants, i.e. the active
        # speaker of the registry (D14 fix: was the hardcoded JD3
        # literal 102.216; JD3 behaviour is unchanged since its
        # f0_default is 102.216).
        if f0_hz is None:
            f0_hz = SpeakerConfig().f0_default
        self.f0_hz = f0_hz
        self.speaker = speaker
        self.engine = engine
        self.use_orthogonal = use_orthogonal
        # Multilingual support (language pack v1.0.7, merged with the
        # multi-speaker branch 2026-09-15): the active language profile
        # is selected at construction time. The g2p dispatch and the
        # F0 declination gains are taken from the profile; when
        # t_cons_ms / t_voy_ms / pause_*_ms are None (the CLI passes
        # explicit values), the LangProfile defaults apply.
        self.lang = lang
        try:
            _setlang(lang)
        except LookupError as exc:
            raise ValueError(str(exc)) from exc
        _profile = _get_lang_profile(lang)
        self._lang_profile = _profile
        if t_cons_ms is None:
            t_cons_ms = _profile.t_cons_ms if _profile is not None else 100.0
        if t_voy_ms is None:
            t_voy_ms = _profile.t_voy_ms if _profile is not None else 80.0
        if pause_short_ms is None:
            pause_short_ms = (_profile.pause_short_ms
                              if _profile is not None else 200.0)
        if pause_long_ms is None:
            pause_long_ms = (_profile.pause_long_ms
                             if _profile is not None else 320.0)
        self.t_cons_ms = t_cons_ms
        self.t_voy_ms = t_voy_ms
        self.pause_short_ms = pause_short_ms
        self.pause_long_ms = pause_long_ms
        # Prosodie expressive (v1.1.0, défaut OFF)
        self.expressive = bool(expressive)
        self._expressivity = getattr(_profile, 'expressivity', None)
        if self.expressive:
            if not _EXPRESSIVE_OK:
                print('[pipeline] prosody_f0 indisponible : '
                      'retombée sur la déclinaison monotone')
                self.expressive = False
            elif self._expressivity is None:
                print(f'[pipeline] pas de profil expressif pour '
                      f'{lang!r} : retombée sur la déclinaison monotone')
                self.expressive = False

    # ------------------------------------------------------------------
    # Full chain
    # ------------------------------------------------------------------

    def run(self,
            text: str,
            output_dir: str = 'out',
            use_g2p: bool = True,
            video: bool = True,
            fps: int = 25,
            scale: int = 2,
            label: Optional[str] = None,
            polar: bool = False) -> PipelineResult:
        """Synthesize ``text`` into .tract + .wav (+ .mp4).

        Parameters
        ----------
        text : str
            English text (g2p applied) or engine SAMPA when
            ``use_g2p=False``; phrases separated by '|' or sentence
            punctuation.
        output_dir : str
            Output directory (created; default ``out``).
        use_g2p : bool
            Convert orthographic English through CMUdict.
        video : bool
            Also render the sagittal MP4 (needs Pillow +
            imageio-ffmpeg).
        label : str, optional
            File stem (default: derived from the first phrase).
        """
        from vtl_synth.core.speaker_registry import announce
        announce(f0_used=self.f0_hz)

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        warnings: List[str] = []
        expressive = self.expressive and use_g2p
        if self.expressive and not use_g2p:
            warnings.append(
                'mode expressif ignoré : l\'entrée phonétique '
                '(use_g2p=False) n\'a pas de structure syntaxique')
            print(f'[pipeline] {warnings[-1]}')
        expressive_plans = None
        if expressive:
            # Respiration syntaxique + plan d'accents : le SAMPA
            # assemblé est celui du g2p de la langue, séparé en
            # groupes de souffle par le marqueur '%'.
            sampa, expressive_plans = _plan_expressive_text(
                text, self.lang, self._lang_profile.g2p_callable,
                self._expressivity, warnings)
        elif use_g2p:
            # Dispatch via the language registry (language pack): the
            # active profile (set at __init__ time via lang) selects
            # the appropriate g2p callable (en = CMUdict gateway).
            sampa = _text_to_sampa_lang(text, warnings)
        else:
            sampa = text.strip()
        phrases = [p.strip() for p in sampa.split('|') if p.strip()]
        if not phrases:
            raise ValueError(f'no phonetic content in: {text!r}')
        if expressive_plans is not None and \
                len(expressive_plans) != len(phrases):
            # garde-fou : le plan et le SAMPA doivent s'aligner
            expressive_plans = None

        # File stem from the *original* text (not the SAMPA), so that
        # "this is easy for us" -> this_is_easy_for_us.tract
        stem = (label or label_of(text)).rstrip('._') or 'output'
        # Conversion ms -> gesture steps (1 step = 10 ms @100 Hz)
        t_cons_steps = max(1, round(self.t_cons_ms / 10.0))
        t_voy_steps = max(1, round(self.t_voy_ms / 10.0))

        all_tracts, all_glottis, all_audio = [], [], []
        pause_breath_ms = None
        if self.expressive and self._expressivity is not None:
            pause_breath_ms = self._expressivity.pause_breath_ms
        for pi, phrase in enumerate(phrases):
            tract400, glott400 = build_phrase_tract(
                phrase,
                phrase_id=pi + 1,
                label=f'{stem}_{pi + 1}',
                output_dir=str(out_dir / 'phrases'),
                f0_hz=self.f0_hz,
                speaker=self.speaker,
                use_orthogonal=self.use_orthogonal,
                return_data=True,
                verbose=False,
                t_cons=t_cons_steps,
                t_voy=t_voy_steps,
                pause_short_ms=self.pause_short_ms,
                pause_long_ms=self.pause_long_ms,
                pause_breath_ms=pause_breath_ms,
            )
            # Prosodie F0 : expressive (accents + reprises + chute
            # nucléaire, plan aligné sur les blocs syltraj) ou
            # déclinaison monotone (language pack : gains du profil
            # actif).
            applied = False
            if expressive and expressive_plans is not None:
                last_build = _get_last_build()
                applied = _apply_expressive_f0(
                    glott400,
                    f0_base=self.f0_hz,
                    onset_gain=self._lang_profile.onset_gain,
                    final_gain=self._lang_profile.final_gain,
                    expr=self._expressivity,
                    chunk_plans=expressive_plans[pi],
                    block_info=last_build['block_info'],
                )
            if not applied:
                if self._lang_profile is not None:
                    glott400 = apply_f0_declination(
                        glott400,
                        f0_base=self.f0_hz,
                        onset_gain=self._lang_profile.onset_gain,
                        final_gain=self._lang_profile.final_gain,
                    )
                else:
                    glott400 = apply_f0_declination(glott400, self.f0_hz)
            all_tracts.append(tract400)
            all_glottis.append(glott400)
            all_audio.append(np.asarray(
                synthesize_audio(tract400, glott400), dtype=np.float64))

        tract_all = np.vstack(all_tracts)
        glott_all = np.vstack(all_glottis)
        audio_all = np.concatenate(all_audio)

        tract_path = out_dir / f'{stem}.tract'
        wav_path = out_dir / f'{stem}.wav'
        transcript_path = out_dir / f'{stem}.txt'
        polar_path = out_dir / f'{stem}.polar'

        AssembleTract.write_tract_file(
            tract_all, glott_all, str(tract_path), sr=int(TRACT_SR))
        duration_s = _write_wav_09(audio_all, wav_path)
        transcript_path.write_text(sampa + '\n', encoding='utf-8')

        result = PipelineResult(
            sampa=sampa,
            phrases=phrases,
            tract_path=tract_path,
            wav_path=wav_path,
            transcript_path=transcript_path,
            n_frames=int(tract_all.shape[0]),
            duration_s=duration_s,
            warnings=warnings,
        )

        if polar:
            # Intermediate .polar file: 100 Hz polar trajectories +
            # phoneme targets + per-phoneme timing, re-run with the
            # same engine parameters as the synthesis above (so the
            # .polar timeline matches the .tract / audio timeline).
            from vtl_synth.video.polar_video import build_polar, write_polar
            polar_data = build_polar(
                phrases, t_cons=t_cons_steps, t_voy=t_voy_steps,
                pause_short_ms=self.pause_short_ms,
                pause_long_ms=self.pause_long_ms)
            write_polar(polar_path, polar_data)
            result.polar_path = polar_path

        if video:
            if polar:
                from vtl_synth.video.polar_video import make_polar_video
                result.mp4_path = make_polar_video(
                    tract_path, polar_path, wav_path=wav_path,
                    out_path=out_dir / f'{stem}.mp4',
                    fps=fps, scale=scale,
                    work_dir=out_dir / 'temp_video')
            else:
                result.mp4_path = self.tract_to_mp4(
                    tract_path, wav_path,
                    out_path=out_dir / f'{stem}.mp4',
                    fps=fps, scale=scale,
                    work_dir=out_dir / 'temp_video')
        return result

    # ------------------------------------------------------------------
    # Audio only
    # ------------------------------------------------------------------

    def text_to_wav(self, text: str, output_dir: str = 'out',
                    use_g2p: bool = True,
                    label: Optional[str] = None) -> PipelineResult:
        """Same as :meth:`run` without the video step."""
        return self.run(text, output_dir=output_dir, use_g2p=use_g2p,
                        video=False, label=label)

    # ------------------------------------------------------------------
    # Video from existing files
    # ------------------------------------------------------------------

    @staticmethod
    def tract_to_mp4(tract_path, wav_path=None, out_path=None,
                     fps: int = 25, scale: int = 2, work_dir=None) -> Path:
        """Render a sagittal MP4 from an existing .tract (+ .wav).

        Port of the former root ``make_video.py``.
        """
        from vtl_synth.video.encoder import encode_mp4
        from vtl_synth.video.renderer import read_tract, render_frames

        tract_path = Path(tract_path)
        out_path = Path(out_path) if out_path is not None \
            else tract_path.with_suffix('.mp4')
        data, sr = read_tract(tract_path)
        png_dir, n_frames = render_frames(
            data, sr, fps=fps, scale=scale, work_dir=work_dir)
        mp4 = encode_mp4(png_dir, out_path, fps=fps, wav_path=wav_path)
        print(f'video: {mp4} ({n_frames} frames @{fps} Hz, '
              f'{mp4.stat().st_size / 1e6:.1f} MB)')
        return mp4
