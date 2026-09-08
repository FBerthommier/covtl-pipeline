# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
encoder.py
==========
MP4 encoding (H.264 + AAC) for the sagittal tract video.

The ffmpeg binary is resolved
through, in order:

  1. ``imageio-ffmpeg``'s bundled binary (embedded wheel, no system
     install needed) — the default on Windows;
  2. plain ``ffmpeg`` from the ``PATH``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str:
    """Return the ffmpeg executable path (imageio-ffmpeg or PATH)."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        if shutil.which('ffmpeg'):
            return 'ffmpeg'
        raise RuntimeError(
            'ffmpeg not found: install imageio-ffmpeg '
            '(pip install imageio-ffmpeg) or put ffmpeg on the PATH')


def encode_mp4(png_dir, out_path, fps: int = 25, wav_path=None) -> Path:
    """Encode ``frame_%05d.png`` (+ optional WAV) into an MP4.

    Parameters
    ----------
    png_dir : Path
        Directory with the rendered PNG frames.
    out_path : Path
        Output .mp4 (H.264 yuv420p, +faststart for web streaming).
    fps : int
        Video frame rate.
    wav_path : Path, optional
        Audio track multiplexed as AAC 192k (``-shortest``).

    Returns
    -------
    Path of the written MP4.
    """
    ff = find_ffmpeg()
    png_dir, out_path = Path(png_dir), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ff, '-y',
           '-framerate', str(fps),
           '-i', str(png_dir / 'frame_%05d.png')]
    if wav_path is not None:
        cmd += ['-i', str(wav_path), '-c:a', 'aac', '-b:a', '192k',
                '-shortest']
    cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(out_path)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f'ffmpeg failed:\n{res.stderr[-2000:]}')
    return out_path


def probe_video(video_path) -> list:
    """Return the ffmpeg probe lines (duration, streams) for the log."""
    try:
        ff = find_ffmpeg()
        res = subprocess.run([ff, '-i', str(video_path)],
                             capture_output=True, text=True)
        return [ln.strip() for ln in res.stderr.splitlines()
                if re.search(r'Duration|Stream #', ln)]
    except Exception:
        return []
