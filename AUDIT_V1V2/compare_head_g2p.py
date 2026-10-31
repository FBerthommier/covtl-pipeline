#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_head_g2p.py — le contournement g2p masque-t-il le défaut ?
===================================================================
Compare, pour chaque texte du corpus, la chaîne SAMPA produite par le
g2p du clone frais (contournement RETIRÉ) avec celle du g2p du HEAD
d'origine (contournement PRÉSENT : espace au lieu du point de liaison
après un mot terminé par une voyelle nasale — commit dea71c6).

La version « HEAD d'origine » est extraite de l'historique git du clone
(parent du commit de revert), donc sans dépendre d'un second checkout.

Sortie : results/sampa_frais_vs_head.txt + results/results_g2p.json
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from vtl_synth.utils.g2p_fr import text_to_sampa_fr as g2p_frais  # noqa: E402


def g2p_depuis_git(commit: str):
    """Charge vtl_synth/utils/g2p_fr.py tel qu'il était à `commit`."""
    src = subprocess.run(
        ['git', '-C', str(REPO), 'show', f'{commit}:vtl_synth/utils/g2p_fr.py'],
        capture_output=True, text=True, check=True).stdout
    tmp = Path(tempfile.mkdtemp(prefix='g2p_head_')) / 'g2p_fr_head.py'
    tmp.write_text(src, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('g2p_fr_head', tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    commit_head = sys.argv[1] if len(sys.argv) > 1 else 'HEAD^'
    g2p_head = g2p_depuis_git(commit_head)

    corpus = json.loads((HERE / 'corpus_v1v2.json').read_text(encoding='utf-8'))
    lignes = []
    table = []
    lignes.append(
        f"Comparaison du SAMPA g2p — clone frais (revert) vs {commit_head} "
        f"(contournement présent)")
    lignes.append('=' * 100)
    lignes.append(f"{'id':<5} {'texte':<20} {'SAMPA frais (moteur exposé)':<28} "
                  f"{'SAMPA HEAD (masqué)':<28} {'état'}")
    lignes.append('-' * 100)
    for it in corpus['items']:
        if not it.get('use_g2p'):
            continue
        rid, texte = it['id'], it['texte']
        s_frais = g2p_frais(texte, [])
        s_head = g2p_head.text_to_sampa_fr(texte, [])
        masque = s_frais != s_head
        etat = 'MASQUÉ par le patch (espace inséré)' if masque \
            else 'NON masqué — exposé aussi avec le patch'
        table.append({'id': rid, 'texte': texte, 'sampa_frais': s_frais,
                      'sampa_head': s_head, 'masque_par_patch': masque})
        lignes.append(f"{rid:<5} {texte:<20} {s_frais:<28} {s_head:<28} {etat}")
    n_masq = sum(1 for t in table if t['masque_par_patch'])
    lignes.append('-' * 100)
    lignes.append(f"Items masqués par le contournement g2p : {n_masq}/{len(table)}"
                  f" — les autres situations restent exposées au défaut moteur "
                  f"même AVEC le patch.")

    out = HERE / 'results'
    out.mkdir(exist_ok=True)
    (out / 'sampa_frais_vs_head.txt').write_text('\n'.join(lignes) + '\n',
                                                 encoding='utf-8')
    (out / 'results_g2p.json').write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n'.join(lignes))


if __name__ == '__main__':
    main()
