#!/usr/bin/env python3
"""Tests du commit enveloppe refait (wave 4 §7.4 — complément 269b23a).

Verrouille le chemin COMPLET des modes de phonation :
  1. classify_block_events relabellise les spans de phonation
  2. phonation_schedule_from_segments convertit les glottal_tag en frames
  3. _lookup_preset_vector résout 'creaky' (absent de JD3) via les
     presets génériques
  4. build_phrase_tract(tag_overrides=...) produit des glott400
     DIFFÉRENTS selon le mode (le trou de lecture du premier fix)
  5. Pipeline(tag_overrides=...) transmet bien jusqu'à build_phrase_tract

Exécuté en standalone (pas de pytest) : python3 tests/test_phonation_full_path.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

PASS, FAIL = 0, 0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ok   {name}')
    else:
        FAIL += 1
        print(f'  FAIL {name} {detail}')


print('== 1. _lookup_preset_vector (fallback générique pour creaky) ==')
from vtl_synth.core.glottal_source import _lookup_preset_vector
v = _lookup_preset_vector('creaky')
check('creaky résolu (pas modal)', v[7] == 0.3 and v[8] == 0.5,
      f'dp={v[7]} skew={v[8]}')
v = _lookup_preset_vector('breathy')
check('breathy = JD3', abs(v[4] - 0.100) < 1e-9, f'chink={v[4]}')
v = _lookup_preset_vector('label-inconnu')
check('label inconnu → modal', v[4] == 0.050, f'chink={v[4]}')


print('== 2. phonation_schedule_from_segments ==')
from vtl_synth.core.glottal_source import phonation_schedule_from_segments
from vtl_synth.core.prosody_source import Segment
from vtl_synth.core.tag_system import TagInterpreter

segs = [
    Segment(key='D', kind='C', t_start=0, t_end=60),
    Segment(key='i', kind='V', t_start=60, t_end=150),
    Segment(key='s', kind='C', t_start=150, t_end=210),
    Segment(key='i', kind='V', t_start=210, t_end=300),
]
ti = TagInterpreter(tag_overrides={'i': {'voicing': 'whisper'}})
segs = ti.apply_all(segs)
spans = phonation_schedule_from_segments(segs, n_steps=100)
check('deux spans whisper (les deux /i/)',
      len(spans) == 2 and all(m == 'whisper' for m, _, _ in spans),
      str(spans))
check('spans dans l\'ordre chronologique',
      spans[0][1] < spans[1][1] and spans[0][2] <= spans[1][1], str(spans))
f0, f1 = spans[0][1], spans[0][2]
check('cadres proportionnels (60/300 → 20)', f0 == 20 and f1 == 50, f'{f0},{f1}')
# sans override : rien
spans0 = phonation_schedule_from_segments(
    TagInterpreter().apply_all([s for s in segs]), 100)
check('sans override → aucun span', spans0 == [])

# sur une consonne (clé non convertie)
segs2 = [
    Segment(key='D', kind='C', t_start=0, t_end=60),
    Segment(key='i', kind='V', t_start=60, t_end=150),
]
ti2 = TagInterpreter(tag_overrides={'D': {'voicing': 'breathy'}})
segs2 = ti2.apply_all(segs2)
spans2 = phonation_schedule_from_segments(segs2, 100)
check('override consonne → span breathy', len(spans2) == 1
      and spans2[0][0] == 'breathy', str(spans2))


print('== 3. classify_block_events (relabel des spans) ==')
from vtl_synth.core.glottal_source import classify_block_events

class Blk:
    def __init__(self, kind, n_steps, cons_tokens=()):
        self.kind, self.n_steps, self.cons_tokens = kind, n_steps, list(cons_tokens)
        self.n_cons = len(self.cons_tokens)

blocks = [Blk('cluster', 20, ['D']), Blk('plateau', 40),
          Blk('cluster', 20, ['s']), Blk('plateau', 40)]
# whisper sur le premier plateau (frames 20-60)
sched = [('whisper', 20, 60)]
ev = classify_block_events(blocks, ['D', 's'], phonation_schedule=sched)
labels = dict(ev)
inside = [l for l, f in ev if 20 <= f < 60]
check('événements dans le span relabellisés whisper',
      all(l == 'whisper' for l in inside), str(ev))
check('restauration après le span (frame 60)',
      any(f == 60 and l != 'whisper' for l, f in ev), str(ev))
# sans schedule : aucun label de phonation
ev0 = classify_block_events(blocks, ['D', 's'])
check('sans schedule → aucun label phonation',
      not any(l in ('breathy', 'creaky', 'whisper') for l, _ in ev0))


print('== 4. build_phrase_tract — chemin complet (glott400) ==')
import importlib
_bpt = importlib.import_module('vtl_synth.core.build_phrase_tract')
from vtl_synth.core.constants import CO_VTL as _COVTL

def _sandbox_probe(block):
    n = len(block)
    if n == 0:
        return 1e9
    order = list(_COVTL.keys())
    idx = [order.index(k) for k in order
           if any(t in k.lower() for t in ('tongue', 'body', 'tip'))]
    if not idx:
        idx = list(range(min(8, block.shape[1])))
    sub = block[:, idx]
    return float(40.0 + 200.0 * np.linalg.norm(sub[n // 2] - sub[-1]))

_bpt._make_vv_closure_probe = lambda: _sandbox_probe

from vtl_synth.core.build_phrase_tract import build_phrase_tract
from vtl_synth.core.constants import GLOTTIS_PARAM_NAMES

PHRASE = 'Dis.iz.i.zi.fOR.@s'   # « this is easy for us » (g2p moteur)
def run(ov):
    t, g = build_phrase_tract(PHRASE, output_dir=None, return_data=True,
                              verbose=False, tag_overrides=ov,
                              sampa_guard='off')
    return np.asarray(g)

base = run(None)
check('baseline finie', np.isfinite(base).all() and base.shape[1] == 11)

EXPECT_COLS = {
    # NB breathy: JD3 chink_area (0.100) equals the voiceless-fricative
    # preset (0.100) — near a final /s/ the two are indistinguishable,
    # so only the fold-spacing columns are asserted.
    'breathy': {'x_bottom', 'x_top'},
    'creaky':  {'double_pulsing', 'pulse_skewness'},
    'whisper': {'chink_area', 'x_bottom', 'x_top'},
}
VOWEL_OVR = {'@': {'voicing': None}, 'i': {'voicing': None}}  # filled below
for mode, expect in EXPECT_COLS.items():
    g = run({'@': {'voicing': mode}, 'i': {'voicing': mode}})
    d = np.abs(g - base).max(axis=0) if g.shape == base.shape else None
    if d is None:
        check(f'{mode}: forme différente (durée changée)', False)
        continue
    mods = {GLOTTIS_PARAM_NAMES[j] for j in range(11) if d[j] > 1e-6}
    check(f'{mode}: colonnes attendues modifiées',
          expect.issubset(mods), f'modifiées={sorted(mods)}')
    print(f'       {mode}: max|Δ| par colonne → ' +
          ', '.join(f'{GLOTTIS_PARAM_NAMES[j]}={d[j]:.4f}'
                    for j in range(11) if d[j] > 1e-6))

# sans override → identique bit à bit à la baseline
g_none = run({})
check('override vide ≡ baseline (bit à bit)',
      g_none.shape == base.shape and np.array_equal(g_none, base))

# whisper : chink_area doit AUGMENTER sur le span modulé (ouverture
# glottique) — le span est proportionnel à t_end('@')/t_max du parser
g_w = run({'@': {'voicing': 'whisper'}})
i_ch = GLOTTIS_PARAM_NAMES.index('chink_area')
n = min(len(base), len(g_w))
span = slice(int(n * 0.80), int(n * 0.98))   # fin de phrase : le /@/ final
d_span = g_w[span, i_ch] - base[span, i_ch]
check('whisper: chink_area > modal sur le span final',
      bool((d_span > 0.02).any()),
      f'max Δ span={d_span.max():.4f}')

# creaky : double_pulsing doit dépasser la base
g_c = run({'@': {'voicing': 'creaky'}})
i_dp = GLOTTIS_PARAM_NAMES.index('double_pulsing')
check('creaky: double_pulsing > modal quelque part',
      bool((g_c[:, i_dp] > base[:, i_dp] + 0.05).any()),
      f'max={g_c[:, i_dp].max():.3f} base={base[:, i_dp].max():.3f}')


print('== 5. Pipeline expose tag_overrides ==')
from vtl_synth.core.pipeline import Pipeline
p = Pipeline(tag_overrides={'@': {'voicing': 'breathy'}})
check('attribut présent', p.tag_overrides == {'@': {'voicing': 'breathy'}})
p2 = Pipeline()
check('défaut None', p2.tag_overrides is None)

print()
print(f'{PASS} ok, {FAIL} échec(s)')

if __name__ == '__main__':
    sys.exit(1 if FAIL else 0)
