#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Frederic Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
"""release_chain.py - one-command release propagation for the COVTL suite.

Single entry point documented in RELEASING.md (covtl-pipeline). Runs the
whole chain AFTER the versions have been bumped in the sources:

  1. preflight: every declared version matches the requested chain and
     the standalone-bundle pins are aligned (auto-bump via API commit if
     not);
  2. PyPI via trusted publishing, dependency order:
     covtl-sandhi -> covtl-pipeline (covtl-synth + covtl meta) ->
     covtl-console;
  3. wait for each new version to be visible on pypi.org;
  4. standalone bundles: dispatch build-windows-x64 / build-linux-x64,
     wait, download the published zips anonymously and compute sha256;
  5. macOS: optional --macos-zip (prebuilt, per PUBLISH-CHECKLIST) ->
     (re)create release macos-standalone + dispatch attest-releases;
  6. covtl.org: replace the three SHA-256 lines in index.html (API
     commit; Pages rebuilds automatically).

GitHub authentication uses `git credential fill` (no tokens in argv).
PyPI is only ever READ here; all uploads happen inside GitHub Actions
(trusted publishing). Nothing is automatic on push - the chain starts
with this script (or manual dispatches).

Usage:
  python release_chain.py --check \
      --sandhi 0.1.1 --synth 1.2.2 --console 3.1.10 --covtl 1.2.3
  python release_chain.py \
      --sandhi 0.1.2 --synth 1.2.3 --console 3.1.11 --covtl 1.2.4 \
      [--macos-zip COVTL-Console-macOS.zip] [--keep-covtl-org]
"""
import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
PYPI = "https://pypi.org/pypi"
REPOS = {
    "sandhi": "FBerthommier/covtl-sandhi",
    "pipeline": "FBerthommier/covtl-pipeline",
    "console": "FBerthommier/covtl-console",
    "pages": "FBerthommier/covtl.org",
}
OLD_SHAS = {  # the values currently displayed on covtl.org
    "36e2e0223182fff2b09f4c5ac53c8a2be8370ef80fe2e72b7d98f6524155f418",
    "32123d349027dc93df3aedf7dae1fc8f92fc42c552a040cb052d0162bbf03c33",
    "810836e371eb9d4399a1224524e7163defe3593c5821616e7505f1233371d6f2",
}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def get_token():
    cred = "protocol=https\nhost=github.com\n\n"
    p = subprocess.run(["git", "credential", "fill"], input=cred,
                       capture_output=True, text=True, timeout=30)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("FATAL: no GitHub token from git credential fill")


TOKEN = get_token()


def api(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        path if path.startswith("http") else API + path,
        method=method, data=data)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        payload = r.read()
        return r.status, (payload if raw else json.loads(payload or b"{}"))
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if raw else json.loads(e.read() or b"{}"))


def get_file(repo, path):
    st, d = api("GET", f"/repos/{repo}/contents/{path}")
    if st != 200:
        raise SystemExit(f"FATAL: GET {repo}/{path} -> HTTP {st}: {d}")
    return d["sha"], base64.b64decode(d["content"]).decode()


def put_file(repo, path, text, message):
    st, d = api("GET", f"/repos/{repo}/contents/{path}")
    old = d["sha"] if st == 200 else None
    body = {"message": message, "branch": "main",
            "content": base64.b64encode(text.encode()).decode()}
    if old:
        body["sha"] = old
    st, d = api("PUT", f"/repos/{repo}/contents/{path}", body)
    if st not in (200, 201):
        raise SystemExit(f"FATAL: PUT {repo}/{path} -> HTTP {st}: {d}")
    log(f"  committed {repo}/{path} ({d['commit']['sha'][:10]})")


def dispatch(repo, workflow, inputs=None):
    body = {"ref": "main"}
    if inputs:
        body["inputs"] = inputs
    st, d = api("POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches",
                body)
    if st != 204:
        raise SystemExit(f"FATAL: dispatch {repo}/{workflow} -> HTTP {st}: {d}")
    log(f"  dispatched {repo} / {workflow}")


def wait_run(repo, workflow, started_after, label, timeout_min=60):
    """Wait for the newest run of the workflow (started after started_after)."""
    deadline = time.time() + timeout_min * 60
    run_id = None
    while time.time() < deadline:
        st, d = api("GET",
                    f"/repos/{repo}/actions/workflows/{workflow}/runs?per_page=3")
        for r in d.get("workflow_runs", []):
            if r["created_at"] >= started_after:
                run_id = r["id"]
                break
        if run_id:
            break
        time.sleep(10)
    if not run_id:
        raise SystemExit(f"FATAL: no run appeared for {repo}/{workflow}")
    while time.time() < deadline:
        st, d = api("GET", f"/repos/{repo}/actions/runs/{run_id}")
        if d["status"] == "completed":
            if d["conclusion"] != "success":
                raise SystemExit(
                    f"FATAL: {label} run {run_id} concluded '{d['conclusion']}' "
                    f"- inspect {d['html_url']} then re-run with the "
                    "appropriate --skip flag once fixed.")
            log(f"  {label}: run {run_id} SUCCESS")
            return run_id
        time.sleep(20)
    raise SystemExit(f"FATAL: timeout waiting for {label} run {run_id}")


def pypi_wait(project, version, timeout_min=10):
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{PYPI}/{project}/json")
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if version in d.get("releases", {}):
                log(f"  pypi.org: {project} {version} visible")
                return
        except Exception:
            pass
        time.sleep(20)
    raise SystemExit(f"FATAL: {project} {version} not visible on pypi.org "
                     f"after {timeout_min} min (CDN lag?)")


def download_sha(url, expected_min_mb=50):
    req = urllib.request.Request(url, headers={"User-Agent": "covtl-release"})
    h = hashlib.sha256()
    n = 0
    tmp = url.rsplit("/", 1)[-1] + ".dl"
    r = urllib.request.urlopen(req, timeout=3600)
    with open(tmp, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
            h.update(chunk)
            n += len(chunk)
    if n < expected_min_mb * (1 << 20):
        raise SystemExit(f"FATAL: {tmp} too small ({n} bytes)")
    return tmp, h.hexdigest()


def publish(repo, workflow, label, started_after):
    dispatch(repo, workflow)
    wait_run(repo, workflow, started_after, label)


# ---------------------------------------------------------------- preflight
def preflight(a):
    ok = True
    specs = [
        ("covtl-sandhi", REPOS["sandhi"], "pyproject.toml"),
        ("covtl-synth", REPOS["pipeline"], "pyproject.toml"),
        ("covtl-console", REPOS["console"], "pyproject.toml"),
        ("covtl (meta)", REPOS["pipeline"], "meta/pyproject.toml"),
    ]
    versions = {"covtl-sandhi": a.sandhi, "covtl-synth": a.synth,
                "covtl-console": a.console, "covtl": a.covtl}
    for name, repo, path in specs:
        st, d = api("GET", f"/repos/{repo}/contents/{path}")
        src = base64.b64decode(d["content"]).decode()
        declared = [l.split('"')[1] for l in src.splitlines()
                    if l.strip().startswith("version = ")][0]
        want = versions[name.split(" ")[0]]
        state = "OK" if declared == want else "MISMATCH"
        print(f"  {name:14s} declared={declared:8s} requested={want:8s} {state}")
        ok = ok and declared == want
        if name.startswith("covtl ("):
            pins = dict(p.strip().strip('",').split("==")
                        for p in src.split("dependencies = [")[1]
                        .split("]")[0].strip().splitlines())
            chain_ok = (pins.get("covtl-synth") == a.synth
                        and pins.get("covtl-console") == a.console
                        and pins.get("covtl-sandhi") == a.sandhi)
            print(f"  meta pins      synth={pins.get('covtl-synth')} "
                  f"console={pins.get('covtl-console')} "
                  f"sandhi={pins.get('covtl-sandhi')} "
                  f"{'OK' if chain_ok else 'MISMATCH'}")
            ok = ok and chain_ok
    return ok


def bump_bundle_pins(a):
    """Align the standalone-chain pins with the requested chain (API commits)."""
    _, win = get_file(REPOS["console"], ".github/workflows/build-windows.yml")
    new = win
    for old, new_v in ((f"covtl-synth=={a.old_synth}", f"covtl-synth=={a.synth}"),
                       (f"covtl-sandhi=={a.old_sandhi}", f"covtl-sandhi=={a.sandhi}"),
                       (f"'{a.old_console}'", f"'{a.console}'")):
        if old in new:
            new = new.replace(old, new_v)
    if new != win:
        put_file(REPOS["console"], ".github/workflows/build-windows.yml", new,
                 "build: bump the standalone chain pins to "
                 f"sandhi {a.sandhi} / synth {a.synth} / console {a.console}")
    _, sh = get_file(REPOS["console"], "packaging/linux/rebuild.sh")
    old_line = f'"covtl-console=={a.old_console}"'
    if old_line in sh:
        put_file(REPOS["console"], "packaging/linux/rebuild.sh",
                 sh.replace(old_line, f'"covtl-console=={a.console}"'),
                 f"build: bump the linux standalone pin to covtl-console=={a.console}")
    log("  bundle pins aligned")


# ------------------------------------------------------------------- steps
def step_pypi(a, t0):
    log("STEP 1: PyPI publication (trusted publishing)")
    publish(REPOS["sandhi"], "publish-prod.yml", "sandhi", t0)
    publish(REPOS["pipeline"], "publish-prod.yml", "synth+meta", t0)
    publish(REPOS["console"], "publish-prod.yml", "console", t0)
    for project, version in (("covtl-sandhi", a.sandhi),
                             ("covtl-synth", a.synth),
                             ("covtl", a.covtl),
                             ("covtl-console", a.console)):
        pypi_wait(project, version)


def step_bundles(a):
    log("STEP 2: standalone bundles (Windows + Linux)")
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    dispatch(REPOS["console"], "build-windows-x64.yml", {"version": a.console})
    dispatch(REPOS["console"], "build-linux-x64.yml")
    wait_run(REPOS["console"], "build-windows-x64.yml", t0, "windows", 60)
    wait_run(REPOS["console"], "build-linux-x64.yml", t0, "linux", 60)
    shas = {}
    for tag, asset in (("windows-standalone", "COVTL-Console-Windows-x64.zip"),
                       ("linux-standalone", "COVTL-Console-Linux-x64.zip")):
        st, rel = api("GET", f"/repos/{REPOS['console']}/releases/tags/{tag}")
        url = next(a_["browser_download_url"] for a_ in rel["assets"]
                   if a_["name"] == asset)
        _, sha = download_sha(url)
        shas[asset] = sha
        note_ok = sha in (rel.get("body") or "")
        log(f"  {asset}: sha256={sha} (release notes mention it: {note_ok})")
    return shas


def step_macos(a):
    if not a.macos_zip:
        log("STEP 3: macOS - SKIPPED (build it per download/MacOS/"
            "PUBLISH-CHECKLIST.md, then re-run with --macos-zip)")
        return
    log("STEP 3: macOS release from prebuilt zip")
    zpath = a.macos_zip
    h = hashlib.sha256()
    with open(zpath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()
    st, d = api("GET", f"/repos/{REPOS['console']}/releases/tags/macos-standalone")
    if st == 200:
        st2, _ = api("DELETE", f"/repos/{REPOS['console']}/releases/{d['id']}")
        log(f"  old release deleted (HTTP {st2}); tag stays, same asset names")
    with open(zpath, "rb") as f:
        payload = f.read()
    st, rel = api("POST", f"/repos/{REPOS['console']}/releases", {
        "tag_name": "macos-standalone",
        "target_commitish": a.console_sha,
        "name": f"COVTL Console - standalone macOS arm64 ({a.console})",
        "body": (f"Automated upload of the prebuilt macOS arm64 bundle "
                 f"(covtl-console {a.console} / covtl-synth {a.synth} / "
                 f"covtl-sandhi {a.sandhi}). Unsigned: right-click the app "
                 f"> Open on first run. Windows twin: windows-standalone. "
                 f"Linux twin: linux-standalone. sha256: {sha}"),
        "make_latest": "false"})
    if st != 201:
        raise SystemExit(f"FATAL: create macos release -> HTTP {st}: {rel}")
    st, _ = api("POST",
                f"https://uploads.github.com/repos/{REPOS['console']}"
                f"/releases/{rel['id']}/assets?name=COVTL-Console-macOS.zip",
                payload, raw=True)
    log(f"  asset upload HTTP {st}")
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    dispatch(REPOS["console"], "attest-releases.yml", {"targets": "macos"})
    wait_run(REPOS["console"], "attest-releases.yml", t0, "attest-macos", 20)
    return sha


def step_covtl_org(a, shas, macos_sha):
    if a.keep_covtl_org:
        log("STEP 4: covtl.org - SKIPPED (--keep-covtl-org)")
        return
    log("STEP 4: covtl.org SHA update")
    _, page = get_file(REPOS["pages"], "index.html")
    pairs = list(zip(sorted(OLD_SHAS), [shas.get("COVTL-Console-Windows-x64.zip"),
                                        shas.get("COVTL-Console-Linux-x64.zip"),
                                        macos_sha or ""]))
    mapping = {}
    if shas.get("COVTL-Console-Windows-x64.zip"):
        mapping["36e2e0223182fff2b09f4c5ac53c8a2be8370ef80fe2e72b7d98f6524155f418"] = \
            shas["COVTL-Console-Windows-x64.zip"]
    if shas.get("COVTL-Console-Linux-x64.zip"):
        mapping["32123d349027dc93df3aedf7dae1fc8f92fc42c552a040cb052d0162bbf03c33"] = \
            shas["COVTL-Console-Linux-x64.zip"]
    if macos_sha:
        mapping["810836e371eb9d4399a1224524e7163defe3593c5821616e7505f1233371d6f2"] = \
            macos_sha
    new_page = page
    for old, new in mapping.items():
        if old not in new_page:
            raise SystemExit(f"FATAL: expected old sha {old[:12]} not found "
                             "on covtl.org index.html - update manually.")
        new_page = new_page.replace(old, new)
    if new_page != page:
        put_file(REPOS["pages"], "index.html", new_page,
                 f"release chain: bundles {a.sandhi}/{a.synth}/{a.console} "
                 "(new SHA-256)")
    log("  covtl.org updated (Pages rebuilds automatically)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="preflight only: print version alignment, change nothing")
    ap.add_argument("--sandhi", required=True)
    ap.add_argument("--synth", required=True)
    ap.add_argument("--console", required=True)
    ap.add_argument("--covtl", required=True, help="meta-package version")
    ap.add_argument("--old-sandhi", default="0.1.1")
    ap.add_argument("--old-synth", default="1.2.2")
    ap.add_argument("--old-console", default="3.1.10")
    ap.add_argument("--macos-zip", help="prebuilt macOS zip (PUBLISH-CHECKLIST)")
    ap.add_argument("--console-sha", help="full 40-char commit SHA for the "
                    "macos-standalone tag target (required with --macos-zip)")
    ap.add_argument("--keep-covtl-org", action="store_true",
                    help="do not touch the covtl.org page")
    a = ap.parse_args()

    print("=== PREFLIGHT: version alignment ===")
    aligned = preflight(a)
    if a.check:
        print("PREFLIGHT", "PASS" if aligned else "FAIL",
              "- nothing was changed")
        sys.exit(0 if aligned else 2)
    if not aligned:
        print("Version mismatch in sources: bump the pyproject.toml files "
              "first (RELEASING.md step 1), then re-run.")
        sys.exit(2)
    if a.macos_zip and not a.console_sha:
        ap.error("--console-sha (40-char SHA) is required with --macos-zip")
    bump_bundle_pins(a)
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    step_pypi(a, t0)
    shas = step_bundles(a)
    macos_sha = step_macos(a)
    step_covtl_org(a, shas, macos_sha)
    print("=== CHAIN COMPLETE ===")
    print("Remaining manual steps: see RELEASING.md section 'After the chain'.")


if __name__ == "__main__":
    main()
