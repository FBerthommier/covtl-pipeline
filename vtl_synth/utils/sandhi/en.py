# SPDX-FileCopyrightText: 2026 covtl-sandhi contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
liaison_en.py
=============
Module de sandhi anglais — **a→an** + **onset linking** (dont le
linking-r comme cas particulier), trois modes en option (``off`` par
défaut), niveaux covtl-sandhi (``off/minimal/standard/careful``).

Le sandhi de l'anglais est le miroir exact de deux phénomènes romans
du package :

* **a→an** (miroir fonctionnel de la consonne latente française) :
  l'article indéfini « a » prend un /n/ devant mot à initiale
  vocalique — « a apple » → [əˈnæpl̩] → ``@.na.p@l``. La règle est
  catégorique ET phonétique : le test porte sur le TOKEN du mot
  droit (« an hour », « an honest man » : h muet → voyelle → n ;
  « a one way », « a university » : [w]/[j] initial → PAS de n —
  mesuré sur clone, le CMUdict gateway rend ``a.w@R``, ``a.n@st``,
  ``w@n``, ``ju``…). Niveau MINIMAL.
* **onset linking** (miroir de l'enlace espagnol / du linking
  français) : la consonne finale de W1, coda de sa dernière syllabe
  en isolation, devient l'**attaque** de la première syllabe de W2 à
  initiale vocalique — « far away » → /fəˈɹə.weɪ/ → ``fa.R@.we``
  (linking-r : le /ɹ/ final du token ``faR`` migre), « turn off » →
  ``t@R.nOf``, « her own car » → ``h@.Ron.kaR``, « car engine » →
  ``ka.REn.dZ@n``. Le r britannique non prévocalique étant DÉJÀ dans
  le token du CMUdict (``faR``), le linking-r n'est pas une règle
  séparée : c'est l'onset linking sur un token fini par R. Niveau
  STANDARD. Jamais après voyelle finale (pas d'enlace sans
  consonne), jamais de glide déplacé, jamais à travers une pause.

Non traité (documenté) : la **sinalefa**/smoothing (fusion de
voyelles adjacentes, « go away » → [gə.weɪ]) — elle SUPPRIMERAIT un
noyau syllabique et désalignerait les plans F0 du patch prosody
(l'invariant du framework : une clé de liaison n'est jamais un
noyau) ; l'accent dynamique (CMUdict rend des tokens plats, le
déplacement d'attaque ne déplace PAS l'accent écrit du mot —
« far away » garde l'accent sur « way » ✓).

Contraintes du patch (mêmes que les cinq autres modules) :

  * **aucune modification du moteur de synthèse** — le module vit
    dans la couche utils (texte/g2p), comme les patchs prosody et
    liaison fr/it/es/pt/de ; le moteur reçoit un SAMPA ordinaire
    dont les attaque-CV des mots liés (``fa.R@.we``) sont exactement
    la convention de son propre g2p anglais ;
  * **compatible toutes les langues** — les tables ne s'appliquent
    qu'à des paires de mots anglais ; pour tout autre profil le
    module est inactif ;
  * **compatible avec le patch prosody** (``--expressive``) : la
    clé insérée/déplacée est une CONSONNE (jamais un noyau), donc
    les indices de noyaux des plans F0 restent alignés ; jamais
    d'insertion à travers une pause (« % », « | », virgule) ;
  * **indépendant des commits g2p** — aucun import depuis
    ``vtl_synth.utils.g2p`` : le g2p actif (CMUdict gateway du
    profil ``en`` par défaut du pipeline) n'est appelé que par son
    interface publique ``(text, warnings) -> str``, mot par mot.

Les trois modes (option historique ``--liaison`` / covtl-sandhi
``--sandhi-mode``)
----------------------------------------------------------------------
1. ``pre``  — **avant le g2p** : réécriture du TEXTE orthographique.
   a→an devient sa graphie réelle (« a apple » → « an apple », le
   g2p non modifié connaît déjà « an »), contrôlée par aller-retour.
   L'onset linking n'a AUCUNE graphie (le r de « far » est écrit,
   le déplacement est phonétique) → avertissement par paire, miroir
   de l'allemand ; utiliser g2p/post.
2. ``g2p`` — **dans la couche g2p** (RECOMMANDÉ) : passerelle
   anglaise consciente du sandhi — le g2p de base est interrogé mot
   par mot (oracle = identité, le per-word CMUdict est mesuré exact
   sur clone : « a » → ``@``, « an » → ``an``, « far » → ``faR``,
   « away » → ``@.we``), les paires sont fusionnées au niveau SAMPA :
   « a apple » → ``@.na.p@l``, « far away » → ``fa.R@.we``. Sans
   paire, sortie bit-identique au g2p.
3. ``post`` — **après le g2p** : post-processeur SAMPA pur. Le g2p
   reste totalement intact ; le module aligne les tokens mot par mot
   sur le SAMPA produit (y compris le SAMPA respiré « % » du plan
   expressif) et insère/déplace aux frontières mot-mot. L'oracle
   étant l'identité, g2p et post produisent des sorties identiques —
   la différence est architecturale (miroir es/it).

Invariants
----------
* ``sandhi=off`` → sorties bit-identiques au pipeline sans patch ;
* un mode ne modifie jamais une phrase sans paire de sandhi ;
* a→an uniquement si W1 est l'article « a » ET W2 à initiale
  vocalique (token) ; onset linking uniquement si W1 finit par une
  consonne simple déplaçable et W2 commence par une voyelle ; jamais
  à travers une pause.

Niveaux covtl-sandhi
--------------------
* ``minimal`` : a→an seul (catégorique, exceptionless) ;
* ``standard`` : + onset linking / linking-r (productif) ;
* ``careful`` : = standard — l'anglais du CMUdict gateway n'a pas de
  règle registre-dépendante fiable au niveau token (documenté
  honnêtement, jamais silencieusement).

Références phonologiques : J. Wells, « Longman Pronunciation
Dictionary » (3e éd., 2008) — linking-r, article a/an ; P. Roach,
« English Phonetics and Phonology » (CUP, 4e éd. 2009), ch. liaison ;
CMUdict 0.7b (conventions SAMPA du dépôt). Usage TTS : la clé liée
est l'attaque de la syllabe suivante, miroir de la convention du
g2p espagnol/portugais du dépôt.
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
    """Rank effectif : ``None`` = standard (couverture complète des
    deux règles — l'anglais n'existait pas en v3, tout est neuf)."""
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

#: Langues supportées (le sandhi traité ici est celui de l'anglais).
LIAISON_LANGS: FrozenSet[str] = frozenset({'en'})

G2PCallable = Callable[..., str]


# ===========================================================================
# 1. Tables phonologiques fraîches (mesurées sur clone : CMUdict
#    gateway du profil 'en' — 'a'→'@', 'an'→'an', 'far'→'faR',
#    'away'→'@.we', 'apple'→'a.p@l', 'hour'→'a.w@R', 'one'→'w@n')
# ===========================================================================

#: Voyelles du SAMPA moteur (test « initiale de token vocalique »).
_TOK_VOWELS = frozenset('aeiouyEO269@2')

#: Clés SAMPA multi-caractères (l'onset linking déplace une clé
#: ENTIÈRE : jamais séparer tS/dZ).
_TOKEN_PAIRS = ('tS', 'dZ')

#: a→an : (graphie réelle, token attendu mesuré). Le g2p de base
#: connaît déjà « an » — l'aller-retour du mode pre le vérifie.
_AN_RESPELL: Dict[str, Tuple[str, str]] = {
    'a': ('an', 'an'),
}


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

    'faR' → ('fa', 'R') ; 't@Rn' → ('t@R', 'n') ; 'klin' → ('kli',
    'n'). None si le token finit par une voyelle (rien à déplacer),
    un glide (j/w), ou si l'amputation laisserait une syllabe sans
    noyau."""
    if not tok1:
        return None
    last = tok1.split('.')[-1]
    keys = _token_keys(last)
    if len(keys) < 2:
        return None                        # syllabe à une clé : garde
    c = keys[-1]
    if len(c) != 1 or c in ('j', 'w', 'ɥ'):
        return None                        # glide / clé double : garde
    if c in _TOK_VOWELS:
        return None                        # finit par une voyelle
    rest_last = ''.join(keys[:-1])
    if not any(k in _TOK_VOWELS for k in keys[:-1]):
        return None                        # amputation = syllabe vide
    head = tok1.rsplit('.', 1)[0] if '.' in tok1 else ''
    rest = f'{head}.{rest_last}' if head else rest_last
    return rest, c


def _starts_with_vowel(tok2: str) -> bool:
    """W2 commence par une voyelle SAMPA (attaque vocalique).

    Le test est PHONÉTIQUE, pas orthographique : « hour » →
    ``a.w@R`` (voyelle → an), « one » → ``w@n`` (consonne → a),
    « university » → glide [j] → a. C'est la force du module
    anglais : le h muet et les digrammes vocaliques sont déjà
    résolus par le CMUdict."""
    if not tok2:
        return False
    first = _token_keys(tok2.split('.')[0])
    return bool(first) and first[0] in _TOK_VOWELS


# ===========================================================================
# 2. Découpage du texte (miroir des conventions du g2p 'en' :
#    phrase [.!?;:]+ → '|', virgule → ' ', mots [A-Za-z']+ —
#    l'apostrophe fait partie du mot : « it's », « don't »)
# ===========================================================================

_SENT_SPLIT = re.compile(r'[.!?;:]+\s*')
_COMMA_SPLIT = re.compile(r'\s*[,–—]\s*')
_WORD_SPLIT = re.compile(r"[A-Za-z']+")
_GAP_SENT = re.compile(r'[.!?;:]')
_GAP_COMMA = re.compile(r'[,–—]')


def _norm(text: str) -> str:
    """NFC, apostrophes typographiques, strip (miroir minimal)."""
    text = unicodedata.normalize('NFC', text or '')
    return text.replace('’', "'").strip()


# ===========================================================================
# 3. Oracle : per-word du g2p actif (identité — CMUdict gateway)
# ===========================================================================

def liaison_oracle(word: str, g2p: G2PCallable,
                   _cache: Optional[Dict[str, str]] = None) -> str:
    """Token SAMPA d'un mot : per-word du g2p actif (lexique CMUdict
    → règles), mesuré exact sur clone (« a » → ``@``, « an » →
    ``an``, « far » → ``faR``, « apple » → ``a.p@l``) : l'oracle est
    l'identité. La fonction existe pour la symétrie de l'architecture
    (et le jour où une correction s'imposerait)."""
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
# 4. Décision commune aux trois modes + niveaux covtl-sandhi
# ===========================================================================

class _Pair:
    __slots__ = ('i', 'w1', 'w2', 'kind', 'insert', 'tok1', 'tok2')

    def __init__(self, i: int, w1: str, w2: str, kind: str,
                 insert: str, tok1: str, tok2: str):
        self.i = i
        self.w1, self.w2 = w1, w2
        self.kind = kind          # 'an' (article) | 'link' (onset)
        self.insert = insert      # 'n' | consonne déplacée
        self.tok1, self.tok2 = tok1, tok2


def _decide(w1: str, w2: str, tok1: str,
            tok2: str) -> Optional[Tuple[str, str]]:
    """(kind, insert) si la paire (W1, W2) porte un sandhi, sinon None.

    * W1 = article « a » ET W2 à initiale vocalique (token) →
      ('an', 'n') — l'alternance catégorique ;
    * sinon W2 à initiale vocalique ET dernière syllabe de W1 à
      finale consonantique simple → ('link', consonne) — l'onset
      linking (linking-r inclus : la consonne est 'R').
    """
    if not tok1 or not tok2:
        return None
    if w1.lower() == 'a' and _starts_with_vowel(tok2):
        return ('an', 'n')
    if _starts_with_vowel(tok2):
        split = _split_final_consonant(tok1)
        if split:
            return ('link', split[1])
    return None


def _pair_level(decision: Tuple[str, str]) -> int:
    """Niveau minimal d'application de la règle qui a tiré."""
    if decision[0] == 'an':
        return LEVEL_MINIMAL               # a→an : catégorique
    return LEVEL_STANDARD                  # onset linking : productif


def _decide_level(w1: str, w2: str, tok1: str, tok2: str,
                  level: str = None) -> Optional[Tuple[str, str]]:
    """Décision FILTRÉE par le niveau de couverture covtl-sandhi."""
    rank = _rank(level)
    decision = _decide(w1, w2, tok1, tok2)
    if decision and _pair_level(decision) <= rank:
        return decision
    return None


def plan_pairs(text: str, g2p: G2PCallable, level: str = None
               ) -> List[Tuple[List[str], List[Optional[_Pair]]]]:
    """Plan des paires, PHRASE par PHRASE (miroir du ' | ' du SAMPA).

    Retourne une liste de phrases ; chaque phrase est une liste de
    parties (virgules) ; chaque partie est (mots, paires_par_index) —
    ``paires[k]`` décrit la paire (mot k, mot k+1) si sandhi, None
    sinon. Les mots à token vide restent dans la liste (ils
    s'alignent avec le SAMPA qui les saute) mais ne forment jamais de
    paire ; le dernier slot de chaque partie est None (une virgule ne
    liaise jamais).

    ``level`` (covtl-sandhi) : filtre de COUVERTURE monotone —
    ``None``/``'standard'`` = les deux règles, ``'minimal'`` = a→an
    seul, ``'careful'`` = standard (aucune règle
    registre-dépendante au niveau token en anglais : documenté).
    """
    rank = _rank(level)
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


def _merge_pair_tokens(kind: str, tok1: str, insert: str,
                       tok2: str) -> Optional[str]:
    """Fusion SAMPA d'une paire : la clé est portée par le slot
    DROIT, en attaque.

    * ``'an'`` : ``('@', 'n', 'a.p@l')`` → ``'@.na.p@l'`` (miroir
      exact de la latente française) ;
    * ``'link'`` : le slot gauche est AMPUTÉ de sa consonne finale,
      qui devient l'attaque du droit — ``('faR', 'R', '@.we')`` →
      ``'fa.R@.we'`` (miroir de l'enlace espagnol).
    """
    if kind == 'link':
        split = _split_final_consonant(tok1)
        if not split:
            return None
        return f'{split[0]}.{insert}{tok2}'
    return f'{tok1}.{insert}{tok2}'


# ===========================================================================
# 5. Mode PRE — réécriture orthographique (avant le g2p)
# ===========================================================================

def apply_liaison_pre(text: str, g2p: G2PCallable,
                      warnings: Optional[list] = None,
                      level: str = None) -> str:
    """Mode ``pre`` : réécrit le TEXTE pour que le g2p non modifié
    produise le sandhi.

    * a→an : W1 (« a ») remplacé par « an », contrôlé au runtime
      contre le token attendu (mesuré) ;
    * onset linking : AUCUNE graphie ne code le déplacement (le r de
      « far » est écrit, l'enchaînement est phonétique) →
      avertissement par paire, miroir de l'allemand ; utiliser les
      modes g2p ou post.

    Retourne le texte réécrit (identique si aucune paire ne trouve
    son encodage)."""
    own = warnings is None
    if own:
        warnings = []
    rank = _rank(level)
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
        if kind == 'an':
            entry = _AN_RESPELL.get(w1.lower())
            if not entry:
                continue
            respell, expected = entry
            got = (g2p(respell, warnings=None) or '').strip()
            if got != expected:
                warnings.append(
                    f"liaison-en pre: repli {respell!r} pour {w1!r} "
                    f"dérivé ({got!r} != {expected!r}) — ignoré")
                continue
            edits.append((s1, e1, respell))          # W1 réécrit seul
        else:
            warnings.append(
                f"liaison-en pre: aucun encodage orthographique de "
                f"l'onset linking devant {w2!r} — utiliser les modes "
                f"g2p ou post")

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
    syllabe, ex. 'a.p@l') font partie du token et ne créent pas de
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
    token_view / replace_tokens : symétrie architecturale avec les
        autres modules — l'oracle anglais étant l'identité, les deux
        vues coïncident et le remplacement de slots (l'onset linking
        est un DÉPLACEMENT) ne dépend pas du drapeau : les modes g2p
        et post produisent des sorties identiques.

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
        warnings.append('liaison-en: structure SAMPA inattendue — no-op')
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
            warnings.append('liaison-en: alignement SAMPA échoué — '
                            'phrase laissée inchangée')
        out_sentences.append(merged)
    return ' | '.join(out_sentences)


def _merge_sentence(sent: str, words: List[str],
                    pairs: List[Optional[_Pair]],
                    g2p: G2PCallable) -> Tuple[str, bool]:
    """Aligne les tokens de la phrase puis insère/déplace."""
    cache: Dict[str, str] = {}

    def view(w: str) -> str:
        # oracle == per-word du g2p (identité) : les deux vues
        # coïncident en anglais, la symétrie est conservée
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

    # 2. fusions (de droite à gauche pour garder les offsets) :
    #    la paire (W1, W2) est réécrite par le slot fusionné —
    #    '@'+'a.p@l' → '@.na.p@l' (an), 'faR'+'@.we' → 'fa.R@.we'
    #    (link). Les paires chaînées restent possibles.
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
        repl = _merge_pair_tokens(pair.kind, pair.tok1, pair.insert,
                                  pair.tok2)
        if not repl:
            continue
        out = out[:s1[0]] + repl + out[s2[1]:]
    return out, True


def liaison_g2p(text: str, g2p: G2PCallable,
                warnings: Optional[list] = None,
                level: str = None) -> str:
    """Mode ``g2p`` : passerelle anglaise consciente du sandhi.

    Le g2p de base produit d'abord le SAMPA (bit-identique sans
    paire), puis les paires sont fusionnées avec les tokens de
    l'oracle (``replace_tokens=True``) — en anglais l'oracle étant
    l'identité, la fusion équivaut à l'insertion/déplacement, mais la
    voie architecturale reste celle du patch français."""
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
    a→an : le /n/ est porté par le slot DROIT, en attaque —
    ``('a', 'apple', '@', 'a.p@l')`` → ``('@', 'na.p@l')`` ; onset
    linking : déplacement — ``('far', 'away', 'faR', '@.we')`` →
    ``('fa', 'R@.we')``.
    """
    decision = _decide_level(w1, w2, tok1, tok2, level)
    if not decision:
        return None
    kind, ins = decision
    if kind == 'an':
        return (tok1, ins + tok2)
    split = _split_final_consonant(tok1)
    if not split:
        return None
    return (split[0], ins + tok2)


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
