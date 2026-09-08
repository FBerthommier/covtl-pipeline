# -*- coding: utf-8 -*-
"""Minimal demo of the vtl_synth package API.

    python examples/demo.py

Produces, in ./out_demo: the .tract, .wav and .mp4 of
"this is easy for us" (English g2p), then re-renders the video from
the tract alone (tract-to-mp4 path).
"""

from pathlib import Path

from vtl_synth import Pipeline, is_vtl_available

OUT = Path(__file__).resolve().parent.parent / 'out_demo'


def main() -> None:
    if not is_vtl_available():
        raise SystemExit('vocaltractlab-cython is not installed')

    pipe = Pipeline()

    # ---- full chain: text -> tract + wav + mp4 --------------------------
    result = pipe.run('this is easy for us', output_dir=str(OUT))
    print(f'SAMPA : {result.sampa}')
    print(f'tract : {result.tract_path} ({result.n_frames} frames)')
    print(f'wav   : {result.wav_path} ({result.duration_s:.2f} s)')
    print(f'mp4   : {result.mp4_path}')

    # ---- direct phonetic input (engine SAMPA, '|' = long pause) ---------
    result2 = pipe.text_to_wav('ba da ga | iowa a g',
                               output_dir=str(OUT / 'phonetic'),
                               use_g2p=False)
    print(f'wav2  : {result2.wav_path} ({result2.duration_s:.2f} s)')


if __name__ == '__main__':
    main()
