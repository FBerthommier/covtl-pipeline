# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_it.py
=========
Graphème-phonème italien : texte orthographique → SAMPA moteur.
Même architecture que ``g2p_fr.py`` (v2) :

  lexique externe (priorité absolue) → dictionnaire d'exceptions →
  prétraitement contextuel (s sonore intervocalique / devant
  consonne sonore) → table de règles (motif le plus long d'abord).

Lexique : ``vtl_synth/data/it_lexicon.tsv`` (Wikipron
``ita_latn_broad_filtered.tsv`` ; variable : ``$COVTL_IT_LEXICON``),
chargé par :mod:`vtl_synth.utils.lexicon_loader`.

Couverture graphémique : gn /ɲ/, gli /ʎ/ (+gli- final), c(e,i) /tʃ/,
g(e,i) /dʒ/, ch/gh (h muet), sc(e,i) /ʃ/, z /ts~dz/, doubles
consonnes (géminées, émises deux fois), diphtongues en glides.

Approximations documentées :
  * z → ``t s`` par défaut (zero/zona /dz/ passent par le lexique ou
    les exceptions) ; zz → géminée ``t t s`` ;
  * /ʎ/ → clé ``L``, /ɲ/ → ``J`` (inventaire moteur) ;
  * e/o non accentués → mi-femmes ``e``/``o`` (é→e, è→E, ò→O) ;
  * pas de raffinement vocalique par harmonicité (e atone /e/).
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

from vtl_synth.core.phonemes import keys_to_connected
from vtl_synth.utils.lexicon_loader import lexicon_for


# ===========================================================================
# Tokenisation (miroir de g2p_fr.py)
# ===========================================================================

_SENT_PUNCT_RE = re.compile(r'[.!?;:]+\s*')
_COMMA_RE = re.compile(r'\s*[,–—]\s*')
_WORD_RE = re.compile(r"[A-Za-zÀÈÉÌÒÙàèéìòóù]+")

_V = 'aeiouàèéìòóù'     # voyelles orthographiques


def _normalize_input(text: str) -> str:
    """NFC + apostrophes typographiques normalisés."""
    text = unicodedata.normalize('NFC', text)
    return text.replace('’', "'")


# ===========================================================================
# Exceptions (mots fréquents irréguliers pour les règles)
# ===========================================================================

_IT_EXCEPTIONS: dict = {
    # h initiale muette (formes du verbe avere)
    'ho': 'o', 'hai': 'a j', 'ha': 'a', 'hanno': 'a n o',
    # mots-outils
    'e': 'e', 'ed': 'e d', 'è': 'E', 'o': 'o', 'od': 'o d',
    'più': 'p j u', 'può': 'p w O', 'già': 'dZ a', 'giù': 'dZ u',
    'perché': 'p e R k e', 'poiché': 'p w O i k e',
    'comunque': 'k o m u n k w e', 'questo': 'k w e s t o',
    'quello': 'k w e l l o',
    # z sonore /dz/ initiale fréquente
    'zero': 'd z e R o', 'zona': 'd z o n a', 'zaino': 'd z a j n o',
    'zucchero': 'd z u k k e R o',
}


# ===========================================================================
# Prétraitement contextuel
# ===========================================================================

def _preprocess(word: str) -> str:
    """Normalisations contextuelles de l'orthographie italienne.

    s sonore /z/ : intervocalique ('casa') ou devant consonde sonore
    (sb, sd, sg, sl, sm, sn, sv… 'slavo'). Le placeholder SZ est
    traduit par la règle ('SZ', 'z').
    """
    word = re.sub(r'(?<=[' + _V + r'])s(?=[' + _V + r'])', 'SZ', word)
    word = re.sub(r'(?<!s)s(?=[bdglmnrvjw])', 'SZ', word)
    return word


# ===========================================================================
# Table de règles (motif le plus long d'abord)
# ===========================================================================

_IT_RULES: list = [
    # --- groupes avec glide contextuel (c/g + i atone + voyelle) ---
    ('cia', 'tS a'), ('cio', 'tS o'), ('ciu', 'tS u'),
    ('gia', 'dZ a'), ('gio', 'dZ o'), ('giu', 'dZ u'),
    ('glie', 'L e'), ('glia', 'L a'), ('glio', 'L o'),
    # --- digraphes / trigraphes ---
    ('ce', 'tS e'), ('ci', 'tS i'),
    ('ge', 'Z e'), ('gi', 'Z i'),
    ('sch', 's k'),        # scherno, scoglio → /sk/
    ('sci', 'S i'), ('sce', 'S e'),
    ('sc', 's k'),         # sca sco scu → /sk/
    ('gn', 'J'),
    ('ch', 'k'), ('gh', 'g'),
    ('gli', 'L i'),        # gli final ('figli') ; devant voyelle pris
                           # par les motifs 4 lettres ci-dessus
    ('gua', 'g w a'), ('guo', 'g w o'),
    ('qu', 'k w'),
    ('zz', 't t s'), ('tz', 't s'), ('z', 't s'),
    ('h', ''),             # h muet résiduel (hors ch/gh déjà pris)
    # --- hiatus accentués (voyelle accentuée pleine) ---
    ('í', 'i'), ('ú', 'u'),
    # --- diphtongues (i/u atones devant voyelle → glide) ---
    ('ia', 'j a'), ('ie', 'j e'), ('io', 'j o'), ('iu', 'j u'),
    ('ua', 'w a'), ('ue', 'w e'), ('uo', 'w o'), ('ui', 'w i'),
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'), ('ou', 'o w'),
    # --- accents → voyelles ---
    ('à', 'a'), ('è', 'E'), ('é', 'e'), ('ì', 'i'), ('ò', 'O'),
    ('ù', 'u'),
    # --- lettres simples ---
    ('SZ', 'z'),
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('b', 'b'), ('c', 'k'), ('d', 'd'), ('f', 'f'), ('g', 'g'),
    ('l', 'l'), ('m', 'm'), ('n', 'n'), ('p', 'p'), ('r', 'R'),
    ('s', 's'), ('t', 't'), ('v', 'v'),
]

_IT_RULES_SORTED: list = sorted(_IT_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Conversion mot → clés
# ===========================================================================

def _word_to_keys(word: str, warnings: list) -> list:
    """Convertit un mot italien en liste de clés SAMPA moteur."""
    word_lc = word.lower().replace('’', "'")

    # (0) lexique externe — priorité absolue
    lex_keys = lexicon_for('it').get(word_lc)
    if lex_keys:
        return list(lex_keys)

    # (a) exceptions
    if word_lc in _IT_EXCEPTIONS:
        return _IT_EXCEPTIONS[word_lc].split()

    # (b) prétraitement + table de règles
    word_lc = _preprocess(word_lc)
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        for pat, repl in _IT_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:
                    keys.extend(repl.split())
                i += len(pat)
                break
        else:
            warnings.append(
                f"IT g2p: unknown character {word_lc[i]!r} in word {word!r}"
            )
            keys.append(word_lc[i])
            i += 1
    return [k for k in keys if k]


def _phrase_to_sampa(phrase: str, warnings: list) -> str:
    """Convertit un syntagme (mots seuls) en SAMPA."""
    words = _WORD_RE.findall(phrase)
    if not words:
        return ''
    tokens: List[str] = []
    for w in words:
        keys = _word_to_keys(w, warnings)
        if not keys:
            continue
        tokens.append(keys_to_connected(keys, cluster_onset=True))
    return '.'.join(tokens)


def text_to_sampa_it(text: str, warnings: list = None, **kwargs) -> str:
    """Convertit un texte italien en séquence SAMPA moteur.

    Même contrat que ``g2p.text_to_sampa`` (anglais) : ponctuation de
    phrase → ``|``, virgule → pause courte, mots adjacents reliés
    par ``.`` (coarticulation).
    """
    own = warnings is None
    if own:
        warnings = []

    text = _normalize_input(text)

    phrases = _SENT_PUNCT_RE.split(text)
    out_phrases: List[str] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        parts = _COMMA_RE.split(phrase)
        sampa_parts = [_phrase_to_sampa(p, warnings) for p in parts]
        sampa_parts = [s for s in sampa_parts if s]
        if sampa_parts:
            out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p-it] {w}')
    return ' | '.join(out_phrases)


__all__ = ['text_to_sampa_it', '_IT_EXCEPTIONS', '_IT_RULES']
