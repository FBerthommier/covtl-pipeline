# SPDX-FileCopyrightText: 2026 Liaison patch contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
liaison_de.py
=============
Module de frontières allemand — **Glottalversatz** (coup de glotte
avant initiale vocalique), trois modes en option (``off`` par
défaut). C'est le membre « anti-liaison » du framework : là où le
français insère une consonne latente et où l'espagnol déplace une
consonne finale, l'allemand **marque** la frontière de mot.

**Glottalversatz (Knacklaut)** : devant un mot lexical à initiale
vocalique, l'allemand soigné pose un coup de glotte (ré-
articulation) au lieu d'enchaîner — « ein Apfel » → [aɪn ˈʔapfəl],
« der alte Mann » → [deːɐ̯ ˈʔaltə ˈman], « ich esse ein Apfel » →
[ɪç ˈʔɛsə aɪn ˈʔapfəl]. Le g2p de base du dépôt relie TOUS les mots
adjacents par « . » (coarticulation maximale : ``ajn.a.pf@l`` =
[aɪ.na.pfəl] — lissé, non standard). Les mots-OUTILS à initiale
vocalique (ein, und, es, ich, in, auf, auch…) restent enchaînés
lisses en parole courante (« und auch » → [ʊnt‿aʊx]) : le module
insère donc la frontière uniquement devant les mots LEXICAUX
(nom, verbe, adjectif, adverbe — classe fermée d'exemptions).

**Encodage moteur** : le coup de glotte [ʔ] n'est PAS un phonème de
l'inventaire moteur (``ALL_PHONEME_KEYS`` n'a pas de ``?``). Le
module l'encode comme **frontière de mot** : remplacer le lien
syllabique « . » par un espace — l'espace est le séparateur de mots
natif du SAMPA moteur (le g2p français l'utilise : ``mO~ a.mi``),
le moteur y produit une ré-articulation (gap inter-mot), réalisation
standard des frontières glottales dans les systèmes sans phonème
/ʔ/. Documenté comme contrainte moteur, sans aucune modification du
moteur.

Contraintes du patch (respectées et testées sur clone) :

  * **aucune modification du moteur de synthèse** — le patch vit
    dans la couche utils (texte/g2p), comme les patchs prosody et
    liaisons fr/it/es/pt ; le moteur reçoit un SAMPA ordinaire ;
  * **compatible toutes les langues** — les tables ne s'appliquent
    qu'à des paires de mots allemands ; pour tout autre profil le
    patch est inactif (avertissement + no-op) ;
  * **compatible avec le patch prosody** (``--expressive``) et avec
    les patchs fr/it/es/pt (profils disjoints) : la frontière
    insérée n'ajoute ni ne retire aucun NOYAU syllabique (elle
    sépare des consonnes/voyelles existantes), donc la séquence de
    noyaux des plans F0 reste alignée ; jamais à travers d'une pause
    (« % », « | », virgule) — et la frontière n'est insérée que là
    où le g2p avait posé un lien « . » ;
  * **indépendant des commits g2p précédents** — aucun import depuis
    ``g2p_de`` : le g2p actif n'est appelé que par son interface
    publique ``(text, warnings) -> str`` (profil ``setlang``), mot
    par mot. Toutes les tables sont fraîches.

Les trois modes (option ``--liaison`` / ``Pipeline(liaison=...)``)
----------------------------------------------------------------------
1. ``pre``  — **avant le g2p** : AUCUNE graphie allemande ne code le
   coup de glotte (contrairement au respelling français ou à
   l'alternance espagnole y→e). Le mode ``pre`` est donc
   structurellement INACTIF pour l'allemand : no-op + avertissement
   explicite. C'est le troisième point de la comparaison
   d'architecture : le mode pre ne peut faire que ce que
   l'orthographe encode — français (partiel), italien (partiel),
   espagnol (alternance totale, enlace partiel), portugais
   (partiel), allemand (rien).
2. ``g2p`` — **dans la couche g2p** (RECOMMANDÉ) : passerelle
   allemande consciente des frontières — le g2p de base produit le
   SAMPA (bit-identique sans paire), le module insère la frontière
   de mot devant chaque mot lexical à initiale vocalique :
   « ein Apfel » → ``ajn a.pf@l``. Sans paire, sortie bit-identique.
3. ``post`` — **après le g2p** : post-processeur SAMPA pur (même
   édition sur le SAMPA monotone ou le SAMPA respiré « % » du plan
   expressif). Comme l'oracle allemand est l'identité, g2p et post
   produisent des sorties identiques — la différence est
   architecturale (miroir espagnol/portugais).

Invariants
----------
* ``liaison=off`` → sorties bit-identiques au pipeline sans patch ;
* un mode ne modifie jamais une phrase sans mot lexical à initiale
  vocalique ;
* frontière uniquement si W2 commence par une voyelle SAMPA ET
  n'appartient pas à la classe fermée des mots-outils ; jamais à
  travers une pause.

Références phonologiques (tables fraîches) : P. Eisenberg, « Grund-
riss der deutschen Grammatik. Der Laut » (Metzler) ; K. Kohler,
« Glottal stops and glottal friction in German and other
languages » (JIPA 1994) — Glottalversatz devant attaque vocalique
lexicale ; Duden, « Aussprachewörterbuch » (Bd. 6). Usage TTS :
frontière de mot = ré-articulation (le moteur n'a pas de phonème
/ʔ/, cf. ``constants.ALL_PHONEME_KEYS``).
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

#: Langues supportées (le sandhi traité ici est celui de l'allemand).
LIAISON_LANGS: FrozenSet[str] = frozenset({'de'})

G2PCallable = Callable[..., str]


# ===========================================================================
# 1. Tables phonologiques fraîches
# ===========================================================================

#: Voyelles du SAMPA moteur (test « initiale de token vocalique »).
_TOK_VOWELS = frozenset('aeiouyEO269@2')

#: Clés SAMPA multi-caractères.
_TOKEN_PAIRS = ('tS', 'dZ')

#: Mots-OUTILS à initiale vocalique (classe fermée) : enchaînement
#: lisse en parole courante — PAS de coup de glotte devant eux.
#: Articles/déterminants (ein-), pronoms (personnels, possessifs),
#: conjonctions, prépositions et particules courantes. Les mots
#: LEXICAUX (nom, verbe, adjectif, adverbe) prennent la frontière.
#: Vue éditable : sandhi/data/de_glottal_exempt.txt (repli =
#: la table embarquée).
_GLOTTAL_EXEMPT: FrozenSet[str] = load_wordlist(
    'de_glottal_exempt.txt', frozenset({
    # articles / déterminants
    'ein', 'eine', 'einen', 'einem', 'einer', 'eines',
    # pronoms personnels et possessifs
    'ich', 'er', 'es', 'ihn', 'ihm', 'ihnen', 'ihr', 'ihre',
    'ihren', 'ihrem', 'ihres', 'euch', 'euer', 'uns',
    # conjonctions
    'und', 'oder', 'aber', 'ob',
    # prépositions
    'in', 'im', 'an', 'am', 'auf', 'aus', 'über', 'unter', 'ohne',
    # particules
    'auch',
}))

#: Déterminants / articles (classe fermée) : la frontière glottale
#: devant le NOM qui suit l'article est le cœur catégorique du
#: Glottalversatz → niveau MINIMAL (« ein Apfel », « das ist
#: ein Ei »). Devant tout autre mot lexical à initiale vocalique :
#: STANDARD. ``careful`` = hyperarticulation : la frontière
#: s'applique aussi devant les mots-outils (plus d'exemption).
_DETERMINERS: FrozenSet[str] = frozenset({
    'der', 'die', 'das', 'den', 'dem', 'des',
    'ein', 'eine', 'einen', 'einem', 'einer', 'eines',
    'kein', 'keine', 'keinen', 'keinem', 'keiner', 'keines',
    'mein', 'meine', 'dein', 'deine', 'sein', 'seine',
    'ihr', 'ihre', 'unser', 'unsere', 'euer', 'eure',
    'dieser', 'diese', 'dieses', 'jeder', 'jede', 'jedes',
    'welcher', 'welche', 'welches', 'alle', 'mancher',
})


def _starts_with_vowel(tok2: str) -> bool:
    """W2 commence par une voyelle SAMPA (attaque vocalique)."""
    if not tok2:
        return False
    first = _token_keys(tok2.split('.')[0])
    return bool(first) and first[0] in _TOK_VOWELS


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


# ===========================================================================
# 2. Découpage du texte (miroir frais des conventions de g2p_de :
#    phrase [.!?;:]+ → '|', virgule → ' ', mots [A-Za-zÄÖÜäöüß]+)
# ===========================================================================

_SENT_SPLIT = re.compile(r'[.!?;:]+\s*')
_COMMA_SPLIT = re.compile(r'\s*[,–—]\s*')
_WORD_SPLIT = re.compile(r"[A-Za-zÄÖÜäöüß]+")
_GAP_SENT = re.compile(r'[.!?;:]')
_GAP_COMMA = re.compile(r'[,–—]')


def _norm(text: str) -> str:
    """NFC, apostrophes typographiques, strip (miroir minimal)."""
    text = unicodedata.normalize('NFC', text or '')
    return text.replace('’', "'").strip()


# ===========================================================================
# 3. Oracle : per-word du g2p actif (identité)
# ===========================================================================

def liaison_oracle(word: str, g2p: G2PCallable,
                   _cache: Optional[Dict[str, str]] = None) -> str:
    """Token SAMPA d'un mot : per-word du g2p actif (lexique →
    exceptions → règles), mesuré exact sur clone (« ein » → ``ajn``,
    « Apfel » → ``a.pf@l``, « esse » → ``E.s@``) : l'oracle est
    l'identité — la symétrie de l'architecture est conservée."""
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
        self.kind = kind          # 'glottal' (frontière de mot)
        self.insert = insert      # ' ' (frontière de mot moteur)
        self.tok1, self.tok2 = tok1, tok2


def _decide(w1: str, w2: str, tok1: str, tok2: str,
            include_function_words: bool = False
            ) -> Optional[Tuple[str, str]]:
    """(kind, insert) si la paire (W1, W2) porte un Glottalversatz,
    sinon None : W2 à initiale vocalique (token) ET W2 mot LEXICAL
    (hors classe fermée des mots-outils) → ('glottal', ' ').

    ``include_function_words`` (niveau ``careful``,
    hyperarticulation) : la frontière s'applique aussi devant
    les mots-outils — l'exemption est levée.
    """
    if not tok1 or not tok2:
        return None
    if w2.lower() in _GLOTTAL_EXEMPT \
            and not include_function_words:
        return None
    if _starts_with_vowel(tok2):
        return ('glottal', ' ')
    return None


def _pair_level(w1: str, decision: Tuple[str, str]) -> int:
    """Niveau minimal d'application de la règle qui a tiré."""
    return (LEVEL_MINIMAL if w1.lower() in _DETERMINERS
            else LEVEL_STANDARD)


def _decide_level(w1: str, w2: str, tok1: str, tok2: str,
                  level: str = None) -> Optional[Tuple[str, str]]:
    """Décision v3 FILTRÉE par le niveau de couverture covtl-sandhi."""
    rank = _rank(level)
    decision = _decide(
        w1, w2, tok1, tok2,
        include_function_words=(rank >= LEVEL_CAREFUL))
    if decision and _pair_level(w1, decision) <= rank:
        return decision
    return None


def plan_pairs(text: str, g2p: G2PCallable, level: str = None
               ) -> List[Tuple[List[str], List[Optional[_Pair]]]]:
    """Plan des paires, PHRASE par PHRASE (miroir du ' | ' du SAMPA).

    Retourne une liste de phrases ; chaque phrase est une liste de
    parties (virgules) ; chaque partie est (mots, paires_par_index) —
    ``paires[k]`` décrit la paire (mot k, mot k+1) si frontière
    glottale, None sinon. Le dernier slot de chaque partie est None
    (une virgule est déjà une frontière).

    ``level`` (covtl-sandhi) : filtre de COUVERTURE monotone —
    ``None``/``'standard'`` = comportement v3 exact,
    ``'minimal'`` = frontière après article/déterminant seule,
    ``'careful'`` = + devant les mots-outils (hyperarticulation).
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


# ===========================================================================
# 5. Mode PRE — aucune graphie ne code le coup de glotte
# ===========================================================================

def apply_liaison_pre(text: str, g2p: G2PCallable,
                      warnings: Optional[list] = None,
                      level: str = None) -> str:
    """Mode ``pre`` : INACTIF pour l'allemand (no-op documenté).

    Aucune graphie allemande ne code le Glottalversatz — ni
    respelling (le coup de glotte n'est pas une lettre), ni
    alternance (pas d'équivalent de y→e). Le seul encodage disponible
    est phonétique (frontière de mot dans le SAMPA), ce qui est
    précisément le travail des modes ``g2p``/``post``. Un
    avertissement est émis par frontière candidate pour que le mode
    pre reste observable (et comparable entre langues)."""
    own = warnings is None
    if own:
        warnings = []
    text = _norm(text)
    if not text:
        return text
    cache: Dict[str, str] = {}
    spans = [(m.start(), m.end(), m.group(0))
             for m in _WORD_SPLIT.finditer(text)]
    for k in range(len(spans) - 1):
        s1, e1, w1 = spans[k]
        s2, e2, w2 = spans[k + 1]
        gap = text[e1:s2]
        if _GAP_SENT.search(gap) or _GAP_COMMA.search(gap):
            continue
        tok1 = liaison_oracle(w1, g2p, cache)
        tok2 = liaison_oracle(w2, g2p, cache)
        if _decide_level(w1, w2, tok1, tok2, level):
            warnings.append(
                f"liaison-de pre: aucun encodage orthographique du "
                f"Glottalversatz devant {w2!r} — utiliser les modes "
                f"g2p ou post")
    return text


# ===========================================================================
# 6. Modes G2P / POST — insertion de la frontière de mot
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
    """Insère les frontières glottales dans un SAMPA déjà produit.

    Devant le slot d'un mot lexical à initiale vocalique, le lien
    syllabique « . » du g2p est remplacé par un ESPACE (frontière de
    mot native du moteur = ré-articulation). Un gap qui n'est pas
    « . » (espace déjà présent, « % », « | », virgule) est laissé
    tel quel — jamais d'édition à travers une pause.

    token_view / replace_tokens : symétrie architecturale avec les
    patchs fr/it/es/pt — l'oracle allemand étant l'identité, les deux
    vues coïncident et l'édition (un seul caractère par frontière)
    ne dépend pas du drapeau.
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
        warnings.append('liaison-de: structure SAMPA inattendue — no-op')
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
            warnings.append('liaison-de: alignement SAMPA échoué — '
                            'phrase laissée inchangée')
        out_sentences.append(merged)
    return ' | '.join(out_sentences)


def _merge_sentence(sent: str, words: List[str],
                    pairs: List[Optional[_Pair]],
                    g2p: G2PCallable) -> Tuple[str, bool]:
    """Aligne les tokens de la phrase puis remplace les liens '.'

    1. alignement séquentiel : chaque mot (token non vide) occupe un
       slot délimité par '.' / ' ' ; l'alignement doit consommer la
       phrase exactement (reste vide hors '%').
    2. frontières : de droite à gauche, le gap '.' devant le slot de
       chaque mot à frontière glottale devient ' ' (les insertions à
       droite ne décalent pas les offsets à gauche)."""
    cache: Dict[str, str] = {}

    def view(w: str) -> str:
        return liaison_oracle(w, g2p, cache)

    # 1. slots
    slot_by_word: Dict[int, Tuple[int, int]] = {}
    pos = 0
    for wi, w in enumerate(words):
        tok = view(w)
        if not tok:
            continue
        idx = _find_slot(sent, tok, pos)
        if idx < 0:
            return sent, False
        slot_by_word[wi] = (idx, idx + len(tok))
        pos = idx + len(tok)
    if sent[pos:].strip(' %'):
        return sent, False

    # 2. frontières glottales : '.' → ' ' devant le slot du mot droit
    out = sent
    for k in range(len(words) - 2, -1, -1):
        pair = pairs[k] if k < len(pairs) else None
        if pair is None:
            continue
        s2 = slot_by_word.get(k + 1)
        if s2 is None or s2[0] == 0:
            continue
        if out[s2[0] - 1] == '.':
            out = out[:s2[0] - 1] + ' ' + out[s2[0]:]
    return out, True


def liaison_g2p(text: str, g2p: G2PCallable,
                warnings: Optional[list] = None,
                level: str = None) -> str:
    """Mode ``g2p`` : passerelle allemande consciente des frontières.

    Le g2p de base produit d'abord le SAMPA (bit-identique sans
    frontière candidate), puis les frontières glottales sont posées
    (mode post) — l'oracle étant l'identité, la voie architecturale
    g2p/post du framework aboutit à la même édition."""
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
    La frontière glottale est portée par le slot DROIT, comme
    un ESPACE de tête (frontière de mot native du moteur) :
    ``('ein', 'a.pf@l')`` → ``('ajn', ' a.pf@l')``.
    """
    decision = _decide_level(w1, w2, tok1, tok2, level)
    if not decision:
        return None
    return (tok1, ' ' + tok2)

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
