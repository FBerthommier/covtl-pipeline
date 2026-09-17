# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
blocks.py — fragments LANG SECTION par langue (source unique)
=============================================================

Un fragment par langue (fr, en, es, de, it, pt) : le corps complet de
la section gérée de ``vtl_synth/core/constants.py`` (marqueur
ACTIVE_LANG + VOWEL_TARGETS (ρ, θ) calibrés + VOWEL_EFFORT_GAIN), avec
les commentaires de preuve (F1/F2 mesurés in situ, verdicts verify,
clés HYPOTHÈSE). Ce module est auto-contenu : il ne dépend d'aucun
import, les valeurs numpy (``np.pi``, ``np.radians``) restant du texte
évalué au moment où le bloc est exécuté dans l'espace de noms de
constants.py (ou d'un test).

Consommateurs :
  * ``setup_lang.py`` (racine du dépôt) le charge par importlib et
    rend la section langue lors de ``install``/``setlang`` ;
  * ``restore`` n'en a pas besoin (les .bak suffisent).

Les marqueurs de section ci-dessous DOIVENT rester identiques à ceux
de ``setup_lang.py`` (cohérence du remplacement regex).
"""

# --- Section markers (MUST match setup_lang.py) ---------------------------
LANG_SECTION_BEGIN = '# === LANG SECTION — BEGIN'
LANG_SECTION_END = '# === LANG SECTION — END'


# ===========================================================================
# Renderer + per-language blocks (extracted verbatim from setup_lang.py)
# ===========================================================================

def _lang_block(lang: str, header: str, vowels: str, effort: str) -> str:
    return f"""{LANG_SECTION_BEGIN} (managed by setup_lang.py — do not edit by hand)
{header}
ACTIVE_LANG: str = '{lang}'

VOWEL_TARGETS: Dict[str, Tuple[float, float]] = {{
{vowels}
}}

# Effort gain per vowel (relative intensity): compensates the intrinsic
# intensity gap of high vowels vs /a/ (clamped downstream to 1.5).
VOWEL_EFFORT_GAIN: Dict[str, float] = {{
{effort}
}}
{LANG_SECTION_END} =============================================================
"""


LANG_BLOCKS = {
    'fr': _lang_block(
        'fr',
        """# Français — cibles vocaliques calibrées par LPC (v1.0.6, 2026-09-13).
# Angles θ de timit-to-maeda (positions cardinales stables), ρ calibrés
# par mesure LPC des formants sur le moteur COVTL, JD3 (homme français).
# F2 cibles (homme français moyen) :
#   /i/ 2200 /e/ 2000 /E/ 1700 /a/ 1100 /O/ 870 /o/ 800 /u/ 870
#   /y/ 1800 /2/ 1500 /@/ 1500""",
        """    'i':  (0.340, 5 * np.pi / 3),         # 300° — F2=2200 (parfait)
    'e':  (0.850, 3 * np.pi / 2),         # 270° — F2=2015 (parfait)
    'E':  (1.000, 4 * np.pi / 3),         # 240° — F2=1598 (correct)
    'a':  (0.520, np.pi),                 # 180° — F2=1839 (un peu haut)
    'O':  (0.950, 2 * np.pi / 3),         # 120° — F2=1884 (haut mais acceptable)
    'o':  (0.300, np.pi / 2),             #  90° — F2=2085 (haut)
    'u':  (0.400, np.pi / 3),             #  60° — F2 mesuré ~870 (LPC instable sur /u/)
    'y':  (0.650, 5.5 * np.pi / 3),       # 330° — F2=1817 (parfait)
    '2':  (0.900, 5.5 * np.pi / 3),       # 330° — F2=1508 (parfait)
    # Voyelles nasales conservées de covtl-pipeline (pas dans timit-to-maeda)
    '6':  (0.894, 3.053),                 # 174.9° (œ) — nasal mid-front
    '9':  (0.722, 3.105),                 # 177.9° (œ̃) — nasal mid-front
    # '@' (schwa) : centre du triangle a-i-u.
    # ρ̄ = (0.520 + 0.340 + 0.400)/3 = 0.420, θ = π.
    '@':  (0.420, np.pi),                 # centre du triangle a-i-u (ə)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,   # /e/ came out -7.5 dB vs /a/ (phrase 2 of input.txt)
    'y': 1.3,   # high/mid front vowels: same order of correction
    '2': 1.2,""",
    ),
    'en': _lang_block(
        'en',
        """# English — strict Maeda anchors (original covtl-pipeline calibration).
# /a/, /i/, /u/ close to the Maeda anchors (ρ≤1); the other vowels are
# adjusted by least squares. English notation: no nasal vowels, /r/ is
# alveolar (resolved by the notation alias layer, not by the targets).""",
        """    'a': (1.000, np.pi),           # 180° — STRICT
    'i': (0.600, 5 * np.pi / 3),   # 300° — compensation for the raised c1(TCY)
    'u': (0.550, np.pi / 3),       #  60° — compensation for the raised c1(TCY)
    'e': (0.988, 4.581),           # 262.5°
    'E': (0.594, 3.563),           # 204.1°
    'o': (1.000, 1.827),           # 104.7° — clamped
    'O': (1.000, 2.616),           # 149.9° — clamped
    '6': (0.894, 3.053),           # 174.9° (œ)
    '9': (0.722, 3.105),           # 177.9° (œ̃)
    # '@' (schwa): centre of the a-i-u triangle, ρ̄ = 0.7167, θ = π.
    '@': (0.7167, np.pi),          # centre du triangle a-i-u (ə)
    'y': (0.519, 4.548),           # 260.6°
    '2': (0.396, 3.946),           # 226.1° (ø)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,
    'y': 1.3,
    '2': 1.2,""",
    ),
    # ------------------------------------------------------------------
    # Nouvelles langues (v1.0.7) : ρ dérivé mécaniquement (calibrate
    # --in-situ : find_best_rho sur la fonction de transfert VTL, puis
    # raffinement par synthèse réelle + mesure LPC — même critère que
    # ``verify``, JD3). Les F1/F2 des commentaires sont MESURÉS in situ
    # le 2026-09-14 ; le verdict est celui de ``setup_lang.py verify``
    # (±30 %). Les écarts résiduels sont le biais LPC documenté : F1
    # mesuré BAS sur les voyelles fermées (cf. bloc fr : /i/ mesuré 210
    # contre 280 attendu ; le /i/ espagnol plafonne à F2≈1350 sur ce
    # moteur sous la même chaîne de mesure).
    # ------------------------------------------------------------------
    'es': _lang_block(
        'es',
        """# Español (castillan) — cibles calibrées in situ (VTL/JD3, 2026-09-14).
# ρ : find_best_rho (fonction de transfert VTL) puis raffinement par
# synthèse réelle + LPC (critère aligné sur verify) ; F1/F2 ci-dessous
# = valeurs mesurées in situ. verify : 6/7 dans la tolérance ±30 %.
# Système à 5 voyelles /a e i o u/ ; E et O ne sont émis par AUCUNE
# règle du g2p (cibles de référence/calibrage uniquement).""",
        """    'i':  (0.700, np.radians(300.0)),  # F1=164 F2=1235 (réf 280/2300) — ÉCART 46 % : F2 plafonne à ~1300 sur ce moteur (cf. fr /i/ : 1744 mesuré) ; HYPOTHÈSE à réévaluer à l'écoute
    'e':  (0.270, np.radians(270.0)),  # F1=300 F2=1707 (réf 400/1900) — OK (25 %)
    'E':  (0.920, np.radians(240.0)),  # F1=448 F2=1873 (réf 520/1700) — OK (14 %)
    'a':  (1.100, np.pi),              # F1=735 F2=1160 (réf 700/1100) — OK (5 %)
    'O':  (0.760, np.radians(120.0)),  # F1=450 F2=1059 (réf 570/970)  — OK (21 %)
    'o':  (0.600, np.radians(90.0)),   # F1=323 F2=993  (réf 450/830)  — OK (28 %) ; F1 bas = biais LPC fermée
    'u':  (0.190, np.radians(60.0)),   # F1=254 F2=811  (réf 320/780)  — OK (21 %)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,""",
    ),
    'it': _lang_block(
        'it',
        """# Italiano — cibles calibrées in situ (VTL/JD3, 2026-09-14).
# ρ : find_best_rho puis raffinement synthèse+LPC (critère verify).
# verify : 4/7 dans la tolérance ±30 % (e E a O OK ; i o u en ÉCART
# par le biais LPC documenté : F1 mesuré bas sur les fermées — F2 de
# /o u/ dans la tolérance, /i/ F2 1873/2250 = −17 % OK, seul F1 dérive).
# Système à 7 voyelles ; le g2p n'émet que /a e i o u/ + E O accentués
# (è→E, ò→O).""",
        """    'i':  (0.440, np.radians(300.0)),  # F1=182 F2=1873 (réf 280/2250) — ÉCART F1 (35 %, biais fermée) ; F2 OK (−17 %)
    'e':  (0.270, np.radians(270.0)),  # F1=305 F2=1706 (réf 400/1950) — OK (24 %)
    'E':  (0.960, np.radians(240.0)),  # F1=444 F2=1870 (réf 550/1750) — OK (19 %)
    'a':  (1.080, np.pi),              # F1=731 F2=1190 (réf 700/1150) — OK (4 %)
    'O':  (0.900, np.radians(120.0)),  # F1=423 F2=983  (réf 580/950)  — OK (27 %)
    'o':  (0.300, np.radians(90.0)),   # F1=302 F2=645  (réf 450/850)  — ÉCART (F2 −24 %, F1 −33 %) ; HYPOTHÈSE : limite moteur+LPC sur fermée-postérieure italienne
    'u':  (0.340, np.radians(60.0)),   # F1=208 F2=892  (réf 310/800)  — ÉCART F1 (33 %, biais fermée) ; F2 OK (+12 %)""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,""",
    ),
    'de': _lang_block(
        'de',
        """# Deutsch — cibles calibrées in situ (VTL/JD3, 2026-09-14 ; corrections
# 2026-09-15 sur /I/ et /2/ après audit de la phrase de démo).
# ρ : find_best_rho puis raffinement synthèse+LPC (critère verify) sur
# deux passes ; F1/F2 mesurés in situ. verify du bloc installé :
# 10/14 — i I e E a O o u y @ OK ; les écarts restants (U Y 2 9) sont
# le biais LPC documenté (F1 bas sur fermées/arrondies, F2 OK).
# NOTE mesure : la LPC des arrondies avant (y Y 2 9) et du schwa est
# INSTABLE entre exécutions (F2 de /@/ mesuré 1484 (OK) puis 896 à
# cible identique) — les valeurs des clés marquées « passe 1 »
# proviennent de la passe où leur mesure était exploitable.
# /I U Y/ laxées : cibles propres calibrées (NE PAS copier les tendues :
# I 0.10 vs i 0.34, U 0.48 vs u 0.42).
# Corrections 2026-09-15 (audit « IC.zu » et « In.k2.nICs ») :
#  - /2/ : ρ 0.90→0.30 + effort 1.5 — l'occlusion vélaire-palatale de
#    /k/ (g_pal) laissait le plateau /2/ à −47 dB (voyelle éliminée) ;
#    ρ0.30 le restaure à −23,6 dB (mesure RMS par plateau, même phrase).
#  - /I/ : ρ 0.20→0.10 — F1 287 plus proche de la réf 350.
#  - Limitation moteur NON corrigeable dans ce bloc (backlog packaging) :
#    déficit d'intensité de ~6–8 dB des fermées en DÉBUT DE PHRASE
#    (/I/ initial −20 dB vs −13 dB après nasale, même cible) — attaque
#    E(t) + clamp gain 1.5 / R_max 1.2. À traiter côté moteur.""",
        """    'i':  (0.340, np.radians(300.0)),  # F1=224 F2=1745 (réf 280/2200) — OK (21 %)
    'I':  (0.100, np.radians(300.0)),  # F1=287 F2=1562 (réf 350/1900) — OK (18 %) ; ρ abaissé 0.20→0.10 (correction 2026-09-15) : +40 Hz de F1 vers la réf et meilleure tenue en contexte
    'e':  (0.400, np.radians(270.0)),  # F1=319 F2=1851 (réf 370/2100) — OK (14 %)
    'E':  (0.920, np.radians(240.0)),  # F1=450 F2=1889 (réf 520/1750) — OK (14 %)
    'a':  (1.100, np.pi),              # F1=717 F2=1135 (réf 690/1100) — OK (4 %)
    'O':  (0.880, np.radians(120.0)),  # F1=484 F2=986  (réf 560/890)  — OK (14 %)
    'o':  (0.660, np.radians(90.0)),   # F1=316 F2=942  (réf 430/770)  — OK (26 %)
    'U':  (0.480, np.radians(60.0)),   # passe 1 : F1=221 F2=949 (réf 410/950) — F2 parfait, F1 biais fermée
    'u':  (0.420, np.radians(60.0)),   # F1=244 F2=1039 (réf 300/870)  — OK (19 %)
    'y':  (0.200, np.radians(330.0)),  # passe 1 : F1=236 F2=1549 (réf 290/1750) — OK ; ρ au plancher de grille (0.2)
    'Y':  (0.200, np.radians(330.0)),  # passe 1 : F1=236 F2=1549 (réf 350/1600) — F2 parfait ; converge vers /yː/ sous la mesure — HYPOTHÈSE
    '2':  (0.300, np.radians(330.0)),  # correction 2026-09-15 (élimination en contexte /k2/) : ρ 0.90→0.30 — à ρ≥0.65 le plateau /2/ après occlusion vélaire-palatale sort à −47 dB (éliminé) ; ρ0.30 le restaure à −23,6 dB. F1=192 F2=1075 (réf 380/1500) : F2 −28 % (à la marge), F1 biais LPC arrondie — HYPOTHÈSE à l'écoute
    '9':  (0.620, np.radians(330.0)),  # passe 1 : F1=167 F2=1312 (réf 500/1400) — F2 OK (−6 %), F1 biais arrondie
    '@':  (0.440, np.pi),              # les deux passes dérivent 0.44 ; F2 mesuré 1484 (OK) puis 896 à cible identique — mesure bimodale, HYPOTHÈSE""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,
    'I': 1.5,
    'U': 1.5,
    'y': 1.3,
    'Y': 1.3,
    '2': 1.5,   # 1.2→1.5 (correction 2026-09-15) : compense l'ouverture ρ0.30 et l'effacement après /k/
""",
    ),
    'pt': _lang_block(
        'pt',
        """# Português (européen) — cibles calibrées in situ (VTL/JD3, 2026-09-14).
# ρ : find_best_rho puis raffinement synthèse+LPC (critère verify).
# verify : 5/8 dans la tolérance ±30 % (i E a @ O OK). '@' = /ɐ/
# européen, voyelle de PLEIN DROIT (calibrée à ρ propre, pas centre du
# triangle) : F1=620 F2=1463, le meilleur verdict de l'inventaire (4 %).
# Voyelles nasales (ã/õ/…, g2p pt) : convention '~' du moteur — bases
# orales ci-dessus, nasalité portée par l'extension VO (syltraj retire
# le '~' avant lookup).""",
        """    'i':  (0.170, np.radians(300.0)),  # F1=203 F2=1603 (réf 280/2200) — OK (28 %)
    'e':  (0.230, np.radians(270.0)),  # F1=247 F2=1693 (réf 400/2000) — ÉCART F1 (38 %, biais fermée) ; F2 OK (−15 %)
    'E':  (0.960, np.radians(240.0)),  # F1=437 F2=1868 (réf 550/1800) — OK (20 %)
    'a':  (1.100, np.pi),              # F1=756 F2=1181 (réf 700/1150) — OK (8 %)
    '@':  (0.580, np.pi),              # F1=620 F2=1463 (réf 600/1400) — OK (4 %) — /ɐ/
    'O':  (0.900, np.radians(120.0)),  # F1=480 F2=974  (réf 580/950)  — OK (17 %)
    'o':  (0.420, np.radians(90.0)),   # F1=247 F2=1126 (réf 430/830)  — ÉCART F2 (+36 %) ; HYPOTHÈSE : compromis F1/F2 du balayage, limite moteur sur postérieure mi-haute
    'u':  (0.150, np.radians(60.0)),   # F1=216 F2=744  (réf 310/800)  — ÉCART F1 à 1 Hz près (30,3 % vs 30 %) ; F2 OK (−7 %) — HYPOTHÈSE""",
        """    'i': 1.5,
    'u': 1.5,
    'e': 1.5,""",
    ),
}
