# -*- coding: utf-8 -*-
"""
calibrate_fine_v2.py — Phase 2 corrigée (défaut D15 du rapport
rapport_test_transfert_DVTD.md) pour les speakers non dérivés de JD3.

Deux correctifs par rapport à covtl-speaker/calibrate_fine.py :

1. OCCLUSIFS — recherche d'onset bidimensionnelle : l'ancre θ de phase 1
   peut être fortement pivotée sur une anatomie étrangère à JD3 (s2 : b à
   280° vs 50°), et la fermeture n'existe alors pas dans cette direction.
   On balaie donc θ autour de l'angle de lieu CANONIQUE (θ JD3 de
   jd3_constants.py, fenêtre ±60°, pas 10°) en plus de l'ancre, et on
   retient le couple (ρ_onset, θ) de plus petit ρ, départage par la
   proximité de θ au lieu canonique. Raffinement du pas 0,10 au pas 0,01.

2. FRICATIFS — les fenêtres de gap (cm²) sont calibrées JD3 ; les aires
   varient comme le carré du rapport de longueur de conduit s_L
   (s_L = longueur sous-glottique du speaker / JD3). Les bornes de
   fenêtre sont multipliées par s_L², la grille est centrée sur le lieu
   canonique, avec raffinement local (±0,04 ρ, ±1° θ).

Les l/L restent ancrés (latérales : le tube central ne voit pas
l'ouverture latérale, mode TS3) ; les clés dérivées (m, n, z_front, R, g)
et la rédaction du constants.py sont celles de la phase 1
(adapt_speaker.rendre_constants).

Usage :
    python calibrate_fine_v2.py s1.speaker --ref s1_constants.py -o out\\fine\\s1
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

_SPEAKER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'vtl_synth', 'data', 'speakers')

_adapt_path = os.environ.get(
    'ADAPT_SPEAKER', r'P:\covtl-speaker\adapt_speaker.py')
_spec = importlib.util.spec_from_file_location('adapt_speaker', _adapt_path)
# Outil de développement : adapt_speaker.py appartient au projet
# d'adaptation externe (covtl-speaker) ; chemin surchargeable par la
# variable d'environnement ADAPT_SPEAKER.
if not os.path.isfile(_spec.origin):
    sys.exit("adapt_speaker.py introuvable (%s) — cet outil de "
             "calibration requiert le projet externe covtl-speaker ; "
             "positionner ADAPT_SPEAKER=<chemin>/adapt_speaker.py "
             "(les constants générés sont déjà commités dans "
             "vtl_synth/data/speakers/)." % _spec.origin)
adapt = importlib.util.module_from_spec(_spec)
sys.modules['adapt_speaker'] = adapt
_spec.loader.exec_module(adapt)

import vocaltractlab as vtl  # noqa: E402

# ---------------------------------------------------------------------------
# Tables (reprises de calibrate_fine.py)
# ---------------------------------------------------------------------------
OCCLUSION = 0.005
SEUIL_PARASITIQUE = 0.10
MARGE_PARASITIQUE = 2
SECTIONS_LARYNX = 6

ART_LANGUE, ART_LEVRES = (1,), (3,)

ZONES = {
    'labial':     (34, 40),
    'alveolaire': (27, 36),
    'postalv':    (25, 32),
    'palatal':    (20, 29),
    'velaire':    (14, 25),
}

OCCLUSIFS: Dict[str, Tuple[str, Tuple[int, ...], float]] = {
    'b':     ('labial',     ART_LEVRES, 0.36),
    'd':     ('alveolaire', ART_LANGUE, 0.00),
    'g_vel': ('velaire',    ART_LANGUE, 0.00),
    'g_pal': ('palatal',    ART_LANGUE, 0.35),
    'dZ':    ('palatal',    ART_LANGUE, 0.75),
    'C':     ('palatal',    ART_LANGUE, 0.70),
}

FRICATIFS: Dict[str, Tuple[str, Tuple[int, ...], Tuple[float, float], bool]] = {
    'v': ('labial',     ART_LEVRES, (0.15, 0.25), False),
    'z': ('alveolaire', ART_LANGUE, (0.10, 0.30), True),
    'Z': ('postalv',    ART_LANGUE, (0.25, 1.40), False),
    'D': ('alveolaire', ART_LANGUE, (0.10, 0.40), False),
    'X': ('velaire',    ART_LANGUE, (0.30, 1.50), False),
    'l': ('alveolaire', ART_LANGUE, (0.05, 0.75), False),
    'L': ('alveolaire', ART_LANGUE, (0.05, 0.75), False),
}

CLES_CONSERVEES_ANCRE = frozenset({'l', 'L'})

ORDRE_19 = ['HX', 'HY', 'JX', 'JA', 'LP', 'LD', 'VS', 'VO',
            'TCX', 'TCY', 'TTX', 'TTY', 'TBX', 'TBY', 'TRX', 'TRY',
            'TS1', 'TS2', 'TS3']

SELECTEURS = {
    'b': ['JA', 'LD', 'LP'],
    'd': ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TTX', 'TTY'],
    'g_vel': ['JA', 'TCX', 'TCY', 'TBX', 'TBY'],
    'g_pal': ['JA', 'TCY', 'TBX', 'TBY'],
    'dZ': ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'LP'],
    'C': ['JA', 'TCX', 'TCY'],
    'v': ['JA', 'JX', 'LP', 'LD'],
    'z': ['JA', 'TCX', 'TCY', 'TBX', 'TBY'],
    'Z': ['JA', 'TCX', 'TBX', 'TBY', 'LP'],
    'D': ['JA', 'TCX', 'TCY', 'TBX', 'TBY'],
    'X': ['JA', 'TCX', 'TCY', 'TBX', 'TBY', 'TS2'],
    'l': ['JA', 'TCX', 'TCY', 'TBX', 'TBY'],
    'L': ['JA', 'TCX', 'TCY', 'TBX', 'TBY'],
}

RHO_ONSET_MAX = 2.20       # étendu (1.75 en v1) : conduits longs ferment plus tard
THETA_FENETRE_ONSET = 60   # ± deg (int) autour du lieu canonique
RHO_PLAGE_FRIC = 0.35

LONG_JD3 = 23.0            # <subglottal_cavity length> de JD3 (cm)


def longueur_sous_glottale(speaker_file: str) -> float:
    with open(speaker_file, 'r', encoding='utf-8') as f:
        m = re.search(r'<subglottal_cavity\s+length="([\d.]+)"', f.read())
    return float(m.group(1)) if m else LONG_JD3


def theta_canoniques() -> Dict[str, float]:
    """θ JD3 (constants de référence) = angle de lieu canonique."""
    spec = importlib.util.spec_from_file_location(
        'jd3_const', os.path.join(_SPEAKER_DIR, 'jd3_constants.py'))
    jd3 = importlib.util.module_from_spec(spec)
    sys.modules['jd3_const'] = jd3
    spec.loader.exec_module(jd3)
    return {k: v[1] for k, v in jd3.CONSONANT_TARGETS.items()}


# ---------------------------------------------------------------------------
# Évaluateur (identique à v1, hors fenêtres paramétrées par s_L²)
# ---------------------------------------------------------------------------
class Evaluateur:
    def __init__(self, speaker_file: str, co_final, cibles_v):
        vtl.load_speaker(speaker_file)
        self.co = co_final
        self.cibles_v = cibles_v
        self.voyelles = tuple(cibles_v.keys())
        self.fonds = {v: adapt.projeter(co_final, *cibles_v[v])
                      for v in self.voyelles}
        self.n_evals = 0

    def _tube(self, clé, rho_c, th_c, voyelle):
        fond = self.fonds[voyelle]
        vec = [0.0] * 19
        for p, val in fond.items():
            vec[ORDRE_19.index(p)] = val
        for p in SELECTEURS[clé]:
            c1, c0, c2 = self.co[p]
            vec[ORDRE_19.index(p)] = c1 + rho_c * c0 * math.cos(c2 - th_c)
        self.n_evals += 1
        ts = vtl.tract_state_to_tube_state(np.array(vec))
        return np.array(ts['tube_area']), np.array(ts['tube_articulator'])

    def mesure(self, clé, rho_c, th_c, voyelle):
        spec = OCCLUSIFS[clé] if clé in OCCLUSIFS else FRICATIFS[clé]
        z0, z1 = ZONES[spec[0]]
        a, art = self._tube(clé, rho_c, th_c, voyelle)
        k = int(np.argmin(a[z0:z1])) + z0
        hors = np.concatenate([a[SECTIONS_LARYNX:z0 - MARGE_PARASITIQUE],
                               a[z1 + MARGE_PARASITIQUE:]])
        art_h = np.concatenate([art[SECTIONS_LARYNX:z0 - MARGE_PARASITIQUE],
                                art[z1 + MARGE_PARASITIQUE:]])
        ling = hors[art_h == 1]
        return float(a[k]), int(art[k]), (float(ling.min()) if ling.size else 10.0)

    def fermeture_ok(self, clé, rho_c, th_c, voyelle, seuil=OCCLUSION):
        zone_nom, arts, _ = OCCLUSIFS[clé]
        m, a, pl = self.mesure(clé, rho_c, th_c, voyelle)
        return (m <= seuil and a in arts and pl >= SEUIL_PARASITIQUE), m, pl

    def ferme_tout(self, clé, rho, th):
        return all(self.fermeture_ok(clé, rho, th, v)[0]
                   for v in self.voyelles)

    def onset_a_theta(self, clé, th, pas=0.10):
        """Onset à θ imposé : plus petit ρ fermant les 12 voyelles."""
        for rho in np.arange(0.20, RHO_ONSET_MAX + 1e-9, pas):
            if self.ferme_tout(clé, rho, th):
                borne = rho - pas
                r_prev = rho
                for r2 in np.arange(borne, rho + 1e-9, pas / 10.0):
                    if self.ferme_tout(clé, r2, th):
                        return round(float(r2), 3)
                return round(float(r_prev), 3)
        return None

    def cout_occlusif(self, clé, rho_c, th_c):
        """Coût de compromis quand la fermeture exacte n'existe pas
        (anatomies non JD3) : somme sur les voyelles du gap de zone au-dessus
        du seuil (borné), + pénalités parasitaire et d'articulateur."""
        c_tot = 0.0
        arts = OCCLUSIFS[clé][1]
        for v in self.voyelles:
            m, a, pl = self.mesure(clé, rho_c, th_c, v)
            dz = 0.0 if m <= OCCLUSION else min(1.0, (m - OCCLUSION) / 0.20)
            cpar = max(0.0, (SEUIL_PARASITIQUE - pl) / 0.10) if pl < SEUIL_PARASITIQUE else 0.0
            cart = 0.0 if a in arts else 1.0
            c_tot += dz + 5.0 * cpar + cart
        return c_tot

    def cout_gap(self, clé, rho_c, th_c, fenetre):
        lo, hi = fenetre
        c_tot = 0.0
        excl_iu = FRICATIFS[clé][3]
        for v in self.voyelles:
            if excl_iu and v in ('i', 'u'):
                continue
            m, a, pl = self.mesure(clé, rho_c, th_c, v)
            if m < lo:
                dz = (lo - m) / (hi - lo)
            elif m > hi:
                dz = (m - hi) / (hi - lo)
            else:
                dz = 0.0
            cpar = max(0.0, (SEUIL_PARASITIQUE - pl) / 0.10) if pl < SEUIL_PARASITIQUE else 0.0
            cart = 0.0 if a in FRICATIFS[clé][1] else 1.0
            c_tot += dz + 5.0 * cpar + cart
        return c_tot


def ecart_angle(a: float, b: float) -> float:
    d = math.degrees(a - b) % 360.0
    return min(d, 360.0 - d)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Décalages étage 2 corrigés (setup non-JD3) : la règle TTY de
# appliquer_decalages remplace c0 par (0.80−Va)/2.3, ce qui ne coïncide avec
# le solve natif que pour JD3 (Va_JD3 = −1.694). Sur s1/s2 cette substitution
# relève la pointe aux ancres (s2 : V(π) −1.299 → +0.394) — source du
# bunching et des occlusions apicales parasites. On conserve ici c0/c2
# natifs du solve analytique et le bonus d'occlusion apicale c1 += 0.15.
# ---------------------------------------------------------------------------
def appliquer_decalages_v2(co_base, sf):
    co_final, journal = adapt.appliquer_decalages(co_base, sf)
    c1b, c0b, c2b = co_base['TTY']
    co_final['TTY'] = (c1b + 0.15, c0b, c2b)
    journal.append('TTY : c0/c2 natifs conservés, c1 += 0.15 (règle JD3 '
                   '(0.80−Va)/2.3 non transférée, correctif bunching)')
    return co_final, journal


def calibrer(speaker_file: str, outdir: Optional[str] = None,
             ref_path: Optional[str] = None, ecrire: bool = True):
    t0 = time.time()
    sf = adapt.parse_speaker(speaker_file)
    co_base = adapt.resoudre_covtl(sf)
    co_final, journal_co = appliquer_decalages_v2(co_base, sf)
    cibles_v, journal_v = adapt.cibles_voyelles(sf, co_base, co_final)
    familles, journal_c = adapt.cibles_consonnes(sf, co_base, co_final, 'deterministic')
    echelle = sum(co_final[p][1] for p in adapt.COVTL_PARAMS) / (
        adapt.C0_MOYEN_JD3 * len(adapt.COVTL_PARAMS))
    ancres = adapt.appliquer_calibrage(familles, cibles_v, echelle, 'calibrated')

    s_l = longueur_sous_glottale(speaker_file) / LONG_JD3
    facteur_aire = s_l * s_l
    th_can = theta_canoniques()
    ev = Evaluateur(speaker_file, co_final, cibles_v)

    rap = [f"# Calibration fine v2 (phase 2, correctifs D15) — speaker {sf.name}\n",
           f"Source : `{speaker_file}`",
           f"s_L = {s_l:.3f} (facteur d'aire s_L² = {facteur_aire:.3f})",
           "\nOcclusifs : onset 2D (ρ, θ) autour du lieu canonique JD3 (±60°, "
           "pas 10°, puis ancre), ρ = onset + marge de pressé par lieu. "
           "Fricatifs : grille centrée lieu canonique, fenêtres × s_L².\n",
           "| Clé | ancre ph.1 (ρ, θ°) | v2 (ρ, θ°) | détail |",
           "|---|---|---|---|"]

    resultats: Dict[str, Tuple[float, float]] = {}
    for clé in list(OCCLUSIFS) + list(FRICATIFS):
        rho_a, th_a = ancres[clé]
        if clé in CLES_CONSERVEES_ANCRE:
            resultats[clé] = (rho_a, th_a)
            rap.append(f"| {clé} | ({rho_a:.2f}, {math.degrees(th_a):.0f}°) "
                       f"| **({rho_a:.2f}, {math.degrees(th_a):.0f}°)** "
                       f"| ancre conservée (latéral / TS3) |")
            print(f"[fine2] {clé:6s} ({rho_a:.2f},{math.degrees(th_a):5.0f}°) "
                  f"-> ancre conservée")
            continue
        th_ref = th_can.get(clé, th_a)
        if clé in OCCLUSIFS:
            thetas: List[float] = [th_ref + math.radians(t) for t in
                                   range(-THETA_FENETRE_ONSET,
                                         THETA_FENETRE_ONSET + 1, 10)]
            if all(ecart_angle(t, th_a) > 1.0 for t in thetas):
                thetas.append(th_a)
            # grille (ρ, θ) : coût de compromis ; à coût quasi égal (±0.5),
            # plus petit ρ (esprit onset), départage θ proche du canonique
            grille = []
            for th in thetas:
                for rho in np.arange(0.20, 1.70 + 1e-9, 0.10):
                    c = ev.cout_occlusif(clé, float(rho), th)
                    grille.append((round(c, 6), float(rho),
                                   ecart_angle(th, th_ref), th))
            c_best = min(g[0] for g in grille)
            proches = [g for g in grille if g[0] <= c_best + 0.5]
            proches.sort(key=lambda g: (g[1], g[2], g[0]))
            c0, r0, dth0, th0 = proches[0]
            # raffinement local (pas 0.01 / 1°)
            for drho in np.arange(-0.09, 0.091, 0.01):
                rho = min(max(0.20, r0 + drho), 1.70)
                c = ev.cout_occlusif(clé, float(rho), th0)
                if c < c0 - 1e-9:
                    c0, r0 = round(c, 6), float(rho)
            for dth in (-1.0, 1.0):
                th = th0 + math.radians(dth)
                c = ev.cout_occlusif(clé, float(r0), th)
                if c < c0 - 1e-9:
                    c0, th0 = round(c, 6), th
            fermeture_exacte = ev.ferme_tout(clé, float(r0), th0)
            if fermeture_exacte:
                r0 = min(r0 + OCCLUSIFS[clé][2], 2.0)
                note = (f'onset exact + marge {OCCLUSIFS[clé][2]:.2f} '
                        f'(θ {math.degrees(th0):.0f}°, '
                        f'Δ lieu {ecart_angle(th0, th_ref):.0f}°)')
            else:
                note = (f'compromis coût {c0:.2f} — fermeture exacte '
                        f'inatteignable sur cette anatomie ; '
                        f'θ {math.degrees(th0):.0f}° '
                        f'(Δ lieu {ecart_angle(th0, th_ref):.0f}°)')
            rho_f, th_f, detail = round(r0, 2), th0, note
        else:
            lo, hi = FRICATIFS[clé][2]
            fen = (lo * facteur_aire, hi * facteur_aire)
            grille = []
            for dth in np.arange(-30.0, 30.0 + 1e-9, 5.0):
                th = math.radians((math.degrees(th_ref) + dth) % 360.0)
                for drho in np.arange(-RHO_PLAGE_FRIC, RHO_PLAGE_FRIC + 1e-9, 0.05):
                    rho = min(max(0.20, rho_a + drho), 1.70)
                    c = ev.cout_gap(clé, float(rho), th, fen)
                    grille.append((round(c, 6), round(abs(dth), 1),
                                   round(abs(drho), 3), float(rho), th))
            c_best = min(g[0] for g in grille)
            proches = [g for g in grille if g[0] <= c_best + 0.5]
            proches.sort(key=lambda g: (g[1], g[2], g[0]))
            # raffinement local autour du meilleur candidat
            c0, _, _, r0, th0 = proches[0]
            for dth in (-1.0, 0.0, 1.0):
                for drho in (-0.04, -0.02, 0.0, 0.02, 0.04):
                    th = math.radians((math.degrees(th0) + dth) % 360.0)
                    rho = min(max(0.20, r0 + drho), 1.70)
                    c = ev.cout_gap(clé, float(rho), th, fen)
                    if c < c0:
                        c0, r0, th0 = round(c, 6), float(rho), th
            rho_f, th_f = round(r0, 2), th0
            detail = (f'coût {c0:.3f} (grille {c_best:.3f}) ; '
                      f'fenêtre ({fen[0]:.2f}-{fen[1]:.2f}) cm²')
        resultats[clé] = (rho_f, th_f)
        rap.append(f"| {clé} | ({rho_a:.2f}, {math.degrees(th_a):.0f}°) "
                   f"| **({rho_f:.2f}, {math.degrees(th_f):.0f}°)** | {detail} |")
        print(f"[fine2] {clé:6s} ({rho_a:.2f},{math.degrees(th_a):5.0f}°) -> "
              f"({rho_f:.2f},{math.degrees(th_f):5.0f}°)  {detail}")

    # clés dérivées (règles phase 1, inchangées)
    resultats['m'] = resultats['b']
    resultats['n'] = (resultats['d'][0], math.radians(7.0))
    resultats['z_front'] = (resultats['z'][0] - 0.10, resultats['z'][1])
    resultats['R'] = resultats['X']
    resultats['g'] = resultats['g_vel']
    resultats.setdefault('w', (0.60, math.pi / 3))
    resultats.setdefault('j', (0.80, cibles_v['i'][1]))
    resultats.setdefault('ɥ', cibles_v.get('y', (0.519, 4.548)))
    resultats.setdefault('h', (0.50, math.pi))
    resultats.setdefault('N', (1.20, math.radians(60.0)))
    resultats.setdefault('J', (1.20, 5 * math.pi / 3))

    # écart vs constants actuels du pipeline (la convergence JD3 n'a plus
    # de sens pour une anatomie étrangère — D15)
    if ref_path and os.path.exists(ref_path):
        spec = importlib.util.spec_from_file_location('ref_const_v2', ref_path)
        ref = importlib.util.module_from_spec(spec)
        sys.modules['ref_const_v2'] = ref
        spec.loader.exec_module(ref)
        cles_test = sorted((set(OCCLUSIFS) | set(FRICATIFS) | {'m', 'n'})
                           & set(ref.CONSONANT_TARGETS))
        lignes = ['\n## Écart au constants.py actuel du pipeline\n',
                  '| Clé | actuel (ρ, θ°) | v2 (ρ, θ°) | Δρ | Δθ° |',
                  '|---|---|---|---|---|']
        for clé in cles_test:
            rr, rt = ref.CONSONANT_TARGETS[clé][0], ref.CONSONANT_TARGETS[clé][1]
            gr, gt = resultats[clé]
            dr = gr - rr
            dt = (math.degrees(gt - rt) + 180) % 360 - 180
            lignes.append(f"| {clé} | ({rr:.2f}, {math.degrees(rt):.0f}°) "
                          f"| ({gr:.2f}, {math.degrees(gt):.0f}°) "
                          f"| {dr:+.2f} | {dt:+.0f} |")
        rap.extend(lignes)
        print(f"[fine2] tableau d'écart vs {os.path.basename(ref_path)}")

    if ecrire:
        out = outdir or os.path.join('out', 'fine', f'{sf.name}_fine')
        os.makedirs(out, exist_ok=True)
        presets = adapt.extraire_glottis(sf)
        scfg = adapt.config_speaker(sf, presets)
        code = adapt.rendre_constants(sf, co_final, cibles_v, resultats,
                                      presets, scfg, journal_co, journal_v,
                                      journal_c)
        with open(os.path.join(out, 'constants.py'), 'w', encoding='utf-8') as f:
            f.write(code)
        rap.append(f"\n\nDurée : {time.time() - t0:.0f} s ; "
                   f"{ev.n_evals} évaluations de fonction d'aire.")
        with open(os.path.join(out, 'calibration_report.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(rap))
        print(f"[fine2] sortie -> {out}")
    return resultats


def main():
    ap = argparse.ArgumentParser(description='Phase 2 v2 (correctifs D15)')
    ap.add_argument('speaker')
    ap.add_argument('-o', '--outdir', default=None)
    ap.add_argument('--ref', default=None,
                    help="constants.py actuel du speaker (tableau d'écart)")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    calibrer(args.speaker, args.outdir, args.ref, ecrire=not args.dry_run)


if __name__ == '__main__':
    main()
