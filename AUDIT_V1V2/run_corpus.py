#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_corpus.py — Harnais de reproduction de l'audit V1V2 (hiatus nasal/oral)
============================================================================
covtl-pipeline — clone frais SANS le contournement g2p (revert dea71c6+f62f185).

Pour chaque item du corpus (corpus_v1v2.json) :
  1. synthétise la phrase (Pipeline lang=fr, moteur syl, speaker jd3) ;
  2. capture la chaîne SAMPA réelle en ENTRÉE DU MOTEUR ;
  3. capture le plan d'articulation (syltraj.get_last_build : nœuds,
     ancrages, blocs) — c'est là que l'élision se voit ;
  4. mesure sur le fichier .tract produit : VO (velum, col 7) et
     rel_amp (voixement, col 25) ; sur le .wav : énergie RMS ;
  5. statue : noyaux vocaliques absents du plan, nasalité perdue,
     audio présent.

Sorties (dans AUDIT_V1V2/results/) :
  results.json     — tableau complet machine-lisible
  plans/<id>.txt   — timeline lisible du plan d'articulation
  wav/<id>.wav     — synthèses
  tract/<id>.tract — séquences de paramètres VTL
  logs/<id>.log    — sorties console (dont la garde SAMPA)

Usage :
  python AUDIT_V1V2/run_corpus.py                     # fr : tout le corpus
  python AUDIT_V1V2/run_corpus.py S1a H1              # un sous-ensemble
  python AUDIT_V1V2/run_corpus.py --lang pt           # corpus pt -> results_pt/
  python AUDIT_V1V2/run_corpus.py --lang pt --corpus AUDIT_V1V2/corpus_v1v2_pt.json
  python AUDIT_V1V2/run_corpus.py --no-preproc        # prouve l'inertie :
      # désactive la porte nasal_preproc (repli conservateur) — les sorties
      # doivent être IDENTIQUES au moteur nu sur les entrées sans hiatus
      # nasal (témoins oraux) et DISTINCTES sur les hiatus nasaux.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))          # le clone local prime sur tout install

from vtl_synth import Pipeline                      # noqa: E402
from vtl_synth.core.syltraj import get_last_build   # noqa: E402
from vtl_synth.core.nasal_preproc import get_last_nasal_plan  # noqa: E402

TARGET_SR = 100          # Hz — pas des blocs syltraj
TRACT_SR = 400           # Hz — frames du fichier .tract
VO_COL = 7               # index de VO (ouverture vélaire) dans .tract
RELAMP_COL = 25          # index de rel_amp (voixement) dans .tract (19+6)
SEUIL_VO_NASAL = 0.30    # VO >= 0.3 <=> nasalité réalisée (référence ~0.5)


# --------------------------------------------------------------------------
# Lecteurs de fichiers engine
# --------------------------------------------------------------------------

def read_tract(path: Path):
    """Lit un .tract -> (array (T,30), sample_rate)."""
    rows = []
    sr = TRACT_SR
    started = False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# ---'):
            started = True
            continue
        if not started or not line.strip():
            continue
        if line.startswith('# sample_rate:'):
            sr = int(line.split(':')[1])
            continue
        rows.append([float(x) for x in line.split()])
    return np.asarray(rows, dtype=np.float64), sr


def read_wav(path: Path):
    """Lit un .wav 16 bits mono -> (float array, sr)."""
    with wave.open(str(path), 'rb') as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2')
    return pcm.astype(np.float64) / 32768.0, sr


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


# --------------------------------------------------------------------------
# Plan d'articulation -> structures lisibles
# --------------------------------------------------------------------------

def timeline_of_build(build: dict, plan: dict | None = None):
    """Nœuds + blocs avec offsets cumulés (steps @100 Hz).

    Les nœuds viennent de la vue d'ORIGINE de la porte nasal_preproc
    quand elle est disponible : les nœuds moteurs (syltraj) voient la
    chaîne oralisée (membres d'hiatus nasal=False), la vue d'origine
    porte les drapeaux vrais — c'est elle qui fonde le verdict.
    """
    view = (plan or {}).get('nodes_view') or build['nodes']
    nodes = [{'i': i,
              'kind': (n['kind'] if isinstance(n, dict) else n.kind),
              'key': (n['key'] if isinstance(n, dict) else n.key),
              'nasal': bool(n['nasal'] if isinstance(n, dict) else n.nasal)}
             for i, n in enumerate(view)]
    blocks, off = [], 0
    for b in build['block_info']:
        blocks.append({
            'kind': b.kind, 'n_steps': int(b.n_steps), 'offset': int(off),
            'vowel_key': getattr(b, 'vowel_key', '') or '',
            'nasal': bool(getattr(b, 'nasal', False)),
            'n_cons': int(getattr(b, 'n_cons', 0)),
        })
        off += int(b.n_steps)
    return nodes, blocks, off


def fmt_timeline(sampa: str, nodes, blocks, total) -> str:
    out = [f'SAMPA (entrée moteur) : {sampa}',
           f'Total : {total} steps @100 Hz = {total / TARGET_SR:.2f} s', '',
           'Nœuds : ' + ' '.join(
               f"[{n['kind']}]{n['key']}{'~' if n['nasal'] else ''}"
               for n in nodes), '',
           f"{'offset':>7} {'dur':>5} {'kind':<11} {'voyelle':<7} {'nasal':<6} contenu",
           '-' * 72]
    for b in blocks:
        contenu = ''
        if b['kind'] == 'plateau':
            contenu = f"plateau de /{b['vowel_key']}{'~' if b['nasal'] else ''}/"
        elif b['kind'] == 'background':
            contenu = ('arc de fond : transition diphtongue de base '
                       '(réalisation des noyaux de l\'hiatus)') \
                if not b['vowel_key'] else f"arc de fond via @{b['vowel_key']}"
        elif b['kind'] == 'cluster':
            contenu = f"cluster ({b['n_cons']} cons.)"
        out.append(f"{b['offset']:>7} {b['n_steps']:>5} {b['kind']:<11} "
                   f"{b['vowel_key'] or '-':<7} {str(b['nasal']):<6} {contenu}")
    return '\n'.join(out)


def fmt_nasal_gate(sampa: str, plan: dict | None) -> str:
    """Section « porte nasalité » des plans (couche de pré-traitement)."""
    if not plan:
        return ''
    ev = plan.get('events') or []
    iv = plan.get('intervals') or []
    lines = ['', 'Porte nasalité (pré-traitement nasal_preproc) :',
             f"  chaîne moteur (syltraj) : {plan['motor']}"]
    if not ev:
        lines.append('  aucun membre d\'hiatus nasal — chaîne inchangée'
                     ' (sorties identiques au moteur nu)')
    else:
        runs = plan.get('runs') or []
        for ri, run in enumerate(runs):
            seq = ' . '.join(f"{m['key']}{'~' if m['nasal'] else ''}"
                             for m in run)
            lines.append(f"  run {ri} : [{seq}]")
        for e in ev:
            lines.append(f"  oralisé : run {e['run']} membre {e['member']} "
                         f"→ /{e['key']}~/ (nasalité capturée)")
    if iv:
        for (t0, t1, k) in iv:
            knas = '+'.join(f"{p}~" for p in k.split('+'))
            lines.append(f"  VO orthogonale : /{knas}/ sur "
                         f"[{t0}, {t1}) pas @100 Hz "
                         f"({t0 / TARGET_SR * 1000:.0f}-"
                         f"{t1 / TARGET_SR * 1000:.0f} ms)")
    elif ev:
        lines.append('  ATTENTION : intervalles VO non calculés '
                     '(correspondance runs/blocs non vérifiée)')
    return '\n'.join(lines)


# --------------------------------------------------------------------------
# Mesures
# --------------------------------------------------------------------------

def window(arr: np.ndarray, sr: int, t0_s: float, t1_s: float) -> np.ndarray:
    return arr[int(round(t0_s * sr)):int(round(t1_s * sr))]


def analyse_item(rec: dict, tract: np.ndarray, audio: np.ndarray,
                 wav_sr: int, blocks: list):
    """Stats VO / rel_amp / RMS par fenêtre (blocs background vs plateaux)."""
    bgs = [b for b in blocks if b['kind'] == 'background']
    pls = [b for b in blocks if b['kind'] == 'plateau']
    nas_pls = [b for b in pls if b['nasal']]
    ora_pls = [b for b in pls if not b['nasal']]

    def span(bs):
        if not bs:
            return None
        t0 = min(b['offset'] for b in bs) / TARGET_SR
        t1 = max(b['offset'] + b['n_steps'] for b in bs) / TARGET_SR
        return t0, t1

    def vo_max(bs):
        sp = span(bs)
        if sp is None:
            return None
        seg = window(tract[:, VO_COL], TRACT_SR, *sp)
        return round(float(seg.max()), 3) if len(seg) else None

    def relamp_mean(bs):
        sp = span(bs)
        if sp is None:
            return None
        seg = window(tract[:, RELAMP_COL], TRACT_SR, *sp)
        return round(float(seg.mean()), 3) if len(seg) else None

    def rms_win(bs):
        sp = span(bs)
        if sp is None:
            return None
        seg = window(audio, wav_sr, *sp)
        return round(rms(seg), 4) if len(seg) else None

    def vo_stats(bs):
        """VO max + VO max sur la moitié centrale de la fenêtre."""
        sp = span(bs)
        if sp is None:
            return None, None
        seg = window(tract[:, VO_COL], TRACT_SR, *sp)
        if not len(seg):
            return None, None
        c0 = len(seg) // 4
        c1 = len(seg) - len(seg) // 4
        return (round(float(seg.max()), 3),
                round(float(seg[c0:c1].max()), 3))

    vo_bg_max, vo_bg_centre = vo_stats(bgs)

    def vo_moites_nasales():
        """max(VO) sur chaque intervalle nasal du plan (vérité terrain
        .tract) — la métrique centrale de l'audit ne voyait pas la
        dernière moitié des runs VVV."""
        vals = []
        for (t0, t1, _k) in rec.get('intervalles_vo') or []:
            seg = window(tract[:, VO_COL], TRACT_SR,
                         t0 / TARGET_SR, t1 / TARGET_SR)
            if len(seg):
                vals.append(round(float(seg.max()), 3))
        return vals or None

    vo_nas = vo_moites_nasales()

    rec['mesures'] = {
        'vo_max_background': vo_bg_max,
        'vo_max_background_centre': vo_bg_centre,
        'vo_moites_nasales': vo_nas,
        'vo_moites_nasales_max': (max(vo_nas) if vo_nas else None),
        'vo_max_plateau_nasal': vo_max(nas_pls),
        'vo_max_plateau_oral': vo_max(ora_pls),
        'relamp_moyen_background': relamp_mean(bgs),
        'rms_background': rms_win(bgs),
        'rms_plateaux': rms_win(pls),
        'rms_global': round(rms(audio), 4),
    }
    return rec


def verdict_item(rec: dict, nodes, blocks):
    """Statut : noyaux élidés, nasalité perdue, audio présent.

    Règle exacte du moteur (syltraj.build_anchors) : une voyelle n'a un
    plateau (SylBlock 'plateau', seul porteur du drapeau `nasal`) que si
    elle n'est adjacente à AUCUNE autre voyelle — hold = not prev_v and
    not next_v. Tout membre d'un hiatus V1V2 perd donc son noyau ; si en
    outre il est nasal, sa nasalité (VO) n'est jamais appliquée.
    """
    vowels = [n for n in nodes if n['kind'] == 'V']
    hiatus = [(vowels[i], vowels[i + 1]) for i in range(len(vowels) - 1)
              if vowels[i + 1]['i'] == vowels[i]['i'] + 1]
    hiatus_ids = {v['i'] for pair in hiatus for v in pair}

    plateau_keys = [b['vowel_key'] for b in blocks if b['kind'] == 'plateau']
    expected = [v['key'] for v in vowels]
    manquants = [v for v in vowels if v['i'] in hiatus_ids]

    m = rec['mesures']
    nasal_in_hiatus = any(v['nasal'] for pair in hiatus for v in pair)
    # critère VO : moitiés nasales du plan (repli : demi-fenêtre centrale
    # de l'arc, métrique de l'audit initial)
    vo_nas = m.get('vo_moites_nasales_max')
    vo_bg = vo_nas if vo_nas is not None else m['vo_max_background_centre']
    vo_ref = m['vo_max_plateau_nasal']
    rms_bg, rms_pl, rms_gl = (m['rms_background'], m['rms_plateaux'],
                              m['rms_global'])
    ref_audio = max(rms_pl or 0.0, rms_gl or 0.0, 1e-9)
    audio_present = rms_bg is not None and rms_bg > 0.05 * ref_audio
    nasalite_perdue = bool(
        nasal_in_hiatus
        and (vo_bg is None or vo_bg < SEUIL_VO_NASAL))
    # arc statique : paires de même cible orale (ex. a~.a, O~.O~) — le
    # fond ne glisse même pas, la voyelle tenue est purement orale
    arc_statique = any(
        a['key'] == b['key'] for a, b in hiatus)

    rec['verdict'] = {
        'voyelles_entree': [f"{v['key']}{'~' if v['nasal'] else ''}"
                            for v in vowels],
        'hiatus': [f"{a['key']}{'~' if a['nasal'] else ''}."
                   f"{b['key']}{'~' if b['nasal'] else ''}"
                   for a, b in hiatus],
        'noyaux_attendus': len(expected),
        'noyaux_plateaux_realises': len(plateau_keys),
        'noyaux_elides': [f"{v['key']}{'~' if v['nasal'] else ''}"
                          for v in manquants],
        'nasalite_perdue': nasalite_perdue,
        'arc_statique': arc_statique,
        'audio_present_dans_hiatus': audio_present,
        'vo_hiatus_centre': m['vo_max_background_centre'],
        'vo_moites_nasales': vo_nas,
        'vo_critere': vo_bg,
        'vo_reference_nasale': vo_ref,
    }
    return rec


# --------------------------------------------------------------------------
# Boucle principale
# --------------------------------------------------------------------------

def main(argv):
    parser = argparse.ArgumentParser(
        description='Harnais audit V1V2 (hiatus nasal/oral), paramétrable '
                    'par langue.')
    parser.add_argument('ids', nargs='*', help='sous-ensemble d\'ids')
    parser.add_argument('--lang', default='fr',
                        help='langue du corpus (fr, pt, …) — Pipeline(lang=…)')
    parser.add_argument('--corpus', default=None,
                        help='fichier corpus JSON (défaut : corpus_v1v2.json, '
                             'ou corpus_v1v2_<lang>.json si --lang != fr)')
    parser.add_argument('--results', default=None,
                        help='dossier résultats (défaut : results, ou '
                             'results_<lang> si --lang != fr)')
    parser.add_argument('--no-preproc', action='store_true',
                        help='désactive la porte nasal_preproc (repli '
                             'conservateur) — preuve d\'inertie / avant-après')
    args = parser.parse_args(argv)

    lang = args.lang
    corpus_path = (Path(args.corpus) if args.corpus else
                   HERE / (f'corpus_v1v2.json' if lang == 'fr' else
                           f'corpus_v1v2_{lang}.json'))
    res_dir = HERE / (args.results or ('results' if lang == 'fr'
                                       else f'results_{lang}'))

    corpus = json.loads(corpus_path.read_text(encoding='utf-8'))
    items = [it for it in corpus['items'] if not args.ids or it['id'] in args.ids]
    if not items:
        print('Aucun item sélectionné.'); return 1

    res_dir.mkdir(parents=True, exist_ok=True)
    for sub in ('wav', 'tract', 'plans', 'logs'):
        (res_dir / sub).mkdir(parents=True, exist_ok=True)

    if args.no_preproc:
        # inertie / avant-après : la porte nasal_preproc est neutralisée
        # (repli conservateur — la chaîne moteur reste la chaîne orale)
        import vtl_synth.core.nasal_preproc as _npre
        _npre.split_nasal_hiatus = (lambda phrase: (phrase, {
            'original': phrase, 'motor': phrase, 'nodes_view': [],
            'runs': [], 'events': [], 'intervals': None, 'fallback': False}))
        print('*** porte nasal_preproc NEUTRALISÉE (--no-preproc) ***')

    pipe = Pipeline(lang=lang)
    results = []
    for it in items:
        rid = it['id']
        entree = it['texte'] if it['use_g2p'] else it['sampa']
        print(f"— [{rid}] {it['situation']} : {entree!r}")
        log_path = res_dir / 'logs' / f'{rid}.log'
        with log_path.open('w', encoding='utf-8') as lf, \
                contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
            try:
                res = pipe.run(entree, output_dir=str(res_dir / '_tmp'),
                               use_g2p=it['use_g2p'], video=False, label=rid)
            except Exception as exc:                    # noqa: BLE001
                print(f'ERREUR synthesis {rid}: {exc!r}')
                results.append({'id': rid, 'erreur': repr(exc)})
                continue
            build = get_last_build()
            plan = get_last_nasal_plan()
            nodes, blocks, total = timeline_of_build(build, plan)
            sampa = res.sampa

        # fichiers renommés
        wav_src = res_dir / '_tmp' / f'{rid}.wav'
        trt_src = res_dir / '_tmp' / f'{rid}.tract'
        wav_dst = res_dir / 'wav' / f'{rid}.wav'
        trt_dst = res_dir / 'tract' / f'{rid}.tract'
        wav_dst.write_bytes(wav_src.read_bytes())
        trt_dst.write_bytes(trt_src.read_bytes())

        rec = {'id': rid, 'situation': it['situation'], 'note': it.get('note', ''),
               'entree': entree, 'use_g2p': it['use_g2p'],
               'sampa_moteur': sampa, 'phrases': res.phrases,
               'duree_s': round(res.duration_s, 3),
               'porte_moteur': (plan or {}).get('motor'),
               'intervalles_vo': (plan or {}).get('intervals')}
        tract, _ = read_tract(trt_dst)
        audio, wav_sr = read_wav(wav_dst)
        rec['n_frames_tract'] = int(tract.shape[0])
        rec = analyse_item(rec, tract, audio, wav_sr, blocks)
        rec = verdict_item(rec, nodes, blocks)
        rec['nodes'] = nodes
        rec['blocks'] = blocks
        rec['md5_wav'] = hashlib.md5(wav_dst.read_bytes()).hexdigest()
        rec['md5_tract'] = hashlib.md5(trt_dst.read_bytes()).hexdigest()
        results.append(rec)

        (res_dir / 'plans' / f'{rid}.txt').write_text(
            fmt_timeline(sampa, nodes, blocks, total)
            + fmt_nasal_gate(sampa, plan) + '\n',
            encoding='utf-8')
        v = rec['verdict']
        print(f"    SAMPA moteur : {sampa} | chaîne syltraj : "
              f"{rec['porte_moteur']}")
        print(f"    noyaux dans l'arc de fond : {v['noyaux_elides'] or 'aucun'} "
              f"| nasalité perdue : {v['nasalite_perdue']} "
              f"(VO moitiés nasales={v['vo_moites_nasales']}, "
              f"réf. nasale={v['vo_reference_nasale']}) "
              f"| audio : {'oui' if v['audio_present_dans_hiatus'] else 'NON'}"
              f"{' | ARC STATIQUE' if v['arc_statique'] else ''}")

    # ménage du répertoire temporaire
    import shutil
    shutil.rmtree(res_dir / '_tmp', ignore_errors=True)

    out = {'corpus': corpus['titre'], 'moteur': corpus['moteur'],
           'langue': lang, 'preproc_neutralise': args.no_preproc,
           'seuils': {'vo_nasal': SEUIL_VO_NASAL,
                      'note': 'VO>=0.3 <=> nasalité réalisée (plateau nasal sain ~0.5)'},
           'items': results}
    (res_dir / 'results.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

    # tableau récapitulatif
    print('\n=== RÉCAPITULATIF ===')
    hdr = (f"{'id':<4} {'situation':<32} {'SAMPA moteur':<22} "
           f"{'dans arc':<12} {'VO nas.':<8} {'VO réf.':<8} {'nas.perdue':<10}")
    print(hdr); print('-' * len(hdr))
    for r in results:
        if 'erreur' in r:
            print(f"{r['id']:<4} ERREUR : {r['erreur']}")
            continue
        v = r['verdict']
        print(f"{r['id']:<4} {r['situation'][:31]:<32} "
              f"{r['sampa_moteur'][:21]:<22} "
              f"{(','.join(v['noyaux_elides']))[:11]:<12} "
              f"{str(v['vo_critere']):<8} {str(v['vo_reference_nasale']):<8} "
              f"{'OUI' if v['nasalite_perdue'] else 'non':<10}")
    print(f"\nÉcrit : {res_dir / 'results.json'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
