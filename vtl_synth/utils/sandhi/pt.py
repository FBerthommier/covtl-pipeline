# SPDX-FileCopyrightText: 2026 Liaison patch contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
liaison_pt.py
=============
Module de sandhi portugais — **encadeamento** (resyllabification) +
**sonorisation de liaison** (s/S → z/Z), trois modes en option
(``off`` par défaut).

Le sandhi du portugais est structurellement celui de l'espagnol (une
consonne finale migre en attaque) avec UNE variation propre : la
consonne finale /s/ — palatale [ʃ] en forme pausale dans le g2p du
dépôt (convention Lisbonne : « os » → ``oS``, « amigos » →
``a.mi.guS``) — **se voise** quand elle lie : [ʃ] → [ʒ] (« os
amigos » → [oʒɐˈmiɡuʃ] → ``o.Z@.mi.guS`` ; la variante alvéolaire
[s] → [z] est couverte par la même table). Deux phénomènes
inter-mots que le g2p strictement mot-à-mots ne peut pas produire :

* **encadeamento** : la consonne finale de W1 (s→S, r→R, l, d, z…)
  — coda de sa dernière syllabe en forme isolée — devient l'**attaque**
  de la première syllabe de W2 à initiale vocalique : « os amigos »
  → ``o.Z@.mi.guS`` ; « ser útil » → ``se.Ru.til`` ; « mar azul » →
  ``ma.R@.zul`` ; « dos elefantes » → ``du.Ze.le.f@~teS``.
* **sonorisation de liaison** (EP/BP) : la finale /s/ voise devant
  voyelle — table ``{S: Z, s: z}`` — miroir de la sonorisation
  française « les » → /le/ + /z/ ; les autres consonnes (R, l, d…)
  migrent sans changement.

Non traité (documenté) :

* l'**élision** atone (« de água » → [dɐˈaɡwɐ]) — elle SUPPRIMERAIT
  un noyau syllabique et désalignerait les plans F0 du patch prosody
  (l'invariant du framework : une clé de liaison n'est jamais un
  noyau) ; de plus elle est régionale (BP familier) ;
* la **nasalisation progressive** (« um elefante » → [ũe...] : « um »
  finit en voyelle nasale ``u~``, sans consonne migra­toire — la
  paire reste sans sandhi, ce qui est la forme soignée).

Contraintes du patch (respectées et testées sur clone) :

  * **aucune modification du moteur de synthèse** — le patch vit
    dans la couche utils (texte/g2p), comme les patchs prosody et
    liaisons fr/it/es ; le moteur reçoit un SAMPA ordinaire dont les
    attaque-CV des mots liés (``o.Z@.mi.guS``) sont exactement la
    convention de son propre g2p portugais ;
  * **compatible toutes les langues** — les tables ne s'appliquent
    qu'à des paires de mots portugais ; pour tout autre profil le
    patch est inactif (avertissement + no-op) ;
  * **compatible avec le patch prosody** (``--expressive``) et avec
    les patchs fr/it/es (profils disjoints dans le même registre) :
    l'encadeamento déplace une CONSONNE (jamais un noyau), donc les
    indices de noyaux des plans F0 restent alignés ; jamais à travers
    d'une pause (« % », « | », virgule) ;
  * **indépendant des commits g2p précédents** — aucun import depuis
    ``g2p_pt`` : le g2p actif n'est appelé que par son interface
    publique ``(text, warnings) -> str`` (profil ``setlang``), mot
    par mot. Toutes les tables sont fraîches.

Les trois modes (option ``--liaison`` / ``Pipeline(liaison=...)``)
----------------------------------------------------------------------
1. ``pre``  — **avant le g2p** : réécriture du TEXTE orthographique.
   W1 amputé de sa consonne finale (« os » → « o », « ser » → « se »)
   et W2 à initiale consonantisée avec la forme LIÉE sonorisée
   (« amigos » → « jamigos » : le « j » code le [ʒ] lié, « útil » →
   « rútil »), chaque réécriture VÉRIFIÉE par aller-retour. Limites
   mesurées et acceptées : la **réduction vocalique atone** du
   portugais (a/ǝ, e/ǝ, o/u — « as » → « a » lu [a] contre ``@S``
   amputé ``@`` ; « sol » → « so » lu [su] contre ``sO``) —
   tolérances documentées, miroir espagnol/italien.
2. ``g2p`` — **dans la couche g2p** (RECOMMANDÉ) : passerelle
   portugaise consciente du sandhi — le g2p de base est interrogé
   mot par mot (oracle), les paires sont fusionnées au niveau SAMPA
   avec la consonne sonorisée en ATTAQUE : « os amigos » →
   ``o.Z@.mi.guS``. Sans paire, sortie bit-identique au g2p.
3. ``post`` — **après le g2p** : post-processeur SAMPA pur. Le g2p
   reste totalement intact ; le patch aligne les tokens mot par mot
   sur le SAMPA produit (y compris le SAMPA respiré « % » du plan
   expressif) et déplace la consonne aux frontières mot-mot.
   N'insère JAMAIS à travers une pause. Comme en espagnol,
   l'encadeamento est un DÉPLACEMENT (deux slots réécrits) — les
   modes g2p et post produisent des sorties identiques (l'oracle
   étant l'identité), la différence est architecturale.

Invariants
----------
* ``liaison=off`` → sorties bit-identiques au pipeline sans patch ;
* un mode ne modifie jamais une phrase sans paire de sandhi ;
* encadeamento uniquement si W1 finit par une consonne SIMPLE
  (jamais un glide, jamais une nasale vocalisée ``u~``/``@~``),
  uniquement si W2 commence par une voyelle ; jamais à travers une
  pause.

Références phonologiques (tables fraîches) : M. H. M. Mateus,
  E. d'Andrade, « The Phonology of Portuguese » (OUP, 2000) —
  encadeamento, voicing de liaison ; J. M. Câmara, « Estrutura da
  Língua Portuguesa » (Vozes, 1970) ; Luís, C. « Sandhi in
  European Portuguese » proc. SST 2002. Usage TTS : la consonne liée
  est l'attaque de la syllabe suivante (convention du g2p portugais
  du dépôt).
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

#: Langues supportées (le sandhi traité ici est celui du portugais).
LIAISON_LANGS: FrozenSet[str] = frozenset({'pt'})

G2PCallable = Callable[..., str]


# ===========================================================================
# 1. Tables phonologiques fraîches
# ===========================================================================

#: Voyelles du SAMPA moteur (test « initiale de token vocalique »).
_TOK_VOWELS = frozenset('aeiouyEO269@2')

#: Clés SAMPA multi-caractères.
_TOKEN_PAIRS = ('tS', 'dZ')

#: Sonorisation de liaison (EP/BP) : la finale /s/ voise devant
#: voyelle — variante palatale du g2p (S=[ʃ] → Z=[ʒ], convention
#: Lisbonne) ET variante alvéolaire (s → z).
_LINK_VOICING: Dict[str, str] = {'S': 'Z', 's': 'z'}

#: Orthographe de la consonne liée pour le mode pre : Z → « j »
#: (jato, jamigos), z → « z », R → « r », autres consonnes → elles-
#: mêmes. None = non écrivable.
_LINK_SPELLING: Dict[str, str] = {
    'Z': 'j', 'z': 'z', 'R': 'r', 'r': 'r', 'l': 'l', 'n': 'n',
    'd': 'd', 't': 't', 'm': 'm', 'v': 'v', 'f': 'f', 'b': 'b',
    'g': 'g', 'p': 'p', 'k': 'k', 's': 'z', 'S': 'j',
}

#: Réduction vocalique atone du portugais, tolérée pour l'aller-retour
#: du mode pre (le pseudo-mot passe par les RÈGLES, le mot droit par
#: le LEXIQUE) : « jamigos » → ``Za.mi.goS`` vs ``Z@.mi.guS``,
#: « se » → ``s@`` vs ``se`` amputé de ``seR``. Paires (want, got).
_PRE_TOLERANCE = frozenset({
    ('@', 'a'), ('a', '@'), ('e', '@'), ('@', 'e'),
    ('o', 'u'), ('u', 'o'), ('O', 'u'), ('O', 'o'),
})


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


def _split_final_consonant(tok1: str) -> Optional[Tuple[str, str]]:
    """(reste, consonne) si la dernière syllabe de tok1 finit par une
    consonne simple déplaçable, None sinon.

    'oS' → ('o', 'S') ; 'seR' → ('se', 'R') ; 'duS' → ('du', 'S') ;
    'maR' → ('ma', 'R'). None si le token finit par une voyelle ou
    une voyelle nasale ('u~', '@~j', 'ko~' : la nasale finale est
    VOCALISÉE en portugais — pas de consonne migra­toire), un glide,
    ou si l'amputation laisserait une syllabe sans noyau."""
    if not tok1:
        return None
    last = tok1.split('.')[-1]
    keys = _token_keys(last)
    if len(keys) < 2:
        return None
    c = keys[-1]
    if len(c) != 1 or c in ('j', 'w', 'ɥ', '~'):
        return None
    if c in _TOK_VOWELS:
        return None
    rest_last = ''.join(keys[:-1])
    if not any(k in _TOK_VOWELS for k in keys[:-1]):
        return None
    head = tok1.rsplit('.', 1)[0] if '.' in tok1 else ''
    rest = f'{head}.{rest_last}' if head else rest_last
    return rest, c


def _starts_with_vowel(tok2: str) -> bool:
    """W2 commence par une voyelle SAMPA (attaque vocalique)."""
    if not tok2:
        return False
    first = _token_keys(tok2.split('.')[0])
    return bool(first) and first[0] in _TOK_VOWELS


#: Mots-outils (classe fermée) : l'encadeamento après eux est
#: catégorique → niveau MINIMAL. Après tout autre W1 (mot
#: lexical), l'encadeamento est productif → STANDARD. Le
#: voicing /s/→[z] fait partie de la RÈGLE d'encadeamento elle-même
#: (le niveau est un filtre de COUVERTURE, jamais un changement
#: de phonologie — cf. base.py). Vue éditable :
#: sandhi/data/pt_function_words.txt.
_FUNC_WORDS: FrozenSet[str] = load_wordlist(
    'pt_function_words.txt', frozenset({
        # articles / déterminants / pronoms atones
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas',
        'do', 'da', 'dos', 'das', 'no', 'na', 'nos', 'nas',
        'meu', 'minha', 'meus', 'minhas', 'teu', 'tua',
        'seu', 'sua', 'seus', 'suas',
        'ele', 'ela', 'eles', 'elas', 'eu', 'tu',
        'me', 'te', 'se', 'lhe', 'lhes', 'nos', 'vos',
        # prépositions / conjonctions / relatifs
        'de', 'em', 'por', 'para', 'com', 'sem', 'sob',
        'sobre', 'entre', 'ate', 'até', 'e', 'ou', 'mas',
        'que', 'se', 'como', 'quando', 'onde', 'porque',
        'este', 'esta', 'esse', 'essa', 'isto', 'isso',
        'aquele', 'aquela', 'aquilo',
    }))


def _link_key(cons: str) -> str:
    """Consonne liée : forme sonorisée si /s/, telle quelle sinon."""
    return _LINK_VOICING.get(cons, cons)


# ===========================================================================
# 2. Découpage du texte (miroir frais des conventions de g2p_pt :
#    phrase [.!?;:]+ → '|', virgule → ' ', mots
#    [A-Za-zÁÀÂÃÇÉÊÍÓÔÕÚáàâãçéêíóôõú]+)
# ===========================================================================

_SENT_SPLIT = re.compile(r'[.!?;:]+\s*')
_COMMA_SPLIT = re.compile(r'\s*[,–—]\s*')
_WORD_SPLIT = re.compile(r"[A-Za-zÁÀÂÃÇÉÊÍÓÔÕÚáàâãçéêíóôõú]+")
_GAP_SENT = re.compile(r'[.!?;:]')
_GAP_COMMA = re.compile(r'[,–—]')


def _norm(text: str) -> str:
    """NFC, apostrophes typographiques, strip (miroir minimal)."""
    text = unicodedata.normalize('NFC', text or '')
    return text.replace('’', "'").strip()


# ===========================================================================
# 3. Oracle : per-word du g2p actif (identité — lexique du dépôt)
# ===========================================================================

def liaison_oracle(word: str, g2p: G2PCallable,
                   _cache: Optional[Dict[str, str]] = None) -> str:
    """Token SAMPA d'un mot : per-word du g2p actif (lexique →
    exceptions → règles).

    Le per-word portugais est adossé au lexique du dépôt et mesuré
    exact sur clone (« os » → ``oS``, « amigos » → ``a.mi.guS``,
    « ser » → ``seR``…) : l'oracle est l'identité. La fonction existe
    pour la symétrie de l'architecture (et le jour où une correction
    s'imposerait)."""
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
        self.kind = kind          # 'link' (encadeamento + sonorisation)
        self.insert = insert      # consonne liée (sonorisée si /s/)
        self.tok1, self.tok2 = tok1, tok2


def _decide(w1: str, w2: str, tok1: str,
            tok2: str) -> Optional[Tuple[str, str]]:
    """(kind, insert) si la paire (W1, W2) porte un encadeamento,
    sinon None : W2 à initiale vocalique (token) ET dernière syllabe
    de W1 à finale consonantique simple → ('link', consonne sonorisée
    si /s/, sinon telle quelle)."""
    if not tok1 or not tok2:
        return None
    if _starts_with_vowel(tok2):
        split = _split_final_consonant(tok1)
        if split:
            return ('link', _link_key(split[1]))
    return None


def _pair_level(w1: str, decision: Tuple[str, str]) -> int:
    """Niveau minimal d'application de la règle qui a tiré."""
    return (LEVEL_MINIMAL if w1.lower() in _FUNC_WORDS
            else LEVEL_STANDARD)


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
    sinon. Les mots à token vide restent dans la liste mais ne forment
    jamais de paire ; le dernier slot de chaque partie est None (une
    virgule ne liaise jamais).

    ``level`` (covtl-sandhi) : filtre de COUVERTURE monotone —
    ``None``/``'standard'`` = comportement v3 exact,
    ``'minimal'`` = encadeamento après mots-outils seuls,
    ``'careful'`` = standard (aucune règle registre-dépendante
    en portugais).
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


def _word_core(tok: str, pair_out: Optional['_Pair']) -> str:
    """Émission SAMPA du mot : token amputé de sa consonne finale
    s'il porte un encadeamento sortant, token intact sinon."""
    if pair_out is not None:
        split = _split_final_consonant(tok)
        if split:
            return split[0]
    return tok


def _merge_group(words: List[str], toks: List[str],
                 pairs: List[Optional[_Pair]], start: int,
                 end: int) -> str:
    """Fusion SAMPA d'un groupe de mots chaînés [start, end]
    (frontières incluses) : reconstruction SEGMENT PAR SEGMENT —
    chaque mot émet (consonne liée reçue de la paire entrante) +
    (token amputé/intact), les mots du groupe étant reliés par '.'.

    Chaîne « os amigos antigos » : 'o' + '.' + 'Z@.mi' + '.' +
    'guS'... chaque paire se compose — impossible par décalages
    d'offsets : l'encadeamento ampute le token gauche."""
    pieces: List[str] = []
    for i in range(start, end + 1):
        pin = pairs[i - 1] if i > start else None
        prefix = pin.insert if pin is not None else ''
        pieces.append(prefix + _word_core(
            toks[i], pairs[i] if i < end else None))
    return '.'.join(pieces)


# ===========================================================================
# 5. Mode PRE — réécriture orthographique (avant le g2p)
# ===========================================================================

def _strip_final_cons_spelling(w1: str) -> Optional[str]:
    """W1 amputé de sa consonne finale écrite : « os » → « o »,
    « ser » → « se », « paz » → « pa ». None si l'amputation est sans
    espoir (mot d'une lettre)."""
    if len(w1) < 2 or w1[-1].lower() not in 'snrdlzcztbfpmkgqhvx':
        return None
    return w1[:-1]


def _add_initial_cons_spelling(w2: str, link: str) -> Optional[str]:
    """W2 à initiale consonantisée avec la forme LIÉE : « amigos » →
    « jamigos » (Z=[ʒ] lié codé « j »), « útil » → « rútil » (R
    migre). None si la clé liée n'a pas d'orthographe."""
    if not w2:
        return None
    sp = _LINK_SPELLING.get(link)
    if not sp:
        return None
    return sp + w2


def _keys_match(got: List[str], want: List[str]) -> bool:
    if len(got) != len(want):
        return False
    return all(g == w or (w, g) in _PRE_TOLERANCE
               for g, w in zip(got, want))


def apply_liaison_pre(text: str, g2p: G2PCallable,
                      warnings: Optional[list] = None,
                      level: str = None) -> str:
    """Mode ``pre`` : réécrit le TEXTE pour que le g2p non modifié
    produise le sandhi.

    Encadeamento : W1 amputé (« os » → « o ») et W2 à initiale
    consonantisée avec la forme liée sonorisée (« amigos » →
    « jamigos »), chaque réécriture VÉRIFIÉE par aller-retour aux
    tolérances de réduction vocalique atone près (a/ǝ, e/ǝ, o/u).
    Un mot partagé par deux paires chaînées compose ses éditions ;
    l'échec d'un contrôle laisse la CHAÎNE entière sans sandhi
    (jamais de forme fausse, jamais de mot orphelin).

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
    # 1. décisions par paire (pause → pas de paire)
    decisions: List[Optional[Tuple[str, str]]] = [None] * len(spans)
    for k in range(len(spans) - 1):
        s1, e1, w1 = spans[k]
        s2, e2, w2 = spans[k + 1]
        gap = text[e1:s2]
        if _GAP_SENT.search(gap) or _GAP_COMMA.search(gap):
            continue
        tok1 = liaison_oracle(w1, g2p, cache)
        tok2 = liaison_oracle(w2, g2p, cache)
        decisions[k] = _decide_level(w1, w2, tok1, tok2, level)

    # 2. orthographe composée GROUPE PAR GROUPE (tout-ou-rien par
    #    chaîne : si UN mot de la chaîne n'a pas d'encodage, la
    #    chaîne ENTIÈRE reste sans édition)
    new_words: List[Optional[str]] = [None] * len(spans)

    def _build_word(k: int) -> Optional[str]:
        """Orthographe réécrite du mot k (None = intact, '' = échec)."""
        w = spans[k][2]
        tok = liaison_oracle(w, g2p, cache)
        pin = decisions[k - 1] if k > 0 else None   # paire entrante
        pout = decisions[k]                          # paire sortante
        prefix = pin[1] if pin is not None else ''
        amput = ''
        if pout is not None:
            split = _split_final_consonant(tok)
            amput = split[1] if split else ''
        if not prefix and not amput:
            return None               # mot intact — pas d'édition
        out_w: Optional[str] = w
        if prefix:
            out_w = _add_initial_cons_spelling(w, prefix)
            if out_w is None:
                warnings.append(
                    f"liaison-pt pre: pas d'orthographe pour la "
                    f"consonne liée {prefix!r} devant {w!r} — chaîne "
                    f"non liée en mode pre (utiliser g2p ou post)")
                return ''
            if amput:
                out_w = _strip_final_cons_spelling(out_w)
        elif amput:
            out_w = _strip_final_cons_spelling(w)
        if not out_w:
            warnings.append(
                f"liaison-pt pre: pas d'amputation pour {w!r} — "
                f"chaîne non liée en mode pre")
            return ''
        if out_w == w:
            return None
        # aller-retour : g2p(out_w) doit rendre [préfixe] + token
        # amputé (aux tolérances de réduction atone près)
        want: List[str] = []
        if prefix:
            want.append(prefix)
        want.extend(_token_keys(tok)[:-1] if amput else _token_keys(tok))
        got = (g2p(out_w, warnings=None) or '').strip()
        if not _keys_match(_token_keys(got), want):
            warnings.append(
                f"liaison-pt pre: aller-retour échoué pour {out_w!r} "
                f"({got!r}) — chaîne non liée en mode pre")
            return ''
        return out_w

    # groupes = chaînes de paires consécutives (pause = rupture) ;
    # None = mot sans édition (OK), '' = échec (toute la chaîne
    # reste sans sandhi)
    k = 0
    while k < len(spans):
        j = k
        while j + 1 < len(spans) and decisions[j] is not None:
            j += 1
        if j > k:                     # chaîne [k..j] : tout-ou-rien
            built = [_build_word(x) for x in range(k, j + 1)]
            if all(b != '' for b in built):
                for x, b in enumerate(built):
                    new_words[k + x] = b
        k = j + 1

    if all(nw is None for nw in new_words):
        return text
    out = text
    for (s, e, w), nw in sorted(zip(spans, new_words),
                                key=lambda t: t[0][0], reverse=True):
        if nw is not None:
            out = out[:s] + nw + out[e:]
    return out


# ===========================================================================
# 6. Modes G2P / POST — fusion au niveau SAMPA
# ===========================================================================

def _find_slot(content: str, tok: str, from_pos: int) -> int:
    """Cherche ``tok`` dans ``content`` comme slot délimité par des
    séparateurs de mots ('.' ou ' ') à partir de ``from_pos`` ;
    -1 si absent."""
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
    token_view / replace_tokens : symétrie architecturale avec les
        patchs fr/it/es — en portugais l'oracle est l'identité, les
        deux vues coïncident ; l'encadeamento étant un DÉPLACEMENT,
        les deux slots de chaque paire sont toujours réécrits.

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
        warnings.append('liaison-pt: structure SAMPA inattendue — no-op')
        return sampa

    out_sentences: List[str] = []
    for sent, parts in zip(sentences, planned):
        words: List[str] = []
        pairs: List[Optional[_Pair]] = []
        for p_words, p_pairs in parts:
            words.extend(p_words)
            pairs.extend(p_pairs)
        merged, ok = _merge_sentence(sent, words, pairs, g2p)
        if not ok:
            warnings.append('liaison-pt: alignement SAMPA échoué — '
                            'phrase laissée inchangée')
        out_sentences.append(merged)
    return ' | '.join(out_sentences)


def _merge_sentence(sent: str, words: List[str],
                    pairs: List[Optional[_Pair]],
                    g2p: G2PCallable) -> Tuple[str, bool]:
    """Aligne les tokens de la phrase puis reconstruit par SEGMENTS.

    1. alignement séquentiel : chaque mot (token non vide) occupe un
       slot délimité par '.' / ' ' ; l'alignement doit consommer la
       phrase exactement (reste vide hors '%').
    2. reconstruction : les mots consécutifs reliés par une paire
       forment un GROUPE fusionné par ``_merge_group`` ; les mots
       hors groupe et les pauses sont recopiés tels quels."""
    cache: Dict[str, str] = {}

    def view(w: str) -> str:
        return liaison_oracle(w, g2p, cache)

    # 1. slots
    slots: List[Tuple[int, int]] = []
    token_words: List[int] = []
    pos = 0
    for wi, w in enumerate(words):
        tok = view(w)
        if not tok:
            continue
        idx = _find_slot(sent, tok, pos)
        if idx < 0:
            return sent, False
        slots.append((idx, idx + len(tok)))
        token_words.append(wi)
        pos = idx + len(tok)
    if sent[pos:].strip(' %'):
        return sent, False

    # 2. groupes (le séparateur inter-mots du g2p pt est '.') ;
    #    une paire n'est fusionnée que si le gap est un séparateur
    tok_of = {wi: slots[k] for k, wi in enumerate(token_words)}
    toks = [view(w) for w in words]
    segments: List[Tuple[int, int, str]] = []
    k = 0
    n_tok = len(token_words)
    while k < n_tok:
        j = k
        while j + 1 < n_tok:
            wi, wj = token_words[j], token_words[j + 1]
            pair = pairs[wi] if wi < len(pairs) else None
            if pair is None or wj != wi + 1:
                break
            gap = sent[tok_of[wi][1]:tok_of[wj][0]]
            if gap not in ('.', ' '):
                break                    # '%' / '|' / ',' : pause
            j += 1
        if j > k:
            group_words = [token_words[x] for x in range(k, j + 1)]
            segments.append((k, j, _merge_group(
                words, toks, pairs,
                group_words[0], group_words[-1])))
        else:
            wi = token_words[k]
            segments.append((k, k, sent[tok_of[wi][0]:tok_of[wi][1]]))
        k = j + 1

    # 3. reconstruction : gaps/pauses originaux recopiés
    out = ''
    pos = 0
    for a, b, txt in segments:
        out += sent[pos:slots[a][0]]
        out += txt
        pos = slots[b][1]
    out += sent[pos:]
    return out, True


def liaison_g2p(text: str, g2p: G2PCallable,
                warnings: Optional[list] = None,
                level: str = None) -> str:
    """Mode ``g2p`` : passerelle portugaise consciente du sandhi.

    Le g2p de base produit d'abord le SAMPA (bit-identique sans
    paire), puis les paires sont fusionnées avec les tokens de
    l'oracle — en portugais l'oracle étant l'identité, la fusion
    équivaut au déplacement sonorisé, mais la voie architecturale
    reste celle du patch français."""
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
    Déplacement avec sonorisation : le slot gauche est amputé,
    le droit reçoit la clé liée en attaque — ``('os',
    'a.mi.guS', 'oS', 'a.mi.guS')`` → ``('o', 'Za.mi.guS')``.
    """
    decision = _decide_level(w1, w2, tok1, tok2, level)
    if not decision:
        return None
    split = _split_final_consonant(tok1)
    if not split:
        return None
    return (split[0], decision[1] + tok2)

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
