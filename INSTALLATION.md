# Installation Guide for covtl-pipeline on Windows (CMD)

Step-by-step installation of the `vtl-synth` package on Windows,
without administrator rights and (optionally) without Git.
This project is **pip-only**: FFmpeg is bundled through the
`imageio-ffmpeg` wheel and the VocalTractLab engine comes from the
`vocaltractlab-cython` wheel — **no system FFmpeg, no Cairo, no DLL
management are required**.

## Prerequisites

| Requirement | Version | Where to get it |
| --- | --- | --- |
| Python | 3.9.x or higher (3.9.13 tested) | [python.org](https://www.python.org/) |
| pip | 23+ | Included with Python |
| Disk space | ~200 MB | For the Python packages |

> During the Python installation, check **Add python.exe to PATH**.

---

## Step 1: Download the source code (without Git)

1. Open your browser and go to
   [https://github.com/fberthommier/covtl-pipeline](https://github.com/fberthommier/covtl-pipeline).
2. Click the green **Code** button → **Download ZIP**.
3. Extract the ZIP to your preferred location, for example:

```
C:\covtl-pipeline
```

Alternatively, with Git installed:

```
git clone https://github.com/fberthommier/covtl-pipeline.git
cd covtl-pipeline
```

---

## Step 2: Install the package

Open a **Command Prompt (CMD)** and run:

```
cd C:\covtl-pipeline
pip install --user .
```

Or, for development (editable install — changes to the code are
immediately live):

```
pip install --user -e .
```

> **Note:** The `--user` flag installs the package for your user account
> only, so administrator rights are not required.

Optional extras:

```
pip install --user ".[plot]"   # PNG figures of .tract files (plot-tract, matplotlib)
pip install --user ".[dev]"    # test suite (pytest)
```

---

## Step 3: Make `vtl-synth` reachable (PATH)

With `pip install --user`, the `vtl-synth.exe` command lands in the user
*Scripts* folder, for example:

```
C:\Users\%USERNAME%\AppData\Roaming\Python\Python39\Scripts
```

You have three options (pick one):

- **Option A — add the folder to your user PATH once.** Press
  **Win + R**, type `sysdm.cpl`, press **Enter**, open the **Advanced**
  tab → **Environment Variables...** → under *User variables* edit
  `Path` → **New** → paste the Scripts folder above. Restart CMD.
- **Option B — call the command by full path** (see Step 5).
- **Option C — use the provided `launch.bat`** (see Tips below), which
  sets the path for you.

---

## Step 4: Python 3.9 note (vocaltractlab-cython)

Prebuilt Windows wheels of `vocaltractlab-cython` exist for
**Python 3.10+**. Under **Python 3.9**, if pip cannot find a wheel and
tries to build from source (which requires Visual Studio + CMake),
install the last version that works without a toolchain **before**
installing the package:

```
pip install --user vocaltractlab-cython==0.0.13
pip install --user .
```

The package then runs in *compatibility mode*: synthesis, SVG video
rendering, shapes and transfer functions are fully available; the four
analysis helpers `get_active_speaker`, `get_cross_sections`,
`get_centerline`, `get_outlines` (added in 0.0.16+) raise a clear error
instead.

---

## Step 5: Run the synthesis

From the project directory (adjust the Python version folder if needed):

```
cd C:\covtl-pipeline
vtl-synth run "this is easy for us" -o out
```

or by full path:

```
C:\Users\%USERNAME%\AppData\Roaming\Python\Python39\Scripts\vtl-synth.exe run "this is easy for us" -o out
```

---

## Expected output

A successful execution prints something similar to:

```
============================================================
SUCCESS
  SAMPA     : Dis.iz.i.zi.fOR.@s
  phrases   : 1
  tract     : out\this_is_easy_for_us.tract (952 frames @400 Hz)
  wav       : out\this_is_easy_for_us.wav (2.37 s)
  mp4       : out\this_is_easy_for_us.mp4
============================================================
```

and produces in `out\`:

| File | Content |
| --- | --- |
| `this_is_easy_for_us.tract` | 400 Hz tract sequence (19 tract + 11 glottis parameters per frame) |
| `this_is_easy_for_us.wav` | PCM 16-bit mono audio, 44 100 Hz |
| `this_is_easy_for_us.mp4` | H.264 + AAC video of the sagittal cross-section (960x840 @ 25 fps) |
| `this_is_easy_for_us.txt` | The engine SAMPA transcript |

---

## Verification

```
python --version
vtl-synth --help
```

If the help message is displayed, the installation is ready. To run the
test suite (63 tests, including the version-coherence check):

```
pip install --user pytest
python -m pytest
```

---

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `'vtl-synth' is not recognized` | Add the Scripts folder to `PATH` (Step 3), call the `.exe` by full path, or use `launch.bat` |
| `Package 'vtl-synth' requires a different Python` | The package requires Python >= 3.9; use `py -3.9` / `py -3.10` to pick the right interpreter |
| pip tries to **build** `vocaltractlab-cython` from source under Python 3.9 | `pip install --user vocaltractlab-cython==0.0.13` first (Step 4) |
| `ffprobe`/`ffmpeg` errors during MP4 encoding | The bundled ffmpeg from `imageio-ffmpeg` is used automatically; make sure the package installed completely (`pip install --user .` again) |
| `Permission denied` during installation | Use the `--user` flag: `pip install --user .` |
| Video is produced but playback fails | Update your video player; the MP4 is H.264 `yuv420p` with the `faststart` flag |

---

## Tips

### Create a launch script

The repository ships a `launch.bat` that prepends the Scripts folder to
`PATH` and synthesizes a demo sentence:

```
@echo off
setlocal
set SCRIPTS=%APPDATA%\Python\Python39\Scripts
set PATH=%SCRIPTS%;%PATH%
vtl-synth run "this is easy for us" -o out
echo.
pause
endlocal
```

(This matches the shipped `launch.bat`; edit the `Python39` suffix to
match your Python version and the phrase to taste, then double-click
`launch.bat` to run the synthesis.)

### Uninstall

```
pip uninstall vtl-synth
```

You are now ready to use **covtl-pipeline** on Windows!
