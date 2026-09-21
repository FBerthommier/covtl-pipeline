# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
chunking.py
===========
Syntactic breathing (expressive prosody, v1.0.8 — option, default OFF).

Splits a sentence into *breath groups* and inserts a short pause at
each boundary, so that no chain of coarticulated words exceeds
``max_chain_words`` (default 5). Without this splitting, the g2p
connects all words of an unpunctuated sentence with ``.`` (v1.0.2
coarticulation): a long phrase becomes ONE unintelligible syllabic
chain lasting several seconds.

DOCUMENTED LEXICAL HEURISTIC — this is NOT a syntactic parser.
The chunking operates on orthographic words (before g2p) with three
rules by order of priority (see docs/PROMPT_prosodie_expressivite.md
§3.1 — the archived design specification, in French):

  1. already-marked boundaries: commas / semicolons / colons / dashes
     (the g2p already converts them to pauses);
  2. boundary function words: coordinating and subordinating
     conjunctions, relative pronouns, connectives → pause BEFORE the
     introduced block (30–50 function-word dictionaries per language,
     typical coverage ~80 % of useful boundaries);
  3. hard limit: any boundary-free run of words is split into
     near-equal parts so that none exceeds ``max_chain_words`` words
     (7 words with max=5 → 4+3); when the boundary falls on the start
     of a prepositional group it is all the more natural;
  4. no pause at an impossible spot: a final function word
     (determiner, preposition, auxiliary) is never left at the end of
     a block when it can be absorbed by the next one (the "dangling
     word" repair pass), and the hard limit stays strict.

References (prosodic hierarchy, juncture): Selkirk (1984), Nespor &
Vogel (1986); contour typology: Jun (2005, 2014).

The module depends on no other module of the package: it is usable
standalone (tests, tooling) and is consumed by
:mod:`vtl_synth.utils.prosody_f0`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Set, Tuple

# ===========================================================================
# Punctuation — exact mirror of the g2p conventions
# ===========================================================================
# Sentence: [.!?;:]+ → '|' (long pause); comma/dash → short pause.
SENT_SPLIT_RE = re.compile(r'[.!?;:]+\s*')
COMMA_SPLIT_RE = re.compile(r'\s*[,–—]\s*')

# Per-language word regexes — mirror of the g2p ``_WORD_RE`` patterns
# (g2p.py, g2p_fr_legacy.py, g2p_es/de/it/pt.py). Equivalence is
# enforced by the non-regression tests (the expressive plan re-counts
# the tokens produced by the g2p and falls back to the monotone
# declination on any mismatch).
WORD_RES: Dict[str, re.Pattern] = {
    'en': re.compile(r"[A-Za-z']+"),
    'fr': re.compile(r"[A-Za-zÀ-ÿ'’]+"),
    'es': re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"),
    'de': re.compile(r"[A-Za-zÄÖÜäöüß]+"),
    'it': re.compile(r"[A-Za-zÀÈÉÌÒÙàèéìòóù]+"),
    'pt': re.compile(r"[A-Za-zÁÀÂÃÇÉÊÍÓÔÕÚáàâãçéêíóôõú]+"),
}

# ===========================================================================
# Per-language function-word dictionaries
# ===========================================================================
# Each language provides:
#   boundary_before : the pause is placed BEFORE this word (conjunctions,
#                     relatives, connectives);
#   bigrams         : (w1, w2) pairs acting as one connective
#                     ("parce que", "so that") — pause before w1;
#   never_start     : words that should not REMAIN at the end of a block
#                     (determiners, prepositions, auxiliaries, clitic
#                     pronouns) — repair pass;
#   prepositions    : for the hard limit, a cut at the start of a
#                     prepositional group is preferred;
#   unaccentable    : words that never carry a pitch accent
#                     (consumed by prosody_f0).
#
# Lexical choices: the 30–50 most frequent function words per language
# (documented heuristic, not a grammar).

_CHUNK_EN: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'and', 'or', 'but', 'nor', 'so', 'yet',
        # subordination / complementizers
        'because', 'although', 'though', 'while', 'when', 'whenever',
        'if', 'unless', 'since', 'after', 'before', 'until', 'once',
        'whereas', 'whether',
        # relatives
        'that', 'which', 'who', 'whom', 'whose', 'where', 'why',
        # connectives
        'however', 'therefore', 'moreover', 'instead', 'then',
    },
    'bigrams': {('so', 'that'), ('even', 'though'), ('as', 'if'),
                ('in', 'order'), ('so', 'as')},
    'never_start': {
        # determiners / quantifiers
        'the', 'a', 'an', 'this', 'that', 'these', 'those', 'my',
        'your', 'his', 'her', 'its', 'our', 'their', 'some', 'any',
        'each', 'every', 'no', 'all', 'both', 'several', 'many',
        'few', 'one', 'two', 'three',
        # prepositions
        'of', 'to', 'in', 'on', 'at', 'for', 'with', 'from', 'by',
        'as', 'into', 'onto', 'over', 'under', 'about', 'between',
        'during', 'without', 'within', 'across', 'through', 'near',
        'above', 'below', 'off', 'up', 'down', 'out',
        # auxiliaries / copula / negation
        'is', 'are', 'was', 'were', 'am', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'can', 'could', 'should', 'shall', 'may', 'might', 'must',
        'not', "n't", 'never',
    },
    'prepositions': {
        'of', 'to', 'in', 'on', 'at', 'for', 'with', 'from', 'by',
        'into', 'onto', 'over', 'under', 'about', 'between', 'during',
        'without', 'within', 'across', 'through', 'near', 'above',
        'below',
    },
    'unaccentable': {
        'the', 'a', 'an', 'of', 'to', 'in', 'on', 'at', 'for', 'with',
        'from', 'by', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
        'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'can', 'could', 'should', 'that', 'which',
        'who', 'this', 'these', 'those', 'it', 'its', 'there',
    },
}

_CHUNK_FR: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'et', 'ou', 'mais', 'donc', 'or', 'ni', 'car',
        # subordination
        'si', 'comme', 'lorsque', 'quand', 'puisque', 'quoique',
        'avant', 'après', 'pendant', 'dès',
        # relatives
        'qui', 'que', 'quoi', 'dont', 'où', 'lequel', 'laquelle',
        'lesquels', 'lesquelles',
        # connectives
        'alors', 'cependant', 'toutefois', 'pourtant', 'ensuite',
        'enfin', 'aussi',
    },
    'bigrams': {('parce', 'que'), ('bien', 'que'), ('alors', 'que'),
                ('pour', 'que'), ('afin', 'que'), ('avant', 'que'),
                ('après', 'que'), ('pendant', 'que')},
    'never_start': {
        # determiners
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'au', 'aux',
        'ce', 'cet', 'cette', 'ces', 'mon', 'ma', 'mes', 'ton', 'ta',
        'tes', 'son', 'sa', 'ses', 'notre', 'nos', 'votre', 'vos',
        'leur', 'leurs', 'quelque', 'plusieurs',
        # prepositions
        'de', 'à', 'en', 'dans', 'sur', 'sous', 'par', 'avec', 'sans',
        'pour', 'chez', 'vers', 'entre', 'depuis', 'jusque',
        # clitics / auxiliaries / negation
        'je', 'tu', 'il', 'elle', 'on', 'nous', 'vous', 'ils', 'elles',
        'me', 'te', 'se', 'lui', 'leur', 'y', "l'", "d'", "qu'", "n'",
        'est', 'sont', 'était', 'étaient', 'été', 'être', 'a', 'ont',
        'avait', 'avaient', 'avoir', 'ne', 'pas', 'plus', 'très',
    },
    'prepositions': {
        'de', 'à', 'en', 'dans', 'sur', 'sous', 'par', 'avec', 'sans',
        'pour', 'chez', 'vers', 'entre', 'depuis',
    },
    'unaccentable': {
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'au', 'aux', 'de',
        'à', 'en', 'dans', 'sur', 'par', 'avec', 'et', 'ou', 'mais',
        'que', 'qui', 'est', 'sont', 'être', 'avoir', 'je', 'tu', 'il',
        'elle', 'on', 'nous', 'vous', 'ce', 'cette', 'ces', 'pas',
        'plus', 'très',
    },
}

_CHUNK_ES: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'y', 'o', 'pero', 'sino',
        # subordination
        'porque', 'aunque', 'cuando', 'si', 'como', 'mientras',
        'pues', 'según', 'aunque', 'apenas',
        # relatives
        'que', 'quien', 'quienes', 'cual', 'cuales', 'donde', 'cuyo',
        # connectives
        'entonces', 'además', 'también', 'tampoco',
    },
    'bigrams': {('para', 'que'), ('así', 'que'), ('por', 'lo'),
                ('sin', 'embargo')},
    'never_start': {
        # determiners
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'lo',
        'mi', 'tu', 'su', 'nuestro', 'nuestra', 'vuestro', 'vuestra',
        'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
        # prepositions
        'de', 'a', 'en', 'con', 'por', 'para', 'sin', 'sobre',
        'entre', 'hacia', 'desde', 'hasta',
        # clitics / auxiliaries / negation
        'me', 'te', 'se', 'le', 'les', 'nos', 'os', 'lo',
        'es', 'son', 'era', 'eran', 'fue', 'fueron', 'sea', 'sean',
        'ha', 'han', 'he', 'hemos', 'había', 'habían', 'ser', 'estar',
        'no', 'muy',
    },
    'prepositions': {
        'de', 'a', 'en', 'con', 'por', 'para', 'sin', 'sobre',
        'entre', 'hacia', 'desde', 'hasta',
    },
    'unaccentable': {
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de',
        'a', 'en', 'con', 'por', 'para', 'y', 'o', 'pero', 'que',
        'es', 'son', 'ser', 'estar', 'me', 'te', 'se', 'le', 'no',
        'muy', 'este', 'esta',
    },
}

_CHUNK_DE: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'und', 'oder', 'aber', 'sondern',
        # subordination
        'weil', 'dass', 'wenn', 'als', 'ob', 'wie', 'obwohl', 'da',
        'denn', 'damit', 'bevor', 'nachdem', 'während', 'bis', 'falls',
        # relatives ('der/die/das' excluded: articles in the vast
        # majority of contexts — systematic false positives)
        'welcher', 'welche', 'welches', 'wessen', 'wem', 'wo',
        # connectives
        'doch', 'jedoch', 'deshalb', 'daher', 'außerdem', 'dann',
    },
    'bigrams': {('zum', 'beispiel'), ('so', 'dass'), ('an', 'statt')},
    'never_start': {
        # determiners / articles
        'ein', 'eine', 'einen', 'einem', 'einer', 'eines', 'dem',
        'den', 'des', 'mein', 'meine', 'dein', 'deine', 'sein', 'seine',
        'ihr', 'ihre', 'unser', 'unsere', 'dieser', 'diese', 'dieses',
        # prepositions
        'in', 'an', 'auf', 'mit', 'von', 'zu', 'zur', 'zum', 'bei',
        'nach', 'aus', 'für', 'über', 'unter', 'vor', 'durch', 'gegen',
        'um', 'ohne', 'bis', 'um',
        # clitics / auxiliaries / negation
        'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'mich', 'dich',
        'ihm', 'uns', 'nicht', 'kein', 'keine', 'ist', 'sind', 'war',
        'waren', 'bin', 'haben', 'hat', 'hatte', 'sein', 'haben',
    },
    'prepositions': {
        'in', 'an', 'auf', 'mit', 'von', 'zu', 'zur', 'zum', 'bei',
        'nach', 'aus', 'für', 'über', 'unter', 'vor', 'durch', 'gegen',
        'ohne',
    },
    'unaccentable': {
        'der', 'die', 'das', 'ein', 'eine', 'einen', 'dem', 'den',
        'des', 'in', 'an', 'auf', 'mit', 'von', 'zu', 'und', 'oder',
        'aber', 'ist', 'sind', 'war', 'nicht', 'kein', 'keine', 'ich',
        'du', 'er', 'sie', 'es', 'wir', 'dieser', 'diese',
    },
}

_CHUNK_IT: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'e', 'o', 'ma', 'però',
        # subordination
        'perché', 'se', 'come', 'mentre', 'quando', 'poiché', 'siccome',
        'affinché', 'benché', 'dato',
        # relatives
        'che', 'chi', 'cui', 'quale', 'quali', 'dove',
        # connectives
        'dunque', 'quindi', 'inoltre', 'allora', 'anche',
    },
    'bigrams': {('per', 'quanto'), ('dato', 'che'), ('per', 'ciò')},
    'never_start': {
        # determiners
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'mi',
        'tu', 'su', 'mio', 'mia', 'tuo', 'tua', 'suo', 'sua', 'nostro',
        'nostra', 'questo', 'questa', 'questi', 'queste',
        # prepositions (preposition + article forms included)
        'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
        'senza', 'sotto', 'sopra', 'del', 'della', 'dei', 'delle',
        'al', 'alla', 'ai', 'alle', 'nel', 'nella', 'sul', 'sulla',
        # clitics / auxiliaries / negation
        'mi', 'ti', 'si', 'ci', 'vi', 'lo', 'gli',
        'è', 'sono', 'era', 'erano', 'fosse', 'ha', 'hanno', 'ho',
        'abbiamo', 'aveva', 'avevano', 'essere', 'non', 'molto',
    },
    'prepositions': {
        'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
        'senza', 'del', 'della', 'al', 'alla', 'nel', 'nella', 'sul',
        'sulla',
    },
    'unaccentable': {
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'una', 'di', 'a',
        'da', 'in', 'con', 'su', 'per', 'e', 'o', 'ma', 'che', 'è',
        'sono', 'essere', 'mi', 'ti', 'si', 'non', 'questo', 'questa',
    },
}

_CHUNK_PT: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'e', 'ou', 'mas', 'porém',
        # subordination
        'porque', 'pois', 'quando', 'se', 'como', 'enquanto', 'embora',
        'caso', 'logo',
        # relatives
        'que', 'quem', 'onde', 'qual', 'quais', 'cujo', 'cuja',
        # connectives
        'então', 'também', 'contudo',
    },
    'bigrams': {('para', 'que'), ('já', 'que'), ('por', 'isso'),
                ('no', 'entanto')},
    'never_start': {
        # determiners
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'meu', 'minha',
        'teu', 'tua', 'seu', 'sua', 'nosso', 'nossa', 'este', 'esta',
        'estes', 'estas', 'esse', 'essa', 'isso',
        # prepositions
        'de', 'a', 'em', 'com', 'por', 'para', 'sem', 'sobre', 'entre',
        'até', 'desde', 'após', 'do', 'da', 'dos', 'das', 'no', 'na',
        'nos', 'nas', 'ao', 'à', 'aos', 'às',
        # clitics / auxiliaries / negation
        'me', 'te', 'se', 'lhe', 'nos', 'vos', 'é', 'são', 'era',
        'eram', 'foi', 'foram', 'ser', 'estar', 'tem', 'têm', 'ter',
        'não', 'muito',
    },
    'prepositions': {
        'de', 'a', 'em', 'com', 'por', 'para', 'sem', 'sobre', 'entre',
        'até', 'desde', 'do', 'da', 'no', 'na', 'ao', 'à',
    },
    'unaccentable': {
        'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'em', 'com', 'por',
        'para', 'e', 'ou', 'mas', 'que', 'é', 'são', 'ser', 'me',
        'te', 'se', 'não', 'muito', 'este', 'esta',
    },
}

CHUNK_WORDS: Dict[str, Dict[str, Set[str]]] = {
    'en': _CHUNK_EN,
    'fr': _CHUNK_FR,
    'es': _CHUNK_ES,
    'de': _CHUNK_DE,
    'it': _CHUNK_IT,
    'pt': _CHUNK_PT,
}


def _norm(word: str) -> str:
    """Normalization for lexical lookup (lowercase, apostrophes)."""
    return word.lower().replace('’', "'").strip()


def _words_of(text: str, lang: str) -> List[str]:
    """Orthographic words according to the language's mirror regex."""
    return WORD_RES.get(lang, WORD_RES['en']).findall(text)


# ===========================================================================
# Chunking
# ===========================================================================

def chunk_word_list(words: Sequence[str],
                    lang: str,
                    max_chain: int = 5) -> List[List[str]]:
    """Split a word list (no punctuation) into breath groups.

    Three passes:

      1. lexical bounding (rule 2): a boundary before every
         conjunction / connective / relative, treating two-word
         connectives ("parce que", "so that") as an inseparable block;
      2. balanced hard limit (rule 3): any boundary-free run longer
         than ``max_chain`` is split into near-equal parts (a 7-word
         run with max=5 yields 4+3, not 5+2) — when the boundary falls
         on the start of a prepositional group it is all the more
         natural;
      3. "dangling word" repair (rule 4): a final function word
         (determiner, preposition, auxiliary, clitic) is absorbed by
         the next block whenever the hard limit is not violated.

    No block exceeds ``max_chain`` words (a one-word block remains
    possible).
    """
    spec = CHUNK_WORDS.get(lang, CHUNK_WORDS['en'])
    boundary = spec['boundary_before']
    bigrams = spec['bigrams']
    never_start = spec['never_start']

    # --- pass 1: word runs between lexical boundaries -----------------
    runs: List[List[str]] = [[]]
    i = 0
    while i < len(words):
        wl = _norm(words[i])
        nxt = _norm(words[i + 1]) if i + 1 < len(words) else ''
        if runs[-1] and (wl, nxt) in bigrams:
            runs.append([])                       # boundary before w1
        elif runs[-1] and wl in boundary and not (
                i > 0 and (_norm(words[i - 1]), wl) in bigrams
        ):
            runs.append([])                       # boundary before wl
        runs[-1].append(words[i])
        i += 1

    # --- pass 2: hard limit, balanced split ----------------------------
    chunks: List[List[str]] = []
    for run in runs:
        if len(run) <= max_chain or len(run) <= 1:
            chunks.append(list(run))
            continue
        k = -(-len(run) // max_chain)             # ceil, ≥ 2 parts
        base, extra = divmod(len(run), k)
        start = 0
        for j in range(k):
            size = base + (1 if j < extra else 0)
            chunks.append(list(run[start:start + size]))
            start += size

    # --- pass 3: dangling function words -------------------------------
    moved = True
    while moved:
        moved = False
        for k in range(len(chunks) - 1):
            while (len(chunks[k]) > 1
                   and _norm(chunks[k][-1]) in never_start
                   and len(chunks[k + 1]) < max_chain):
                chunks[k + 1].insert(0, chunks[k].pop())
                moved = True
    return [c for c in chunks if c]


def chunk_part(part: str, lang: str,
               max_chain: int = 5) -> List[List[str]]:
    """Split a punctuation-free fragment (a "comma-free part")."""
    words = _words_of(part, lang)
    if not words:
        return []
    return chunk_word_list(words, lang, max_chain=max_chain)


def chunk_sentence(sentence: str, lang: str,
                   max_chain: int = 5) -> List[List[List[str]]]:
    """One sentence (no final punctuation) → blocks, grouped by
    comma-separated part (each sub-list = the blocks of one part).

    The "parts" structure is kept so that the SAMPA assembly mirrors
    the g2p conventions: comma → short pause (' '), breath boundary →
    '%' marker (see prosody_f0).
    """
    out: List[List[List[str]]] = []
    for part in COMMA_SPLIT_RE.split(sentence):
        part = part.strip()
        if not part:
            continue
        blocks = chunk_part(part, lang, max_chain=max_chain)
        if blocks:
            out.append(blocks)
    return out


def split_sentences(text: str) -> List[str]:
    """Raw text → sentence list (mirror of the g2p punctuation)."""
    return [s.strip() for s in SENT_SPLIT_RE.split(text) if s.strip()]


def chunk_text(text: str, lang: str,
               max_chain: int = 5) -> List[List[List[List[str]]]]:
    """Full text → sentences → parts (commas) → breath groups."""
    return [chunk_sentence(s, lang, max_chain=max_chain)
            for s in split_sentences(text)]


__all__ = [
    'CHUNK_WORDS', 'WORD_RES', 'SENT_SPLIT_RE', 'COMMA_SPLIT_RE',
    'chunk_word_list', 'chunk_part', 'chunk_sentence', 'split_sentences',
    'chunk_text',
]
