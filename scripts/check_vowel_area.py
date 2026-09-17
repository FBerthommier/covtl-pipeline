# -*- coding: utf-8 -*-
"""Contrôle de la fonction d'aire des 12 fonds vocaliques d'un speaker
(min constriction linguale sections 26-35, bombement max, lèvres LD,
constriction palatale 20-28) — détection bunching / pointe haute.

Usage : python scripts/check_vowel_area.py [s1|s2|jd3]
"""
import importlib.util
import math
import os
import sys
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
SPK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', 'vtl_synth', 'data', 'speakers')
ORDRE_19 = ['HX', 'HY', 'JX', 'JA', 'LP', 'LD', 'VS', 'VO', 'TCX', 'TCY',
            'TTX', 'TTY', 'TBX', 'TBY', 'TRX', 'TRY', 'TS1', 'TS2', 'TS3']


def load_const(name):
    s = importlib.util.spec_from_file_location(
        name, os.path.join(SPK, name + '.py'))
    m = importlib.util.module_from_spec(s)
    sys.modules[name] = m
    s.loader.exec_module(m)
    return m


import vocaltractlab as vtl

name = sys.argv[1] if len(sys.argv) > 1 else 's1'
if name == 'jd3':
    mod = load_const('jd3_constants')
    spk = os.path.join(SPK, 'jd3.speaker')
else:
    mod = load_const(f'{name}_constants')
    spk = os.path.join(SPK, f'{name}.speaker')
vtl.load_speaker(spk)
print(f'=== {name} ===  (voy : min lingual 26-35 / max hump / min LD / pal 20-28)')
for v, (r, t) in sorted(mod.VOWEL_TARGETS.items()):
    vec = [0.0] * 19
    for p, (c1, c0, c2) in mod.CO_VTL.items():
        vec[ORDRE_19.index(p)] = c1 + r * c0 * math.cos(c2 - t)
    ts = vtl.tract_state_to_tube_state(np.array(vec))
    a = np.array(ts['tube_area'])
    print(f'  {v:2s} ling {a[26:36].min():5.2f}  hump {a.max():5.2f}  '
          f'LD {vec[ORDRE_19.index("LD")]:5.2f}  pal {a[20:29].min():5.2f}')
