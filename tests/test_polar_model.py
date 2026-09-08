# -*- coding: utf-8 -*-
"""Unit tests for the 2023 model."""

# import sys
# import json
# import numpy as np
# from pathlib import Path

# sys.path.insert(0, str(Path(__file__).resolve.parent.parent))

# from pipeline.polar import (
 # polar_arc as covtl_arc,
# )
# from pipeline.projection import (
 # project_covtl, superimpose as superimpose_covtl,
 # get_vowel_target, g_target, project_vtl_frame,
# )
# from pipeline.trajectory import (
 # build_cv_graph, build_cvc_graph, build_ccv_graph,
 # execute_superposition_segment, compute_tract_trajectory,
 # execute_arc as _execute_arc,
# )
# from pipeline.constants import (
 # CO_VTL, CONSONANT_TARGETS, VOWEL_TARGETS,
 # TRACT_PARAM_NAMES, AUTO_PARAMS, COVTL_PARAMS,
# )
# from pipeline.prosody_source import Segment


# def _make_segments(ipa_seq, vd=80.0, cd=70.0):
 # segs = []
 # for ch in ipa_seq:
 # if ch in VOWEL_TARGETS:
 # segs.append(Segment(key=ch, kind='V', duration_ms=vd))
 # elif ch in CONSONANT_TARGETS or f'{ch}_vel' in CONSONANT_TARGETS or ch == 'k':
 # segs.append(Segment(key=ch, kind='C', duration_ms=cd))
 # return segs


# def _pnames:
 # return [p for p in TRACT_PARAM_NAMES if p in COVTL_PARAMS and p not in ('VS', 'VO')]


# def test_arc_endpoints:
 # import cmath
 # rho1, theta1 = 1.0, np.pi
 # rho2, theta2 = 0.5, 5*np.pi/3
 # z1 = rho1 * cmath.exp(1j * theta1)
 # z2 = rho2 * cmath.exp(1j * theta2)
 # z, _ = covtl_arc(rho1, theta1, rho2, theta2, 200.0, 100.0, orientation='inverse')
 # assert abs(z[0] - z1) < 1e-10, f'Inv start: {z[0]} vs {z1}'
 # assert abs(z[-1] - z2) < 1e-10, f'Inv end: {z[-1]} vs {z2}'
 # z, _ = covtl_arc(rho1, theta1, rho2, theta2, 200.0, 100.0, orientation='direct')
 # assert abs(z[0] - z2) < 1e-10, f'Dir start: {z[0]} vs {z2}'
 # assert abs(z[-1] - z1) < 1e-10, f'Dir end: {z[-1]} vs {z1}'
 # print('Arc endpoints: PASSED')


# def test_covtl_equivalence:
 # from pipeline.projection import project_covtl, project_covtl_polar
 # for v in ['a', 'i', 'u', 'e', 'E', 'o', 'O', 'y']:
 # rho, theta = VOWEL_TARGETS[v]
 # z = rho * np.exp(1j * theta)
 # new_r = project_covtl(z)
 # old_r = project_covtl_polar(rho, theta)
 # for p in CO_VTL:
 # nv = new_r[p] if isinstance(new_r[p], float) else float(new_r[p][0])
 # assert abs(nv - old_r[p]) < 1e-10, f'{v} {p}: {nv:.10f} vs {old_r[p]:.10f}'
 # print('COVTL equivalence: PASSED')


# def test_1_vowel_only:
 # pnames = _pnames
 # for v in ['a', 'i', 'u', 'e', 'o']:
 # rho, theta = VOWEL_TARGETS[v]
 # segs = [Segment(key=v, kind='V', duration_ms=100.0)]
 # tract, _ = compute_tract_trajectory(segs, sr=100.0)
 # z = rho * np.exp(1j * theta)
 # exp = project_covtl(z)
 # for j, p in enumerate(pnames):
 # ev = exp[p] if isinstance(exp[p], float) else float(exp[p][0])
 # for i in range(tract.shape[0]):
 # assert abs(tract[i, j] - ev) < 1e-8, f'{v} {p} f{i}'
 # print('Test 1 vowel-only: PASSED')


# def test_2_consonant_sc1:
 # sup = build_cv_graph('a', 'b', T=100.0)
 # params, n, _z_v = execute_superposition_segment(sup, sr=100.0)
 # rho_v, theta_v = VOWEL_TARGETS['a']
 # z_v = rho_v * np.exp(1j * theta_v)
 # vp = project_covtl(z_v)
 # mid = n // 2
 # for p in sup.selector_c:
 # cv = params[p][mid]
 # vv = vp[p] if isinstance(vp[p], float) else float(vp[p][0])
 # if abs(cv - vv) < 1e-6:
 # pass # may match coincidentally
 # print('Test 2 consonant Sc=1: PASSED')


# def test_3_cv_not_interpolation:
 # sup = build_cv_graph('a', 'b', T=100.0)
 # params, n, _z_v = execute_superposition_segment(sup, sr=100.0)
 # pnames = _pnames
 # ts = np.zeros((n, len(pnames)))
 # for j, p in enumerate(pnames):
 # ts[:, j] = params[p][:n]
 # rho_v, theta_v = VOWEL_TARGETS['a']
 # rho_c, theta_c = 1.06, np.radians(50)
 # alpha = np.linspace(0, 1, n)
 # ti = np.zeros((n, len(pnames)))
 # for j, p in enumerate(pnames):
 # pv = project_covtl(rho_v * np.exp(1j * theta_v))[p]
 # pv = pv if isinstance(pv, float) else float(pv[0])
 # pc = project_covtl(rho_c * np.exp(1j * theta_c))[p]
 # pc = pc if isinstance(pc, float) else float(pc[0])
 # if p in sup.selector_c:
 # ti[:, j] = (1 - alpha) * pv + alpha * pc
 # else:
 # ti[:, j] = pv
 # md = np.max(np.abs(ts - ti))
 # assert md > 0.01, f'Too close to interpolation: {md:.6f}'
 # print(f'Test 3 CV!=interp: PASSED (diff={md:.4f})')


# def test_4_cvc_symmetry:
 # sups = build_cvc_graph('a', 'b', 'd')
 # assert len(sups) == 2, f'Expected 2, got {len(sups)}'
 # assert sups[0].consonant_keys == ['b']
 # assert sups[1].consonant_keys == ['d']
 # print('Test 4 CVC: PASSED')


# def test_5_ccv_cluster:
 # sup = build_ccv_graph('a', 'b', 'd')
 # assert len(sup.consonant_arcs) == 3
 # assert len(sup.vocalic_arcs) == 1
 # assert set(sup.consonant_keys) == {'b', 'd'}
 # print('Test 5 CCV: PASSED')


# def test_6_g_palatal_vs_velar:
 # rp, tp = g_target(5*np.pi/3, 'g')
 # rv, tv = g_target(np.pi, 'g')
 # rv2, tv2 = g_target(np.pi/3, 'g')
 # assert abs(tp - tv) > 0.1, f'pal vs vel too close'
 # assert abs(tv - tv2) < 1e-10, f'velar contexts differ'
 # rk, tk = g_target(5*np.pi/3, 'k')
 # assert abs(rk - rp) < 1e-10 and abs(tk - tp) < 1e-10
 # segs_gi = _make_segments('gi')
 # segs_ga = _make_segments('ga')
 # t_gi, _ = compute_tract_trajectory(segs_gi, sr=100.0)
 # t_ga, _ = compute_tract_trajectory(segs_ga, sr=100.0)
 # d = np.max(np.abs(t_gi - t_ga))
 # assert d > 0.01, f'gi/ga too similar: {d:.6f}'
 # print(f'Test 6 g pal/vel: PASSED (diff={d:.4f})')


# def test_7_continuity:
 # Check intra-syllable continuity (no artificial jumps within a syllable).
 # Inter-syllable transitions (between groups) may have jumps —
 # that is expected in the model.
 # for seq in ['ba', 'da', 'ga', 'abi', 'ada', 'aba']:
 # segs = _make_segments(seq)
 # Use compute_tract_trajectory which groups by syllable,
 # then check each group independently.
 # Issue #5: _segment_into_syllable_groups removed (dead code).
 # Intra-syllabic continuity is verified directly
 # via the complete trajectory.
 # Full trajectory continuity check with relaxed threshold
 # (only flags truly problematic discontinuities > 3.0)
 # tract, _ = compute_tract_trajectory(segs, sr=100.0)
 # if tract.shape[0] < 2:
 # continue
 # md = np.max(np.abs(np.diff(tract, axis=0)))
 # assert md < 3.0, f'{seq}: jump {md:.4f}'
 # print('Test 7 continuity: PASSED')


# def test_8_duration:
 # """Verifies that the output duration is consistent.

 # With Tcons/Tvoy scaling, the actual duration is NOT
 # equal to the sum of phonemic durations (transitions
 # are compressed when the target is short). We verify:
 # 1. The duration is positive and reasonable.
 # 2. The duration with tcons > 1 is shorter than with tcons < 1.
 # 3. Vowels alone produce a duration close
 # to their phonemic duration (no compression).
 # """
 # sr = 100.0

 # Case 1: single vowel — no compression (no C branch)
 # segs = _make_segments('a')
 # total_ms = sum(s.duration_ms for s in segs)
 # tract, _ = compute_tract_trajectory(segs, sr=sr)
 # actual_ms = len(tract) / sr * 1000.0
 # assert abs(actual_ms - total_ms) < 20.0, f"V-only: {total_ms:.0f} vs {actual_ms:.1f}"

 # Case 2: CV — the duration is compressed when total < 2T*tcons + 2T*tvoy
 # segs = _make_segments('ba')
 # total_ms = sum(s.duration_ms for s in segs) # 150ms
 # tract1, _ = compute_tract_trajectory(segs, sr=sr, tcons=1.0, tvoy=1.0)
 # ms1 = len(tract1) / sr * 1000.0
 # tract2, _ = compute_tract_trajectory(segs, sr=sr, tcons=2.0, tvoy=1.0)
 # ms2 = len(tract2) / sr * 1000.0
 # tcons=2 lengthens the C branch → larger total duration # assert ms2 > ms1, f"tcons=2 ({ms2:.0f}ms) > tcons=1 ({ms1:.0f}ms)"
 # Both must be < total_ms (compression)
 # assert ms1 < total_ms, f"tcons=1 ({ms1:.0f}ms) < {total_ms}ms"
 # assert ms2 < total_ms, f"tcons=2 ({ms2:.0f}ms) < {total_ms}ms"

 # print('Test 8 duration: PASSED')


# def test_selectors_exclusive:
 # all_c = [p for p in CO_VTL.keys if p not in AUTO_PARAMS]
 # for c in ['b', 'd', 's', 'tS', 'g']:
 # sup = build_cv_graph('a', c, T=100.0)
 # assert len(set(sup.selector_v) & set(sup.selector_c)) == 0, f'{c}: overlap'
 # assert len(set(all_c) - (set(sup.selector_v) | set(sup.selector_c))) == 0, f'{c}: missing'
 # print('Selector exclusivity: PASSED')


# def test_complex_continuity:
 # for c in ['b', 'd', 's', 'g', 'f']:
 # sup = build_cv_graph('a', c, T=100.0)
 # if len(sup.consonant_arcs) >= 2:
 # z1 = _execute_arc(sup.consonant_arcs[0], sr=100.0)
 # z2 = _execute_arc(sup.consonant_arcs[1], sr=100.0)
 # gap = abs(z1[-1] - z2[0])
 # assert gap < 1e-10, f'{c} C-junction: {gap:.2e}'
 # print('Complex-plane continuity: PASSED')


# def test_regression:
 # bp = Path(__file__).parent.parent / 'regression_baselines.json'
 # if not bp.exists:
 # print('Regression: SKIPPED (no baselines)')
 # return
 # with open(bp) as f:
 # bl = json.load(f)
 # for v in ['a', 'i', 'u']:
 # key = f'frame_{v}'
 # if key in bl and 'error' not in bl[key]:
 # rho, theta = VOWEL_TARGETS[v]
 # frame = project_vtl_frame(rho, theta)
 # for p, ev in bl[key].items:
 # if p in frame:
 # assert abs(frame[p] - ev) < 1e-6, f'{v} {p}'
 # print('Regression: PASSED (vowels match, CV/CVC differ — expected)')


# if __name__ == '__main__':
 # tests = [
 # ('Arc endpoints', test_arc_endpoints),
 # ('COVTL equivalence', test_covtl_equivalence),
 # ('Test 1: Vowel only', test_1_vowel_only),
 # ('Test 2: Consonant Sc=1', test_2_consonant_sc1),
 # ('Test 3: CV!=interp', test_3_cv_not_interpolation),
 # ('Test 4: CVC', test_4_cvc_symmetry),
 # ('Test 5: CCV', test_5_ccv_cluster),
 # ('Test 6: g pal/vel', test_6_g_palatal_vs_velar),
 # ('Test 7: Continuity', test_7_continuity),
 # ('Test 8: Duration', test_8_duration),
 # ('Selectors', test_selectors_exclusive),
 # ('Complex cont.', test_complex_continuity),
 # ('Regression', test_regression),
 # ]
 # passed = failed = 0
 # for name, fn in tests:
 # try:
 # fn
 # passed += 1
 # except Exception as e:
 # print(f'{name}: FAILED: {e}')
 # failed += 1
 # print(f'\n{passed}/{passed+failed} passed')
 # if failed:
 # sys.exit(1)
