# Installation (Windows, pip only — no Git required)

## 1. Requirements

- **Python 3.9 or newer** (3.9.13 tested) —
  https://www.python.org/downloads/ (check *Add python.exe to PATH*)
- ~200 MB of disk for the Python packages
- ffmpeg is **not** needed as a system install: the
  `imageio-ffmpeg` wheel bundles a private ffmpeg binary

## 2. Get and install the package

Download the repository
<https://github.com/fberthommier/covtl-pipeline> (Code → Download
ZIP) and unpack it, or clone it:

```bat
git clone https://github.com/fberthommier/covtl-pipeline.git
cd covtl-pipeline
```

From the repository folder (or the unpacked `covtl-pipeline` folder):

```bat
pip install --user .
```

or, for development (editable install, changes to the code are
immediately live):

```bat
pip install --user -e .
```

This installs the `vtl_synth` package, its dependencies and the
`vtl-synth` command.

### Python scripts folder

With `pip install --user`, the `vtl-synth.exe` command lands in the
user Scripts folder, e.g.:

```
C:\Users\<you>\AppData\Roaming\Python\Python39\Scripts
```

Add that folder to your `PATH` once (System properties → Environment
variables → Path → New), **or** call the command by full path, **or**
use the provided `launch.bat` which does it for you.

## 3. Check the installation

```bat
vtl-synth --help
vtl-synth run "this is easy for us" -o out
```

You should get `out\this_is_easy_for_us.tract`, `.wav`, `.mp4` and
`.txt` (the SAMPA transcript). The default speaker is **jd3**; after
cloning/updating the repository, (re)install the speaker you want
before synthesizing — the selector rewrites the active constants and
the wheel resource:

```bat
python install_speaker.py list          :: jd3 s1 s2 m01 w02 + active
python install_speaker.py install m01   :: example: switch to M01
```

Languages (de/en/es/fr/it/pt) are managed by `python setup_lang.py
list` / `install --lang fr` / `setlang de` / `restore` — see the
README section *Languages*.

## 4. Optional: run the test suite

```bat
pip install --user pytest
python -m pytest
```

111 tests (lightweight suite, ~80 s): engine non-regression against
the active speaker's `regression_baselines*.json`, CLI/g2p units,
registry integrity, expressive-prosody and polar-model units. The
heavyweight install/restore end-to-end test stayed in the development
repository (see `MIGRATION_NOTES.md` §5).

## Notes on vocaltractlab-cython

The VTL synthesizer comes from the `vocaltractlab-cython` wheel
(Paul Krug's Cython binding of Peter Birkholz's VocalTractLab 2.4).

- Prebuilt Windows wheels exist for **Python 3.10+** on PyPI.
- Under **Python 3.9**, if pip cannot find a wheel and tries to build
  from source (requires Visual Studio + CMake), install the last
  version that works without a toolchain:

  ```bat
  pip install --user vocaltractlab-cython==0.0.13
  ```

  The package then runs in *compatibility mode*: synthesis, SVG video
  rendering, shapes and transfer functions are fully available; the
  four analysis helpers `get_active_speaker`, `get_cross_sections`,
  `get_centerline`, `get_outlines` (added in 0.0.16+) raise a clear
  error instead.

## Uninstall

```bat
pip uninstall vtl-synth
```
