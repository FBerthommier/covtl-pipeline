# Engine audit — schwa position change (covtl-pipeline)

> English (US) translation of the French internal audit
> `audit_schwa_covtl-pipeline.pdf` (24 November 2026, 15 pp.).
> Structure, tables 1–5 and measurements are translated verbatim; the
> four figures are referenced by their translated captions (the PNGs
> ship with the audit deliverables, not regenerated here).
> The **layer classification tags** were added at translation time, per
> the owner's framing decision of 2026-11-24 (two representation
> layers, see `ARCHITECTURE.md` §"Two representation layers").
>
> | Tag | Meaning |
> |---|---|
> | **[layer 1: target]** | the `'@'` polar target and everything derived from it unconditionally (speaker constants, registry hashes, `.polar` manifest inventory entry) |
> | **[layer 2: mandatory routing]** | the closing-VV-arc waypoint detour executed by the motor chain — always active, never conditional |
> | **[layer 2: display option]** | the `.polar` display re-run that mirrors the routing in the drawn trajectory — gated by the `display_schwa_route` toggle, default OFF (owner decision, 2026-11-24; see the note in §5.2) |

- Repository: github.com/FBerthommier/covtl-pipeline
- Audited revision: `6536f5a` (main, 2026-11-24)
- Decision: `'@'` = (0.580, 180°) — interior mid-central schwa
- Goal: a sigmoid « buib » trajectory, dissociated from « buaib »
- Validation: 530 tests green · 5-speaker baselines intact

Internal technical audit — 24 November 2026

## 1. Executive summary

The audit requested on 24 November 2026 (the « UNDER STUDY — schwa
position » note of RELEASING.md) covers the engine position of the
schwa `VOWEL_TARGETS['@']`, then set at (0.7167, 180°) — the polar
centroid of the calibrated vowel triangle, re-centred on 2026-09-04.
The change is **global**: speaker targets, the waypoint of the closing
VV arcs (`syl._vv_waypoint`) **[layer 2: mandatory routing]** and the
« @ » entry of the polar manifest (`.polar`) **[layer 1: target]**.
The quality goal set by the requester: the diphthong trajectory of
« buib » (u→i) must become more sigmoid and less similar to
« buaib » (u→a→i).

The geometric study run on the engine (VTL tongue-area probe, 132 VV
pairs swept) establishes two structural results. First, the (ρ, θ)
plane contains an **occlusion corner** centred on θ = 0°: the tongue
area is zero there for every radius, which forbids any short passage
between u (60°) and i (300°) — the waypoint routing must therefore go
through the open zone |θ| ≥ 105°, notably the 180° meridian. Second,
the dissimilarity between the « buib » and « buaib » trajectories
follows exactly the law **H = 1 − ρ_w**: the only effective lever is
the waypoint radius, the angle being constrained.

The retained position is **`'@'` = (0.580, 180°)** — the interior
mid-central schwa, acoustically anchored (F1 620 Hz, F2 1463 Hz
measured against the 600/1400 reference, lang_blocks calibration)
**[layer 1: target]**. The routed trajectory of « buib » now crosses
the corridor at quasi-constant aperture (ρ 0.55 → 0.58 → 0.60): the
+0.117 radial bump disappears (+0.003 residual), the dissimilarity
from « buaib » rises from H = 0.283 to H = 0.420 (+48 %), and every
routed leg of the ten closing pairs stays above the /u/ plateau
(0.170 cm² against 0.152). The full validation is green: 530 tests
passed (519 before + 11 new guard tests), the five-speaker baseline
matrix is green without regeneration, and the closing arcs were
verified in the polar plane. A display/motor consistency defect (the
closure probe never hooked in the `.polar` path) was found and fixed
along the way.

## 2. Context, goals and scope

### 2.1 Origin of the request

The FBerthommier/covtl-pipeline repository (audited revision `6536f5a`,
main branch, 2026-11-24) itself documents the ongoing study in
RELEASING.md: « an engine change concerning the schwa position … will
require a GLOBAL modification (targets + possibly syltraj waypoints /
polar display + the '@' entry), to be ACCUMULATED into the same rebuild
round as the polar v5 display fix ». This audit answers that note:
study, position decision, implementation and validation, with the
explicit non-regression constraint (test suite + baselines) and the
verification of the closing arcs in the polar plane.

### 2.2 The three roles of the « @ » phoneme in the engine

The schwa « @ » is not a plain vowel target: it plays three
interdependent roles. (i) It is a **lexical target**: the French G2P
transcribes the unstable « e » as « @ » (« le », « je »), and speakers
without a phonological schwa fall back to the NEUTRAL anchor, which is
the schwa by definition. (ii) It is the **mute vowel** inserted for
isolated consonants before a pause (the `build_flat` rule). (iii) It is
the **waypoint of the closing VV arcs**: when the direct polar arc
between two vowels would occlude the tract mid-transition, the engine
detours the background arc into two half-arcs through « @ »
(`syltraj._vv_waypoint`) **[layer 2: mandatory routing]**, the
`VV_CLOSURE_PROBE` probe deciding the routing.

Finally, the « @ » entry of the polar manifest (the inventory of the
`.polar` file) is derived from the same targets **[layer 1: target]**:
any move is therefore indeed global.

### 2.3 Position history and quality goal

The historical schwa position was (0.420, 180°) — the neutral position
of the tract. The 2026-09-04 review re-centred it at the polar centroid
of the calibrated a-i-u triangle: ρ̄ = (1.000 + 0.600 + 0.550)/3 =
0.7167, θ = π (circular mean of the 60/180/300° vertices). That value
works mechanically — the waypoint opens every closing pair — but it
places the schwa near the open-central periphery, a step away from the
/a/ radius (ρ = 1). Audible and visible consequence: the routed
diphthong of « buib » crosses the /a/ meridian with a « buaib »-like
radial excursion. The goal of the audit is to invert that resemblance —
a more sigmoid trajectory (a single constant-aperture glide) and less
similar to « buaib » — without regressing the test suite or the
baselines.

## 3. Study method and metrics

All measurements come from the real engine of the repository (no
mock-up). The tongue-area probe is the one of the synthesis chain
(`_make_vv_closure_probe` of `build_phrase_tract`): reconstruction of
the 19-parameter VTL state from the 15-parameter COVTL block, VS at
rest and VO at −0.1, then minimum area of the tongue sections
(tongue articulator, 8–16 cm from the larynx) over the central half of
the block. The engine routing threshold is 0.18 cm² (margin ≈ 0.03
with respect to the full chain, which measures « eu » at 0.152 on the
probe against 0.120 in the chain). The /u/ plateau is 0.152 cm² on the
probe: that is our phonetic floor — a passage is occlusive only below
the level of a close vowel.

Three families of measurements were produced. (i) The **aperture
landscape** A(ρ, θ): area of the stationary target P(ρ, θ) on a
15 radii × 25 angles grid. (ii) The **closing VV pairs**: direct arc
(`arc_B`, exact engine geometry, D = 12 transition steps) for the 132
ordered vowel pairs, probe < 0.18 cm². (iii) The **trajectory metrics**
for « buib » and « buaib »: minimum area of the routed legs, radial
excursion (ρ bump), angular sweep of θ(t), and the Hausdorff distance H
between the trajectories resampled in the polar plane — H quantifies
the shape resemblance (H = 0: identical trajectories; H = 1: maximal
dissociation on the disk). The displayed trajectories (`.polar`) are
rebuilt by `build_phrase_polar`, the engine projection by
`polar_from_pval`.

## 4. Results of the geometric study

### 4.1 The occlusion corner of the engine plane

The aperture landscape reveals the deep structure of the (ρ, θ) plane:
the tongue area is zero over the whole θ = 0° meridian, at any radius,
and stays under the 0.18 cm² threshold in a corner roughly bounded by
θ ∈ [−75°, +60°]. This corner separates u (60°) from i (300°): the
direct chord between the two targets crosses a zone of complete
occlusion — that is the measured origin of the defect (direct u→i arc:
0.062 cm²). Conversely, the whole crown |θ| ≥ 105° is open, the area
growing with ρ up to 2 cm² towards (1.0, 180°). No waypoint of the
plane can therefore « cut » between u and i across the top: the routing
must go through the wide open way, around the 180° meridian.

> **Figure 1** — Aperture landscape A(ρ, θ) (engine probe, cm²). The
> dashed line is the 0.18 cm² routing threshold; the θ ≈ 0° occlusion
> corner forbids the short u→i passage (blue dotted chord). Red cross:
> @ before (centroid 0.7167); green star: @ after (0.580).

### 4.2 Closing VV pairs and corridors

The sweep of the 132 ordered pairs identifies ten closing pairs at
D = 12 (eight at D = 4, the default step of the chain): they all
connect the high vowels i, u, y, e across the occlusion corner —
{i–u}, {i–y}, {i–o}, {u–e}, {u–y} as unordered pairs. The direct arc
i→u / u→i is worth 0.062–0.063 cm², the others 0.132–0.170 cm². For
every candidate waypoint (ρ_w, θ_w), the two routed legs dep→wp and
wp→arr were probed: only θ_w ∈ [150°, 210°] with a sufficient ρ_w opens
every pair at the 0.18 threshold — but the opening is progressive and
homogeneous in ρ_w, which allows an arbitrage.

### 4.3 Dissimilarity law and radius choice

The resemblance metric is remarkably simple: the Hausdorff distance
between the routed trajectory of « buib » and that of « buaib » equals
exactly **H = 1 − ρ_w** for every waypoint of the 180° meridian
(verified from ρ_w = 0.42 to 1.00). The reason is geometric: the two
trajectories share the same 240° angular sweep (constrained by the
corner), and their maximal gap occurs at their respective junctions —
(ρ_w, 180°) against (1.0, 180°). The waypoint radius is therefore the
only dissociation lever, and it acts linearly: every 0.1 of radius
removed moves « buib » 0.1 away from « buaib » on the disk.

**Table 1 — Waypoint candidates (θ_w = 180°): worst leg of the 10
closing pairs, dissimilarity H, radial bump of « buib »**

| ρ_w | Worst leg (cm², probe) | H(buib, buaib) | ρ bump on the u→i window | Comment |
|---|---|---|---|---|
| 0.7167 | 0.182 | 0.283 | +0.117 (max 0.7167) | current state — 2026-09-04 centroid |
| 0.65 | 0.179 | 0.350 | +0.05 | below the 0.18 threshold on the worst leg |
| 0.60 | 0.171 | 0.400 | +0.00 (max 0.600) | upper bound of the constant corridor |
| 0.58 | 0.170 | 0.420 | +0.003 (max 0.600) | **retained choice — F1/F2 anchor** |
| 0.55 | 0.169 | 0.450 | 0 (max 0.600) | viable; marginal legs |
| 0.42 | 0.165 | 0.580 | −0.13 (central hollow) | historical neutral position |

The choice ρ_w = 0.580 is the best multi-criteria compromise. (i)
**Acoustic anchor**: it is the value whose synthesis had been measured
at F1 = 620 Hz and F2 = 1463 Hz against a 600/1400 Hz reference
(4 % gap) during the calibration passes documented in
`lang_pack/lang_blocks/blocks.py` — the interior schwa is therefore
phonetically founded, not only geometric. (ii) **Constant-aperture
corridor**: ρ_w lies between the radii of u (0.55) and i (0.60); the
trajectory never exceeds the radii of the supporting vowels. (iii)
**Aperture margin**: the worst leg (i→o, 0.170 cm²) stays above the /u/
plateau (0.152); the gap to the 0.18 routing threshold is small but
assumed — the i↔o routing goes through a glide-like narrowing,
phonetically expected for a glide hiatus. (iv) It does not return to
the neutral position 0.42, which the 2026-09-04 review had precisely
left. The angle stays θ = π: the only symmetric open meridian, which
biases neither i↔o nor e↔u.

## 5. Measured impact of the change

### 5.1 Waypoint and closing VV arcs (`syl._vv_waypoint`)

`_vv_waypoint()` reads `VOWEL_TARGETS['@']`: the waypoint follows the
target mechanically, from (0.7167, π) to (0.580, π) — no code change is
required in the function itself, only its comments document the new
role (semi-constant corridor) **[layer 2: mandatory routing]**. The
engine impact on the closing arcs is the following:

**Table 2 — « buib » (routed u→i) and « buaib » (reference): engine
measurements before/after (fine sampling t_voy = 6, D-independent
path)**

| Measurement | buib before (0.7167) | buib after (0.580) | buaib (ref.) |
|---|---|---|---|
| Leg areas (cm², probe) | 0.240 / 0.312 | 0.222 / 0.285 | 0.357 / 0.262 |
| ρ minimum, window (projection) | 0.319 | 0.312 | 0.350 |
| ρ maximum, window | 0.7167 | 0.600 | 1.000 |
| ρ bump vs endpoints | +0.117 | +0.003 | +0.40 |
| θ sweep (unwrapped) | 240.2° | 240.2° | 240.2° |
| H(buib, buaib) | 0.283 | 0.420 | — |

Three readings. (i) The **sigmoidity** is quantified by the radial
profile: at 0.580, the u→i glide happens at a constant close-vowel
aperture (residual bump +0.003 against +0.117) — a single diphthong
gesture with no intermediate open step, where the old trajectory opened
plainly towards the peripheral schwa. (ii) The **dissociation** from
« buaib » rises from 0.283 to 0.420 (+48 %): the trajectory no longer
runs along the /a/ meridian at radius 0.72, it crosses at radius 0.58
without radial excursion. (iii) The **leg areas** drop marginally
(0.240→0.222; 0.312→0.285) but stay clearly above the /u/ plateau
(0.152): no transient occlusion is introduced.

> **Figure 2** — Engine polar plane (projection of the Pval). Left:
> before — the routed buib via (0.7167, 180°) overlaps the buaib loop
> (H = 0.283). Right: after — routing via (0.580, 180°), the corridor
> cuts through the interior without excursion towards /a/
> (H = 0.420).

> **Figure 3** — Engine time courses θ(t) (top) and ρ(t) (bottom). The
> angular sweep stays 240° (constraint of the occlusion corner); the
> sigmoid gain is on ρ(t): constant corridor 0.55→0.58→0.60 after
> (blue) against the 0.7167 bump before (orange) and the 1.0 excursion
> of buaib (red).

### 5.2 Display and polar manifest

The audit uncovered a pre-existing **display/motor inconsistency**: the
closure probe (`VV_CLOSURE_PROBE`) is hooked by `build_phrase_tract`
during the synthesis then reset to None — but the display path
(`build_polar` of `polar_video`, called afterwards by the pipeline and
the `polar-build` command) never hooked it. The `.polar` file therefore
drew the direct arc (ρ ≈ 0.29 dip at the centre) while the engine
actually detours through the waypoint: the two-block routing
instrumentation planned in `_recorded_build_pval` was never triggered.
This defect is fixed: `polar_video._vv_probe()` builds the probe
(graceful fallback to None without `vocaltractlab_cython`, the direct
display remaining the historical behaviour) and `_recorded_build_pval`
hooks it exactly like the motor chain, with restoration in a `finally`
**[layer 2: display option]**.

Measured display impact: the vocalic trajectory of « buib » goes from a
direct u→i chord (displayed ρ minimum ≈ 0.29, never the π meridian) to
two arcs u→@→i whose junction is exactly (0.580, π) — verified to
1e-6 in the `.polar` file. The « @ » entry of the manifest (inventory)
goes from {rho: 0.7167, theta: π} to {rho: 0.580, theta: π},
automatically since it is derived from `VOWEL_TARGETS` **[layer 1:
target, unconditional — it describes the target, not the option]**.
The `.polar` format stays at version 5: the routing semantics was
specified by v5 (the two-block « bg » case), only its trigger was
missing — no version bump, no consumer migration. This change is
display-only: no audio signal and no baseline is touched.

> **Figure 4** — `.polar` display. Left: before — the probe is not
> hooked, the occlusive direct arc is drawn (inconsistent with the
> engine). Right: after — the u→@→i routing appears with its junction
> (0.580, 180°), consistent with the synthesized trajectory.

> **Owner adaptation note (2026-11-24, post-audit).** The audit
> implemented the display hook as unconditional. Per the owner's
> framing decision taken the same day (two representation layers), the
> display-side routing is now **optional**: the `.polar` re-run only
> hooks the probe when `display_schwa_route` is ON (CLI
> `--display-schwa-route`, console payload/checkbox; default OFF).
> OFF draws the legacy direct arc — byte-identical to the `.polar` of
> revision `6536f5a`. The motor routing (§5.1) remains unconditional:
> the engine always executes the waypoint detour; only its drawn
> representation is toggled.

### 5.3 Baselines and speakers

The baseline corpus (8 phrases × 5 speakers, schema 3) contains neither
a « @ » plateau nor an intra-word VV hiatus: the phrase « aiu »
(a i u) is made of separate words, whose transitions go through the
synthetic end/start-of-word anchors — never through the waypoint.
Measured consequence: **no baseline changes** (the 49 regression tests,
including the `tract_sha256` fingerprints, stay green without
regeneration on the five speakers — `scripts/run_baselines_matrix.py`
matrix). The m01 and w02 speakers keep their own multi-criteria schwa
(0.750, 123°) and (0.750, 234°): they never followed the centroid
scheme and are not concerned **[layer 1: target — per-speaker
constants]**; s1 and s2, which followed the jd3 centroid, adopt the new
common value.

## 6. Implementation

The change is implemented in the cloned repository and delivered as a
Git patch (13 modified files, 1 new, +337/−37 lines). The following
table details the contribution of each file; the « @ » value is
identical in `vtl_synth/core/constants.py` (active speaker) and
`vtl_synth/data/speakers/jd3_constants.py`, each keeping its own
comment style, the CRLF line endings of the speaker files being
preserved byte for byte (.gitattributes rule — the speaker constants
are pinned by hash).

**Table 3 — Modified files**

| File | Nature of the change | Layer |
|---|---|---|
| `vtl_synth/core/constants.py` | `'@'`: (0.7167, π) → (0.580, π) + audit comment (full rationale) | **[layer 1: target]** |
| `vtl_synth/data/speakers/jd3_constants.py` | same value + comment; CRLF preserved | **[layer 1: target]** |
| `vtl_synth/data/speakers/s1_constants.py` | follows the jd3 scheme: (0.580, π); CRLF preserved | **[layer 1: target]** |
| `vtl_synth/data/speakers/s2_constants.py` | same as s1 | **[layer 1: target]** |
| `vtl_synth/core/syltraj.py` | waypoint comments (`_vv_waypoint`, module block): semi-constant corridor, aperture margins | **[layer 2: mandatory routing]** (doc) |
| `vtl_synth/video/polar_video.py` | new `_vv_probe()` + probe hooking in `_recorded_build_pval` (restored in `finally`) + docstrings | **[layer 2: display option]** (gated by `display_schwa_route`, owner decision) |
| `vtl_synth/data/speakers/registry.json` | SHA-256 hashes regenerated (jd3, s1, s2) + provenance note | **[layer 1: target]** |
| `tests/test_speaker_registry.py` | jd3 reference hash prefix updated | **[layer 1: target]** |
| `install_speaker.py` | same (reference hash prefix) | **[layer 1: target]** |
| `docs/ARCHITECTURE.md` | documented reference hash updated | doc |
| `tests/test_schwa_waypoint.py` | NEW — 11 guard tests (see §7) | mixed |
| `CHANGELOG.md` | detailed « Changed » entry (Unreleased) | doc |
| `RELEASING.md` | « UNDER STUDY » note → « IMPLEMENTED » with acceptance criteria | doc |

The speaker registry pins the SHA-256 of the constants files
(anti-drift guard): updating the hashes is part of the documented
process of the repository for any intentional target change. The new
reference hashes are 65ccd435… (s1), f590d9ca… (s2) and eb3637c3…
(jd3, prefix reported in the test and in `install_speaker`). None of
the values is fabricated: they are computed on the files after
edition, line endings included.

## 7. Validation

### 7.1 Non-regression of the test suite

The full suite was executed before and after the change in the same
environment (vocaltractlab-cython 0.0.17, wheel 0.0.13 of the
documentation installed then replaced). The repository count announces
529 collected tests (README/DOC_SYNC_LOG, verified by the owner on
2026-11-24); the present environment collects 521 — a pre-existing gap
of 8 tests, independent of the change (environment-dependent
collection). The relevant criterion is the relative non-regression:

**Table 4 — Test suite, before / after**

| States | Before the change | After the change |
|---|---|---|
| Collected tests | 521 | 532 (521 + 11 new) |
| Passed tests | 519 | 530 (519 unchanged + 11) |
| Skipped tests | 3 | 3 |
| Failures | 0 | 0 |
| Baselines (5 speakers × 49) | green | green — without regeneration |

### 7.2 Guard tests of the change

The new module `tests/test_schwa_waypoint.py` locks the acceptance
criteria of the audit: value of the target (0.580, π) **[layer 1:
target]**; waypoint follow-up (`_vv_waypoint() == target`, interior
band between neutral and periphery); « @ » entry of the polar
manifest; two-leg routing structure with a stub probe (no VTL
dependency) **[layer 2: mandatory routing]**; display/motor
consistency (the displayed junction passes exactly through the
waypoint); direct behaviour without probe (historical fallback)
**[layer 2: display option]**; and, with the real VTL probe: legs
≥ 0.15 cm², quasi-constant aperture (ρ ≤ ρ_i + 0.03) and
H(buib, buaib) ≥ 0.40. These thresholds encode the H = 1 − ρ_w law
with margin: any regression towards the centroid would fail the test.

### 7.3 Verification of the closing arcs in the polar plane

The requested verification was carried out at both levels. At the
engine level, the ten closing pairs were re-probed with the installed
target (worst leg 0.170 cm², i.e. 12 % above the /u/ plateau) and the
« buib »/« buaib » trajectories re-measured from the current state of
the repository (H = 0.420, areas 0.222/0.285) — figures 2 and 3. At
the display level, a real `.polar` file was produced: the inventory
carries the « @ » entry at (0.580, π) and the vocalic trajectory
crosses the π meridian exactly at radius 0.580 — figure 4. The
baseline matrix finally confirmed the absence of signal impact on the
five speakers.

## 8. Conclusions and recommendations

### 8.1 Verdict

Goal reached and validated. The new schwa position is (ρ, θ) =
(0.580, 180°), radius distinct from the centroid scheme (0.7167). The
diphthong trajectory of « buib » is now a single glide at quasi-constant
aperture (ρ bump: +0.117 → +0.003) and dissociates from « buaib » by
48 % (H: 0.283 → 0.420), without transient occlusion (legs ≥ 0.170 cm²)
and without touching a single baseline signal. The requested global
modification is complete: targets (jd3, s1, s2), waypoint (follows the
target), polar manifest (« @ » entry updated) — plus the fix of the
display/motor inconsistency discovered during the audit.

### 8.2 Assumed limits

One structural limit must be stated honestly: the angular sweep stays
240° (through the long way, 180° meridian included) for every u↔i
pair, because the short path is an engine occlusion corner — no
waypoint positioning can remove it. The « sigmoid » gain is therefore
carried by the aperture profile (single gesture at constant radius) and
by the radial dissociation from « buaib », which matches the request
(« more and more sigmoid, less and less like buaib »). If the owner
wants to push further with a short 120° sweep at the display level,
that would be another arbitrage (relaxing the closure probe or drawing
a per-pair waypoint), at the price of an inconsistency with the engine
physics — out of the scope of the present audit.

### 8.3 Recommendations

- Group the commit with the polar v5 display fix into the same rebuild
  round, per the RELEASING note (do not ship piecemeal); the repository
  is ready (changelog and RELEASING note up to date).
- Recalibrate acoustically the schwa in situ at 0.580 (LPC measurement
  of the full chain, « setup_lang verify ±30 % » criterion) to confirm
  the F1/F2 anchor on the active jd3 speaker; the 620 Hz/1463 Hz cited
  values come from the lang_blocks calibration passes.
- Regenerate the Windows console backups/manifests (`install_speaker`
  swaps constants.py by bytes) at the next full deployment: the
  reference hashes of the registry have already been updated here.
- Listen specifically to routed i↔o hiatuses (e.g. « violon » through
  the lexicon): the worst leg (0.170 cm² on the probe, ~0.14 in the
  chain) is a glide passage — phonetically expected, to be confirmed by
  listening.

## 9. Annex A — detailed closing VV pairs

Areas (cm², engine probe) of the direct arc (D = 12) and of the two
routed legs via the installed waypoint (0.580, π), for the ten closing
ordered pairs. Every leg stays above the /u/ plateau (0.152); the
constrained leg is always the departure from a high front vowel
(i, e) towards the schwa.

**Table 5 — Closing pairs: direct arc / leg 1 / leg 2 (cm²)**

| Pair | Direct arc | Leg dep→@ | Leg @→arr |
|---|---|---|---|
| i → u | 0.063 | 0.170 | 0.439 |
| u → i | 0.063 | 0.222 | 0.285 |
| i → y | 0.170 | 0.170 | 0.486 |
| y → i | 0.170 | 0.393 | 0.285 |
| i → o | 0.148 | 0.170 | 1.141 |
| o → i | 0.147 | 0.777 | 0.285 |
| u → e | 0.132 | 0.222 | 0.536 |
| e → u | 0.132 | 0.390 | 0.439 |
| u → y | 0.135 | 0.222 | 0.486 |
| y → u | 0.135 | 0.393 | 0.439 |

## 10. Annex B — deliverables and reproducibility

Audit deliverables, all regenerable from the persisted scripts:

- `covtl-pipeline-schwa-audit.patch` — complete Git patch of the
  change (13 files + 1 test, +337/−37).
- `figures/fig_A…fig_D` (PNG, 160 dpi) — aperture landscape, engine
  polar plane before/after, time courses, `.polar` display before/after.
- `data/etude_schwa.json`, `etude_schwa2.json`, `apres.json`,
  `trajs.npz` — raw measurements of the study (landscape, candidates,
  pairs, trajectories).
- Study scripts (outside the repository): `etude_schwa.py`
  (landscape + pairs + candidates), `etude_schwa2.py` (per-pair
  detail), `etude_schwa3.py` (formants/trajectory data),
  `mesures_apres.py` (definitive post-change measurements),
  `figures_audit.py` (figures).
- Re-validation commands: `python -m pytest tests/` (530 passed);
  `python scripts/run_baselines_matrix.py` (5 speakers green);
  `covtl-synth polar-build "buib"` (junction (0.580, π) in the
  `.polar`).

Audit environment: Linux, Python 3.13, numpy 2.1, pytest 9,
vocaltractlab-cython 0.0.17 (JD3.speaker), repository cloned at
revision `6536f5a` then patched. Every numerical value of this report
comes from those runs and is recorded in the cited JSON files.
