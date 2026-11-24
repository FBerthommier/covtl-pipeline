# RELEASING.md — the single reference for releasing the COVTL suite

Audience: any agent or maintainer performing a release. Follow this file
top to bottom; every command is copy-pasteable. This file lives in
`covtl-pipeline`, the project's core repository, because the whole chain
organizes around the engine.

## The suite and its repositories

| PyPI project | Role | Source repo | Published by |
|---|---|---|---|
| `covtl-sandhi` | cross-word rules | `FBerthommier/covtl-sandhi` | `publish-prod.yml` (trusted publishing) |
| `covtl-synth` | engine | `FBerthommier/covtl-pipeline` | `publish-prod.yml` (job `synth`) |
| `covtl` | meta-package (pins the 3 others) | `covtl-pipeline` → `meta/` | `publish-prod.yml` (job `meta`) |
| `covtl-console` | local web console | `FBerthommier/covtl-console` | `publish-prod.yml` (trusted publishing) |

All PyPI uploads go through **Trusted Publishing** (GitHub OIDC,
environment `pypi`, no API tokens). Every publishing workflow is
`workflow_dispatch`-only: nothing ships without an explicit gesture.

Standalone bundles (from PyPI, pinned):

| Bundle | Release tag | Built by |
|---|---|---|
| Windows x64 zip | `windows-standalone` | `build-windows-x64.yml` (+ Sigstore attestation, automatic) |
| Linux x64 zip | `linux-standalone` | `build-linux-x64.yml` (+ attestation) |
| macOS arm64 zip | `macos-standalone` | external prebuilt zip (see below) + `attest-releases.yml` |

Site: `FBerthommier/covtl.org` (GitHub Pages, domain covtl.org).

## Step 1 — bump the versions in the sources (manual commits)

Bump **all four** pyproject.toml files in ONE pass, with coherent values:

1. `covtl-sandhi`: `pyproject.toml` → `version = "0.1.x"`
2. `covtl-pipeline`: `pyproject.toml` → `version = "1.2.x"`
3. `covtl-console`: `pyproject.toml` → `version = "3.1.x"`
4. `covtl-pipeline`: `meta/pyproject.toml` → `version = "1.2.x"` **and**
   the three pins (`covtl-synth==…`, `covtl-console==…`,
   `covtl-sandhi==…`) — exact pins on purpose.

Push the commits to `main` on each repo. Version bumps in the console
repo touch `pyproject.toml` only — do NOT bump `covtl_console/__init__.py`
(stamped) or the spec unless needed.

## Step 2 — run the chain (one command)

```bash
python release_chain.py \
    --sandhi 0.1.X --synth 1.2.X --console 3.1.X --covtl 1.2.X
```

`release_chain.py` (in this repo, `scripts/`) runs the entire propagation:
preflight (abort on any version mismatch, before touching anything) →
PyPI publishes in dependency order (sandhi → synth+meta → console) →
waits for each version on pypi.org → bumps the standalone pins if needed
(build-windows.yml, packaging/linux/rebuild.sh; API commits) → dispatches
both bundle builds and verifies the published SHAs → updates the three
SHA-256 lines on covtl.org. GitHub auth = `git credential fill` of the
machine (no tokens in arguments).

Useful variants:

```bash
# preflight only (prints the alignment table, changes nothing)
python release_chain.py --check --sandhi ... --synth ... --console ... --covtl ...

# same run, plus a prebuilt macOS zip (full chain)
python release_chain.py --sandhi ... --synth ... --console ... --covtl ... \
    --macos-zip COVTL-Console-macOS.zip --console-sha <40-char SHA of console main>
```

Manual fallback (if the script cannot run): dispatch on github.com →
Actions, in this exact order: `publish-prod` on covtl-sandhi, then on
covtl-pipeline (both jobs green), then on covtl-console; then
`build-windows-x64` (input = console version) and `build-linux-x64`;
finally update the SHAs on covtl.org and commit. Never re-upload an
existing version — PyPI rejects duplicates permanently.

## Step 3 — macOS bundle (only when the engine moved)

The macOS zip is built outside CI (no macOS runner configured). Follow
`download/MacOS/PUBLISH-CHECKLIST.md` (scripts/build_bundle.sh → … →
test_zip.py) with the new pins, then either pass `--macos-zip` in step 2
(release + `attest-releases` dispatch handled for you) or upload manually
and dispatch `attest-releases.yml` (targets `macos`) on covtl-console.
Asset name MUST stay `COVTL-Console-macOS.zip` (stable download URLs).
Honest limits to keep in the notes: unsigned/notarized, native arm64
never executed on macOS (cross-checked on Linux), no Intel build.

## Step 4 — after the chain (checks + ancillary)

1. **Releases**: `windows-standalone` / `linux-standalone` / optional
   `macos-standalone` re-created by the CI with the same asset names;
   the release body must carry the new sha256 (the script checks it).
2. **Attestations** (automatic since commit 1532e7f): verify
   `gh attestation verify COVTL-Console-Windows-x64.zip -R FBerthommier/covtl-console`
   (idem Linux/macOS), or GET `repos/…/attestations/sha256:<digest>`.
3. **covtl.org**: Pages rebuilds on the SHA commit; verify the served
   page shows the 3 new cards/SHAs (audit script `audit_page_qr_links.py`;
   QR codes and buttons are stable and must NOT be regenerated).
4. **pip e2e** (fresh venv, Python 3.12):
   `pip install covtl` → `vtl-synth run "this is easy for us" -o out`
   (fr by default) and `-l en` variant → `covtl-console --help`.
5. **Windows bundle real smoke** (13 checks):
   `python packaging/windows/standalone_smoke.py <extracted>\covtl-console.exe`
6. **Trace**: append a section to
   `covtl-console-pypi/modif-build/TRACE-REALIGNEMENT-N1N2N3-TESTPYPI.md`
   and update the user memory index.

## Known traps (do not relearn)

- TestPyPI (`publish.yml`, dev suffix `.devN`) forbids re-upload: use a
  fresh suffix, never overwrite.
- GitHub API: `target_commitish` needs the FULL 40-char SHA.
- Pushing changes to `build-windows.yml` / `build-linux.yml` triggers
  rebuilds through their `paths:` filters — add `[skip ci]` to the commit
  message unless a rebuild is intended.
- Workflow dispatch on a just-pushed workflow may need a few seconds.
- Action logs are 401 via API with the agent token: diagnose a failed
  upload by reading the repo's **deployments** (PyPI integration posts
  `pypi`-environment deployments; OIDC minted = deployment created).
- `windows-standalone` stays the repo's `--latest` release; macOS is
  `make_latest=false`.
- covtl.org: don't regenerate QR codes for a version bump (targets are
  content URLs); only the SHA lines change.


## PENDING for the next release round (owner-approved, already on main)

- **Polar display fix, do not miss it**: commit `d294f51` on main
  (2026-11-23) fixes the inverted return-leg concavity of the polar
  display ("ventre" fix) — `POLAR_VERSION = 5` in
  `vtl_synth/video/polar_video.py` (CV reduced-vowel approach anchoring,
  manual §5.6). It ships automatically with the next `publish-prod`
  dispatches: any `covtl-synth` >= this main is the fixed build. The
  console bundles rebuilt from that PyPI state embed it; display-only
  (audio/baselines untouched), so no pin or migration concern.

- **UNDER STUDY (owner, 2026-11-24) — schwa position**: an engine change
  concerning the schwa position (currently `VOWEL_TARGETS['@'] =
  (0.7167, pi)`, the centroid of the calibrated triangle, re-centred
  2026-09-04) is being studied and will require a GLOBAL modification
  (targets + possibly syltraj waypoints/polar display, cf.
  `syl._vv_waypoint` and the '@' phoneme entry). To be ACCUMULATED into
  the same next full rebuild round as the polar v5 display fix above —
  do not ship it piecemeal. Not started: no code exists yet; this is a
  planning note only.

- **Schwa study deliverable (audit 2026-11-24)**: the position study is
  documented in `docs/schwa-position-audit-EN.md` (English translation
  of the French internal audit, layer-classified: layer 1 target /
  layer 2 mandatory routing / layer 2 display option) — read it before
  reviewing the schwa change; it carries the acceptance criteria reused
  by `tests/test_schwa_waypoint.py`.
