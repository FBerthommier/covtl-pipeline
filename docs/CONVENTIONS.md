# Naming Conventions — covtl-pipeline (vtl_synth)

Documented 2026-09-04 (P3 of RAPPORT_ANALYSE_CODE.md). These conventions
describe the *established* state of the code; they apply to new files and
to modifications.

## 1. Language

- **Code (identifiers)**: English, PEP 8.
- **Comments and docstrings**: English (American English) across the whole
  project as of 2026-09-04 (full translation; French was the previous
  default).
- The two envelope modules must no longer be confused:
  `amplitude_envelope.py` (token-based amplitude envelope, formerly
  `envelope.py`) and `enveloppe.py` (`TimedEnvelope`, anchors +
  FeatureTimer). Module names are kept as-is (they are identifiers).

## 2. Physical notation (documented deviation from PEP 8)

Parameters of the articulatory model functions use the notation of the
reference publications of the Berthommier COVTL model (see the
References section of the README). Within this scope, these
**mixedCase or single-letter identifiers are the rule** — do not "fix"
them into snake_case, as that would break traceability with the
reference:

| Symbol | Role | Usage examples |
|---|---|---|
| `K`, `K_v`, `K_c`, `Kvoy` | arc stiffness / coarticulation (V, C, schwa) | `arc_B`, `build_global_pval` |
| `Pexp` | arc power-law exponent | `arc_B` |
| `D` | duration in sample steps | `arc_B`, `_append_arc` |
| `T` | generic duration (steps); `T_cons`, `T_voy` in ms | `build_cluster_pval` |
| `E` | normalized amplitude envelope | timers, glottal_source |
| `A`, `B`, `nu` | arc parameters (start/end, asymmetry) | `polar.py` |
| `rho`, `theta` | articulatory polar coordinates (never `ρ`/`θ` in ASCII) | everywhere |
| `VO`, `VS`, `V` | velum opening / velum spreading / voicing — **do not confuse** (cf. BUG-008) | timers, assemble |

Outside this scope (parsing, I/O, analysis scripts), return to strict
snake_case.

## 3. Modules and files

- Module names: `snake_case` exclusively. Fixed on 2026-09-04:
  `Z_candidate_eval.py` → `z_candidate_eval.py`, `test_fa_sa_Sa.py` →
  `test_fa_sa_sa.py`, `_diag_Zn.py` → `_diag_zn.py`,
  `_verify_C_fix.py` → `_verify_c_fix.py`, `envelope.py` →
  `amplitude_envelope.py`.
- `_` prefix = private use or throwaway diagnostic script; the shared
  libraries of `scripts/` do not carry it (`vtl_lib.py`,
  `velar_contact_analysis.py`, `dental_closure_analysis.py`,
  `_fric_spectral.py` being historical).
- `attic/` = non-compilable or obsolete artifacts, excluded from
  `scripts/check_compile.py`.

## 4. Symbols

- Classes: `PascalCase` (52/52 compliant).
- Module-level "constants": `UPPER_CASE` in `constants.py`
  (single source: `COVTL_TO_FULL` mapping, `EFFORT_DEFAULTS` bounds,
  derived tables `IDX`/`COVTL_KEYS` in `scripts/vtl_lib.py`).
- Do not export `_private` names in `__all__` (residual debt:
  `_env_rise` & co in `pipeline/__init__.py`).
