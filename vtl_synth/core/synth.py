# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
synth.py
=========
Audio synthesis (WAV) and visualization (SVG/video) via VocalTractLab.

This module is the single entry point to Peter Birkholz's VocalTractLab
SDK, via Paul Krug's Python wrapper (vocaltractlab-cython).
It permanently replaces any former vlam.py module or separate
synthesis file.

Three capabilities exposed:

  1. **Audio**: synth_block → WAV (44100 Hz, 16-bit PCM)
  2. **Images**: tract_state → SVG (sagittal view of the vocal tract)
  3. **Video**: SVG sequence → MP4 (via ffmpeg)

Functions imported from vocaltractlab_cython (12 out of 35+):

  +---------------------------+------------------------------------------+
  | VTL function              | Usage in the Berthommier pipeline         |
  +===========================+==========================================+
  | synth_block               | (tract, glottis) → audio float64          |
  | tract_state_to_svg        | tract_state(19,) → SVG file              |
  | get_constants             | → dict (sr_audio, n_tract_params, …)     |
  | get_version               | → str                                     |
  | active_speaker            | → str (current .speaker path)              |
  | get_param_info            | → list[dict] (names, bounds, units)       |
  | get_shape                 | (name, 'tract'|'glottis') → ndarray       |
  | get_cross_sections        | tract_state → dict (areas, positions)     |
  | get_centerline            | tract_state → (129, 2) ndarray             |
  | get_outlines              | tract_state → dict (surfaces)             |
  | tract_state_to_transfer   | tract_state → dict (magnitude, phase)      |
  |    _function              |   (acoustic analysis)                      |
  +---------------------------+------------------------------------------+

Not imported (native VTL pipeline, not needed here):
gesture_file_to_audio, motor_file_to_audio_file,
phoneme_file_to_gesture_file, set_anatomy_*, tds_*,
synthesis_*, glottis_*, save_speaker, etc.

Minimal installation
---------------------
    pip install vocaltractlab-cython==0.0.17

See INSTALL_VTL.md for the complete procedure.

References
----------
- Paul Krug, VocalTractLab-Python : https://github.com/paul-krug/VocalTractLab-Python
- PyPI : https://pypi.org/project/vocaltractlab-cython/
- Peter Birkholz, VocalTractLab 2.4 : https://www.vocaltractlab.de
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ==========================================================================
# Conditional import — vocaltractlab_cython is optional
# ==========================================================================

_VTL_AVAILABLE = False
_VTL_INIT_ERROR: Optional[str] = None

try:
    from vocaltractlab_cython import (  # noqa: F401
        synth_block as _vtl_synth_block,
        tract_state_to_svg as _vtl_tract_state_to_svg,
        tract_state_to_transfer_function as _vtl_tract_state_to_transfer_function,
        get_constants as _vtl_get_constants,
        get_version as _vtl_get_version,
        get_param_info as _vtl_get_param_info,
        get_shape as _vtl_get_shape,
        VtlApiError,
    )
    _VTL_AVAILABLE = True
except ImportError as _e:
    _VTL_INIT_ERROR = str(_e)
    _vtl_synth_block = None
    _vtl_tract_state_to_svg = None
    _vtl_tract_state_to_transfer_function = None
    _vtl_get_constants = None
    _vtl_get_version = None
    _vtl_get_param_info = None
    _vtl_get_shape = None
    VtlApiError = RuntimeError
except Exception as _e:
    _VTL_INIT_ERROR = str(_e)
    _vtl_synth_block = None
    _vtl_tract_state_to_svg = None
    _vtl_tract_state_to_transfer_function = None
    _vtl_get_constants = None
    _vtl_get_version = None
    _vtl_get_param_info = None
    _vtl_get_shape = None
    VtlApiError = RuntimeError

# Optional analysis bindings: active_speaker / get_cross_sections /
# get_centerline / get_outlines only exist in vocaltractlab-cython
# >= 0.0.16.  The synthesis path (synth_block, tract_state_to_svg,
# get_shape, ...) never touches them, so they degrade gracefully on
# older wheels — 0.0.13 is the last version installable under
# Python 3.9 on Windows (PyPI wheels start at cp310).  The matching
# getters raise a clear error instead of failing the whole module.
try:
    from vocaltractlab_cython import (
        active_speaker as _vtl_active_speaker,
    )
except ImportError:                                 # pragma: no cover
    _vtl_active_speaker = None
try:
    from vocaltractlab_cython import (
        get_cross_sections as _vtl_get_cross_sections,
    )
except ImportError:                                 # pragma: no cover
    _vtl_get_cross_sections = None
try:
    from vocaltractlab_cython import (
        get_centerline as _vtl_get_centerline,
    )
except ImportError:                                 # pragma: no cover
    _vtl_get_centerline = None
try:
    from vocaltractlab_cython import (
        get_outlines as _vtl_get_outlines,
    )
except ImportError:                                 # pragma: no cover
    _vtl_get_outlines = None


def _require_optional(symbol: str, api_name: str):
    """Resolve an optional VTL binding or raise a clear error."""
    fn = globals()[symbol]
    if fn is None:
        raise RuntimeError(
            f'{api_name}() needs vocaltractlab-cython >= 0.0.16 '
            f'(the installed wheel does not provide it)')
    return fn


def is_vtl_available() -> bool:
    """Checks whether vocaltractlab_cython is available and functional.

    Returns
    -------
    bool
        True if the VTL API is importable and initializable.
    """
    return _VTL_AVAILABLE


def get_vtl_error() -> Optional[str]:
    """Returns the VTL import error message, or None if OK."""
    return _VTL_INIT_ERROR


def require_vtl() -> None:
    """Raises a clear error if VTL is not installed.

    Raises
    ------
    ImportError
        With a detailed installation message.
    """
    if not _VTL_AVAILABLE:
        msg = (
            "vocaltractlab-cython is required for this operation.\n\n"
            "Installation:\n"
            "  pip install vocaltractlab-cython==0.0.17\n\n"
            "Reference:\n"
            "  https://github.com/paul-krug/VocalTractLab-Python\n"
            "  https://pypi.org/project/vocaltractlab-cython/\n"
        )
        if _VTL_INIT_ERROR:
            msg += f"\nDetail: {_VTL_INIT_ERROR}"
        raise ImportError(msg)


# ==========================================================================
# 1. Audio: WAV synthesis
# ==========================================================================

def synthesize_audio(
    tract_parameters: np.ndarray,
    glottis_parameters: np.ndarray,
    output_wav: Optional[str] = None,
    state_samples: Optional[int] = None,
    normalize: bool = True,
    sample_rate: int = 44100,
) -> np.ndarray:
    """Synthesizes audio from tract and glottis parameters.

    Wraps vocaltractlab_cython.synth_block with:
      - Automatic computation of state_samples if not provided
      - Optional normalization
      - Optional WAV saving (16-bit PCM)

    Parameters
    ----------
    tract_parameters : np.ndarray, shape (n_frames, 19)
        Vocal tract parameters per frame (400 Hz).
    glottis_parameters : np.ndarray, shape (n_frames, 11)
        Glottal parameters per frame (400 Hz).
    output_wav : str, optional
        Path of the output WAV file.
    state_samples : int, optional
        Number of audio samples per tract frame.
        Default: sample_rate // 400 (→ 110 at 44100 Hz).
    normalize : bool
        Normalize audio to [-1, 1] before WAV export.
    sample_rate : int
        Audio sample rate (Hz).

    Returns
    -------
    np.ndarray
        Audio signal (float64), shape (n_samples,).

    Raises
    ------
    ImportError
        If vocaltractlab-cython is not installed.
    VtlApiError
        If VTL synthesis fails.
    """
    require_vtl()

    if state_samples is None:
        # Tract frames per audio block: TRACT_SR (400 Hz) is the single
        # source (HARD-002), not a literal.
        from .constants import TRACT_SR
        state_samples = sample_rate // int(TRACT_SR)

    audio = _vtl_synth_block(
        tract_parameters=tract_parameters,
        glottis_parameters=glottis_parameters,
        state_samples=state_samples,
        verbose_api=False,
    )

    if output_wav is not None:
        _write_wav(audio, output_wav, sample_rate=sample_rate,
                   normalize=normalize)

    return audio


def synthesize_to_wav(
    tract_path: str,
    output_wav: str,
    sample_rate: int = 44100,
) -> np.ndarray:
    """Synthesizes audio from an existing .tract file.

    Parameters
    ----------
    tract_path : str
        Path to a .tract file (native VTL format, 19+11 columns).
    output_wav : str
        Path of the output WAV file.
    sample_rate : int
        Sample rate (Hz).

    Returns
    -------
    np.ndarray
        Synthesized audio signal.
    """
    require_vtl()

    # Read the .tract file (19 tract + 11 glottis = 30 columns)
    data = np.loadtxt(tract_path)
    if data.ndim != 2 or data.shape[1] < 19:
        raise ValueError(
            f"Invalid .tract file: expected (n, >=19), "
            f"got {data.shape}"
        )

    tract = data[:, :19]
    glottis = data[:, 19:30] if data.shape[1] >= 30 else np.zeros(
        (data.shape[0], 11), dtype=np.float64
    )

    return synthesize_audio(
        tract, glottis,
        output_wav=output_wav,
        sample_rate=sample_rate,
    )


# ==========================================================================
# 2. Images: vocal tract SVG
# ==========================================================================

def render_tract_svg(
    tract_state: np.ndarray,
    svg_path: str,
) -> None:
    """Exports a vocal tract state to an SVG file.

    Parameters
    ----------
    tract_state : np.ndarray, shape (19,)
        Vocal tract state (19 VTL parameters).
    svg_path : str
        Path of the output SVG file.

    Raises
    ------
    ImportError
        If vocaltractlab-cython is not installed.
    ValueError
        If tract_state does not have 19 elements.
    """
    require_vtl()

    tract_state = np.asarray(tract_state, dtype=np.float64).ravel()
    if len(tract_state) != 19:
        raise ValueError(
            f"tract_state must have 19 elements, got {len(tract_state)}"
        )

    _vtl_tract_state_to_svg(tract_state, svg_path)
    logger.debug('SVG exported: %s', svg_path)


def render_tract_svgs(
    tract_parameters: np.ndarray,
    output_dir: str,
    prefix: str = 'frame',
    step: int = 1,
) -> List[str]:
    """Exports a sequence of vocal tract states to SVG files.

    Parameters
    ----------
    tract_parameters : np.ndarray, shape (n_frames, 19)
        Tract parameters per frame.
    output_dir : str
        Output directory (created if necessary).
    prefix : str
        File prefix (default: 'frame').
    step : int
        One image every `step` frames (default: 1 = all).

    Returns
    -------
    list[str]
        List of generated SVG paths.
    """
    require_vtl()

    os.makedirs(output_dir, exist_ok=True)
    svg_paths = []
    for i in range(0, tract_parameters.shape[0], step):
        path = os.path.join(output_dir, f'{prefix}_{i:05d}.svg')
        render_tract_svg(tract_parameters[i], path)
        svg_paths.append(path)

    logger.info('%d SVGs exported to %s (step=%d)',
                len(svg_paths), output_dir, step)
    return svg_paths


# ==========================================================================
# 3. Video: SVG → MP4 via ffmpeg
# ==========================================================================

def svgs_to_video(
    svg_dir: str,
    output_video: str,
    frame_rate: float = 25.0,
    resolution: Tuple[int, int] = (800, 600),
    ffmpeg_path: str = 'ffmpeg',
) -> str:
    """Converts a sequence of SVG files to an MP4 video.

    Uses ffmpeg to convert the SVGs to PNG images and then
    to an H.264 video.

    Parameters
    ----------
    svg_dir : str
        Directory containing the SVG files (sorted by name).
    output_video : str
        Path of the output video file (.mp4).
    frame_rate : float
        Frames per second (default: 25).
    resolution : tuple[int, int]
        Resolution (width, height) in pixels.
    ffmpeg_path : str
        Path to the ffmpeg executable.

    Returns
    -------
    str
        Path of the generated video file.

    Raises
    ------
    FileNotFoundError
        If ffmpeg is not found.
    subprocess.CalledProcessError
        If the conversion fails.
    """
    # Check ffmpeg
    try:
        subprocess.run([ffmpeg_path, '-version'], capture_output=True,
                       check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise FileNotFoundError(
            f"ffmpeg not found ({ffmpeg_path}).\n"
            f"Installation: apt install ffmpeg / brew install ffmpeg"
        )

    svg_files = sorted(
        f for f in os.listdir(svg_dir) if f.endswith('.svg')
    )
    if not svg_files:
        raise ValueError(f'No SVG files in {svg_dir}')

    w, h = resolution

    # Step 1: SVG → PNG
    png_pattern = os.path.join(svg_dir, 'frame_%05d.png')
    cmd_svg_to_png = [
        ffmpeg_path, '-y',
        '-framerate', str(frame_rate),
        '-i', os.path.join(svg_dir, '%*.svg'),
        '-vf', f'scale={w}:{h}',
        '-start_number', '0',
        png_pattern,
    ]
    subprocess.run(cmd_svg_to_png, capture_output=True, check=True)

    # Step 2: PNG → MP4
    cmd_png_to_mp4 = [
        ffmpeg_path, '-y',
        '-framerate', str(frame_rate),
        '-i', png_pattern,
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        output_video,
    ]
    subprocess.run(cmd_png_to_mp4, capture_output=True, check=True)

    # Clean up intermediate PNGs
    for f in os.listdir(svg_dir):
        if f.endswith('.png'):
            os.remove(os.path.join(svg_dir, f))

    logger.info('Video generated: %s (%d frames, %.1f fps)',
                output_video, len(svg_files), frame_rate)
    return output_video


def synthesize_video(
    tract_parameters: np.ndarray,
    glottis_parameters: np.ndarray,
    output_video: str,
    output_wav: Optional[str] = None,
    svg_step: int = 1,
    frame_rate: float = 25.0,
    resolution: Tuple[int, int] = (800, 600),
    state_samples: Optional[int] = None,
    sample_rate: int = 44100,
    tmp_dir: Optional[str] = None,
) -> Tuple[str, Optional[np.ndarray]]:
    """Synthesizes audio + video of the vocal tract.

    Full pipeline:
      1. Export tract states to SVG (one per `svg_step` frames)
      2. Convert the SVGs to an MP4 video (via ffmpeg)
      3. Synthesize the WAV audio (via synth_block)

    Parameters
    ----------
    tract_parameters : np.ndarray, shape (n_frames, 19)
    glottis_parameters : np.ndarray, shape (n_frames, 11)
    output_video : str
        Path of the output video file (.mp4).
    output_wav : str, optional
        Path of the output WAV file (optional).
    svg_step : int
        One SVG image every `svg_step` frames.
    frame_rate : float
        Frames per second for the video.
    resolution : tuple[int, int]
        Resolution (width, height) in pixels.
    state_samples : int, optional
        Audio samples per tract frame.
    sample_rate : int
        Audio sample rate (Hz).
    tmp_dir : str, optional
        Temporary directory for SVGs (cleaned up afterwards).

    Returns
    -------
    tuple[str, np.ndarray | None]
        (video_path, audio | None)
    """
    import tempfile

    require_vtl()

    # 1. SVG
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix='vtl_svg_')

    render_tract_svgs(tract_parameters, tmp_dir, step=svg_step)

    # 2. Video
    video_path = svgs_to_video(
        tmp_dir, output_video,
        frame_rate=frame_rate, resolution=resolution,
    )

    # 3. Audio
    audio = None
    if output_wav is not None:
        audio = synthesize_audio(
            tract_parameters, glottis_parameters,
            output_wav=output_wav,
            state_samples=state_samples,
            sample_rate=sample_rate,
        )

    # Clean up
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return video_path, audio


# ==========================================================================
# 4. VTL information
# ==========================================================================

def get_vtl_info() -> Dict:
    """Returns information about the VTL installation.

    Returns
    -------
    dict
        Keys: version, speaker, sr_audio, sr_internal,
        n_tract_params, n_glottis_params, n_samples_per_state,
        n_tube_sections, available.
    """
    if not _VTL_AVAILABLE:
        return {'available': False}

    constants = _vtl_get_constants()
    return {
        'available': True,
        'version': _vtl_get_version(),
        'speaker': _vtl_active_speaker(),
        'sr_audio': constants.get('sr_audio', 44100),
        'sr_internal': constants.get('sr_internal', 400.0),
        'n_tract_params': constants.get('n_tract_params', 19),
        'n_glottis_params': constants.get('n_glottis_params', 11),
        'n_samples_per_state': constants.get('n_samples_per_state', 110),
        'n_tube_sections': constants.get('n_tube_sections', 40),
    }


# ==========================================================================
# 5. Direct access to VTL functions (for advanced use)
# ==========================================================================

def get_tract_param_info() -> List[Dict]:
    """Returns information about the 19 VTL tract parameters.

    Returns
    -------
    list[dict]
        Each dict contains: name, description, unit, min, max, default.
    """
    require_vtl()
    return _vtl_get_param_info('tract')


def get_glottis_param_info() -> List[Dict]:
    """Returns information about the 11 VTL glottis parameters.

    Returns
    -------
    list[dict]
    """
    require_vtl()
    return _vtl_get_param_info('glottis')


def get_vowel_shape(name: str) -> np.ndarray:
    """Returns the 19 tract parameters for a named vowel.

    Equivalent to vocaltractlab_cython.get_shape(name, 'tract').

    Parameters
    ----------
    name : str
        Name of the vowel (e.g. 'a', 'i', 'u', 'e', 'o', …).

    Returns
    -------
    np.ndarray, shape (19,)
        Default tract parameters for this vowel.
    """
    require_vtl()
    return _vtl_get_shape(name, 'tract')


def get_glottis_shape(name: str) -> np.ndarray:
    """Returns the 11 glottis parameters for a named configuration.

    Parameters
    ----------
    name : str
        Name of the glottal configuration.

    Returns
    -------
    np.ndarray, shape (11,)
    """
    require_vtl()
    return _vtl_get_shape(name, 'glottis')


def get_cross_sections(tract_state: np.ndarray) -> Dict:
    """Returns the areas and positions of the vocal tract sections.

    Parameters
    ----------
    tract_state : np.ndarray, shape (19,)

    Returns
    -------
    dict
        Keys: area (cm²), position (cm).
    """
    require_vtl()
    fn = _require_optional('_vtl_get_cross_sections', 'get_cross_sections')
    return fn(np.asarray(tract_state, dtype=np.float64).ravel())


def get_centerline(tract_state: np.ndarray) -> np.ndarray:
    """Returns the vocal tract centerline.

    Parameters
    ----------
    tract_state : np.ndarray, shape (19,)

    Returns
    -------
    np.ndarray, shape (129, 2)
        (x, y) coordinates of the centerline.
    """
    require_vtl()
    fn = _require_optional('_vtl_get_centerline', 'get_centerline')
    return fn(np.asarray(tract_state, dtype=np.float64).ravel())


def get_outlines(tract_state: np.ndarray) -> Dict:
    """Returns the vocal tract outlines.

    Parameters
    ----------
    tract_state : np.ndarray, shape (19,)

    Returns
    -------
    dict
        Keys: upper, lower, tongue, epiglottis, …
    """
    require_vtl()
    fn = _require_optional('_vtl_get_outlines', 'get_outlines')
    return fn(np.asarray(tract_state, dtype=np.float64).ravel())


def get_transfer_function(
    tract_state: np.ndarray,
    n_spectrum_samples: int = 8192,
) -> Dict[str, np.ndarray]:
    """Computes the vocal tract transfer function.

    Useful for acoustic analysis (magnitude/phase spectrum).

    Parameters
    ----------
    tract_state : np.ndarray, shape (19,)
    n_spectrum_samples : int
        Number of spectrum points (default: 8192).

    Returns
    -------
    dict
        Keys: magnitude_spectrum, phase_spectrum, frequency_axis.
    """
    require_vtl()
    return _vtl_tract_state_to_transfer_function(
        np.asarray(tract_state, dtype=np.float64).ravel(),
        n_spectrum_samples=n_spectrum_samples,
        save_magnitude_spectrum=True,
        save_phase_spectrum=True,
    )


def get_active_speaker() -> str:
    """Returns the path of the currently loaded .speaker file.

    Returns
    -------
    str
        Absolute path to the .speaker file (e.g. JD3.speaker).
    """
    require_vtl()
    fn = _require_optional('_vtl_active_speaker', 'get_active_speaker')
    return fn()


# ==========================================================================
# Internals
# ==========================================================================

def _write_wav(
    audio: np.ndarray,
    path: str,
    sample_rate: int = 44100,
    normalize: bool = True,
) -> None:
    """Writes a 16-bit PCM WAV file."""
    try:
        from scipy.io.wavfile import write
    except ImportError:
        # Fallback without scipy: numpy raw + minimal WAV header
        _write_wav_raw(audio, path, sample_rate, normalize)
        return

    if normalize:
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 32767
        else:
            audio = np.zeros_like(audio)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write(path, sample_rate, audio.astype(np.int16))
    logger.info('WAV written: %s (%d samples, %d Hz)',
                path, len(audio), sample_rate)


def _write_wav_raw(
    audio: np.ndarray,
    path: str,
    sample_rate: int = 44100,
    normalize: bool = True,
) -> None:
    """Writes a 16-bit PCM WAV without scipy (minimal header)."""
    import struct
    import wave

    if normalize:
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 32767
        else:
            audio = np.zeros_like(audio)

    audio_int = audio.astype(np.int16)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int.tobytes())
