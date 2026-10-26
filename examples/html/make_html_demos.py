#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the self-contained interactive HTML demos of examples/html/.

For each demo phrase the JD3 pipeline is run with the SAME parameters
as ``examples/polar_demo_en.mp4`` (f0 = 102.216 Hz, t_cons = 100 ms,
t_voy = 80 ms, engine 'syl'), and one fully self-contained HTML page is
emitted from ``polar_player.template.html``:

  - polar planning figure (.polar v4 trajectories, 100 Hz) rendered on
    canvas exactly like ``vtl_synth/video/polar_video.py``
    ``render_polar_frame`` (dual branch: vocalic z_v red / consonantal
    z_c blue, 300 ms fading trail, transient phoneme labels, inventory
    dots);
  - mid-sagittal vocal tract drawn from the same SVG polylines as the
    MP4 renderer (``vocaltractlab_cython.tract_state_to_svg``, 25 fps);
  - the synthesized audio (AAC in a data URI) as the playback master
    clock;
  - transport: play/pause, scrub, speed 0.25x-1x, loop, keyboard
    stepping, clickable time traces.

The pages embed all their data (no fetch, no server, no network): they
work straight from the file system (file://).  An index.html landing
page is regenerated as well.

Usage (from the repository root, with the project venv)::

    python examples/html/make_html_demos.py

Outputs (in this directory): polar_demo_fr.html, polar_demo_en.html,
index.html.  ffmpeg is required for the embedded audio; without it the
pages are still generated (silent, clock-driven playback).
"""

from __future__ import annotations

import base64
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from vtl_synth import Pipeline, __version__ as VTL_VERSION  # noqa: E402
from vtl_synth.video.renderer import read_tract             # noqa: E402

# Same parameters as the shipped examples/polar_demo_en.mp4 (and the
# manual polar figures) -- keep them in sync.
DEMO_PARAMS = dict(f0_hz=102.216, speaker='JD3',
                   t_cons_ms=100.0, t_voy_ms=80.0)
SAG_FPS = 25            # sagittal frame rate (same as the MP4)
POLAR_SR = 100          # .polar trajectory sampling (Hz)
SVG_NS = '{http://www.w3.org/2000/svg}'

DEMOS = [
    dict(
        out='polar_demo_fr.html',
        label='polar_demo_fr',
        text='ba.da.ga',
        use_g2p=False,
        input_note='engine SAMPA input (use_g2p=False)',
        phrase_display='ba.da.ga',
        blurb='Canonical CV.CV.CV sequence: three stop+vowel syllables '
              'on three different places of articulation. The consonantal '
              'branch (blue) loops to the /b/, /d/, /g/ targets while the '
              'vocalic branch (red) holds the /a/ plateau.',
    ),
    dict(
        out='polar_demo_en.html',
        label='polar_demo_en',
        text='this is easy for us',
        use_g2p=True,
        input_note='English orthographic input (CMUdict g2p)',
        phrase_display='this is easy for us',
        blurb='Same utterance as examples/polar_demo_en.mp4: English text '
              'through the CMUdict g2p, fricatives and affricates drive '
              'the consonantal branch through front ( dental ) targets '
              'while the vocalic branch glides between the reduced '
              'vowels.',
    ),
]


def _round(x, nd=4):
    return None if x is None else round(float(x), nd)


def slim_polar(polar_path: Path) -> dict:
    """The .polar JSON document, floats rounded for embedding."""
    doc = json.loads(polar_path.read_text(encoding='utf-8'))
    keep = dict(
        format=doc['format'],
        version=doc['version'],
        sample_rate=doc['sample_rate'],
        speaker=doc['speaker'],
        orientation=doc.get('orientation'),
        notation=doc.get('notation'),
        trajectory=dict(
            vocalic=dict(
                rho=[_round(v) for v in
                     doc['trajectory']['vocalic']['rho']],
                theta=[_round(v) for v in
                       doc['trajectory']['vocalic']['theta']]),
            consonantal=dict(
                rho=[_round(v) for v in
                     doc['trajectory']['consonantal']['rho']],
                theta=[_round(v) for v in
                       doc['trajectory']['consonantal']['theta']]),
        ),
        phonemes=[dict(key=p['key'], category=p['category'],
                       rho=_round(p['rho']), theta=_round(p['theta']),
                       t0=p['t0'], t1=p['t1'])
                  for p in doc['phonemes']],
        inventory=[dict(key=p['key'], category=p['category'],
                        rho=_round(p['rho']), theta=_round(p['theta']))
                   for p in doc['inventory']],
    )
    n_steps = doc['n_steps']
    assert len(keep['trajectory']['vocalic']['rho']) == n_steps, \
        'polar trajectory length != n_steps'
    return keep


def sagittal_frames(tract_path: Path, fps: int = SAG_FPS) -> tuple:
    """(viewBox, frames) -- VTL SVG polylines per frame, rounded 0.1.

    Mirrors renderer.render_frames (tract row k*sr/fps) and
    make_polar_video's frame count (min with the polar duration).
    """
    import numpy as np
    from vocaltractlab_cython import tract_state_to_svg

    data, sr = read_tract(tract_path)
    step = max(1, round(sr / fps))
    n = len(range(0, data.shape[0], step))
    frames, viewBox = [], None
    for k, f in enumerate(range(0, data.shape[0], step)):
        svg_path = HERE / '.sag_tmp.svg'
        tract_state_to_svg(data[f, :19], str(svg_path))
        root = ET.parse(svg_path).getroot()
        vb = [float(v) for v in root.get('viewBox').split()]
        if viewBox is None:
            viewBox = vb
        assert vb == viewBox, 'viewBox changed across frames'
        lines = []
        for el in root.iter():
            if el.tag != SVG_NS + 'polyline':
                continue
            nums = el.get('points', '').split()
            pts = [round(float(nums[i]), 1) for i in range(len(nums))]
            if len(pts) >= 4:
                lines.append([el.get('stroke', 'black'),
                              float(el.get('stroke-width', 1)),
                              el.get('fill', 'none'), pts])
        frames.append(lines)
    svg_path.unlink()
    assert len(frames) == n
    return viewBox, frames


def audio_b64(wav_path: Path) -> dict | None:
    """WAV -> AAC/MP4 data-URI payload (None if ffmpeg is missing)."""
    m4a = HERE / '.audio_tmp.m4a'
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(wav_path),
           '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart',
           str(m4a)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f'  ! ffmpeg unavailable ({e}); the demo will be silent')
        return None
    b64 = base64.b64encode(m4a.read_bytes()).decode('ascii')
    m4a.unlink()
    return dict(mime='audio/mp4', b64=b64)


def build_demo(cfg: dict, work_dir: Path) -> dict:
    """Run the pipeline for one demo phrase -> embedded payload."""
    print(f"[{cfg['label']}] running pipeline: {cfg['text']!r} "
          f"(use_g2p={cfg['use_g2p']})")
    p = Pipeline(**DEMO_PARAMS)
    res = p.run(cfg['text'], output_dir=str(work_dir),
                use_g2p=cfg['use_g2p'], label=cfg['label'],
                polar=True, video=False)

    polar = slim_polar(res.polar_path)
    viewBox, sag = sagittal_frames(res.tract_path)
    # same frame count rule as make_polar_video: min(sagittal frames,
    # ceil(polar duration * fps)) -- tolerate the tract/polar rounding
    n_expect = min(len(sag), math.ceil(res.duration_s * SAG_FPS))
    assert abs(len(sag) - n_expect) <= 1, \
        f'sagittal frame count {len(sag)} vs expected {n_expect}'
    audio = audio_b64(res.wav_path)

    dur = res.duration_s
    sampa = res.sampa
    meta = dict(
        page_title=f"Polar planning demo - {cfg['phrase_display']}",
        h1=(f"Polar planning demo &mdash; "
            f"<span class=\"phrase\">{cfg['phrase_display']}</span>"),
        sub=(f"speaker JD3 &middot; engine <code>syl</code> &middot; "
             f"f0 {DEMO_PARAMS['f0_hz']:.3f} Hz &middot; "
             f"t<sub>cons</sub> {DEMO_PARAMS['t_cons_ms']:.0f} ms &middot; "
             f"t<sub>voy</sub> {DEMO_PARAMS['t_voy_ms']:.0f} ms &middot; "
             f"{dur:.2f} s &middot; {cfg['input_note']} &middot; "
             f"engine keys: <code>{sampa}</code>"),
        provenance=(f"Generated by <code>examples/html/"
                    f"make_html_demos.py</code> &mdash; vtl_synth "
                    f"{VTL_VERSION}, speaker JD3, {date.today().isoformat()}. "
                    f"Same parameters as <code>examples/polar_demo_en.mp4"
                    f"</code>."),
    )
    payload = dict(meta=meta, duration_s=round(dur, 4),
                   sagittal_fps=SAG_FPS, viewBox=viewBox,
                   polar=polar, sagittal=sag, audio=audio)
    return payload


def render_player(payload: dict, template: str) -> str:
    html = template.replace(
        '__DEMO_JSON__',
        json.dumps(payload, separators=(',', ':'), ensure_ascii=False))
    assert '__DEMO_JSON__' not in html, 'placeholder not substituted'
    return html


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>covtl-pipeline &mdash; interactive HTML demos</title>
<!--
  index.html -- landing page of the interactive HTML demos.
  Generated by examples/html/make_html_demos.py (do not edit by hand).
-->
<style>
  :root { --line:#d9d9d9; --bg:#f4f4f2; --panel:#fff; --muted:#6a6a6a;
          --red:#d62728; --blue:#1f77b4; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.55 system-ui,"Segoe UI",Roboto,Arial,
         sans-serif; color:#1c1c1c; background:var(--bg);
         padding:26px clamp(14px,4vw,50px) 40px; }
  main, header { max-width:920px; margin:0 auto; }
  h1 { font-size:23px; margin:0 0 6px; }
  .sub { color:var(--muted); font-size:13.5px; margin:0 0 22px; }
  .card { background:var(--panel); border:1px solid var(--line);
          border-radius:10px; padding:18px 22px; margin:14px 0;
          box-shadow:0 1px 2px rgba(0,0,0,.04); }
  .card h2 { font-size:17px; margin:0 0 6px; }
  .card h2 .phrase { font-style:italic; }
  .card p { margin:6px 0; font-size:14px; color:#333; }
  .card a.btn { display:inline-block; margin:10px 0 2px; padding:8px 16px;
          background:#2b5d8a; color:#fff; border-radius:7px;
          text-decoration:none; font-weight:600; font-size:14px; }
  .card a.btn:hover { background:#234b70; }
  .meta { color:var(--muted); font-size:12.5px; }
  .sw { display:inline-block; width:10px; height:10px; border-radius:50%;
        vertical-align:-1px; margin:0 3px 0 8px;
        border:1px solid rgba(0,0,0,.3); }
  section { margin:26px 0 0; }
  h2.section { font-size:16px; }
  p, li { font-size:14px; color:#333; }
  code { font:12.5px/1.4 ui-monospace,Consolas,Menlo,monospace;
         background:#ececea; border-radius:3px; padding:1px 5px; }
  footer { max-width:920px; margin:30px auto 0; padding-top:12px;
           border-top:1px solid var(--line); color:var(--muted);
           font-size:12.5px; }
</style>
</head>
<body>
<header>
  <h1>covtl-pipeline &mdash; interactive HTML demos</h1>
  <p class="sub">self-contained pages (no server, no network): open directly from the file system</p>
</header>
<main>
  <p>The COVTL polar planning model drives the tongue body toward
  targets in a mid-sagittal polar space
  (&rho;, &theta;). Two dissociated gestures are superposed: the
  <b style="color:var(--red)">vocalic branch z<sub>v</sub></b> (red,
  always active, anchor-to-anchor arcs and vowel plateaus) and the
  <b style="color:var(--blue)">consonantal branch z<sub>c</sub></b>
  (blue, active during the consonant clusters, looping through the
  consonant node targets). Each demo animates the mid-sagittal vocal
  tract, the polar figure and the branch trajectories, synchronized
  with the synthesized audio &mdash; the interactive counterpart of the
  dual-panel MP4 (<code>examples/polar_demo_en.mp4</code>).</p>
__CARDS__
  <section>
    <h2 class="section">Controls</h2>
    <ul>
      <li><b>space</b> play / pause &middot; <b>&larr; / &rarr;</b> step
        &plusmn;10 ms (<b>shift</b>: &plusmn;100 ms) &middot;
        <b>home / end</b> jump to the boundaries</li>
      <li>scrub with the timeline slider, or click / drag directly on
        the &rho; / &theta; traces chart</li>
      <li>speed 0.25&times; / 0.5&times; / 1&times; (audio-rate), loop
        and mute toggles</li>
    </ul>
  </section>
  <section>
    <h2 class="section">How it is built</h2>
    <p>Everything is embedded at generation time: the .polar v4
    trajectories (100 Hz, two branches + phoneme inventory), the
    sagittal frames (SVG polylines from
    <code>vocaltractlab_cython.tract_state_to_svg</code>, 25 fps) and
    the synthesized audio (AAC data URI, the playback master clock).
    The canvas rendering mirrors
    <code>vtl_synth/video/polar_video.py</code>
    (<code>render_polar_frame</code>): display curvature K=30
    (&nu;=+1) for the vocalic arcs and K=10 (&nu;=&minus;1) for the
    consonantal sub-arcs &mdash; the reference planning geometry of
    arXiv:2307.02299 &sect;2.1, not the quasi-rectilinear SYL_K=1000
    parameter arcs used by the synthesis engine.</p>
    <p>Regenerate after changing the pipeline or the demo
    phrases:<br>
    <code>python examples/html/make_html_demos.py</code></p>
  </section>
</main>
<footer>
  <p>covtl-pipeline &middot; interactive demos &middot; generated by
  <code>examples/html/make_html_demos.py</code> &middot; speaker JD3
  &middot; GPL-3.0-or-later</p>
</footer>
</body>
</html>
"""


def render_index(payloads: list) -> str:
    cards = []
    for cfg, payload in payloads:
        cards.append(f"""  <div class="card">
    <h2><a href="{cfg['out']}"><span class="phrase">{cfg['phrase_display']}</span></a>
        &mdash; {cfg['input_note']}</h2>
    <p>{cfg['blurb']}</p>
    <p class="meta">{payload['duration_s']:.2f} s &middot; speaker JD3
      &middot; engine syl &middot; f0 102.216 Hz &middot;
      {len(payload['polar']['phonemes'])} phoneme spans &middot;
      {len(payload['polar']['inventory'])} inventory targets
      <span class="sw" style="background:var(--red)"></span>vowels
      <span class="sw" style="background:var(--blue)"></span>consonants
    </p>
    <a class="btn" href="{cfg['out']}">Open the demo &rarr;</a>
  </div>""")
    return INDEX_TEMPLATE.replace('__CARDS__', '\n'.join(cards))


def main() -> int:
    work_dir = REPO / 'out' / 'html_demos'
    template = (HERE / 'polar_player.template.html').read_text(
        encoding='utf-8')
    payloads = []
    for cfg in DEMOS:
        payload = build_demo(cfg, work_dir)
        html = render_player(payload, template)
        out = HERE / cfg['out']
        out.write_text(html, encoding='utf-8')
        audio_kb = (len(payload['audio']['b64']) / 1024
                    if payload['audio'] else 0)
        print(f"  -> {out.name}: {out.stat().st_size / 1024:.0f} KB "
              f"(audio {audio_kb:.0f} KB, "
              f"sagittal {len(payload['sagittal'])} frames)")
        payloads.append((cfg, payload))
    index = render_index(payloads)
    (HERE / 'index.html').write_text(index, encoding='utf-8')
    print(f"  -> index.html: {(HERE / 'index.html').stat().st_size / 1024:.0f} KB")
    print('done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
