# -*- coding: utf-8 -*-
"""
install_speaker.py — gestion multi-speakers de covtl-pipeline (2026-09-11).

Substitue en un geste reversible les deux faces d'un speaker :
  * le constants.py de la branche principale (geometrie, cibles,
    presets glottaux, f0_default) ;
  * la ressource .speaker partagee de la wheel vocaltractlab_cython
    (couche audio + SVG/video) — active au PROCHAIN processus (la DLL
    charge son .speaker a l'import ; la wheel 0.0.13 n'expose ni
    vtlInitialize ni vtlClose, pas de rechargement a chaud).

La branche orthogonale (VS/VO/TRX/TRY/TS3) suit le marqueur
ACTIVE_SPEAKER du registre vtl_synth/data/speakers/ (resolution
dynamique dans speaker_jd.py / build_phrase_tract.py — aucun .speaker
n'est copie dans vtl_binaries/, qui garde son JD3.speaker d'origine).

Usage (depuis P:\\covtl-pipeline) :
    python install_speaker.py list
    python install_speaker.py install s1|s2|jd3
    python install_speaker.py restore [--check-baselines]
    python install_speaker.py status

Journaux : P:\\covtl-speaker\\upgrade_speaker\\install_<nom>.log et
restore.log ; backups originaux dans upgrade_speaker\\backup_install\\
(manifeste SHA-256). Toute erreur -> rollback automatique de l'etat
precedent, jamais d'etat a moitie installe.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

PIPE_ROOT = Path(__file__).resolve().parent          # P:\covtl-pipeline
sys.path.insert(0, str(PIPE_ROOT))                   # import vtl_synth local

UP_DIR = Path(r"P:\covtl-speaker\upgrade_speaker")
BACKUP_DIR = UP_DIR / "backup_install"
BACKUP_MANIFEST = BACKUP_DIR / "backup_manifest.json"

from vtl_synth.core import speaker_registry as sr    # noqa: E402
from vtl_synth.core.speaker_jd import parse_speaker_file  # noqa: E402

JD3_CONSTANTS_HASH_PREFIX = "75ae0ba837ed106d"       # original de reference


# ==========================================================================
# Journal (ecran + fichier)
# ==========================================================================

class Tee:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, msg: str = ""):
        print(msg)
        self.f.write(msg + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def sha256_of(path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ==========================================================================
# Garde-fou : pointeur editable -> covtl-pipeline (§0-2)
# ==========================================================================

def editable_target() -> str:
    """Lit la cartographie editable de site-packages (sans influer dessus).

    Retourne le chemin pointe par le MAPPING editable de vtl_synth
    (chaine vide si introuvable).
    """
    import site
    import sysconfig
    dirs = set()
    try:
        dirs.add(sysconfig.get_path("purelib"))
    except Exception:
        pass
    try:
        dirs.add(site.getusersitepackages())
    except Exception:
        pass
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for p in glob.glob(os.path.join(d, "__editable___vtl_synth*finder*.py")):
            try:
                content = open(p, encoding="utf-8").read()
            except OSError:
                continue
            m = re.search(r"'vtl_synth'\s*:\s*'([^']+)'", content)
            if m:
                return m.group(1).replace("\\\\", "\\")
        # dist-info direct_url.json (secours)
        for p in glob.glob(os.path.join(d, "vtl_synth-*.dist-info", "direct_url.json")):
            try:
                url = json.load(open(p, encoding="utf-8")).get("url", "")
            except Exception:
                continue
            if url.startswith("file:///"):
                return url[8:].replace("/", "\\")
    return ""


def check_editable_pointer(log) -> None:
    target = editable_target()
    log(f"[garde-fou] pointeur editable vtl_synth -> {target or 'INTROUVABLE'}")
    if "covtl-pipeline" not in target.lower():
        raise RuntimeError(
            "Le pointeur editable de site-packages ne pointe PAS vers "
            "P:\\covtl-pipeline (actuel : %s).\\n"
            "Correction : pip install -e P:\\covtl-pipeline  puis reessayer. "
            "(cf. conditions §0-2 : la cartographie est GLOBALE ; un editable "
            "vers un autre depot redirigerait tous les scripts.)" % (target or "?")
        )


# ==========================================================================
# Backups originaux (une seule fois ; §2.2 pas 2)
# ==========================================================================

BACKUP_SOURCES = [
    ("pipeline/vtl_synth/core/constants.py",
     PIPE_ROOT / r"vtl_synth\core\constants.py",
     r"pipeline\vtl_synth\core\constants.py"),
    ("pipeline/vtl_synth/data/vtl_binaries/JD3.speaker",
     PIPE_ROOT / r"vtl_synth\data\vtl_binaries\JD3.speaker",
     r"pipeline\vtl_synth\data\vtl_binaries\JD3.speaker"),
]


def wheel_resource() -> Path:
    p = sr.wheel_resource_path()
    if p is None:
        raise RuntimeError(
            "Ressource wheel introuvable (vocaltractlab_cython absent ou "
            "sans resources/JD3.speaker) — la couche audio/video ne peut pas "
            "etre permutee.")
    return Path(p)


def backup_originals(log) -> None:
    if BACKUP_MANIFEST.exists():
        manifest = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {}
    items = BACKUP_SOURCES + [
        ("wheel/resources/JD3.speaker", wheel_resource(), r"wheel\JD3.speaker"),
    ]
    for key, src, rel in items:
        dest = BACKUP_DIR / rel
        if dest.exists() and key in manifest:
            log(f"[backup] deja present : {key} ({manifest[key][:16]})")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        h = sha256_of(dest)
        assert h == sha256_of(src)
        if key in manifest:
            assert manifest[key] == h, f"conflit de backup pour {key}"
        manifest[key] = h
        log(f"[backup] {key} <- {src}  sha256={h[:16]}")
    BACKUP_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    h0 = manifest["pipeline/vtl_synth/core/constants.py"]
    if not h0.startswith(JD3_CONSTANTS_HASH_PREFIX):
        raise RuntimeError(
            f"Le constants.py original sauvegarde ({h0[:16]}) n'est pas la "
            f"reference JD3 attendue ({JD3_CONSTANTS_HASH_PREFIX}).")


# ==========================================================================
# Etat / stash pour rollback
# ==========================================================================

class Stash:
    """Snapshot binaire de l'etat installe (constants, marqueur, wheel)."""

    def __init__(self, tmpdir: Path):
        self.dir = tmpdir
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PIPE_ROOT / r"vtl_synth\core\constants.py",
                     self.dir / "constants.py")
        shutil.copy2(sr.ACTIVE_MARKER, self.dir / "ACTIVE_SPEAKER")
        shutil.copy2(wheel_resource(), self.dir / "wheel_JD3.speaker")

    def rollback(self) -> None:
        shutil.copy2(self.dir / "constants.py",
                     PIPE_ROOT / r"vtl_synth\core\constants.py")
        shutil.copy2(self.dir / "ACTIVE_SPEAKER", sr.ACTIVE_MARKER)
        shutil.copy2(self.dir / "wheel_JD3.speaker", wheel_resource())
        _purge_constants_pyc()


def _purge_constants_pyc() -> None:
    """Supprime le .pyc de constants.py (mtime reseau granularity)."""
    cache = PIPE_ROOT / r"vtl_synth\core\__pycache__"
    if cache.is_dir():
        for pyc in cache.glob("constants.cpython-*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass


# ==========================================================================
# Independance speaker / language pack (2026-09-15)
# ==========================================================================
# install_speaker.py permute constants.py EN ENTIER ; setup_lang.py
# (language pack) edite la LANG SECTION a l'interieur. Les deux
# installations sont independantes : une permutation de speaker
# TRANSPORTE la section de langue active dans le nouveau constants
# (remplace son bloc vowel natif), et la coherence se verifie sur la
# forme canonique (region vowel/langue neutralisee, cf.
# speaker_registry.canonical_constants_text).

def _extract_lang_section(src_text: str) -> str:
    """Retourne la LANG SECTION complete (marqueurs inclus) ou ''."""
    m = re.search(
        re.escape(sr.LANG_SECTION_BEGIN) + r".*?"
        + re.escape(sr.LANG_SECTION_END) + r"[^\r\n]*\n?",
        src_text, re.S)
    return m.group(0) if m else ""


def _carry_lang_section(old_src: str, dest: Path, name: str, log) -> None:
    """Reinjecte la section de langue de l'ancien constants dans dest.

    Sans section dans l'ancien fichier : ne fait rien (etat natif).
    v1.2.0 (2026-09-23, D24 résolu) : la section est un MARQUEUR SEUL
    (ACTIVE_LANG) — elle est INSÉRÉE APRÈS la région vocalique native
    du constants cible, qui reste intégralement en place (les cibles
    appartiennent au speaker). Une ancienne section riche (avec cibles,
    < v1.2.0) n'est PAS transportée : c'est justement l'effet de bord
    supprimé — ré-amorcer la langue via `setup_lang.py setlang <lang>`.
    """
    section = _extract_lang_section(old_src)
    if not section:
        log("      (pas de section de langue a transporter)")
        return
    if "ACTIVE_LANG" not in section or "VOWEL_TARGETS" in section:
        log("      (section de langue ancienne format (avec cibles) NON "
            "transportee — effet de bord D24 supprime ; reactiver la "
            "langue par : python setup_lang.py setlang <lang>)")
        return
    new_src = dest.read_text(encoding="utf-8")
    native = re.compile(r"(?ms)^VOWEL_TARGETS:.*?^VOWEL_EFFORT_GAIN:.*?^\}\n?")
    if not native.search(new_src):
        raise RuntimeError(
            "transport de la section de langue impossible : bloc "
            "VOWEL_TARGETS/VOWEL_EFFORT_GAIN introuvable dans le "
            "constants cible")
    dest.write_text(native.sub(lambda m: m.group(0) + section, new_src,
                               count=1),
                    encoding="utf-8")
    _purge_constants_pyc()
    lang = sr.active_lang()
    log(f"      section de langue transportee (marqueur seul) : {lang}")


# ==========================================================================
# Verification par sous-processus (prochain processus = verite terrain)
# ==========================================================================

def smoke_test(name: str, log, timeout: int = 240) -> str:
    """Lance un run 'a i u' dans un NOUVEAU processus (cwd temporaire).

    Retourne la sortie ; verifie SUCCESS + annonce du speaker attendu.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, "-m", "vtl_synth.cli.main", "run",
               "--phonetic", "a i u", "-o", tmp, "--no-video"]
        t0 = time.time()
        r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True,
                           timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        log(f"[smoke] exit={r.returncode} en {time.time() - t0:.1f}s")
        for line in out.strip().splitlines():
            log("  | " + line)
        if r.returncode != 0 or "SUCCESS" not in out:
            raise RuntimeError(f"smoke test ECHOUE (exit {r.returncode})")
        if f"Speaker actif : {name}" not in out:
            raise RuntimeError(
                f"annonce attendue 'Speaker actif : {name}' absente de la "
                f"sortie du smoke test")
        if "INCOHERENCE" in out:
            raise RuntimeError("INCOHERENCE signalee dans l'annonce du smoke test")
        return out


# ==========================================================================
# Actions
# ==========================================================================

def do_install(name: str, log) -> None:
    log(f"=== install {name} — {datetime.now().isoformat(timespec='seconds')} ===")
    log(f"python      : {sys.version.split()[0]} ({sys.executable})")
    log(f"depot       : {PIPE_ROOT}")

    # --- pas 1 : controles prealables ---
    if not sr.registry_available():
        raise RuntimeError("registre absent : vtl_synth/data/speakers/registry.json")
    entry = sr.get_entry(name)  # KeyError si inconnu
    log(f"[1/7] registre : {name} -> speaker={entry['speaker']} "
        f"constants={entry['constants']} f0_default={entry['f0_default']} "
        f"({entry['description']})")

    check_editable_pointer(log)

    spk_path = sr.speaker_file_path(name)
    parse_speaker_file(str(spk_path))     # chargeable (XML) ; la wheel 0.0.13
    log(f"[1/7] .speaker chargeable (XML) : {spk_path.name} "
        f"({spk_path.stat().st_size} octets) — NB : la wheel n'expose pas "
        f"load_speaker/vtlInitialize, pas de test de chargement DLL possible")
    src_const = sr.constants_source_path(name)
    h_src = sha256_of(src_const)
    log(f"[1/7] hash constants source : {h_src[:16]} ({src_const.name})")

    # --- pas 2 : backups (si pas deja presents) ---
    log("[2/7] backups originaux")
    backup_originals(log)

    # --- stash de l'etat actuel (rollback) ---
    stash = Stash(Path(tempfile.mkdtemp(prefix="install_speaker_")))
    try:
        # --- pas 3 : permutation constants.py (+ transport de la
        #     section de langue du language pack, s'il y en a une) ---
        dest_const = PIPE_ROOT / r"vtl_synth\core\constants.py"
        old_src = dest_const.read_text(encoding="utf-8")
        shutil.copy2(src_const, dest_const)
        _purge_constants_pyc()
        got = sha256_of(dest_const)
        if got != h_src:
            raise RuntimeError(f"copie constants invalide : {got[:16]} != {h_src[:16]}")
        log(f"[3/7] constants.py permute : {dest_const} sha256={got[:16]} "
            f"(= source {src_const.name})")
        _carry_lang_section(old_src, dest_const, name, log)

        # --- pas 4 : branche orthogonale via marqueur (code deja resolu
        #     par le registre ; aucune copie dans vtl_binaries/) ---
        sr.set_active(name)
        log(f"[4/7] marqueur ACTIVE_SPEAKER = {name} -> branche orthogonale "
            f"lit {sr.active_speaker_file()} (resolution dynamique "
            f"speaker_jd.py / build_phrase_tract.py ; vtl_binaries/JD3.speaker "
            f"NON touche)")

        # --- pas 5 : couche audio/video : ressource wheel partagee ---
        res = wheel_resource()
        shutil.copy2(spk_path, res)
        got = sha256_of(res)
        if got != entry["speaker_sha256"]:
            raise RuntimeError(f"copie ressource wheel invalide : {got[:16]}")
        log(f"[5/7] ressource wheel permutee : {res} sha256={got[:16]}")
        log("      !! active au PROCHAIN processus seulement (la DLL charge "
            "son .speaker a l'import ; wheel 0.0.13 sans vtlInitialize/"
            "vtlClose -> rechargement a chaud impossible, limite consignee)")
        log("      !! ressource PARTAGEE par tout depot utilisant la meme "
            "wheel — l'original est conserve dans backup_install/wheel/")

        # --- pas 6 : f0 — rien a faire ici ---
        log("[6/7] f0 : aucun action fichier — cli/main.py et Pipeline "
            "resolvent -f0 vers SpeakerConfig().f0_default du constants "
            "installe (D14 corrige)")

        # --- pas 7 : verifications finales en nouveau processus ---
        log(f"[7/7] verifications finales (nouveau processus)")
        import vtl_synth  # local (le smoke test couvre le mapping editable)
        log(f"      import vtl_synth -> {vtl_synth.__file__}")
        if "covtl-pipeline" not in str(vtl_synth.__file__).lower():
            raise RuntimeError("import vtl_synth ne resout pas covtl-pipeline")
        smoke_test(name, log)
        log(f"=== install {name} : OK ===")
    except Exception as e:
        log(f"!!! ERREUR pendant install {name} : {e}")
        stash.rollback()
        log("    -> ROLLBACK effectue : etat d'avant install restaure "
            "(constants, marqueur, ressource wheel)")
        raise
    finally:
        shutil.rmtree(stash.dir, ignore_errors=True)


def do_restore(log, check_baselines: bool = False) -> None:
    log(f"=== restore — {datetime.now().isoformat(timespec='seconds')} ===")
    if not BACKUP_MANIFEST.exists():
        raise RuntimeError(f"backups absents : {BACKUP_MANIFEST}")
    manifest = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))

    # hashs des backups compares au manifeste
    for key, _, rel in BACKUP_SOURCES + [("wheel/resources/JD3.speaker", None, r"wheel\JD3.speaker")]:
        dest = BACKUP_DIR / rel
        h = sha256_of(dest)
        if manifest.get(key) != h:
            raise RuntimeError(f"backup altere : {key} {h[:16]} != {manifest.get(key, '?')[:16]}")
    log(f"[1/5] backups intacts ({len(manifest)} entrees, manifeste verifie)")

    stash = Stash(Path(tempfile.mkdtemp(prefix="install_speaker_")))
    try:
        old_src = (PIPE_ROOT / r"vtl_synth\core\constants.py").read_text(
            encoding="utf-8")
        shutil.copy2(BACKUP_DIR / r"pipeline\vtl_synth\core\constants.py",
                     PIPE_ROOT / r"vtl_synth\core\constants.py")
        _purge_constants_pyc()
        dest_const = PIPE_ROOT / r"vtl_synth\core\constants.py"
        h = sha256_of(dest_const)
        if not h.startswith(JD3_CONSTANTS_HASH_PREFIX):
            # soit la section de langue a ete transportee (canonique
            # attendu), soit vrai probleme — tranche sur la forme
            # canonique (region vowel/langue neutralisee)
            if (sr.canonical_hash12(dest_const)
                    != sr.canonical_hash12(BACKUP_DIR
                                           / r"pipeline\vtl_synth\core"
                                           r"\constants.py")):
                raise RuntimeError(f"constants restaure inattendu : {h[:16]}")
        log(f"[2/5] constants.py restaure : sha256={h[:16]} (original JD3)")
        # transport de la section de langue (installations independantes) :
        # restore rend le speaker jd3, PAS l'etat monolingue d'origine
        _carry_lang_section(old_src, dest_const, "jd3", log)

        sr.set_active("jd3")
        log(f"[3/5] marqueur ACTIVE_SPEAKER = jd3 ; branche orthogonale -> "
            f"{sr.active_speaker_file()}")

        res = wheel_resource()
        shutil.copy2(BACKUP_DIR / r"wheel\JD3.speaker", res)
        h = sha256_of(res)
        if h != manifest["wheel/resources/JD3.speaker"]:
            raise RuntimeError(f"ressource wheel restauree inattendue : {h[:16]}")
        log(f"[4/5] ressource wheel restauree : sha256={h[:16]} (original)")

        # vtl_binaries jamais touche : verification defensive
        h = sha256_of(PIPE_ROOT / r"vtl_synth\data\vtl_binaries\JD3.speaker")
        if h != manifest["pipeline/vtl_synth/data/vtl_binaries/JD3.speaker"]:
            raise RuntimeError(f"vtl_binaries/JD3.speaker a ete modifie ! {h[:16]}")
        log("      vtl_binaries/JD3.speaker intouch (hash conforme au backup)")

        smoke_test("jd3", log)
        log("[5/5] smoke test jd3 : SUCCESS + annonce jd3")

        if check_baselines:
            r = subprocess.run(
                [sys.executable, "-m", "pytest",
                 "tests/test_regression_baselines.py", "-q"],
                cwd=str(PIPE_ROOT), capture_output=True, text=True, timeout=600)
            tail = (r.stdout or "").strip().splitlines()[-3:]
            for line in tail:
                log("  | " + line)
            if r.returncode != 0:
                raise RuntimeError("baselines non 15/15 apres restore")
            log("      baselines : 15/15")
        log("=== restore : OK (etat d'origine) ===")
    except Exception as e:
        log(f"!!! ERREUR pendant restore : {e}")
        stash.rollback()
        log("    -> ROLLBACK effectue : etat d'avant restore restaure")
        raise
    finally:
        shutil.rmtree(stash.dir, ignore_errors=True)


def do_list(log) -> None:
    act = sr.active_name()
    print(f"Speakers enregistres (registre {sr.REGISTRY_DIR})")
    print(f"{'nom':6s} {'actif':6s} {'f0_default':>10s}  "
          f"{'speaker':>16s} {'constants':>16s}  description")
    for name in sr.list_speakers():
        e = sr.get_entry(name)
        mark = "  <-- " if name == act else ""
        print(f"{name:6s} {('*' if name == act else ''):6s} "
              f"{e['f0_default']:>10.3f}  {e['speaker_sha256'][:16]:>16s} "
              f"{e['constants_sha256'][:16]:>16s}  {e['description']}{mark}")
    print(f"actif : {act}")
    print("couches : geometry/constants + ortho (marqueur) ; "
          "audio/video = ressource wheel "
          f"({sr.wheel_speaker_name() or 'indisponible'})")


def do_status(log) -> None:
    log(f"=== status — {datetime.now().isoformat(timespec='seconds')} ===")
    tgt = editable_target()
    log(f"pointeur editable   : {tgt or 'INTROUVABLE'} "
        f"{'OK' if 'covtl-pipeline' in tgt.lower() else '!! HORS covtl-pipeline'}")
    log(f"depot               : {PIPE_ROOT}")
    name = sr.active_name()
    e = sr.get_entry(name)
    log(f"speaker actif       : {name} ({e['description']}) "
        f"f0_default={e['f0_default']}")
    lang = sr.active_lang()
    log(f"langue (pack)       : {lang or 'native (aucune section de langue)'}"
        + (f"  !! cibles calibrees JD3 — speaker {name} = HYPOTHESE"
           if lang and name != 'jd3' else ""))
    log(f"constants installe  : {sr.installed_constants_hash()}  "
        f"(attendu {sr.active_constants_hash()} -> "
        f"{'coherent' if sr.constants_coherent() else '!! INCOHERENT'})")
    wp = sr.wheel_resource_path()
    log(f"ressource wheel     : {wp}")
    if wp:
        log(f"  sha256            : {sr.sha256_of(wp)[:16]} -> speaker "
            f"{sr.wheel_speaker_name()}")
    log(f"speaker ortho       : {sr.active_speaker_file()}")
    ref_spk = sr.sha256_of(
        PIPE_ROOT / "vtl_synth" / "data" / "vtl_binaries" / "JD3.speaker")
    log(f"speaker fichier reference vtl_binaries/JD3.speaker : "
        f"{ref_spk[:16]} (intouch par install/restore)")
    if BACKUP_MANIFEST.exists():
        manifest = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))
        log(f"backups             : {BACKUP_DIR} ({len(manifest)} entrees)")
        for k in sorted(manifest):
            log(f"  {k:52s} {manifest[k][:16]}")
    else:
        log("backups             : ABSENTS (aucun install encore fait)")
    for s in sr.list_speakers():
        b = PIPE_ROOT / f"regression_baselines_{s}.json"
        if s != "jd3":
            log(f"baselines {s:4s}        : "
                f"{'presentes' if b.exists() else 'absentes (scripts/regen_baselines.py)'}")
    log(f"annonce actuelle :")
    for line in sr.describe().splitlines():
        log("  " + line)


# ==========================================================================
# CLI
# ==========================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="install_speaker.py",
        description="Gestion multi-speakers de covtl-pipeline "
                    "(constants + branche orthogonale + ressource wheel, "
                    "reversible)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="speakers disponibles + actif")
    p_inst = sub.add_parser("install", help="substituer un speaker")
    p_inst.add_argument("name", help="jd3 | s1 | s2")
    p_res = sub.add_parser("restore", help="revenir a jd3 (etat d'origine)")
    p_res.add_argument("--check-baselines", action="store_true",
                       help="lance aussi pytest baselines (15/15 attendu)")
    sub.add_parser("status", help="etat detaille : hashes, coherences")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "list":
            do_list(None)
            return 0
        if args.cmd == "status":
            log = Tee(UP_DIR / "status.log")
            try:
                do_status(log)
            finally:
                log.close()
            return 0
        if args.cmd == "install":
            log = Tee(UP_DIR / f"install_{args.name}.log")
            try:
                do_install(args.name, log)
            finally:
                log.close()
            return 0
        if args.cmd == "restore":
            log = Tee(UP_DIR / "restore.log")
            try:
                do_restore(log, check_baselines=args.check_baselines)
            finally:
                log.close()
            return 0
    except Exception as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
