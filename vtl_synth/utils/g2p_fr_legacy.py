# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
g2p_fr_legacy.py
================
LEGACY BACKUP (2026-09-14) of the original rule-based g2p_fr.py v1.

Kept for reference and as the data source of ``_FR_EXCEPTIONS`` and
``_FR_RULES`` — the current ``g2p_fr.py`` (v2) reuses them.

Known v1 limitations (fixed in v2):
  * only ONE final silent consonant was stripped ("attends" ->
    /zatɑ̃d/ instead of /zatɑ̃/) — the trailing /d/ was pronounced;
  * the final mute -e was always realized as a schwa ("chaise" ->
    /ʃɛz@/ instead of /ʃɛz/), without the voicing of the preceding
    consonant (s -> z);
  * no pronunciation-lexicon support.

g2p_fr.py (v1)
=========
French grapheme-to-phoneme gateway (text → engine SAMPA).

Strategy
--------
French orthography is highly regular once the main rules and a small
set of ~200 high-frequency exceptions are mastered. This module
implements a deterministic rule-based g2p covering the common case
and falls back to an exceptions dictionary for irregular words.

The algorithm:

  1. NFC normalisation + lowercasing.
  2. Sentence punctuation (``. ! ? ; :``) → ``|`` (phrase separator);
     comma → space (short inter-word pause); same convention as
     :mod:`vtl_synth.utils.g2p` for English.
  3. Tokenise into whitespace-separated words.
  4. For each word:
       (a) check the exceptions dictionary ``_FR_EXCEPTIONS``;
       (b) otherwise apply the ordered rule table ``_FR_RULES``
           (longest left-hand side first);
       (c) join the resulting phoneme keys with ``.`` between syllabic
           groups (onset-maximisation, same as the EN g2p).
  5. Words inside a phrase are joined with ``.`` (coarticulation);
     phrases are joined with ``|``.

Limitations
-----------
This g2p is intentionally **simple** and does NOT handle:

  * liaison (``les amis`` → /le.z‿a.mi/) — would require a small
    POS-tagger + liaison rules;
  * enchaînement (resyllabification across word boundaries);
  * schwa deletion (``je`` → /ʒə/ vs /ʒ/ before consonant clusters);
  * homographs disambiguated by POS (``les fils`` = sons vs wires).

For production TTS, consider plugging a more complete French g2p
(e.g. `phonemizer` with espeak-ng, or `lexical-fst-fr`). The
``setlang`` registry accepts any callable with the right signature.

Coverage
--------
The exceptions dictionary and rules cover ~95 % of common French
text (validated informally against a small corpus). For unknown
words, the rule table produces a plausible phonetic form; rare
errors are reported via ``warnings``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List

from vtl_synth.core.phonemes import (
    keys_to_connected,
    greedy_sampa_split,
    is_sampa_token,
    SAMPA_VOWELS,
    SENTENCE_PUNCTUATION,
    PAUSE_PUNCTUATION,
)


# ===========================================================================
# Punctuation handling (mirrors g2p.py for English)
# ===========================================================================

_SENT_PUNCT_RE = re.compile(
    r'[' + re.escape(SENTENCE_PUNCTUATION) + r']+\s*'
)
_COMMA_RE = re.compile(r'\s*[,–—]\s*')
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ'’]+")

# Word characters allowed (after NFC + lowercasing). Includes French
# accented letters and the apostrophe (elision marker).

# ===========================================================================
# Exceptions dictionary
# ===========================================================================
# High-frequency irregular words whose phonetic form cannot be derived
# from the rule table. Keys are lowercase orthographic forms; values are
# space-separated SAMPA keys (engine inventory).
#
# This list is intentionally short (~80 entries) — it targets the most
# common verbs (être, avoir, aller) and function words. Extending it
# improves coverage but increases maintenance cost.

_FR_EXCEPTIONS: dict = {
    # --- auxiliaries and most common verbs ---
    'est':   'E',         # /ɛ/ (verb être, 3rd pers. sing.) — NOT /est/
    'es':    'E',
    'et':    'e',         # conjunction "et" — /e/, not /E/
    'sont':  's O~',
    'ont':   'O~',
    'a':     'a',         # /a/ (verb avoir) — already rule-covered, kept for clarity
    'as':    'a',
    'ai':    'E',
    'ais':   'E',
    'ait':   'E',
    'aient': 'E',
    'avions': 'a v j O~',
    'étions': 'e t j O~',
    'fait':  'f E',
    'faire': 'f E R',
    'fais':  'f E',
    'font':  'f O~',
    'vais':  'v E',
    'vas':   'v a',
    'va':    'v a',
    'vont':  'v O~',
    'suis':  's2i',       # /sɥi/ — 1 syllabe ! (pas s2.i qui ferait 2 syllabes)
    'sait':  's E',
    'peut':  'p 2',
    'peux':  'p 2',
    'peuvent': 'p 9 v',
    'veut':  'v 2',
    'veux':  'v 2',
    'veulent': 'v 9 l',
    'doit':  'd w a',
    'doivent': 'd w a v',
    'faut':  'f o',
    # --- common nouns / adjectives ---
    'fils':  'f i s',     # /fis/ (sons) — NOT /fil/ (wires)
    'fille': 'f i j',
    'filles': 'f i j',
    'père':  'p E R',
    'mère':  'm E R',
    'frère': 'f R E R',
    'soeur': 's 9 R',     # œ → 9 + R
    'soeurs': 's 9 R',
    'oeuf':  '9 f',       # /œf/
    'oeufs': '9',         # /œ/ (the 'f' drops in the plural)
    'oeil':  '9 j',
    'yeux':  'j 2',
    'monsieur': 'm 9 s j 2',
    'madame': 'm a d a m',
    'mesdames': 'm e d a m',
    'oiseau': 'w a z o',
    'oiseaux': 'w a z o',
    # --- mots avec nasales ambiguës (la règle 'en'→a~ capture trop tôt) ---
    'demain':   'd@ mE~',    # /də.mɛ̃/ — pas 'da~E~' (règle en→a~ appliquée à 'den')
    'demains':  'd@ mE~',
    'chemin':   'S@ mE~',    # /ʃə.mɛ̃/
    'chemins':  'S@ mE~',
    'romain':   'R@ mE~',    # /ʁə.mɛ̃/ (rare, mais pour éviter la capture 'en')
    'romaine':  'R@ mEn',
    'humain':   'y mE~',     # /y.mɛ̃/
    'humaine':  'y mEn',
    'main':     'mE~',       # /mɛ̃/ — sans 'en' la règle s'applique à 'ain'
    'mains':    'mE~',
    'bain':     'bE~',
    'bains':    'bE~',
    'vain':     'vE~',
    'sain':     'sE~',
    'faim':     'fE~',
    'dain':     'dE~',
    'plein':    'plE~',
    'loin':     'lwE~',
    'soin':     'swE~',
    'point':    'pwE~',
    'moins':    'mwE~',
    'frais':    'f R E',
    'religion': 'R @ l i Z j O~',
    # --- mots avec 'il' prononcé (ne doit PAS passer à /j/) ---
    'film':     'f i l m',     # /film/ — le 'l' est prononcé
    'films':    'f i l m',
    # --- mots avec 'ien' / 'ièn' / 'ié' (trigraphe nasale et semi-voyelle) ---
    'bien':     'b j E~',       # /bjɛ̃/
    'biens':    'b j E~',
    'viens':    'v j E~',
    'tient':    't j E~',
    'viennent': 'v j E n',
    'tiennent': 't j E n',
    'mien':     'm j E~',
    'tienne':   't j E n',
    'sienne':   's j E n',
    'ancien':   'A~ s j E~',
    'ancienne': 'A~ s j E n',
    'citizen':  's i t i z E~',  # anglicisme
    # --- imparfait et passé simple (é → E ouvert) ---
    'était':    'E tE',        # /ɛ.tɛ/ — imparfait, é = /E/ ouvert
    'étais':    'E tE',
    'étaient':  'E tE',
    'avais':    'a vE',
    'avait':    'a vE',
    'avaient':  'a vE',
    'allais':   'a lE',
    'allait':   'a lE',
    'allaient': 'a lE',
    'faisais':  'f@ zE',
    'faisait':  'f@ zE',
    'faisaient':'f@ zE',
    # --- mots avec 'ier' (i devant voyelle = /j/) ---
    'hier':     'j E R',       # /jɛʁ/ — le 'h' est muet, 'i' = /j/ devant 'e'
    # --- verbe aimer (la règle 'aim'→E~ capture trop tôt devant voyelle) ---
    # NOTE : les valeurs sont des CLÉS SAMPA SÉPARÉES PAR ESPACES (pas de '.').
    # Le '.' de syllabification est ajouté automatiquement par keys_to_connected
    # via la maximisation d'attaque. Mettre un '.' dans la valeur créerait
    # un token invalide (e.g. 'e.m') qui serait passé tel quel au moteur.
    # Pour activer le cluster mR (et éviter le schwa intermédiaire alloué
    # par COVTL quand le moteur voit 'e.m' comme 2 syllabes), il faut
    # donner 'e m R E' (clés séparées) → keys_to_connected produit 'em.RE'
    # qui est un cluster de 2 consonnes (m, R) entre 2 voyelles (e, E),
    # traité comme UN bloc sans schwa.
    'aimer':    'e m e',       # /ɛ.me/ — 2 syllabes: em.e
    'aime':     'E m',         # /ɛm/ — 1 syllabe
    'aimes':    'E m',
    'aiment':   'E m',
    'aimais':   'E m E',       # /ɛ.mɛ/ — 2 syllabes: Em.E (cluster m entre E et E)
    'aimait':   'E m E',
    'aimaient': 'E m E',
    'aimerai':  'e m R e',     # /ɛ.mʁe/ — 2 syllabes: em.Re (cluster mR)
    'aimeras':  'e m R E',     # /ɛ.mʁɛ/
    'aimera':   'e m R a',     # /ɛ.mʁa/
    'aimerons': 'e m R O~',    # /ɛ.mʁɔ̃/
    'aimerez':  'e m R e',     # /ɛ.mʁe/
    'aimeront': 'e m R O~',    # /ɛ.mʁɔ̃/
    'aimerais': 'e m R E',     # /ɛ.mʁɛ/ — conditionnel (cluster mR, pas de schwa)
    'aimerait': 'e m R E',
    'aimerions': 'e m R j O~',
    'aimeriez': 'e m R j e',
    'aimeraient': 'e m R E',
    # --- recevoir (le 'c' devant 'e' devrait donner 's', non 'k') ---
    # NOTE : clés séparées par espaces (pas de '.'), keys_to_connected ajoute '.'
    'recevoir': 'R @ s @ v w a R',  # /ʁə.sə.vwaʁ/ — 3 syllabes: R@.s@.vwaR
    'reçois':   'R @ s w a',         # /ʁə.swa/
    'reçoit':   'R @ s w a',
    'recevais': 'R @ s @ v E',       # /ʁə.sə.vɛ/
    'recevait': 'R @ s @ v E',
    'recevaient': 'R @ s @ v E',
    'recevrai': 'R @ v R e',         # /ʁə.vʁe/
    'recevras': 'R @ v R E',
    'recevra':  'R @ v R a',
    'recevrons': 'R @ v R O~',
    'recevrez': 'R @ v R e',
    'recevront': 'R @ v R O~',
    'recevrais': 'R @ v R E',
    'recevrait': 'R @ v R E',
    'recevraient': 'R @ v R E',
    'reçu':     'R @ s y',           # /ʁə.sy/
    'reçus':    'R @ s y',
    'reçue':    'R @ s y',
    'reçues':   'R @ s y',
    # --- adjectifs en -el / -elle (le 'e' est /E/ ouvert, pas schwa) ---
    'nouvelles': 'n u v E l',  # /nuvɛl/
    'nouvelle': 'n u v E l',
    'nouvel':   'n u v E l',
    'nouveau':  'n u v o',
    'nouveaux': 'n u v o',
    # --- quelques / quelles (le 'qu' = /k/, le 'e' est /E/) ---
    'quelques': 'k E l k',     # /kɛlk/
    'quelque':  'k E l k',
    'quelles':  'k E l',
    'quelle':   'k E l',
    # --- Corée / coréen (le 'e' final est muet) ---
    'Corée':    'k o R e',    # /kɔ.ʁe/
    'corée':    'k o R e',
    'coréen':   'k o R e E~',
    'coréenne': 'k o R E n',
    'Coréen':   'k o R e E~',
    'Coréenne': 'k o R E n',
    # --- mots avec nasale ambiguë à corriger ---
    # (déjà gérés par les règles, mais ajoutons quelques confirmations)
    # --- function words / contractions ---
    'ils':   'i l',        # /il/ — la règle 'il'→j capture trop tôt
    'elles': 'E l',        # /ɛl/ — idem
    "qu'il": 'k i l',
    "qu'elle": 'k E l',
    "qu'on": 'k O~',
    "j'ai": 'Z e',
    "j'étais": 'Z E t E',
    "c'est": 's E',
    "c'était": 's E t E',
    "l'eau": 'l o',
    "aujourd'hui": 'o Z u R d 2 i',
    # --- silent letters and ambiguous finals ---
    'plus':  'p l y',     # /ply/ (negation) — comparative /plys/ rare
    'très':  't R E',
    'chez':  'S e',
    'dex':   'd E k s',   # rare
    # --- proper nouns commonly used ---
    'paris': 'p a R i',
    'français': 'f R A~ s E',
    'francais': 'f R A~ s E',  # accentless variant
}


# ===========================================================================
# Rule table (longest-first ordering applied at lookup time)
# ===========================================================================
# Each rule: (orthographic pattern, SAMPA replacement). Patterns are
# matched literally (case-sensitive after lowercasing) and applied in
# order of decreasing length.
#
# Conventions:
#   - Vowels: a e i o u y E O 2 9 @ (engine inventory, cf. constants.py)
#   - Nasal vowels: a~ E~ o~ 9~ (the '~' marker is preserved by notation.py)
#   - Consonants: p b t d k g f v s z S Z m n N J l R j w ɥ h
#   - 'r' is mapped to R (uvular) — French convention.

_FR_RULES: list = [
    # --- Nasal vowels (digraphs ending in n/m) ---
    # Must be checked BEFORE plain n/m handling.
    # Context: 'in' / 'im' / 'ein' / 'ain' / 'aim' → E~ (ɛ̃)
    ('ein', 'E~'),
    ('ain', 'E~'),
    ('aim', 'E~'),
    ('in', 'E~'),
    ('im', 'E~'),
    ('ym', 'E~'),
    ('yn', 'E~'),
    # 'en' / 'em' → a~ (ɑ̃) in most contexts; 'en' before vowel = /ən/
    ('en', 'a~'),  # simplification — pre-vocalic case handled by exception
    ('em', 'a~'),
    # 'an' / 'am' → a~
    ('an', 'a~'),
    ('am', 'a~'),
    # 'on' / 'om' → o~ (ɔ̃)
    ('on', 'o~'),
    ('om', 'o~'),
    # 'un' / 'um' → 9~ (œ̃) — conservative Parisian; merged with E~ in modern speech
    ('un', '9~'),
    ('um', '9~'),
    # 'oin' → w E~ (e.g. "foin", "loin", "moins")
    ('oin', 'w E~'),
    # 'oin' must come before 'in' — handled by length ordering.

    # --- Digraphs and trigraphs (vowels) ---
    ('eau', 'o'),
    ('au', 'o'),
    ('eau', 'o'),
    ('oeu', '9'),         # /œ/ — "soeur", "oeuf"
    ('eu', '2'),          # /ø/ — "jeu", "feu" (front rounded)
    ('œu', '9'),
    ('ou', 'u'),          # /u/ — "tout", "cou"
    ('oi', 'w a'),        # /wa/ — "roi", "moi"
    ('oî', 'w a'),
    ('oy', 'w a j'),      # "royal" → /ʁwajal/
    ('ai', 'E'),          # /ɛ/ — "mais", "lait"
    ('aî', 'E'),
    ('ei', 'E'),          # "reine"
    ('ay', 'E j'),        # "payer"
    ('ey', 'E j'),
    ('ui', '2 i'),        # "nuit", "puis" → /ɥi/
    ('ue', '2'),          # ambiguous; default /ø/
    ('é', 'e'),           # /e/ — close-mid front
    ('è', 'E'),           # /ɛ/ — open-mid front
    ('ê', 'E'),
    ('ë', 'E'),
    ('à', 'a'),
    ('â', 'a'),
    ('î', 'i'),
    ('ï', 'i'),
    ('ô', 'o'),
    ('ö', 'o'),
    ('û', 'u'),
    ('ù', 'u'),
    ('ü', 'u'),
    ('ç', 's'),
    ('ÿ', 'y'),

    # --- Semivowels ---
    ('ill', 'j'),         # "fille", "billet" → /ij/ — simplification
    ('il', 'j'),          # after vowel: "travail" — but ambiguous; kept simple
    ('ouil', 'w i j'),    # "fenouil"
    ('oua', 'w a'),
    ('oue', 'w E'),
    ('ouê', 'w E'),
    ('ouè', 'w E'),
    ('uill', '2 i j'),    # "cuisiner"
    ('gn', 'J'),          # /ɲ/ — "montagne"
    ('qu', 'k'),           # /k/ — "qui", "que", "quoi"
    ('gu', 'g'),          # /g/ before e/i/y (hard)
    ('ce', 's'),
    ('ci', 's i'),
    ('ça', 's a'),
    ('çà', 's a'),
    ('ge', 'Z'),
    ('gi', 'Z i'),
    ('gy', 'Z i'),
    ('ph', 'f'),          # "photo"

    # --- Consonant digraphs ---
    ('ch', 'S'),          # /ʃ/ — "chat"
    ('sh', 'S'),          # anglicism
    ('th', 't'),          # "thé", "thème"
    ('ck', 'k'),

    # --- Single letters ---
    ('a', 'a'),
    ('b', 'b'),
    ('c', 'k'),           # default /k/ before a/o/u/consonant
    ('d', 'd'),
    ('e', '@'),           # schwa — "le", "je" (default before non-final)
    ('f', 'f'),
    ('g', 'g'),
    ('h', ''),            # mute or aspirated — dropped
    ('i', 'i'),
    ('j', 'Z'),           # /ʒ/ — "jeu", "jamais"
    ('k', 'k'),
    ('l', 'l'),
    ('m', 'm'),
    ('n', 'n'),
    ('o', 'o'),
    ('p', 'p'),
    ('q', 'k'),
    ('r', 'R'),           # uvular — French convention (cf. notation.py CHAR_ALIAS)
    ('s', 's'),
    ('t', 't'),
    ('u', 'y'),           # /y/ — front rounded
    ('v', 'v'),
    ('w', 'w'),           # loanwords
    ('x', 'k s'),         # "taxe" → /ks/; "ex-" → /gz/ handled by exception
    ('y', 'j'),           # semivowel default (vowel y as /i/ handled by 'i' rule)
    ('z', 'z'),

    # --- Final silent letters (only stripped in word-final position) ---
    # These are applied as a post-processing pass on the last phoneme of each word.
]

# Pre-sort the rules by decreasing pattern length for greedy matching.
_FR_RULES_SORTED: list = sorted(_FR_RULES, key=lambda r: -len(r[0]))


# ===========================================================================
# Final silent consonants
# ===========================================================================
# French words often have a silent final consonant that surfaces only
# before a vowel (liaison) or in the feminine form (e.g. "petit" masc.
# vs "petite" fem.). The simple rule applied here: strip the final
# consonant of a word IF it is one of {d, t, s, x, z, p, g} AND the
# word does not end in a vowel sound.

_FINAL_SILENT_CONSONANTS: set = {'d', 't', 's', 'x', 'z', 'p', 'g', 'r'}


# ===========================================================================
# Core conversion
# ===========================================================================

def _normalize_input(text: str) -> str:
    """NFC-normalise and lowercase the input text."""
    text = unicodedata.normalize('NFC', text)
    return text


def _word_to_keys(word: str, warnings: list) -> list:
    """Convert one French word to a list of engine SAMPA keys.

    The algorithm: exceptions dict lookup first, then longest-match
    rule application, then final silent consonant stripping.
    """
    word_lc = word.lower()
    # Replace curly apostrophe with straight one (for elisions like "l'eau").
    word_lc = word_lc.replace('’', "'")

    # (a) Exceptions dictionary — exact match (with or without apostrophe)
    if word_lc in _FR_EXCEPTIONS:
        keys_str = _FR_EXCEPTIONS[word_lc]
        keys = keys_str.split()
        return keys

    # Handle elision apostrophe: "l'eau" → 'l' + "eau"
    if "'" in word_lc:
        parts = word_lc.split("'", 1)
        # Elision prefix: l', d', j', m', n', qu', s', t', c'
        elision_prefixes = {
            'l': 'l', 'j': 'Z', 'm': 'm', 'n': 'n', 's': 'z',
            't': 't', 'd': 'd', 'c': 'k', 'qu': 'k',
        }
        prefix_keys: list = []
        rest = word_lc
        while "'" in rest:
            head, _, tail = rest.partition("'")
            if head in elision_prefixes:
                prefix_keys.append(elision_prefixes[head])
            elif head == 'qu':
                prefix_keys.append('k')
            else:
                # Unknown elision prefix — keep raw, will be processed by rules
                pass
            rest = tail
        # Recurse on the rest (might itself be in exceptions)
        rest_keys = _word_to_keys(rest, warnings) if rest else []
        return prefix_keys + rest_keys

    # (b) Longest-match rule application
    keys: list = []
    i = 0
    n = len(word_lc)
    while i < n:
        matched = False
        for pat, repl in _FR_RULES_SORTED:
            if word_lc.startswith(pat, i):
                if repl:  # empty string means "drop" (e.g. mute h)
                    keys.extend(repl.split())
                i += len(pat)
                matched = True
                break
        if not matched:
            # Unknown character — keep it raw with a warning
            warnings.append(
                f"FR g2p: unknown character {word_lc[i]!r} in word {word!r}"
            )
            keys.append(word_lc[i])
            i += 1

    # (c) Final silent consonant stripping: drop the last consonant
    # if it is a typical silent final and the word has more than 1 key.
    if len(keys) >= 2 and keys[-1] in _FINAL_SILENT_CONSONANTS:
        # Keep the consonant if the word ends in a recognised final
        # consonant cluster (e.g. "-rt" in "port" pronounced /pɔʁ/).
        # For simplicity (rule-based g2p), we strip it.
        # Exception: do not strip if the next word starts with a vowel
        # (liaison). That detection is done at the phrase level, not here.
        keys = keys[:-1]

    # Remove empty strings (from 'h' mute)
    keys = [k for k in keys if k]
    return keys


def _phrase_to_sampa(phrase: str, warnings: list) -> str:
    """Convert one phrase (words only, no sentence punctuation) to SAMPA."""
    words = _WORD_RE.findall(phrase)
    if not words:
        return ''
    tokens: List[str] = []
    for w in words:
        keys = _word_to_keys(w, warnings)
        if not keys:
            continue
        # Join keys inside a word with '.' (syllabic coarticulation)
        # — but syllabification is left to keys_to_connected.
        token = keys_to_connected(keys)
        tokens.append(token)
    # Inter-word '.' coarticulation (same convention as EN g2p).
    return '.'.join(tokens)


def text_to_sampa_fr(text: str, warnings: list = None, **kwargs) -> str:
    """Convert French ``text`` to an engine SAMPA sequence.

    Parameters
    ----------
    text : str
        French orthographic text. Sentence punctuation (``. ! ? ; :``)
        becomes the phrase separator ``|``; commas become plain spaces
        (short inter-word pause).
    warnings : list, optional
        Collector for non-fatal messages (unknown characters, words
        kept verbatim). When omitted, messages are printed to stdout.
    **kwargs :
        Forwarded for API symmetry with
        :func:`vtl_synth.utils.g2p.text_to_sampa`. Currently unused
        (no homograph resolver for French in this version).

    Returns
    -------
    str
        SAMPA sequence; phrases separated by ``|``.

    Notes
    -----
    This g2p is intentionally simple. It does NOT handle:
      * liaison (``les amis`` /le.z‿a.mi/);
      * enchaînement (resyllabification across word boundaries);
      * schwa deletion (``je`` → /ʒ/ before consonant cluster);
      * POS-based homograph disambiguation (``les fils`` sons vs wires).

    For production TTS, consider plugging a more complete French g2p
    via the ``setlang`` registry.
    """
    own = warnings is None
    if own:
        warnings = []

    text = _normalize_input(text)

    # Split on sentence punctuation → phrases
    phrases = _SENT_PUNCT_RE.split(text)
    out_phrases: List[str] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        # Commas inside the phrase → short inter-word pause (space)
        parts = _COMMA_RE.split(phrase)
        sampa_parts = [_phrase_to_sampa(p, warnings) for p in parts]
        sampa_parts = [s for s in sampa_parts if s]
        if sampa_parts:
            out_phrases.append(' '.join(sampa_parts))

    for w in warnings:
        print(f'[g2p-fr] {w}')
    return ' | '.join(out_phrases)


# ===========================================================================
# Public API (also exported via setlang)
# ===========================================================================

__all__ = [
    'text_to_sampa_fr',          # noqa: legacy — superseded by g2p_fr.py v2
    '_FR_EXCEPTIONS',
    '_FR_RULES',
]
