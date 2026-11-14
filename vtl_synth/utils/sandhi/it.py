# SPDX-FileCopyrightText: 2026 Liaison patch contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
liaison_it.py
=============
Module de liaison italienne — raddoppiamento sintattico + *d* eufonico,
trois modes en option (``off`` par défaut).

La « liaison » de l'italien n'est pas la consonne latente du français :
ce sont DEUX sandhi inter-mots, tous deux invisibles (ou presque) dans
l'orthographe, que le g2p strictement mot-à-mots ne peut pas produire :

* **raddoppiamento sintattico** (RS) : après un mot déclencheur, la
  consonne initiale du mot suivant se gémine — « città bella » →
  /tʃit.taˈbːɛl.la/ → ``tSi.tta.bbE.lla`` ; « a casa » →
  /ak.ˈkaː.sa/ → ``a.kka.sa`` ; « come va » → /ˈko.mev.ˈvaː/ →
  ``ko.me.vva``. Déclencheurs : (a) tout oxyton — l'orthographe
  italienne marque TOUJOURS l'accent final d'une voyelle finale
  accentuée (città, però, virtù, caffè, sarà, andò, è, più, può…) ;
  (b) une classe fermée de mots-outils sans accent écrit (a, da, e,
  o, ma, se, che, come, dove, qualche, fra, tra, su, fu, qui, qua,
  sta, sto, va, fa, do). Ne déclenchent PAS (norme) : per, con, in,
  di, non, articles et pronoms atones. La gémination s'annule devant
  initiale vocalique (però è : rien) et est reportée devant un glide
  (/j/, /w/ : norme variable). Pas de blocage devant nom propre : le
  RS est une conséquence phonétique, pas une règle grammaticale
  (« a Roma » → ``a.RRo.ma``) — différence documentée avec le patch
  français.
* **d eufonico** : la conjonction « e » et la préposition « a » (nues)
  prennent un /d/ devant mot à initiale vocalique — « e io » →
  /eˈdio/ → ``e.di.o`` ; « a esempio » → ``a.de.ze.mpjo``. Usage
  classique : « o » → « od » devant initiale o- (« od oggi »). Quand
  la graphie porte DÉJÀ le d (« ed anche »), le RS s'applique à ce d
  écrit : /ed.ˈdaŋ.ke/ → ``ed.da.nke`` — « e anche » (e nu + d inséré)
  et « ed anche » (ed écrit + d géminé) aboutissent au même sandhi
  [edː]. « è » n'est pas eufonique (« è ora » : jamais *èd ora*).

Contraintes du patch (respectées et testées sur clone) :

  * **aucune modification du moteur de synthèse** — le patch vit dans
    la couche utils (texte/g2p), comme les patchs prosody et liaison
    française ; le moteur reçoit un SAMPA ordinaire dont les géminées
    en attaque (``a.kka.sa``, ``bE.lla``) sont exactement la
    convention de son propre g2p italien (``cluster_onset``) ;
  * **compatible toutes les langues** — les tables ne s'appliquent
    qu'à des paires de mots italiens ; pour tout autre profil le
    patch est inactif (avertissement + no-op) ;
  * **compatible avec le patch prosody** (``--expressive``) et avec le
    patch de liaison française (profils disjoints fr/it dans le même
    registre) : la clé insérée n'est jamais un noyau, donc les indices
    de noyaux des plans F0 restent alignés ; jamais d'insertion à
    travers une pause (« % », « | », virgule) ;
  * **indépendant des commits g2p précédents** — aucun import depuis
    ``g2p_it`` : le g2p actif n'est appelé que par son interface
    publique ``(text, warnings) -> str`` (profil ``setlang``), mot par
    mot. Toutes les tables sont fraîches.

Les trois modes (option ``--liaison`` / ``Pipeline(liaison=...)``)
----------------------------------------------------------------------
1. ``pre``  — **avant le g2p** : réécriture du TEXTE orthographique.
   Le d eufonique devient sa graphie réelle (« e io » → « ed io »,
   « a esempio » → « ad esempio » — le g2p non modifié connaît déjà
   « ed/ad/od »). Le RS double l'initiale ÉCRITE du mot droit (« a
   casa » → « a ccasa », « che cosa » → « che ccosa », « che » →
   « cche » : le h garde le /k/), chaque doublée étant VÉRIFIÉE par
   aller-retour (le g2p sur le mot réécrit doit rendre exactement
   [géminée + prononciation du mot], aux tolérances près). Limites
   mesurées et acceptées : voyelles mi-fermées/ouvertes de la table
   de règles (``E``/``e``, ``O``/``o`` : « bella » → ``bbe.lla`` vs
   ``bbE.lla`` en g2p), s intervocalique toscan sonore (``casa`` →
   ``kka.za``), affriquées initiales non encodables (« a cena » :
   « ccena » se relirait /k.tS…/ → paire non liée), hiatus du lexique
   vs diphtongues des règles (« andò via », « come mai » → non liés),
   « q » initial hors table (« a quando » → non lié).
2. ``g2p`` — **dans la couche g2p** (RECOMMANDÉ) : passerelle
   italienne consciente du sandhi — le g2p de base est interrogé mot
   par mot (oracle), les paires sont fusionnées au niveau SAMPA avec
   la géminée en ATTAQUE : « città bella » → ``tSi.tta.bbE.lla``,
   « e io » → ``e.di.o``. L'oracle n'a AUCUNE correction de classe
   fermée à faire (le per-word italien est adossé au lexique
   Wikipron : « il » → ``il``, « che » → ``ke``, mesuré sur clone) —
   contrairement au français (« il » → ``i``), la passerelle italienne
   est une pure fusion. Sans paire, sortie bit-identique au g2p.
3. ``post`` — **après le g2p** : post-processeur SAMPA pur. Le g2p
   reste totalement intact ; le patch aligne les tokens mot par mot
   sur le SAMPA produit (y compris le SAMPA respiré « % » du plan
   expressif) et insère la géminée/le d aux frontières mot-mot.
   N'insère JAMAIS à travers une pause. Particularité italienne : le
   mode post ne souffre d'aucune ambiguïté faut/faux — le déclencheur
   (accent final écrit) est ORTHOGRAPHIQUE, il est donc lu sur le
   texte réaligné et non perdu dans la sortie phonétique ; les modes
   g2p et post produisent des sorties identiques (l'oracle étant
   l'identité), la différence est architecturale.

Invariants
----------
* ``liaison=off`` → sorties bit-identiques au pipeline sans patch ;
* un mode ne modifie jamais une phrase sans paire de sandhi ;
* gémination uniquement si le token gauche finit par une voyelle
  (jamais de triple consonne), insertion /d/ uniquement pour la
  classe fermée e/a/o/ed/ad/od, jamais à travers une pause.

Références phonologiques (tables fraîches) : L. Serianni, « Grammatica
italiana » (Mondadori, 1989) — déclencheurs du RS, d eufonique ;
M. Dardano & P. Trifone, « Grammatica italiana » (Zanichelli) — RS ;
L. Bertinetto & M. Loporcaro, « The sound pattern of Italian… »,
Journal of the IPA 35 (2005) — réalisation phonétique du RS. Usage
TTS : géminée = attaque de la syllabe suivante (miroir de la
convention ``cluster_onset`` du g2p : ``bE.lla``) ; affriquée géminée
= occlusive allongée (``a.ttSe.na``, miroir de ``zz`` → ``t t s``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

# --- covtl-sandhi levels (Branch B package; standalone copies of the
#     v3 patch import nothing and use the embedded fallback) --------
try:
    from .base import (LEVEL_CAREFUL, LEVEL_MINIMAL, LEVEL_STANDARD,
                       level_rank, load_wordlist)
except ImportError:                                    # pragma: no cover
    LEVEL_MINIMAL, LEVEL_STANDARD, LEVEL_CAREFUL = 1, 2, 3

    def level_rank(level: str) -> int:
        return {'off': 0, 'minimal': 1, 'standard': 2,
                'careful': 3}[str(level or 'off').lower()]

    def load_wordlist(filename, fallback):
        return fallback


def _rank(level) -> int:
    """Rank effectif : ``None`` = standard (comportement v3 exact,
    bit-identique au patch 5 langues)."""
    return LEVEL_STANDARD if level is None else level_rank(level)

__all__ = [
    'LIAISON_MODES',
    'LIAISON_LANGS',
    'apply_liaison_pre',
    'liaison_g2p',
    'apply_liaison_post',
    'liaison_oracle',
    'supports_liaison',
    'plan_pairs',
]

#: Modes acceptés par l'option.
LIAISON_MODES: Tuple[str, ...] = ('off', 'pre', 'g2p', 'post')

#: Langues supportées (le sandhi traité ici est celui de l'italien).
LIAISON_LANGS: FrozenSet[str] = frozenset({'it'})

G2PCallable = Callable[..., str]


# ===========================================================================
# 1. Tables phonologiques fraîches
# ===========================================================================

#: Voyelles du SAMPA moteur (union des jeux de langues, cf. phonemes +
#: language_vowel_sets) — test « initiale de token voyelle/glide ».
_TOK_VOWELS = frozenset('aeiouyEO269@2')

#: Voyelles orthographiques italiennes (test « W2 à initiale
#: vocalique » pour le d eufonico — l'orthographe, pas la phonétique :
#: « io » compte comme voyelle-initiale → « ed io »).
_ORT_VOWELS = frozenset('aeiouàèéìòóùíú')

#: Accent final écrit = oxyton (règle absolue de l'orthographe
#: italienne : voyelle finale accentuée TOUJOURS accentuée à l'écrit).
_FINAL_ACCENTED = frozenset('àèéìòóùíú')

#: Mots-outils déclencheurs du RS SANS accent écrit (classe fermée,
#: Serianni 1989 ; les oxytons et monosyllabes accentués — già, giù,
#: più, può, è, perché… — sont couverts par _FINAL_ACCENTED).
#: Hors liste (non déclencheurs en norme) : per, con, in, di, non,
#: un, il, lo, la, le, gli, mi, ti, si, ci, vi, del, al, nel…
#: Vue éditable : sandhi/data/it_rs_triggers.txt (un mot-outil
#: par ligne ; un mot AJOUTÉ là est de niveau standard ; le
#: repli est la table embarquée ci-dessous).
_RS_TRIGGERS: FrozenSet[str] = load_wordlist(
    'it_rs_triggers.txt', frozenset({
    # prépositions / conjonctions / mots-outils
    'a', 'da', 'e', 'o', 'ma', 'se', 'che', 'come', 'dove', 'qualche',
    'fra', 'tra', 'su', 'fu',
    # monosyllabes accentués sans accent écrit
    'qui', 'qua', 'sta', 'sto', 'va', 'fa', 'do',
}))

#: Sous-classe MINIMALE : déclencheurs MONOSYLLABIQUES du RS (le
#: d eufonico est minimal de fait — catégorique, exceptionless).
#: Le niveau STANDARD ajoute les polysyllabes de la liste (« come »,
#: « dove », « qualche ») et TOUS les oxytons écrits (« città »,
#: « però »…) : raddoppiamento productif. ``careful`` = standard —
#: aucune règle italienne n'est registre-dépendante (documenté
#: honnêtement, jamais silencieusement).
_RS_TRIGGERS_MINIMAL: FrozenSet[str] = frozenset({
    'a', 'da', 'e', 'o', 'ma', 'se', 'che', 'fra', 'tra', 'su', 'fu',
    'qui', 'qua', 'sta', 'sto', 'va', 'fa', 'do',
})

#: d eufonico — graphies réelles pour le mode ``pre`` : (repli,
#: token attendu mesuré). Le g2p de base connaît déjà ed/ad/od.
_EUPHONIC_RESPELL: Dict[str, Tuple[str, str]] = {
    'e': ('ed', 'ed'),
    'a': ('ad', 'ad'),
    'o': ('od', 'od'),          # usage classique, devant o- initial
}

#: Formes DÉJÀ écrites avec le d : pas d'insertion orthographique en
#: mode pre (le RS du d écrit n'a pas de graphie), mais le d est
#: géminé au niveau SAMPA par les modes g2p/post (« ed anche » →
#: ``ed.da.nke``).
_EUPHONIC_WRITTEN: FrozenSet[str] = frozenset({'ed', 'ad', 'od'})

#: Affriquées : la géminée allonge l'OCCLUSION (tS→t·tS, dZ→d·dZ),
#: miroir de la convention du g2p (« zz » → ``t t s``).
_GEM_AFFRICATE: Dict[str, str] = {'tS': 't', 'dZ': 'd'}

#: Glides : jamais géminés (norme variable → paire reportée).
_GEM_SKIP: FrozenSet[str] = frozenset('jw')


def _is_rs_trigger(low: str) -> bool:
    """Le mot (minuscule) déclenche-t-il le raddoppiamento ?"""
    if not low:
        return False
    return low in _RS_TRIGGERS or low[-1] in _FINAL_ACCENTED


def _orth_vowel_initial(low: str) -> bool:
    """W2 commence par une voyelle ORTHOGRAPHIQUE (d eufonico)."""
    return bool(low) and low[0] in _ORT_VOWELS


def _tok_ends_with_vowel(tok: str) -> bool:
    """Garde RS : le token gauche finit par une voyelle (jamais de
    géminée plaquée après une consonne finale)."""
    return bool(tok) and tok[-1] in _TOK_VOWELS


def _gem_key(tok2: str) -> Optional[str]:
    """Clé de gémination de l'initiale de tok2 (None = report).

    * affriquée ``tS``/``dZ`` → occlusive (``t``/``d``) ;
    * glide ``j``/``w`` ou voyelle → None ;
    * autre consonne → la consonne elle-même.
    """
    first = tok2.split('.')[0] if tok2 else ''
    if not first:
        return None
    two = first[:2]
    if two in _GEM_AFFRICATE:
        return _GEM_AFFRICATE[two]
    k = first[0]
    if k in _TOK_VOWELS or k in _GEM_SKIP:
        return None
    return k


# ===========================================================================
# 2. Découpage du texte (miroir frais des conventions de g2p_it :
#    phrase [.!?;:]+ → '|', virgule → ' ', mots [A-Za-zÀÈÉÌÒÙàèéìòóù]+
#    — SANS apostrophe, comme le tokenizer du g2p italien)
# ===========================================================================

_SENT_SPLIT = re.compile(r'[.!?;:]+\s*')
_COMMA_SPLIT = re.compile(r'\s*[,–—]\s*')
_WORD_SPLIT = re.compile(r"[A-Za-zÀÈÉÌÒÙàèéìòóù]+")
_GAP_SENT = re.compile(r'[.!?;:]')
_GAP_COMMA = re.compile(r'[,–—]')


def _norm(text: str) -> str:
    """NFC, apostrophes typographiques, strip (miroir minimal)."""
    text = unicodedata.normalize('NFC', text or '')
    return text.replace('’', "'").strip()


# ===========================================================================
# 3. Oracle : per-word du g2p actif (aucune correction nécessaire)
# ===========================================================================

def liaison_oracle(word: str, g2p: G2PCallable,
                   _cache: Optional[Dict[str, str]] = None) -> str:
    """Token SAMPA d'un mot : per-word du g2p actif (lexique →
    exceptions → règles).

    Contrairement au patch français (dont le g2p de base abîme la
    classe fermée : « il » → ``i``, « est » → ``e``), le per-word
    italien est adossé au lexique Wikipron et mesuré exact sur clone
    (« il » → ``il``, « che » → ``ke``, « come » → ``ko.me``…) :
    l'oracle est l'identité. La fonction existe pour la symétrie de
    l'architecture (et le jour où une correction s'imposerait)."""
    if _cache is not None:
        cached = _cache.get(word)
        if cached is not None:
            return cached
    low = word.lower()
    try:
        tok = (g2p(low, warnings=None) or '').strip()
    except Exception:
        tok = ''
    if _cache is not None:
        _cache[low] = tok
    return tok


def supports_liaison(lang: str) -> bool:
    """Le module de sandhi est-il actif pour cette langue ?"""
    return (lang or '').lower() in LIAISON_LANGS


# ===========================================================================
# 4. Décision commune aux trois modes
# ===========================================================================

class _Pair:
    __slots__ = ('i', 'w1', 'w2', 'kind', 'insert', 'tok1', 'tok2')

    def __init__(self, i: int, w1: str, w2: str, kind: str,
                 insert: str, tok1: str, tok2: str):
        self.i = i
        self.w1, self.w2 = w1, w2
        self.kind = kind          # 'rs' (raddoppiamento) | 'd' (eufonico)
        self.insert = insert      # clé insérée à la frontière
        self.tok1, self.tok2 = tok1, tok2


def _decide(w1: str, w2: str, tok1: str,
            tok2: str) -> Optional[Tuple[str, str]]:
    """(kind, insert) si la paire (W1, W2) porte un sandhi, sinon None.

    * W2 à initiale vocalique (orthographe) → *d* eufonico : insert
      ``'d'`` pour e/a nus (insertion du d) et pour ed/ad/od écrits
      (gémination du d écrit) ; « o » nu seulement devant o- initial ;
      tout autre W1 → None (« è » n'est pas eufonique).
    * W2 à initiale consonantique → raddoppiamento sintattico si W1
      est déclencheur (oxyton écrit ou mot-outil) : insert = clé de
      gémination de l'initiale de W2 (None si glide/voyelle → report).
    """
    if not tok1 or not tok2:
        return None
    low1, low2 = w1.lower(), w2.lower()
    if _orth_vowel_initial(low2):
        if low1 in _EUPHONIC_WRITTEN or low1 in ('e', 'a'):
            return ('d', 'd')
        if low1 == 'o' and low2[:1] in ('o', 'ò', 'ó'):
            return ('d', 'd')
        return None
    if not _is_rs_trigger(low1):
        return None
    if not _tok_ends_with_vowel(tok1):
        return None               # garde : jamais de géminée après C
    gem = _gem_key(tok2)
    if not gem:
        return None               # glide/voyelle : norme variable
    return ('rs', gem)


def _pair_level(w1: str, decision: Tuple[str, str]) -> int:
    """Niveau minimal d'application de la règle qui a tiré."""
    if decision[0] == 'd':
        return LEVEL_MINIMAL               # d eufonico : catégorique
    if w1.lower() in _RS_TRIGGERS_MINIMAL:
        return LEVEL_MINIMAL
    return LEVEL_STANDARD                  # polysyllabe / oxyton


def _decide_level(w1: str, w2: str, tok1: str, tok2: str,
                  level: str = None) -> Optional[Tuple[str, str]]:
    """Décision v3 FILTRÉE par le niveau de couverture covtl-sandhi."""
    rank = _rank(level)
    decision = _decide(w1, w2, tok1, tok2)
    if decision and _pair_level(w1, decision) <= rank:
        return decision
    return None


def plan_pairs(text: str, g2p: G2PCallable, level: str = None
               ) -> List[Tuple[List[str], List[Optional[_Pair]]]]:
    """Plan des paires, PHRASE par PHRASE (miroir du ' | ' du SAMPA).

    Retourne une liste de phrases ; chaque phrase est une liste de
    parties (virgules) ; chaque partie est (mots, paires_par_index) —
    ``paires[k]`` décrit la paire (mot k, mot k+1) si sandhi, None
    sinon. Les paires peuvent se CHAÎNER (« così come va » : ainsi→
    come ET come→va). Les mots à token vide restent dans la liste
    (ils s'alignent avec le SAMPA qui les saute) mais ne forment
    jamais de paire ; le dernier slot de chaque partie est None
    (une virgule ne liaise jamais).

    ``level`` (covtl-sandhi) : filtre de COUVERTURE monotone —
    ``None``/``'standard'`` = comportement v3 exact,
    ``'minimal'`` = d eufonico + déclencheurs monosyllabiques,
    ``'careful'`` = standard (aucune règle registre-dépendante
    en italien).
    """
    text = _norm(text)
    cache: Dict[str, str] = {}
    sentences: List[Tuple[List[str], List[Optional[_Pair]]]] = []
    for sentence in _SENT_SPLIT.split(text):
        sentence = (sentence or '').strip()
        if not sentence:
            continue
        parts: List[Tuple[List[str], List[Optional[_Pair]]]] = []
        for part in _COMMA_SPLIT.split(sentence):
            part = (part or '').strip()
            if not part:
                continue
            words = _WORD_SPLIT.findall(part)
            if not words:
                continue
            toks = [liaison_oracle(w, g2p, cache) for w in words]
            pairs: List[Optional[_Pair]] = [None] * len(words)
            for k in range(len(words) - 1):
                decision = _decide_level(words[k], words[k + 1],
                                         toks[k], toks[k + 1], level)
                if decision:
                    pairs[k] = _Pair(k, words[k], words[k + 1],
                                     decision[0], decision[1],
                                     toks[k], toks[k + 1])
            parts.append((words, pairs))
        if parts:
            sentences.append(parts)
    return sentences


def _merge_pair_tokens(tok1: str, insert: str, tok2: str) -> str:
    """Fusion SAMPA d'une paire : géminée/d en ATTAQUE de W2.

    'tSi.tta' + 'b' + 'bE.lla' → 'tSi.tta.bbE.lla' : la géminée tombe
    en attaque de la syllabe suivante (convention cluster_onset du
    g2p italien — 'bE.lla' — respectée par simple concaténation)."""
    return f'{tok1}.{insert}{tok2}'


# ===========================================================================
# 5. Mode PRE — réécriture orthographique (avant le g2p)
# ===========================================================================

def _pre_double_spelling(w2: str) -> Optional[str]:
    """W2 → orthographe à initiale doublée lisible par la table de
    règles : « casa » → « ccasa », « che » → « cche » (le h garde le
    /k/), « scuola » → « sscuola ». None si l'encodage est sans
    espoir : « q » initial (le q isolé est absent de la table de
    règles → repli impossible, « a quando » non lié en mode pre)."""
    if not w2:
        return None
    low = w2.lower()
    if low[0] == 'q':
        return None
    if low[:2] in ('ch', 'gh'):
        return w2[0] + w2[:2] + w2[2:]     # che → cche, ghe → gghe
    return w2[0] + w2                       # casa → ccasa


#: Décalages documentés règles-vs-lexique tolérés pour l'aller-retour
#: du mode pre (le pseudo-mot passe par les RÈGLES, le mot droit par
#: le LEXIQUE) : mi-ouvertes E/O rendues mi-fermées e/o par la table
#: (« bella » : lexique ``bE`` / règles ``be``), s intervocalique
#: toscan sonore dans les règles là où le lexique a retenu la
#: variante sourde (« casa » : lexique ``sa`` / règles ``za``).
_PRE_TOLERANCE = frozenset({('E', 'e'), ('O', 'o'), ('s', 'z')})

_TOKEN_PAIRS = ('tS', 'dZ')


def _token_keys(tok: str) -> List[str]:
    """Token connecté → liste de clés (affriquées 'tS'/'dZ' gardées)."""
    keys: List[str] = []
    for group in tok.split('.'):
        i = 0
        while i < len(group):
            two = group[i:i + 2]
            if two in _TOKEN_PAIRS:
                keys.append(two)
                i += 2
                continue
            keys.append(group[i])
            i += 1
    return keys


def _keys_match(got: List[str], want: List[str]) -> bool:
    if len(got) != len(want):
        return False
    return all(g == w or (w, g) in _PRE_TOLERANCE
               for g, w in zip(got, want))


def _pre_rs_entry(w2: str, gem: str, tok2: str,
                  g2p: G2PCallable) -> Optional[str]:
    """Entrée RS du mode pre : orthographe doublée VÉRIFIÉE par
    aller-retour (les clés du g2p sur le mot réécrit doivent être
    exactement [géminée] + clés du mot droit, aux tolérances près).
    None → la paire reste sans sandhi en mode pre (jamais de forme
    fausse)."""
    respell = _pre_double_spelling(w2)
    if respell is None:
        return None
    got = (g2p(respell, warnings=None) or '').strip()
    if not got:
        return None
    if _keys_match(_token_keys(got), [gem] + _token_keys(tok2)):
        return respell
    return None


def apply_liaison_pre(text: str, g2p: G2PCallable,
                      warnings: Optional[list] = None,
                      level: str = None) -> str:
    """Mode ``pre`` : réécrit le TEXTE pour que le g2p non modifié
    produise le sandhi.

    * d eufonico : W1 (« e », « a », « o ») remplacé par sa graphie
      réelle « ed/ad/od », contrôlée au runtime contre le token
      attendu (mesuré). W2 reste un mot séparé.
    * raddoppiamento : W2 remplacé par son orthographe à initiale
      doublée (« casa » → « ccasa »), contrôlée par aller-retour.
      L'édition porte sur le span de W2 (la géminée est phonétique-
      ment l'attaque de W2) : les paires chaînées restent possibles
      (« così come va » → « così ccome vva »).

    Retourne le texte réécrit (identique si aucune paire ne trouve
    son encodage)."""
    own = warnings is None
    if own:
        warnings = []
    text = _norm(text)
    if not text:
        return text
    cache: Dict[str, str] = {}

    spans = [(m.start(), m.end(), m.group(0))
             for m in _WORD_SPLIT.finditer(text)]
    edits: List[Tuple[int, int, str]] = []
    for k in range(len(spans) - 1):
        s1, e1, w1 = spans[k]
        s2, e2, w2 = spans[k + 1]
        gap = text[e1:s2]
        if _GAP_SENT.search(gap) or _GAP_COMMA.search(gap):
            continue                      # pause de phrase / virgule
        tok1 = liaison_oracle(w1, g2p, cache)
        tok2 = liaison_oracle(w2, g2p, cache)
        decision = _decide_level(w1, w2, tok1, tok2, level)
        if not decision:
            continue
        kind, ins = decision
        if kind == 'd':
            entry = _EUPHONIC_RESPELL.get(w1.lower())
            if not entry:
                continue
            respell, expected = entry
            got = (g2p(respell, warnings=None) or '').strip()
            if got != expected:
                warnings.append(
                    f"liaison-it pre: repli {respell!r} pour {w1!r} "
                    f"dérivé ({got!r} != {expected!r}) — ignoré")
                continue
            edits.append((s1, e1, respell))          # W1 réécrit seul
        else:
            respell = _pre_rs_entry(w2, ins, tok2, g2p)
            if not respell:
                warnings.append(
                    f"liaison-it pre: pas d'orthographe doublée pour "
                    f"{w2!r} après {w1!r} ({ins!r}) — paire non liée "
                    f"en mode pre (utiliser le mode g2p ou post)")
                continue
            edits.append((s2, e2, respell))          # W2 réécrit seul

    if not edits:
        return text
    out = text
    for s, e, rep in sorted(edits, reverse=True):
        out = out[:s] + rep + out[e:]
    return out


# ===========================================================================
# 6. Modes G2P / POST — fusion au niveau SAMPA
# ===========================================================================

def _find_slot(content: str, tok: str, from_pos: int) -> int:
    """Cherche ``tok`` dans ``content`` comme slot délimité par des
    séparateurs de mots ('.' ou ' ') à partir de ``from_pos`` ;
    -1 si absent. Les points internes du token (frontières de
    syllabe, ex. 'ka.sa') font partie du token et ne créent pas de
    faux slots."""
    if not tok:
        return -1
    start = from_pos
    while True:
        idx = content.find(tok, start)
        if idx < 0:
            return -1
        before = content[idx - 1] if idx > 0 else '.'
        end = idx + len(tok)
        after = content[end] if end < len(content) else '.'
        if before in ('.', ' ') and after in ('.', ' '):
            return idx
        start = idx + 1


def apply_liaison_post(text: str, sampa: str, g2p: G2PCallable,
                       warnings: Optional[list] = None,
                       token_view: str = 'base',
                       replace_tokens: bool = False,
                       level: str = None) -> str:
    """Fusionne les paires de sandhi dans un SAMPA déjà produit.

    Params
    ------
    sampa : SAMPA du g2p (monotone) ou du plan expressif (marqueurs
        « % » et « | » présents).
    token_view : ``'base'`` — le SAMPA vient du g2p de base (mode
        ``post``) ; ``'oracle'`` — il vient de l'oracle du patch (mode
        ``g2p`` expressif). Ne concerne que l'alignement.
    replace_tokens : False = insertion seule (mode ``post`` : les
        tokens du g2p restent intacts) ; True = la paire est réécrite
        avec les tokens de l'oracle (mode ``g2p`` : géminée en attaque
        + per-word de l'oracle).

    Jamais d'insertion à travers une pause (gap ≠ '.' / ' ') ; en cas
    d'échec d'alignement d'une phrase, elle est retournée inchangée.
    """
    own = warnings is None
    if own:
        warnings = []
    if not sampa or not (text or '').strip():
        return sampa
    planned = plan_pairs(text, g2p, level=level)
    if not planned:
        return sampa
    sentences = sampa.split(' | ')
    if len(sentences) != len(planned):
        warnings.append('liaison-it: structure SAMPA inattendue — no-op')
        return sampa

    out_sentences: List[str] = []
    for sent, parts in zip(sentences, planned):
        # phrase → liste de mots + paires ; le dernier slot de chaque
        # partie est None : une virgule ne liaise jamais
        words: List[str] = []
        pairs: List[Optional[_Pair]] = []
        for p_words, p_pairs in parts:
            words.extend(p_words)
            pairs.extend(p_pairs)
        merged, ok = _merge_sentence(
            sent, words, pairs, g2p, token_view, replace_tokens)
        if not ok:
            warnings.append('liaison-it: alignement SAMPA échoué — '
                            'phrase laissée inchangée')
        out_sentences.append(merged)
    return ' | '.join(out_sentences)


def _merge_sentence(sent: str, words: List[str],
                    pairs: List[Optional[_Pair]],
                    g2p: G2PCallable, token_view: str,
                    replace_tokens: bool) -> Tuple[str, bool]:
    """Aligne les tokens de la phrase puis insère les géminées."""
    cache: Dict[str, str] = {}

    def view(w: str) -> str:
        # oracle == per-word du g2p (identité) : les deux vues
        # coïncident en italien, la symétrie est conservée
        return liaison_oracle(w, g2p, cache)

    # 1. alignement séquentiel : chaque mot (token non vide) occupe un
    #    slot délimité par '.' / ' ' dans la phrase SAMPA.
    slot_by_word: Dict[int, Tuple[int, int]] = {}
    pos = 0
    for wi, w in enumerate(words):
        tok = view(w)
        if not tok:
            continue                      # mot sans token : sauté
        idx = _find_slot(sent, tok, pos)
        if idx < 0:
            return sent, False
        slot_by_word[wi] = (idx, idx + len(tok))
        pos = idx + len(tok)
    if sent[pos:].strip(' %'):
        return sent, False                # reste non aligné

    # 2. insertions (de droite à gauche pour garder les offsets) —
    #    les paires chaînées (« così come va ») se composent : chaque
    #    insertion est à/après le slot du mot droit, les offsets des
    #    paires précédentes restent valides.
    out = sent
    for k in range(len(words) - 2, -1, -1):
        pair = pairs[k] if k < len(pairs) else None
        if pair is None:
            continue
        s1 = slot_by_word.get(k)
        s2 = slot_by_word.get(k + 1)
        if s1 is None or s2 is None or s2[0] <= s1[1]:
            continue
        gap = sent[s1[1]:s2[0]]
        if gap not in ('.', ' '):
            continue                       # '%' / '|' / virgule : pause
        if replace_tokens:
            repl = _merge_pair_tokens(pair.tok1, pair.insert, pair.tok2)
            out = out[:s1[0]] + repl + out[s2[1]:]
        else:
            # insertion seule : '.' + géminée/d devant le token droit
            out = out[:s1[1]] + '.' + pair.insert + out[s2[0]:]
    return out, True


def liaison_g2p(text: str, g2p: G2PCallable,
                warnings: Optional[list] = None,
                level: str = None) -> str:
    """Mode ``g2p`` : passerelle italienne consciente du sandhi.

    Le g2p de base produit d'abord le SAMPA (bit-identique sans
    paire), puis les paires sont fusionnées avec les tokens de
    l'oracle (``replace_tokens=True``) — en italien l'oracle étant
    l'identité, la fusion équivaut à l'insertion, mais la voie
    architecturale reste celle du patch français."""
    own = warnings is None
    if own:
        warnings = []
    base = g2p(_norm(text), warnings=warnings)
    if not base:
        return base
    return apply_liaison_post(
        text, base, g2p, warnings=warnings,
        token_view='base', replace_tokens=True, level=level)


# ===========================================================================
# 7. API covtl-sandhi — niveaux + decide_pair (Branch B)
# ===========================================================================

def sandhi_oracle(word: str, g2p: G2PCallable) -> str:
    """Alias covtl-sandhi de :func:`liaison_oracle` (per-word)."""
    return liaison_oracle(word, g2p)


def decide_pair(w1: str, w2: str, tok1: str, tok2: str,
                first_in_part: bool = False,
                level: str = 'standard') -> Optional[Tuple[str, str]]:
    """Décision bas-niveau d'UNE paire (API ``apply_sandhi`` du
    package) : ``(nouveau_tok1, nouveau_tok2)`` si sandhi, None sinon.
    RS : la géminée/clé est portée par le slot DROIT, en
    attaque : ``('a', 'ka.sa')`` → ``('a', 'kka.sa')`` ; d
    eufonico : ``('e', 'i.o')`` → ``('e', 'di.o')``.
    """
    decision = _decide_level(w1, w2, tok1, tok2, level)
    if not decision:
        return None
    kind, ins = decision
    if kind == 'd':
        return (tok1, 'd' + tok2)
    return (tok1, ins + tok2)

def sandhi_g2p(text: str, g2p: G2PCallable, level: str = 'standard',
               warnings: Optional[list] = None) -> str:
    """Alias covtl-sandhi de :func:`liaison_g2p` (mode g2p, avec
    niveau de couverture)."""
    return liaison_g2p(text, g2p, warnings=warnings, level=level)


def apply_sandhi_pre(text: str, g2p: G2PCallable,
                     level: str = 'standard',
                     warnings: Optional[list] = None) -> str:
    """Alias covtl-sandhi de :func:`apply_liaison_pre` (mode pre,
    avec niveau de couverture)."""
    return apply_liaison_pre(text, g2p, warnings=warnings, level=level)


def apply_sandhi_post(text: str, sampa: str, g2p: G2PCallable,
                      level: str = 'standard',
                      warnings: Optional[list] = None,
                      token_view: str = 'base',
                      replace_tokens: bool = False) -> str:
    """Alias covtl-sandhi de :func:`apply_liaison_post` (mode post,
    avec niveau de couverture)."""
    return apply_liaison_post(text, sampa, g2p, warnings=warnings,
                              token_view=token_view,
                              replace_tokens=replace_tokens,
                              level=level)
