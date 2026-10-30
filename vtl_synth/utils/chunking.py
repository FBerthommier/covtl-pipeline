# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
chunking.py
===========
Respiration syntaxique (expressive prosody, v1.0.8 — option, défaut OFF).

Découpe une phrase en *groupes de souffle* (breath groups) et insère
une pause courte à chaque frontière, pour qu'aucune chaîne de mots
coarticulés ne dépasse ``max_chain_words`` (défaut 5). Sans ce
découpage, le g2p relie tous les mots d'une phrase sans ponctuation
par ``.`` (coarticulation v1.0.2) : une phrase longue devient UNE
chaîne syllabique inintelligible de plusieurs secondes.

HEURISTIQUE LEXICALE AVOUÉE — ceci n'est PAS un parseur syntaxique.
Le chunking opère sur les mots orthographiques (avant g2p) avec trois
règles par ordre de priorité (cf. docs/PROMPT_prosodie_expressivite.md
§3.1) :

  1. frontières déjà marquées : virgules / points-virgules /
     deux-points / tirets (le g2p les convertit déjà en pause) ;
  2. mots fonctionnels de frontière : conjonctions de coordination et
     de subordination, pronoms relatifs, connecteurs → pause AVANT le
     bloc introduit (dictionnaires de 30–50 mots-outils par langue,
     couverture typique ~80 % des frontières utiles) ;
  3. limite dure : toute course de mots sans frontière est découpée
     en parts équilibrées de sorte qu'aucune ne dépasse
     ``max_chain_words`` mots (7 mots avec max=5 → 4+3) ; si la
     frontière tombe sur le début d'un groupe prépositionnel, elle
     est d'autant plus naturelle ;
  4. pas de pause à un endroit impossible : un mot-outil final
     (déterminant, préposition, auxiliaire) n'est jamais laissé en
     fin de bloc lorsqu'il peut rattraper le bloc suivant (passe de
     correction « mot han-gant »), et la limite dure reste stricte.

Références (hiérarchie prosodique, joncture) : Selkirk (1984), Nespor
& Vogel (1986) ; typologie des contours : Jun (2005, 2014).

Le module ne dépend d'aucun autre module du paquet : il est utilisable
seul (tests, outillage) et est consommé par
:mod:`vtl_synth.utils.prosody_f0`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Set, Tuple

# ===========================================================================
# Ponctuation — miroir exact des conventions des g2p
# ===========================================================================
# Phrase : [.!?;:]+ → '|' (pause longue) ; virgule/tiret → pause courte.
SENT_SPLIT_RE = re.compile(r'[.!?;:]+\s*')
COMMA_SPLIT_RE = re.compile(r'\s*[,–—]\s*')

# Expressions régulières de mot par langue — miroir des ``_WORD_RE`` des
# g2p (g2p.py, g2p_fr_legacy.py, g2p_es/de/it/pt.py). L'équivalence est
# vérifiée par la non-régression (le plan expressif recompte les tokens
# produits par le g2p et retombe sur la déclinaison monotone en cas
# d'écart).
WORD_RES: Dict[str, re.Pattern] = {
    'en': re.compile(r"[A-Za-z']+"),
    'fr': re.compile(r"[A-Za-zÀ-ÿ'’]+"),
    'es': re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"),
    'de': re.compile(r"[A-Za-zÄÖÜäöüß]+"),
    'it': re.compile(r"[A-Za-zÀÈÉÌÒÙàèéìòóù]+"),
    'pt': re.compile(r"[A-Za-zÁÀÂÃÇÉÊÍÓÔÕÚáàâãçéêíóôõú]+"),
}

# ===========================================================================
# Dictionnaires de mots fonctionnels par langue
# ===========================================================================
# Chaque langue fournit :
#   boundary_before : la pause se place AVANT ce mot (conjonctions,
#                     relatifs, connecteurs) ;
#   bigrams         : paires (w1, w2) jouant le rôle de connecteur
#                     (« parce que », « so that ») — pause avant w1 ;
#   never_start     : mots qui ne devraient pas RESTER en fin de bloc
#                     (déterminants, prépositions, auxiliaires,
#                     pronoms clitiques) — passe de correction ;
#   prepositions    : pour la limite dure, la coupure privilégie le
#                     début d'un groupe prépositionnel ;
#   unaccentable    : mots qui ne portent jamais l'accent de hauteur
#                     (consommé par prosody_f0).
#
# Choix lexicaux : les 30–50 mots-outils les plus fréquents par langue
# (heuristique documentée, pas une grammaire).

_CHUNK_EN: Dict[str, Set[str]] = {
    'boundary_before': {
        # coordination
        'and', 'or', 'but', 'nor', 'so', 'yet',
        # subordination / complétives
        'because', 'although', 'though', 'while', 'when', 'whenever',
        'if', 'unless', 'since', 'after', 'before', 'until', 'once',
        'whereas', 'whether',
        # relatifs
        'that', 'which', 'who', 'whom', 'whose', 'where', 'why',
        # connecteurs
        'however', 'therefore', 'moreover', 'instead', 'then',
    },
    'bigrams': {('so', 'that'), ('even', 'though'), ('as', 'if'),
                ('in', 'order'), ('so', 'as')},
    'never_start': {
        # déterminants / quantifieurs
        'the', 'a', 'an', 'this', 'that', 'these', 'those', 'my',
        'your', 'his', 'her', 'its', 'our', 'their', 'some', 'any',
        'each', 'every', 'no', 'all', 'both', 'several', 'many',
        'few', 'one', 'two', 'three',
        # prépositions
        'of', 'to', 'in', 'on', 'at', 'for', 'with', 'from', 'by',
        'as', 'into', 'onto', 'over', 'under', 'about', 'between',
        'during', 'without', 'within', 'across', 'through', 'near',
        'above', 'below', 'off', 'up', 'down', 'out',
        # auxiliaires / copule / négation
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
        # relatifs
        'qui', 'que', 'quoi', 'dont', 'où', 'lequel', 'laquelle',
        'lesquels', 'lesquelles',
        # connecteurs
        'alors', 'cependant', 'toutefois', 'pourtant', 'ensuite',
        'enfin', 'aussi',
    },
    'bigrams': {('parce', 'que'), ('bien', 'que'), ('alors', 'que'),
                ('pour', 'que'), ('afin', 'que'), ('avant', 'que'),
                ('après', 'que'), ('pendant', 'que')},
    'never_start': {
        # déterminants
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'au', 'aux',
        'ce', 'cet', 'cette', 'ces', 'mon', 'ma', 'mes', 'ton', 'ta',
        'tes', 'son', 'sa', 'ses', 'notre', 'nos', 'votre', 'vos',
        'leur', 'leurs', 'quelque', 'plusieurs',
        # prépositions
        'de', 'à', 'en', 'dans', 'sur', 'sous', 'par', 'avec', 'sans',
        'pour', 'chez', 'vers', 'entre', 'depuis', 'jusque',
        # clitiques / auxiliaires / négation
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
        # relatifs
        'que', 'quien', 'quienes', 'cual', 'cuales', 'donde', 'cuyo',
        # connecteurs
        'entonces', 'además', 'también', 'tampoco',
    },
    'bigrams': {('para', 'que'), ('así', 'que'), ('por', 'lo'),
                ('sin', 'embargo')},
    'never_start': {
        # déterminants
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'lo',
        'mi', 'tu', 'su', 'nuestro', 'nuestra', 'vuestro', 'vuestra',
        'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
        # prépositions
        'de', 'a', 'en', 'con', 'por', 'para', 'sin', 'sobre',
        'entre', 'hacia', 'desde', 'hasta',
        # clitiques / auxiliaires / négation
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
        # relatifs ('der/die/das' exclus : articles dans l'immense
        # majorité des contextes — faux positifs systématiques)
        'welcher', 'welche', 'welches', 'wessen', 'wem', 'wo',
        # connecteurs
        'doch', 'jedoch', 'deshalb', 'daher', 'außerdem', 'dann',
    },
    'bigrams': {('zum', 'beispiel'), ('so', 'dass'), ('an', 'statt')},
    'never_start': {
        # déterminants / articles
        'ein', 'eine', 'einen', 'einem', 'einer', 'eines', 'dem',
        'den', 'des', 'mein', 'meine', 'dein', 'deine', 'sein', 'seine',
        'ihr', 'ihre', 'unser', 'unsere', 'dieser', 'diese', 'dieses',
        # prépositions
        'in', 'an', 'auf', 'mit', 'von', 'zu', 'zur', 'zum', 'bei',
        'nach', 'aus', 'für', 'über', 'unter', 'vor', 'durch', 'gegen',
        'um', 'ohne', 'bis', 'um',
        # clitiques / auxiliaires / négation
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
        # relatifs
        'che', 'chi', 'cui', 'quale', 'quali', 'dove',
        # connecteurs
        'dunque', 'quindi', 'inoltre', 'allora', 'anche',
    },
    'bigrams': {('per', 'quanto'), ('dato', 'che'), ('per', 'ciò')},
    'never_start': {
        # déterminants
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'mi',
        'tu', 'su', 'mio', 'mia', 'tuo', 'tua', 'suo', 'sua', 'nostro',
        'nostra', 'questo', 'questa', 'questi', 'queste',
        # prépositions (article + préposition included)
        'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
        'senza', 'sotto', 'sopra', 'del', 'della', 'dei', 'delle',
        'al', 'alla', 'ai', 'alle', 'nel', 'nella', 'sul', 'sulla',
        # clitiques / auxiliaires / négation
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
        # relatifs
        'que', 'quem', 'onde', 'qual', 'quais', 'cujo', 'cuja',
        # connecteurs
        'então', 'também', 'contudo',
    },
    'bigrams': {('para', 'que'), ('já', 'que'), ('por', 'isso'),
                ('no', 'entanto')},
    'never_start': {
        # déterminants
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'meu', 'minha',
        'teu', 'tua', 'seu', 'sua', 'nosso', 'nossa', 'este', 'esta',
        'estes', 'estas', 'esse', 'essa', 'isso',
        # prépositions
        'de', 'a', 'em', 'com', 'por', 'para', 'sem', 'sobre', 'entre',
        'até', 'desde', 'após', 'do', 'da', 'dos', 'das', 'no', 'na',
        'nos', 'nas', 'ao', 'à', 'aos', 'às',
        # clitiques / auxiliaires / négation
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
    """Normalisation pour recherche lexicale (minuscules, apostrophes)."""
    return word.lower().replace('’', "'").strip()


def _words_of(text: str, lang: str) -> List[str]:
    """Mots orthographiques selon la regex miroir de la langue."""
    return WORD_RES.get(lang, WORD_RES['en']).findall(text)


# ===========================================================================
# Chunking
# ===========================================================================

def chunk_word_list(words: Sequence[str],
                    lang: str,
                    max_chain: int = 5) -> List[List[str]]:
    """Découpe une liste de mots (sans ponctuation) en groupes de souffle.

    Trois passes :

      1. bornage lexical (règle 2) : frontière avant chaque
         conjonction / connecteur / relatif, en traitant les
         connecteurs bisyllabiques (« parce que », « so that ») comme
         un bloc insécable ;
      2. limite dure équilibrée (règle 3) : toute course de mots sans
         frontière plus longue que ``max_chain`` est découpée en
         parts voisines de la même taille (une course de 7 mots avec
         max=5 donne 4+3, pas 5+2) — si la frontière tombe sur le
         début d'un groupe prépositionnel, elle est d'autant plus
         naturelle ;
      3. correction « mot han-gant » (règle 4) : un mot-outil final
         (déterminant, préposition, auxiliaire, clitique) rattrape le
         bloc suivant lorsque la limite dure n'est pas violée.

    Aucun bloc ne dépasse ``max_chain`` mots (un bloc d'un mot reste
    possible).
    """
    spec = CHUNK_WORDS.get(lang, CHUNK_WORDS['en'])
    boundary = spec['boundary_before']
    bigrams = spec['bigrams']
    never_start = spec['never_start']

    # --- passe 1 : courses de mots entre frontières lexicales --------
    runs: List[List[str]] = [[]]
    i = 0
    while i < len(words):
        wl = _norm(words[i])
        nxt = _norm(words[i + 1]) if i + 1 < len(words) else ''
        if runs[-1] and (wl, nxt) in bigrams:
            runs.append([])                       # frontière avant w1
        elif runs[-1] and wl in boundary and not (
                i > 0 and (_norm(words[i - 1]), wl) in bigrams
        ):
            runs.append([])                       # frontière avant wl
        runs[-1].append(words[i])
        i += 1

    # --- passe 2 : limite dure, découpe équilibrée --------------------
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

    # --- passe 3 : mots han-gants -------------------------------------
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
    """Découpe un fragment sans ponctuation (une « partie sans virgule »)."""
    words = _words_of(part, lang)
    if not words:
        return []
    return chunk_word_list(words, lang, max_chain=max_chain)


def chunk_sentence(sentence: str, lang: str,
                   max_chain: int = 5) -> List[List[List[str]]]:
    """Une phrase (sans ponctuation de fin) → blocs, groupés par partie
    séparée par virgule (chaque sous-liste = les blocs d'une partie).

    La structure « parties » est conservée pour que l'assemblage SAMPA
    reproduise la convention du g2p : virgule → pause courte (' '),
    frontière de souffle → marqueur '%' (cf. prosody_f0).
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
    """Phrase-texte → liste de phrases (miroir de la ponctuation g2p)."""
    return [s.strip() for s in SENT_SPLIT_RE.split(text) if s.strip()]


def chunk_text(text: str, lang: str,
               max_chain: int = 5) -> List[List[List[List[str]]]]:
    """Texte complet → phrases → parties (virgules) → blocs de souffle."""
    return [chunk_sentence(s, lang, max_chain=max_chain)
            for s in split_sentences(text)]


__all__ = [
    'CHUNK_WORDS', 'WORD_RES', 'SENT_SPLIT_RE', 'COMMA_SPLIT_RE',
    'chunk_word_list', 'chunk_part', 'chunk_sentence', 'split_sentences',
    'chunk_text',
]
