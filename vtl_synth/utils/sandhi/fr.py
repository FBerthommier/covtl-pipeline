# SPDX-FileCopyrightText: 2026 Liaison patch contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
liaison_fr.py
=============
Patch de liaison française — trois modes en option (``off`` par défaut).

La liaison est un sandhi inter-mots : la consonne latente finale d'un
mot (écrite, muette en fin de groupe) se prononce devant un mot à
initiale vocalique — « faut il » → /fo.til/, « mon ami » →
/mO~.na.mi/, « les amis » → /le.za.mi/.

Contraintes du patch (respectées et testées sur clone) :

  * **aucune modification du moteur de synthèse** — le patch vit dans
    la couche utils (texte/g2p), comme le patch prosody ; le moteur
    reçoit un SAMPA lié ordinaire (``mO~.na.mi``) qu'il synthétise tel
    quel (vérifié : les formes liées passent syltraj sans l'effondrement
    ``V~.V`` — la consonne de liaison s'intercale entre les voyelles) ;
  * **compatible toutes les langues** — les tables ne s'appliquent
    qu'à des paires de mots français ; pour tout autre profil le patch
    est inactif (avertissement + no-op) ;
  * **compatible avec le patch prosody** (``--expressive``) — la
    consonne insérée n'est jamais un noyau, donc les indices de noyaux
    des plans F0 restent alignés ; jamais d'insertion à travers une
    pause (« % », « | », virgule) ;
  * **indépendant des commits g2p précédents** — aucun import depuis
    ``g2p_fr``/``g2p_fr_legacy`` : le g2p actif n'est appelé que par
    son interface publique ``(text, warnings) -> str`` (profil
    ``setlang``), mot par mot. Toutes les tables sont fraîches.

Les trois modes (option ``--liaison`` / ``Pipeline(liaison=...)``)
----------------------------------------------------------------------
1. ``pre``  — **avant le g2p** : réécriture du TEXTE orthographique.
   W1 est remplacé par une orthographe de repli (« faut » → « faute »,
   « grand » → « grante », « mon » → « monne ») que le g2p NON MODIFIÉ
   convertit en [pron(W1) + latente] ; W2 reste un mot séparé (chemin
   lexique/exceptions du g2p). Limites mesurées et acceptées : la
   consonne atterrit en coda de W1 (pas en attaque de la syllabe
   suivante), petits décalages de symboles voyelles (``o~``/``O~``,
   ``e``/``E``) et couverture partielle (pas de repli correct pour
   « est », « petit », « en », « plus », « vieux », « ces », « plein »,
   « jamais », « beaucoup »). Mode le plus découplé, le moins fidèle.
2. ``g2p`` — **dans la couche g2p** (RECOMMANDÉ) : passerelle française
   consciente de la liaison — le g2p de base est interrogé mot par mot
   (oracle), les paires liées sont fusionnées au niveau SAMPA avec la
   consonne en ATTAQUE : « faut il » → ``fo.til``, « mon ami » →
   ``mO~.na.mi``. L'oracle corrige au passage les per-word du g2p de
   base sur la classe fermée (« il »→``il`` et non ``i``). Sans paire,
   la sortie est bit-identique au g2p de base.
3. ``post`` — **après le g2p** : post-processeur SAMPA pur. Le g2p
   reste totalement intact ; le patch aligne les tokens mot par mot
   sur le SAMPA produit (y compris le SAMPA respiré « % » du plan
   expressif) et insère la consonne latente aux frontières mot-mot.
   N'insère JAMAIS à travers une pause. Hérite les défauts du g2p de
   base (ex. « il »→``i`` : « faut il » → ``fo.ti``) — insérer ne peut
   pas corriger un token.

Invariants
----------
* ``liaison=off`` → sorties bit-identiques au pipeline sans patch ;
* un mode ne modifie jamais une phrase sans paire de liaison ;
* insertion uniquement si W1 finit par une voyelle (jamais de double
  consonne), W2 commence par une voyelle, jamais après « et », jamais
  devant un *h aspiré* (liste fermée) ni un nom propre (majuscule non
  initiale de partie), jamais à travers une pause.

Références phonologiques (tables fraîches) : P. Delattre, « La liaison
en français », The French Review 24/4 (1951) ; P. Encrevé, « La
liaison sans enchaînement », Langue française 58 (1988) ; F. Tranel,
Aspects of French Phonology, Oxford (2000), ch. liaison. Usage TTS :
consonne latente = attaque de la syllabe suivante ; dévoisement des
latentes (/d/→[t] : « grand ami » → /gRa~.ta.mi/) ; « neuf » → /v/
devant a- (neuf ans /n2.va~/), /f/ ailleurs (neuf heures /n2.f9R/).
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

#: Langues supportées (la liaison est un sandhi du français).
LIAISON_LANGS: FrozenSet[str] = frozenset({'fr'})

G2PCallable = Callable[..., str]


# ===========================================================================
# 1. Tables phonologiques fraîches
# ===========================================================================

#: Voyelles orales du SAMPA moteur (clés stables, cf. phonemes + lang sets).
_ORAL_VOWELS = frozenset('aeiouyEO@269')

#: Voyelles nasales émises par le g2p français.
_NASAL_VOWELS = frozenset(('a~', 'E~', 'O~', '9~', 'o~'))

#: Consonne latente selon la dernière LETTRE écrite de W1 ; dévoisement
#: standard d→t (« grand ami » → /gRa~.ta.mi/).
_LATENT_BY_LETTER: Dict[str, str] = {
    't': 't', 'd': 't', 's': 'z', 'x': 'z', 'z': 'z',
    'n': 'n', 'r': 'R', 'p': 'p', 'f': 'f', 'g': 'g',
}


def _latent_phone(w1: str, w2: str) -> Optional[str]:
    """Consonne latente de W1 devant W2 (None = pas de liaison)."""
    low1, low2 = w1.lower(), w2.lower()
    if low1 == 'neuf':                      # neuf ans /n2.va~/
        return 'v' if low2[:1] in ('a', 'à', 'â') else 'f'
    last = low1[-1:] if low1 else ''
    return _LATENT_BY_LETTER.get(last)


#: Mots déclencheurs (classe fermée) — la prononciation de W1 (finie
#: par une voyelle) et l'initiale de W2 (voyelle) filtrent en dessous.
_TRIGGERS: FrozenSet[str] = frozenset({
    # déterminants / possessifs / démonstratifs
    'les', 'des', 'ces', 'cet', 'cette', 'mes', 'tes', 'ses', 'nos',
    'vos', 'mon', 'ton', 'son', 'un',
    # pronoms
    'il', 'ils', 'elle', 'elles', 'on', 'en', 'nous', 'vous',
    # copules, auxiliaires, modaux (3e pers.)
    'est', 'sont', 'ont', 'avait', 'avaient', 'etait', 'etaient',
    'étais', 'étaient', 'es', 'font', 'vont', 'doit', 'peut', 'veut',
    'faut', 'dit', 'fait', 'vais', "c'est", "n'est", 'est-ce',
    # adverbes, prépositions, négation, conjonctions liantes
    'très', 'tres', 'trop', 'plus', 'moins', 'bien', 'souvent',
    'pendant', 'quand', 'sans', 'dans', 'chez', 'jamais', 'comment',
    'pas', 'tout', 'tous', 'mais', 'rien', 'combien', 'tres',
    'avant', 'assez', 'vraiment', 'dont',
    # adjectifs antéposés
    'petit', 'grand', 'gros', 'bon', 'mauvais', 'premier', 'dernier',
    'second', 'ancien', 'certain', 'vingt', 'cent', 'plein', 'long',
    'vieux', 'ancienne', 'grande',
    # numéraux
    'deux', 'trois', 'six', 'dix', 'neuf', 'beaucoup',
})

#: Jamais de liaison depuis W1 (« et » — règle classique).
_BLOCKERS_W1: FrozenSet[str] = frozenset({'et'})

#: Sous-classe MINIMALE des déclencheurs : liaisons OBLIGATOIRES
#: (catégoriques, exceptionless) — déterminants / possessifs /
#: démonstratifs, pronoms, copules et auxiliaires être/avoir. Le
#: reste de ``_TRIGGERS`` (adverbes, prépositions, négation,
#: adjectifs antéposés, numéraux, verbes pleins/modaux) relève du
#: niveau STANDARD (liaison facultative courante).
_TRIGGERS_MINIMAL: FrozenSet[str] = frozenset({
    # déterminants / possessifs / démonstratifs
    'les', 'des', 'ces', 'cet', 'cette', 'mes', 'tes', 'ses', 'nos',
    'vos', 'mon', 'ton', 'son', 'un',
    # pronoms
    'il', 'ils', 'elle', 'elles', 'on', 'en', 'nous', 'vous',
    # copules / auxiliaires être et avoir (3e pers.)
    'est', 'sont', 'ont', 'avait', 'avaient', 'etait', 'etaient',
    'étais', 'étaient', 'es',
})

#: Niveau CAREFUL (style soutenu) : liaison après nom/adjectif
#: PLURIEL — W1 hors ``_TRIGGERS`` finissant par -s/-x (latente /z/)
#: mais PAS une forme verbale détectable (terminaisons personnelles
#: -es/-ent/-ez/-ons) : heuristique fermée et documentée, la
#: frontière nom/verbe n'étant pas marquée à l'écrit. Les
#: invariables réels (« puis », « toujours ») restent admis —
#: leur liaison est de fait soutenable (« puis il »).
_PLURAL_VERB_ENDINGS: Tuple[str, ...] = ('es', 'ent', 'ez', 'ons')


def _plural_candidate(low1: str) -> bool:
    """W1 (minuscule) = pluriel de nom/adjectif probable (careful)."""
    if len(low1) < 3 or low1[-1:] not in ('s', 'x'):
        return False
    if low1.endswith(_PLURAL_VERB_ENDINGS):
        return False                     # forme verbale probable
    return True


#: *h aspiré* (liste fermée usuelle) — bloque la liaison sur W2.
#: Vue éditable : sandhi/data/fr_h_aspire.txt (une entrée par
#: ligne, commentaires '#', repli = la table embarquée).
_H_ASPIRE: FrozenSet[str] = load_wordlist(
    'fr_h_aspire.txt', frozenset({
    'héros', 'heros', 'haut', 'hauts', 'haute', 'hautes', 'hauteur',
    'hauteurs', 'hache', 'haie', 'haine', 'hall', 'halle', 'harpe',
    'hasard', 'hélas', 'helas', 'hectare', 'homard', 'huche', 'hoyau',
    'hamburger',
}))

#: Corrections de per-word du g2p de base, nécessaires à la fidélité
#: de la liaison (mesurées sur clone : « il »→``i``, « est »→``e``,
#: « petit »→``ti``, « plus »→``py``…). L'oracle les applique aux mots
#: d'une paire de liaison ; le reste de la phrase garde les tokens du
#: g2p de base (liaison=off → bit-identique).
_PRON_OVERRIDES: Dict[str, str] = {
    'il': 'il',          # base: 'i'   — /il/
    'ils': 'il',         # base: 'i'   — /il/
    'elle': 'El',        # base: 'a'   — /ɛl/
    'est': 'E',          # base: 'e'   — /ɛ/
    'cet': 'sE',         # base: 'st'  — /sɛ/
    'ces': 'se',         # base: 'se.@.Es' — /se/
    'petit': 'p@.ti',    # base: 'ti'  — /pə.ti/
    'plus': 'ply',       # base: 'py'  — /ply/
    'second': 's@gO~',   # base: 'zgO~' — /sə.gɔ̃/
    'huit': 'ɥit',       # base: 'ɥi'  — /ɥit/
    'dernier': 'dER.nje',     # base: 'dERn.je'
    'ancien': 'a~sjE',   # base: 'a~sjE~' (nasale !) — /ɑ̃.sjɛ/
    'certain': 'sER.tE', # base: 'sERtE~' (nasale !) — /sɛʁ.tɛ/
}


def _pre_entry(low1: str, w2: str
               ) -> Optional[Tuple[str, str]]:
    """Entrée du mode ``pre`` : (orthographe de repli, token attendu).

    Les entrées non mesurées ou driftées (la base dit autre chose que
    le token attendu) sont absentes → la paire est signalée et non
    liée en mode ``pre`` (utiliser g2p/post). Couverture partielle
    assumée et documentée.
    """
    low2 = w2.lower()
    if low1 == 'neuf':
        # /v/ devant a-, /f/ ailleurs (les deux mesurés)
        if low2[:1] in ('a', 'à', 'â'):
            return ('neuve', 'n9v')
        return ('neufe', 'n2f')
    return _PRE_RESPELL.get(low1)


#: Orthographes de repli mesurées sur clone : W1' est un mot que le
#: g2p NON MODIFIÉ convertit exactement en [pron(W1) + latente] ;
#: « attendu » est le token mesuré pour W1'. W2 reste un mot séparé.
_PRE_RESPELL: Dict[str, Tuple[str, str]] = {
    'faut':    ('faute', 'fot'),
    'grand':   ('grante', 'gRa~t'),     # d écrit → t (dévoisement)
    'avant':   ('avante', 'ava~t'),
    'vous':    ('vouze', 'vuz'),
    'nous':    ('nouze', 'nuz'),
    'mon':     ('monne', 'mo~n'),       # o~ vs O~ : décalage accepté
    'ton':     ('tonne', 'tOn'),
    'son':     ('sonne', 'sOn'),
    'un':      ('unne', '9~n'),
    'on':      ('onne', 'o~n'),         # o~ accepté
    'ont':     ('onte', 'o~t'),
    'sont':    ('sonte', 'so~t'),
    'font':    ('fonte', 'fO~t'),
    'vont':    ('vonte', 'vo~t'),
    'les':     ('léze', 'lez'),
    'des':     ('déze', 'dez'),
    'mes':     ('méze', 'mez'),
    'tes':     ('téze', 'tez'),
    'ses':     ('séze', 'sez'),
    'nos':     ('nose', 'noz'),
    'vos':     ('voze', 'voz'),
    'deux':    ('deuze', 'd2z'),
    'trois':   ('troize', 'tRwaz'),
    'six':     ('size', 'siz'),
    'dix':     ('dize', 'diz'),
    'tous':    ('touze', 'tuz'),
    'tout':    ('toute', 'tut'),
    'très':    ('trèze', 'tREz'),
    'trop':    ('trope', 'tROp'),
    'quand':   ('quante', 'ka~t'),
    'sans':    ('sanze', 'sa~z'),
    'dans':    ('danze', 'da~z'),
    'chez':    ('chèze', 'SEz'),
    'bon':     ('bonne', 'bOn'),
    'mais':    ('mèze', 'mEz'),
    'pas':     ('paze', 'paz'),
    'vingt':   ('vinte', 'vE~t'),
    'cent':    ('sante', 'sa~t'),
    'long':    ('longue', 'lO~g'),
    'ancien':  ('ancienne', 'a~sjEn'),
    'certain': ('certaine', 'sER.tEn'),
    'premier': ('première', 'pR@m.jER'),   # e/E : décalage accepté
    'dernier': ('dernière', 'd@R.ni.ER'),
    'second':  ('seconte', 's@ko~t'),
    'souvent': ('souvente', 'suva~t'),
    'pendant': ('pendante', 'pa~da~t'),
    'comment': ('commente', 'ko~ma~t'),    # o~ accepté
    'peut':    ('peute', 'p2t'),
    'veut':    ('veute', 'v2t'),
    'doit':    ('doite', 'dwat'),
    'dit':     ('dite', 'dit'),
    'fait':    ('faite', 'fEt'),
    'vais':    ('vaise', 'vEz'),
}


# ===========================================================================
# 2. Découpage du texte (miroir frais des conventions du paquet,
#    cf. chunking.py / g2p_fr_legacy.py : phrase [.!?;:]+ → '|',
#    virgule → ' ', mots [A-Za-zÀ-ÿ'’]+)
# ===========================================================================

_SENT_SPLIT = re.compile(r'[.!?;:]+\s*')
_COMMA_SPLIT = re.compile(r'\s*[,–—]\s*')
_WORD_SPLIT = re.compile(r"[A-Za-zÀ-ÿ'’]+")
_GAP_SENT = re.compile(r'[.!?;:]')
_GAP_COMMA = re.compile(r'[,–—]')


def _norm(text: str) -> str:
    """NFC, apostrophes typographiques, strip (miroir minimal)."""
    text = unicodedata.normalize('NFC', text or '')
    return text.replace('’', "'").strip()


def _first_is_vowel(tok: str) -> bool:
    if not tok:
        return False
    if tok[:2] in _NASAL_VOWELS:
        return True
    return tok[0] in _ORAL_VOWELS


# ===========================================================================
# 3. Oracle : per-word du g2p actif + corrections de classe fermée
# ===========================================================================

def liaison_oracle(word: str, g2p: G2PCallable,
                   _cache: Optional[Dict[str, str]] = None) -> str:
    """Token SAMPA d'un mot : correction du patch si définie, sinon
    per-word du g2p actif (lexique → exceptions → règles)."""
    if _cache is not None:
        cached = _cache.get(word)
        if cached is not None:
            return cached
    low = word.lower()
    if low in _PRON_OVERRIDES:
        tok = _PRON_OVERRIDES[low]
    else:
        try:
            tok = (g2p(low, warnings=None) or '').strip()
        except Exception:
            tok = ''
    if _cache is not None:
        _cache[low] = tok
    return tok


def _base_token(word: str, g2p: G2PCallable,
                cache: Dict[str, str]) -> str:
    """Token per-word du g2p de base (sans correction)."""
    low = word.lower()
    if low in cache:
        return cache[low]
    try:
        tok = (g2p(low, warnings=None) or '').strip()
    except Exception:
        tok = ''
    cache[low] = tok
    return tok


def supports_liaison(lang: str) -> bool:
    """Le patch de liaison est-il actif pour cette langue ?"""
    return (lang or '').lower() in LIAISON_LANGS


# ===========================================================================
# 4. Décision commune aux trois modes
# ===========================================================================

class _Pair:
    __slots__ = ('i', 'w1', 'w2', 'latent', 'tok1', 'tok2')

    def __init__(self, i: int, w1: str, w2: str, latent: str,
                 tok1: str, tok2: str):
        self.i = i
        self.w1, self.w2 = w1, w2
        self.latent = latent
        self.tok1, self.tok2 = tok1, tok2


def _decide(w1: str, w2: str, tok1: str, tok2: str,
            first_in_part: bool,
            include_plural: bool = False) -> Optional[str]:
    """Consonne latente si la paire (W1, W2) doit être liée, sinon None.

    La latente est la dernière LETTRE écrite de W1, muette dans la
    prononciation isolée (« ils » /il/ + s latent → « ils ont »
    /il.zO~/) ; elle n'est PAS insérée si le token la prononce déjà
    en finale (« sept heures » /sE.t9R/ : lien naturel, pas de
    double consonne).

    ``include_plural`` (niveau ``careful``) étend la classe des
    déclencheurs aux noms/adjectifs pluriels (-s/-x, hors formes
    verbales) — liaison de style soutenu : « enfants adorables » →
    /A~.fa~.za.dO.rabl/, « idées intéressantes ».
    """
    if not tok1 or not tok2:
        return None
    low1, low2 = w1.lower(), w2.lower()
    if low1 in _BLOCKERS_W1:
        return None
    if low2 in _H_ASPIRE:
        return None
    if w2[:1].isupper() and not first_in_part:
        return None                       # nom propre (non initial)
    if low1 not in _TRIGGERS:
        if not (include_plural and _plural_candidate(low1)):
            return None
    if not _first_is_vowel(tok2):
        return None                       # W2 pas à initiale vocalique
    latent = _latent_phone(w1, w2)
    if not latent:
        return None
    if tok1.endswith(latent):
        return None                       # déjà prononcée en finale
    return latent


def _pair_level(w1: str, latent: str) -> int:
    """Niveau minimal d'application de la règle qui a tiré."""
    low1 = w1.lower()
    if low1 in _TRIGGERS_MINIMAL:
        return LEVEL_MINIMAL
    if low1 in _TRIGGERS:
        return LEVEL_STANDARD
    return LEVEL_CAREFUL                  # pluriel hors classe fermée


def plan_pairs(text: str, g2p: G2PCallable, level: str = None
               ) -> List[Tuple[List[str], List[Optional[_Pair]]]]:
    """Plan des paires, PHRASE par PHRASE (miroir du ' | ' du SAMPA).

    Retourne une liste de phrases ; chaque phrase est une liste de
    parties (virgules) ; chaque partie est (mots, paires_par_index) —
    ``paires[k]`` décrit la paire (mot k, mot k+1) si liaison, None
    sinon. Les mots à token vide restent dans la liste (ils s'alignent
    avec le SAMPA qui les saute) mais ne forment jamais de paire.

    ``level`` (covtl-sandhi) : filtre de COUVERTURE monotone sur la
    table — ``None``/``'standard'`` = comportement v3 exact,
    ``'minimal'`` = liaisons obligatoires seules, ``'careful'`` =
    + style soutenu (noms pluriels). Le niveau ne change JAMAIS la
    phonologie d'une règle qui tire (cf. ``base.level_rank``).
    """
    rank = _rank(level)
    include_plural = rank >= LEVEL_CAREFUL
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
                w1, w2 = words[k], words[k + 1]
                latent = _decide(w1, w2, toks[k], toks[k + 1], k == 0,
                                 include_plural=include_plural)
                if latent and _pair_level(w1, latent) <= rank:
                    pairs[k] = _Pair(k, w1, w2, latent,
                                     toks[k], toks[k + 1])
            parts.append((words, pairs))
        if parts:
            sentences.append(parts)
    return sentences


def _merge_pair_tokens(tok1: str, latent: str, tok2: str) -> str:
    """Fusion SAMPA d'une paire : latente en ATTAQUE de W2."""
    return f'{tok1}.{latent}{tok2}'


# ===========================================================================
# 5. Mode PRE — réécriture orthographique (avant le g2p)
# ===========================================================================

def apply_liaison_pre(text: str, g2p: G2PCallable,
                      warnings: Optional[list] = None,
                      level: str = None) -> str:
    """Mode ``pre`` : réécrit le TEXTE pour que le g2p non modifié
    produise la liaison.

    Chaque W1 porteur est remplacé (en place, ponctuation conservée)
    par son orthographe de repli ``_PRE_RESPELL`` — contrôlée au
    runtime contre le token attendu. W2 reste un mot séparé. Retourne
    le texte réécrit (identique si aucune paire ne trouve de repli).
    """
    own = warnings is None
    if own:
        warnings = []
    rank = _rank(level)
    include_plural = rank >= LEVEL_CAREFUL
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
        # w1 est-il le premier mot de sa partie ? (sinon une majuscule
        # sur w2 = nom propre → pas de liaison)
        if k == 0:
            first_in_part = True
        else:
            prev_gap = text[spans[k - 1][1]:s1]
            first_in_part = bool(
                _GAP_SENT.search(prev_gap) or _GAP_COMMA.search(prev_gap))
        tok1 = liaison_oracle(w1, g2p, cache)
        tok2 = liaison_oracle(w2, g2p, cache)
        latent = _decide(w1, w2, tok1, tok2, first_in_part,
                         include_plural=include_plural)
        if not latent or _pair_level(w1, latent) > rank:
            continue
        entry = _pre_entry(w1.lower(), w2)
        if not entry:
            warnings.append(
                f"liaison pre: pas d'orthographe de repli pour {w1!r} "
                f"devant {w2!r} ({latent!r}) — paire non liée en mode pre "
                f"(utiliser le mode g2p ou post)")
            continue
        respell, expected = entry
        got = (g2p(respell, warnings=None) or '').strip()
        if got != expected:
            warnings.append(
                f"liaison pre: repli {respell!r} pour {w1!r} drifté "
                f"({got!r} != {expected!r}) — ignoré")
            continue
        edits.append((s1, e1, respell))

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
    syllabe, ex. 'a.mi') font partie du token et ne créent pas de
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
    """Fusionne les paires de liaison dans un SAMPA déjà produit.

    Params
    ------
    sampa : SAMPA du g2p (monotone) ou du plan expressif (marqueurs
        « % » et « | » présents).
    token_view : ``'base'`` — le SAMPA vient du g2p de base (mode
        ``post``) ; ``'oracle'`` — il vient de l'oracle du patch (mode
        ``g2p`` expressif). Ne concerne que l'alignement.
    replace_tokens : False = insertion seule (mode ``post`` : les
        tokens du g2p restent intacts) ; True = la paire est réécrite
        avec les tokens de l'oracle (mode ``g2p`` : latente en attaque
        + per-word corrigés).

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
        warnings.append('liaison: structure SAMPA inattendue — no-op')
        return sampa

    out_sentences: List[str] = []
    for sent, parts in zip(sentences, planned):
        # phrase → liste de mots + paires (None aux frontières de
        # parties : une virgule ne liaise jamais)
        words: List[str] = []
        pairs: List[Optional[_Pair]] = []
        for p_words, p_pairs in parts:
            words.extend(p_words)
            pairs.extend(p_pairs)
            if p_pairs:
                pairs[len(pairs) - 1] = pairs[len(pairs) - 1]  # déjà None
        merged, ok = _merge_sentence(
            sent, words, pairs, g2p, token_view, replace_tokens)
        if not ok:
            warnings.append('liaison: alignement SAMPA échoué — '
                            'phrase laissée inchangée')
        out_sentences.append(merged)
    return ' | '.join(out_sentences)


def _merge_sentence(sent: str, words: List[str],
                    pairs: List[Optional[_Pair]],
                    g2p: G2PCallable, token_view: str,
                    replace_tokens: bool) -> Tuple[str, bool]:
    """Aligne les tokens de la phrase puis insère les latentes."""
    cache: Dict[str, str] = {}

    def view(w: str) -> str:
        if token_view == 'oracle':
            return liaison_oracle(w, g2p, cache)
        return _base_token(w, g2p, cache)

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

    # 2. insertions (de droite à gauche pour garder les offsets)
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
            repl = _merge_pair_tokens(pair.tok1, pair.latent, pair.tok2)
            out = out[:s1[0]] + repl + out[s2[1]:]
        else:
            # insertion seule : ' ' (pause nasale) ou '.' → '.' + latente
            out = out[:s1[1]] + '.' + pair.latent + out[s2[0]:]
    return out, True


def liaison_g2p(text: str, g2p: G2PCallable,
                warnings: Optional[list] = None,
                level: str = None) -> str:
    """Mode ``g2p`` : passerelle française consciente de la liaison.

    Le g2p de base produit d'abord le SAMPA (bit-identique sans
    paire), puis les paires sont fusionnées avec les tokens corrigés
    de l'oracle (``replace_tokens=True``)."""
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
    Rank + décision v3 filtrés ; la latente est portée par le
    slot DROIT, en attaque : ``('faut', 'il', 'fo', 'i')`` →
    ``('fo', 'ti')`` ; pluriel careful : ``('enfants',
    'adorables', 'A~.fa~', 'a.dO.rabl')`` → ``('A~.fa~',
    'za.dO.rabl')``.
    """
    rank = _rank(level)
    latent = _decide(w1, w2, tok1, tok2, first_in_part,
                     include_plural=(rank >= LEVEL_CAREFUL))
    if not latent or _pair_level(w1, latent) > rank:
        return None
    return (tok1, latent + tok2)

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
