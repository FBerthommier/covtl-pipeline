# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
prosody_f0.py
=============
Prosodie expressive : contour de F0 sculpté + accents de hauteur
(v1.0.8 — OPTION, défaut OFF).

Le mode monotone (:func:`vtl_synth.core.pipeline.apply_f0_declination`)
applique une déclinaison LINÉAIRE par phrase : une phrase longue est
une rampe plate, perçue comme monotone. Ce module la remplace, en mode
expressif uniquement, par un contour à trois composantes par groupe de
souffle (chunk, cf. :mod:`vtl_synth.utils.chunking`) :

  1. **déclinaison de base conservée** (onset → final du profil de
     langue) MAIS avec reprise d'attaque à chaque chunk (le profil
     d'attaque ne se produit plus qu'à la première phrase) ;
  2. **accents de hauteur locaux** : bosse asymétrique (montée douce
     ~70 ms, descente ~60–90 ms selon la langue, PAS de saut — le
     synthétiseur glottal suit f0 échantillon par échantillon) posée
     sur la syllabe accentuée du mot porteur, avec downstep cumulé
     optionnel après chaque accent (allemand, Ladd 2008) ;
  3. **chute nucléaire terminale** sur la dernière syllabe accentuée
     du dernier chunk (profondeur par langue).

Le stress lexical voyage HORS BANDE (jamais dans le flux SAMPA) :
Wikipron ˈ/ˌ via :func:`vtl_synth.utils.lexicon_loader.ipa_to_keys_stress`,
digits CMUdict (0/1/2) pour l'anglais, puis règles orthographiques de
repli par langue (accent écrit es/it/pt, pénultième par défaut,
première syllabe pour de, accent de GROUPE pour fr — Jun & Fougeron
2002 : pas d'accent lexical interne en français).

Simplification AVOUÉE à 2–3 paramètres par langue (amplitudes,
profondeur de chute, reprise), justifiés par les références citées
dans :mod:`vtl_synth.utils.setlang` (Face 2003 / Grice et al. 2005 /
Avesani 1995 / Frota 2000 / Pierrehumbert 1980…) : c'est une
caricature calculable des contours, pas une implémentation ToBI.

Le module ne touche QUE la colonne f0 du glottis et les durées de
pause (marqueur '%' de syltraj) — jamais le tract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from vtl_synth.utils.chunking import CHUNK_WORDS, chunk_sentence, split_sentences

# Facteur d'échantillonnage blocs @100 Hz → glottis @400 Hz.
_SR_STEP = 4


# ===========================================================================
# ExpressivityProfile
# ===========================================================================

@dataclass
class ExpressivityProfile:
    """Paramètres d'expressivité d'une langue (option, défaut off).

    pause_breath_ms : durée de la pause respiratoire '%' (130 ms,
        plus courte que la pause virgule 200 ms).
    max_chain_words : aucun bloc de souffle ne dépasse ce nombre de
        mots (respiration syntaxique).
    accent_amplitude : amplitude des bosses de hauteur, en FRACTION de
        f0_base (0.16 = +16 % ≈ +16 Hz à 102 Hz).
    accent_rise_ms / accent_fall_ms : demi-largeurs de la bosse
        (montée / descente) — la douceur est garantie par construction
        (gaussienne asymétrique, pas de saut).
    chunk_reset : part de la reprise d'attaque récupérée à chaque
        chunk (0 = pas de reprise, 1 = attaque complète comme en
        tête de phrase).
    downstep : facteur multiplicatif du niveau de base après chaque
        accent (1.0 = aucun ; de 0.985 — downstep allemand marqué,
        Ladd 2008).
    nuclear_fall_factor : multiplicateur terminal SUPPLÉMENTAIRE de la
        chute nucléaire (0.90 = la fin du dernier chunk descend 10 %
        sous le niveau final_gain — terminal bas allemand/portugais).
    """
    pause_breath_ms: float = 130.0
    max_chain_words: int = 5
    accent_amplitude: float = 0.14
    accent_rise_ms: float = 70.0
    accent_fall_ms: float = 90.0
    chunk_reset: float = 0.7
    downstep: float = 1.0
    nuclear_fall_factor: float = 0.95


#: Paramètres par langue — les amplitudes suivent les plages décrites
#: dans la littérature d'intonation (cf. docstring du module) :
#: de (Grice et al. 2005 : accents marqués + downstep + terminal bas
#: profond) > es (Face 2003 : pré-nucléaires larges) ≈ it (Avesani
#: 1995) > en (Pierrehumbert 1980) > pt (Frota 2000 : plage plus
#: étroite) > fr (Jun & Fougeron 2002 : accent final d'AP modéré).
#: Étalonnage perceptif : +18–24 Hz sur f0_base ≈ 102 Hz = 3–4
#: demi-tons, la plage usuelle des accents de hauteur lus.
EXPRESSIVITY_PROFILES: Dict[str, ExpressivityProfile] = {
    'en': ExpressivityProfile(
        accent_amplitude=0.20, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.7, downstep=0.99, nuclear_fall_factor=0.92),
    'fr': ExpressivityProfile(
        accent_amplitude=0.16, accent_rise_ms=70.0, accent_fall_ms=80.0,
        chunk_reset=0.6, downstep=1.0, nuclear_fall_factor=0.90),
    'es': ExpressivityProfile(
        accent_amplitude=0.22, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.8, downstep=1.0, nuclear_fall_factor=0.94),
    'de': ExpressivityProfile(
        accent_amplitude=0.24, accent_rise_ms=70.0, accent_fall_ms=60.0,
        chunk_reset=1.0, downstep=0.975, nuclear_fall_factor=0.88),
    'it': ExpressivityProfile(
        accent_amplitude=0.22, accent_rise_ms=70.0, accent_fall_ms=90.0,
        chunk_reset=0.8, downstep=1.0, nuclear_fall_factor=0.93),
    'pt': ExpressivityProfile(
        accent_amplitude=0.18, accent_rise_ms=70.0, accent_fall_ms=80.0,
        chunk_reset=0.7, downstep=1.0, nuclear_fall_factor=0.90),
}


# ===========================================================================
# Noyaux vocaliques d'un token SAMPA
# ===========================================================================

def token_nuclei(token: str) -> List[str]:
    """Clés vocaliques (une par syllabe) d'un token connecté SAMPA.

    ``'Di.si.zi'`` → ``['i', 'i', 'i']`` ; les clés nasales sont
    normalisées sans '~' (comme les plateaux de syltraj). Token non
    segmentable → [] (l'appelant retombe sur l'accent de groupe).
    """
    from vtl_synth.core.constants import VOWEL_TARGETS
    from vtl_synth.core.phonemes import greedy_sampa_split
    # '~' (nasalité) retiré avant découpe : les noyaux sont comparés
    # aux clés de plateaux de syltraj, elles-mêmes sans '~'
    residual = token.replace('.', '').replace(' ', '').replace('~', '')
    keys = greedy_sampa_split(residual)
    if not keys:
        return []
    return [k for k in keys if k in VOWEL_TARGETS]


# ===========================================================================
# Stress lexical hors-bande
# ===========================================================================

_ARPA_VOWELS = frozenset({
    'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'EY', 'ER', 'IH', 'IY',
    'OW', 'OY', 'UH', 'UW',
})

# Lettres vocaliques pour les règles orthographiques (es/it/pt) — les
# accents écrits marquent la syllabe irrégulière dans ces graphies.
_ACCENTED_LETTERS = {
    'es': 'áéíóú', 'it': 'àèéìòóù', 'pt': 'áàâãéêíóôõú',
}
_VOWEL_LETTERS = {
    'es': 'aeiouáéíóúü',
    'it': 'aeiouàèéìòóù',
    'pt': 'aeiouáàâãéêíóôõú',
}
_STRONG = frozenset('aeoàèòáéóâêôãõ')
# finales oxytoniques portugaises (spec §4 : -l -r -i -u -im -ns, et
# nasales finales -ão/-ães/-ões)
_PT_OXYTONE_RE = re.compile(
    r'(?:l|r|z|i|u|im|ins|ns|ns|ái|éu|ói)$|ãos?$|ães$|õe?s?$')
# finales espagnoles : consonne finale ≠ n/s → oxytonique
_ES_OXYTONE_RE = re.compile(r'(?:[^aeiouáéíóúns])$')


def _cmu_stress(word: str) -> Optional[int]:
    """Index de syllabe accentuée depuis les digits CMUdict (0/1/2).

    L'accent primaire '1' prime ; à défaut le secondaire '2'.
    Compte les symboles vocaliques ARPAbet avant le symbole porteur
    (chaque voyelle ARPAbet = exactement un noyau moteur).
    """
    try:
        import cmudict
    except Exception:                                      # pragma: no cover
        return None
    variants = cmudict.dict().get(word.lower())
    if not variants:
        return None
    primary = secondary = None
    n_vow = 0
    for sym in variants[0]:
        if sym.rstrip('012') in _ARPA_VOWELS:
            if sym.endswith('1') and primary is None:
                primary = n_vow
            elif sym.endswith('2') and secondary is None:
                secondary = n_vow
            n_vow += 1
    return primary if primary is not None else secondary


def _vowel_groups(word: str, lang: str) -> List[Tuple[int, int, int]]:
    """Groupes vocaliques orthographiques : (début, fin, pos_accent).

    pos_accent = index du caractère accentué DANS le groupe, ou -1.
    """
    vowels = _VOWEL_LETTERS[lang]
    accented = set(_ACCENTED_LETTERS[lang])
    groups: List[Tuple[int, int, int]] = []
    start = -1
    acc_pos = -1
    for i, ch in enumerate(word.lower()):
        if ch in vowels:
            if start < 0:
                start, acc_pos = i, -1
            if ch in accented and acc_pos < 0:
                acc_pos = i - start
        elif start >= 0:
            groups.append((start, i - 1, acc_pos))
            start = -1
    if start >= 0:
        groups.append((start, len(word) - 1, acc_pos))
    return groups


def _group_yield(group: Tuple[int, int, int], word: str, lang: str) -> int:
    """Nombre de noyaux SAMPA produits par un groupe vocalique.

    1 par défaut (diphtongue ai/ei/ia/ua… = noyau + glide) ; 2 pour
    un hiatus : voyelle faible accentuée (í a, ú e… — l'accent écrit
    brise la diphtongue) ou deux fortes adjacentes (le-er).
    """
    seg = word[group[0]:group[1] + 1].lower()
    if len(seg) >= 2:
        weak_accented = any(c in 'íìúù' for c in seg)
        if weak_accented:
            return 2
        strong_pairs = all(c in _STRONG for c in seg)
        if strong_pairs and len(set(seg)) >= 1 and seg[0] != seg[1]:
            return 2
        if len(seg) == 2 and seg[0] == seg[1]:
            return 2                      # voyelle double (leer, cooperar)
    return 1


def orthographic_stress_index(word: str, lang: str,
                              n_nuclei: int) -> Optional[int]:
    """Index de syllabe accentuée depuis l'orthographe (es/it/pt/de).

    Hiérarchie : accent écrit → cette syllabe ; sinon règle par
    langue (es : oxytonique si consonne finale ≠ n/s, sinon
    pénultième ; it : pénultième ; pt : oxytonique sur finales
    -l/-r/-i/-u/-im/-ns/-ão, sinon pénultième ; de : première
    syllabe — approximation documentée, préfixes non traités).
    L'index est calculé dans l'espace des noyaux SAMPA (n_nuclei),
    la divergence diphtonge/hiatus étant corrigée par comptage de
    queue.
    """
    if n_nuclei <= 0:
        return None
    if lang == 'de':
        return 0
    if lang not in ('es', 'it', 'pt'):
        return None
    groups = _vowel_groups(word, lang)
    if not groups:
        return None
    yields = [_group_yield(g, word, lang) for g in groups]

    acc = next((gi for gi, g in enumerate(groups) if g[2] >= 0), None)
    if acc is not None:
        tail = sum(yields[acc + 1:])
        base = n_nuclei - tail - yields[acc]   # 1er noyau du groupe
        seg = word.lower()[groups[acc][0]:groups[acc][1] + 1]
        # position du caractère accentué parmi les lettres vocaliques
        # du groupe (hiatus í-a : accent sur le 1er noyau ; a-í : 2e)
        vow = _VOWEL_LETTERS[lang]
        vow_idx = [j for j, c in enumerate(seg) if c in vow]
        pos_in_group = vow_idx.index(groups[acc][2]) if groups[acc][2] < len(vow_idx) else 0
        within = 1 if (yields[acc] == 2 and pos_in_group >= 1) else 0
        return max(0, min(base + within, n_nuclei - 1))

    wl = word.lower()
    if lang == 'es':
        last = bool(_ES_OXYTONE_RE.search(wl)) and not wl.endswith(('n', 's'))
        return n_nuclei - 1 if last else max(0, n_nuclei - 2)
    if lang == 'pt':
        last = bool(_PT_OXYTONE_RE.search(wl))
        return n_nuclei - 1 if last else max(0, n_nuclei - 2)
    # it
    return max(0, n_nuclei - 2)


def word_stress(word: str, lang: str, n_nuclei: int) -> Optional[int]:
    """Index de syllabe accentuée d'un mot (stress hors-bande).

    Ordre : CMUdict digits (en) → marque Wikipron ˈ/ˌ du lexique
    chargé → règle orthographique par langue → None (l'appelant
    retombe sur l'accent de groupe). Jamais ≥ n_nuclei.
    """
    if n_nuclei <= 0:
        return None
    wl = word.lower().replace('’', "'")
    idx: Optional[int] = None
    if lang == 'en':
        idx = _cmu_stress(wl)
        if idx is None:
            idx = 0 if n_nuclei == 1 else min(0, n_nuclei - 1)
    else:
        try:
            from vtl_synth.utils.lexicon_loader import LEXICONS, stress_for
            if lang in LEXICONS:
                s = stress_for(lang).get(wl)
                if s is not None and 0 <= s < n_nuclei:
                    return s
        except Exception:                                  # pragma: no cover
            pass
        idx = orthographic_stress_index(word, lang, n_nuclei)
    if idx is None:
        return None
    return max(0, min(int(idx), n_nuclei - 1))


# ===========================================================================
# Plan expressif : texte → SAMPA respiré + plans par chunk
# ===========================================================================

@dataclass
class WordPlan:
    """Un mot : token SAMPA connecté, noyaux, accent hors-bande."""
    word: str
    token: str
    nuclei: List[str] = field(default_factory=list)
    stress: Optional[int] = None


@dataclass
class ChunkPlan:
    """Un groupe de souffle : mots, SAMPA ('.'-joint), noyaux, accents.

    accents : liste (index_noyau, poids) — l'accent nucléaire est
    déterminé par position (dernier accent du dernier chunk).
    """
    words: List[WordPlan] = field(default_factory=list)
    sampa: str = ''
    nuclei: List[str] = field(default_factory=list)
    word_start: List[int] = field(default_factory=list)
    accents: List[Tuple[int, float]] = field(default_factory=list)


def _norm(word: str) -> str:
    return word.lower().replace('’', "'")


def _make_chunk_plan(wps: Sequence[WordPlan], lang: str) -> ChunkPlan:
    """Assemble le plan d'un chunk et choisit les accents de hauteur.

    Politique (simplification documentée) :

      * fr : pas d'accent lexical — accent de GROUPE sur la dernière
        syllabe du chunk (Jun & Fougeron 2002 : finale d'AP) ;
      * autres : accents sur la syllabe accentuée du PREMIER et du
        DERNIER mot lexical du chunk (déaccentuation des mots-outils
        et des mots intermédiaires — heuristique given/new) ;
      * aucun mot lexical (mots-outils seuls) : accent de groupe.
    """
    chunk = ChunkPlan(words=list(wps), sampa='.'.join(wp.token for wp in wps))
    off = 0
    for wp in wps:
        chunk.word_start.append(off)
        chunk.nuclei.extend(wp.nuclei)
        off += len(wp.nuclei)
    if not chunk.nuclei:
        return chunk
    if lang == 'fr':
        chunk.accents = [(len(chunk.nuclei) - 1, 1.0)]
        return chunk
    unacc = CHUNK_WORDS.get(lang, CHUNK_WORDS['en'])['unaccentable']
    lexical = [i for i, wp in enumerate(wps)
               if _norm(wp.word) not in unacc]
    picks = []
    if lexical:
        picks = [lexical[0]]
        if lexical[-1] != lexical[0]:
            picks.append(lexical[-1])
    accents: List[Tuple[int, float]] = []
    for wi in picks:
        wp = wps[wi]
        if not wp.nuclei:
            continue
        syl = wp.stress if wp.stress is not None else len(wp.nuclei) - 1
        syl = max(0, min(syl, len(wp.nuclei) - 1))
        idx = chunk.word_start[wi] + syl
        if all(idx != a[0] for a in accents):
            accents.append((idx, 1.0))
    if not accents:
        accents = [(len(chunk.nuclei) - 1, 1.0)]
    chunk.accents = sorted(accents)
    return chunk


def plan_expressive_text(text: str,
                         lang: str,
                         g2p_callable: Callable,
                         expr: ExpressivityProfile,
                         warnings: Optional[list] = None,
                         ) -> Tuple[str, Optional[List[List[ChunkPlan]]]]:
    """Texte → (SAMPA respiré, plans par phrase).

    Le SAMPA assemblé est IDENTIQUE à celui du g2p de la langue à
    ceci près que les groupes de souffle sont séparés par le marqueur
    ``' % '`` (pause respiratoire) : mots joints par ``.``, parties
    (virgules) par ``' '``, phrases par ``' | '`` — mêmes conventions
    que ``text_to_sampa``. Le g2p est appelé MOT PAR MOT (les g2p du
    paquet sont strictement mot-à-mots : lexique → exceptions →
    règles), ce qui donne le plan mots↔tokens vérifiable.

    Retourne (sampa, plans) ; plans[i] = chunks (aplanis) de la
    phrase i, ou None si AUCUNE phrase n'a pu être planifiée
    (l'appelant retombe sur la déclinaison monotone).
    """
    own = warnings is None
    if own:
        warnings = []
    phrase_sampas: List[str] = []
    plans: List[List[ChunkPlan]] = []
    for sentence in split_sentences(text):
        parts = chunk_sentence(sentence, lang,
                               max_chain=expr.max_chain_words)
        part_strs: List[str] = []
        phrase_chunks: List[ChunkPlan] = []
        for part in parts:
            chunk_strs: List[str] = []
            for words in part:
                wps: List[WordPlan] = []
                for w in words:
                    tok = g2p_callable(w, warnings=warnings).strip()
                    if not tok:
                        continue
                    nuclei = token_nuclei(tok)
                    stress = word_stress(w, lang, len(nuclei))
                    wps.append(WordPlan(w, tok, nuclei, stress))
                if not wps:
                    continue
                chunk_strs.append('.'.join(wp.token for wp in wps))
                phrase_chunks.append(_make_chunk_plan(wps, lang))
            if chunk_strs:
                part_strs.append(' % '.join(chunk_strs))
        if part_strs:
            phrase_sampas.append(' '.join(part_strs))
            plans.append(phrase_chunks)
    if not plans:
        return ' | '.join(phrase_sampas), None
    return ' | '.join(phrase_sampas), plans


# ===========================================================================
# Sculpture du contour F0
# ===========================================================================

def _segments_from_blocks(block_info) -> List[Tuple[int, int]]:
    """Segments de contenu (pas @100 Hz) séparés par les blocs pause.

    Les blocs 'pause' / 'initial' / 'terminal' sont des séparateurs ;
    le 'initial' de tête de phrase est sauté (silence initial).
    """
    segs: List[Tuple[int, int]] = []
    off = 0
    seg_start: Optional[int] = None
    for b in block_info:
        sep = b.kind in ('pause', 'initial', 'terminal')
        if seg_start is None:
            if not sep:
                seg_start = off
        elif sep:
            segs.append((seg_start, off))
            seg_start = None
        off += b.n_steps
    if seg_start is not None:
        segs.append((seg_start, off))
    return segs


def _plateaus_from_blocks(block_info, seg: Tuple[int, int]):
    """Plateaux vocaliques (pas @100 Hz, clé) d'un segment."""
    out: List[Tuple[int, int, str]] = []
    off = 0
    s, e = seg
    for b in block_info:
        if b.kind == 'plateau' and off + b.n_steps > s and off < e:
            lo = max(off, s)
            hi = min(off + b.n_steps, e)
            out.append((lo, hi, b.vowel_key or ''))
        off += b.n_steps
    return out


def apply_expressive_f0(glott400: np.ndarray,
                        f0_base: float,
                        onset_gain: float,
                        final_gain: float,
                        expr: ExpressivityProfile,
                        chunk_plans: Sequence[ChunkPlan],
                        block_info) -> bool:
    """Sculpte le F0 expressif d'une phrase (colonne 0 du glottis).

    Retourne True si le contour a pu être appliqué, False si
    l'alignement chunks↔segments échoue (l'appelant retombe sur la
    déclinaison monotone). Ne modifie AUCUNE autre colonne : le tract
    et l'amplitude restent ceux du moteur.
    """
    n = len(glott400)
    segs = _segments_from_blocks(block_info)
    if not segs or len(segs) != len(chunk_plans):
        return False

    # f0 écrit par chunk (pour ponte des trous inter-segments) :
    # les zones de pause gardent le f0 moteur, mais leurs bords
    # peuvent rester voisés (attaque/arc post-pause) — sans pont,
    # la jonction avec la reprise d'attaque du chunk suivant saute.
    written: List[Tuple[int, int]] = []
    K = len(segs)
    for k, (seg, plan) in enumerate(zip(segs, chunk_plans)):
        s400 = seg[0] * _SR_STEP
        e400 = min(seg[1] * _SR_STEP, n)
        L = e400 - s400
        if L <= 12:
            continue
        # --- déclinaison de base + reprise d'attaque ----------------
        start_gain = onset_gain if k == 0 else \
            1.0 + (onset_gain - 1.0) * expr.chunk_reset
        end_gain = onset_gain + (final_gain - onset_gain) * (k + 1) / K
        progress = np.linspace(0.0, 1.0, L)
        decl = start_gain + (end_gain - start_gain) * progress
        ramp_len = min(10, L // 5)
        if ramp_len > 0:
            decl[:ramp_len] = np.linspace(1.0, decl[ramp_len - 1], ramp_len)

        # --- alignement plateaux ↔ noyaux ----------------------------
        plateaus = _plateaus_from_blocks(block_info, seg)
        keys_engine = [p[2] for p in plateaus]
        aligned = keys_engine == list(plan.nuclei)
        if aligned:
            accents = plan.accents
        else:
            # repli : accent de groupe (dernière syllabe du chunk)
            accents = [(len(plateaus) - 1, 1.0)] if plateaus else []
        accents = [(i, w) for i, w in accents
                   if plateaus and 0 <= i < len(plateaus)]
        if not plateaus:
            # pas de noyau localisé : déclinaison seule
            glott400[s400:e400, 0] = f0_base * decl
            continue

        # --- bosses de hauteur + downstep ---------------------------
        bumps = np.zeros(L)
        down_count = np.zeros(L)
        accent_ends: List[int] = []
        t = np.arange(L)
        for nuc_idx, weight in accents:
            p0, p1, _ = plateaus[nuc_idx]
            # centre de la bosse : 35 % dans le plateau (pic H* sur la
            # syllabe accentuée), positions relatives au chunk @400 Hz
            c = int((p0 - seg[0] + 0.35 * (p1 - p0)) * _SR_STEP)
            c = max(0, min(L - 1, c))
            amp = expr.accent_amplitude * weight
            sigma = np.where(t < c,
                             expr.accent_rise_ms * 0.4,
                             expr.accent_fall_ms * 0.4)
            bumps += amp * np.exp(-0.5 * ((t - c) / sigma) ** 2)
            accent_ends.append(int(c + 3.0 * expr.accent_fall_ms * 0.4))
        for fe in accent_ends:
            down_count[fe:] += 1
        decl = decl * (expr.downstep ** down_count)

        # --- chute nucléaire (dernier chunk) -------------------------
        nuclear_mult = np.ones(L)
        if k == K - 1 and accents:
            p0, p1, _ = plateaus[accents[-1][0]]
            c_nuc = int((p0 - seg[0] + 0.35 * (p1 - p0)) * _SR_STEP)
            c_nuc = max(0, min(L - 1, c_nuc))
            if e400 > s400 + c_nuc:
                s_term = np.clip(
                    (np.arange(L) - c_nuc) / max(1, L - c_nuc), 0.0, 1.0)
                nuclear_mult = 1.0 - (1.0 - expr.nuclear_fall_factor) * s_term

        f0 = f0_base * decl * (1.0 + bumps) * nuclear_mult
        # lissage court (anti-coin numérique) sur le chunk
        if L > 3:
            kernel = np.ones(5) / 5.0
            f0 = np.convolve(f0, kernel, mode='same')
            # bordes : recoller les extrémités non lissées
            f0[:2] = f0[2]
            f0[-2:] = f0[-3]
        glott400[s400:e400, 0] = f0
        written.append((s400, e400))

    # --- ponts inter-chunks : rampe linéaire sur les zones de pause
    # (f0 ignoré quand rel_amp ≈ 0, continu quand l'attaque est
    # déjà voisée) — garantit l'absence de saut à la jonction.
    for (s0, e0), (s1, e1) in zip(written, written[1:]):
        gap = s1 - e0
        if gap > 0:
            f0a = float(glott400[e0 - 1, 0])
            f0b = float(glott400[s1, 0])
            glott400[e0:s1, 0] = np.linspace(f0a, f0b, gap + 2)[1:-1]
    return True


__all__ = [
    'ExpressivityProfile', 'EXPRESSIVITY_PROFILES',
    'token_nuclei', 'word_stress', 'orthographic_stress_index',
    'WordPlan', 'ChunkPlan', 'plan_expressive_text',
    'apply_expressive_f0',
]
