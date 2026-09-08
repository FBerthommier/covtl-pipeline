# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
renderer.py
===========
Sagittal-view frame rendering for the tract video.

Rendering pipeline:

  .tract (400 Hz, 19 tract + 11 glottis per line)
    → 1 frame out of sr/fps (default 400/25 = 16) → SVG
      (``vocaltractlab_cython.tract_state_to_svg``)
    → PNG (PIL rendering of the SVG polylines — no cairo needed)

The VTL SVG only contains a background ``rect`` and ``polyline``
elements (viewBox 480x420), which is why a lightweight ElementTree +
Pillow renderer is enough.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SVG_NS = '{http://www.w3.org/2000/svg}'

# Geometry of the VTL sagittal SVG
SVG_VIEW_W, SVG_VIEW_H = 480, 420


# ==========================================================================
# Reading the .tract
# ==========================================================================

def read_tract(path) -> tuple:
    """Read a VTL .tract -> (data (n, 30), sample_rate)."""
    sr = 400.0
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.startswith('#'):
                break
            m = re.match(r'#\s*sample_rate:\s*([\d.]+)', line)
            if m:
                sr = float(m.group(1))
    data = np.loadtxt(path, comments='#')
    if data.ndim != 2 or data.shape[1] < 19:
        raise ValueError(f'{path}: unexpected .tract format ({data.shape})')
    return data, sr


# ==========================================================================
# SVG -> PNG rendering (PIL; the VTL SVG = rect + polylines)
# ==========================================================================

def _parse_svg_retry(svg_path: Path, tries: int = 4) -> ET.ElementTree:
    for k in range(tries):
        try:
            return ET.parse(svg_path)
        except ET.ParseError:
            if svg_path.stat().st_size == 0:
                raise
            time.sleep(0.05 * (k + 1))   # immediate re-read on network share
    return ET.parse(svg_path)


def render_svg_png(svg_path, png_path, scale: int) -> None:
    """Rasterise one VTL sagittal SVG into a PNG (Pillow backend)."""
    svg_path, png_path = Path(svg_path), Path(png_path)
    root = _parse_svg_retry(svg_path).getroot()
    vx, vy, vw, vh = (float(v) for v in root.get('viewBox').split())
    img = Image.new('RGB', (int(vw * scale), int(vh * scale)), 'white')
    draw = ImageDraw.Draw(img)

    def to_px(x: float, y: float):
        return ((x - vx) * scale, (y - vy) * scale)

    for el in root.iter():
        tag = el.tag.replace(SVG_NS, '')
        if tag == 'rect':
            continue                      # background: image already white
        if tag != 'polyline':
            continue
        nums = el.get('points', '').split()
        pix = [to_px(float(nums[i]), float(nums[i + 1]))
               for i in range(0, len(nums) - 1, 2)]
        if len(pix) < 2:
            continue
        stroke = el.get('stroke', 'black')
        width = max(1, round(float(el.get('stroke-width', 1)) * scale))
        fill = el.get('fill', 'none')
        if fill not in (None, 'none'):
            draw.polygon(pix, fill=fill, outline=stroke)
        else:
            draw.line(pix, fill=stroke, width=width, joint='curve')
    img.save(png_path)


# ==========================================================================
# Frame sequence
# ==========================================================================

def render_frames(data: np.ndarray, sr: float, fps: int = 25,
                  scale: int = 2, work_dir=None) -> tuple:
    """Render the SVG+PNG frame sequence for a tract matrix.

    Parameters
    ----------
    data : ndarray (n, >=19)
        Tract frames (19 first columns used, as in make_video.py).
    sr : float
        Tract sample rate (Hz), typically 400.
    fps : int
        Output video frame rate.
    scale : int
        Pixels per SVG unit (2 -> 960x840).
    work_dir : Path, optional
        Working directory (recreated; default ``./temp_video``).

    Returns
    -------
    (png_dir, n_frames)
    """
    from vocaltractlab_cython import tract_state_to_svg

    work = Path(work_dir) if work_dir is not None else Path('temp_video')
    if work.exists():
        import shutil
        shutil.rmtree(work)
    svg_dir = work / 'svg'
    png_dir = work / 'png'
    svg_dir.mkdir(parents=True)
    png_dir.mkdir(parents=True)

    step = max(1, round(sr / fps))
    frames = np.arange(0, data.shape[0], step)
    for k, f in enumerate(frames):
        svg_path = svg_dir / f'frame_{k:05d}.svg'
        png_path = png_dir / f'frame_{k:05d}.png'
        tract_state_to_svg(data[f, :19], str(svg_path))
        render_svg_png(svg_path, png_path, scale)
    return png_dir, len(frames)
