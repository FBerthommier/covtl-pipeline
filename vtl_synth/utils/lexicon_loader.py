# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
lexicon_loader.py
=================
Chargeur commun des lexiques de prononciation (Wikipron TSV), partagé
par tous les g2p multilingues (fr, es, de, it, pt).

Factorisation de ``_load_lexicon`` de ``g2p_fr.py`` (v2) : chaque langue
décrit son lexique par un ``LexiconSpec`` (nom de fichier, variable
d'environnement, table IPA → clés moteur). Le chargeur est paresseux,
tolérant aux pannes (lexique absent → dégradation douce vers les règles)
et met ses résultats en cache.

Formats acceptés par ligne ``mot<TAB>pron`` (détection automatique) :
  * clés moteur SAMPA séparées par des espaces (``a t a~``) ;
  * IPA Wikipron (``atɑ̃``), converti par la table de la langue.

Sources Wikipron (données du Wiktionnaire, CC BY-SA 3.0 — cf.
``vtl_synth/data/README_fr_lexicon.md`` et les notices
``README_xx_lexicon.md`` par langue) :

  ========  ======  =====================================================
  langue    code    fichier Wikipron (data/scrape/tsv/, branche master)
  ========  ======  =====================================================
  fr        fra     fra_latn_broad_filtered.tsv
  es        spa     spa_latn_ca_broad_filtered.tsv   (castillan, /θ/)
  de        deu     deu_latn_broad_filtered.tsv
  it        ita     ita_latn_broad_filtered.tsv
  pt        por     por_latn_po_broad_filtered.tsv   (port. européen)
  ========  ======  =====================================================

L'URL brute est de la forme ::
https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/<fichier>
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vtl_synth.core.constants import ALL_CONSONANT_KEYS

# Union des voyelles de TOUTES les langues (language_vowel_sets) : le
# test « token = clé moteur valide » ne doit pas dépendre de la langue
# ACTIVE (ex. 'I'/'U'/'Y' allemands doivent être reconnus même quand la
# section langue active est 'en'). Import paresseux pour éviter tout
# cycle d'import au chargement du paquet.
def _all_vowel_keys() -> frozenset:
    from vtl_synth.utils.language_vowel_sets import VOWEL_SETS
    keys = set()
    for entry in VOWEL_SETS.values():
        keys.update(entry['vowels'].keys())
    return frozenset(keys)


# Clés valides pour la branche « clés moteur » du chargeur : consonnes +
# toutes les voyelles connues + voyelles nasales (base + '~').
_VALID_KEYS: frozenset = frozenset(
    set(ALL_CONSONANT_KEYS) | _all_vowel_keys()
    | {k + '~' for k in _all_vowel_keys()}
    | {'a~', 'e~', 'i~', 'o~', 'u~', 'y~', '9~', '2~', '@~',
       'E~', 'O~', '6~'}
)


# ===========================================================================
# Tables IPA → clés moteur (par langue)
# ===========================================================================
# Conventions :
#   * l'entrée est normalisée NFC avant conversion (les nasales
#     décomposées de Wikipron portugais se composent seules pour
#     a/e/i/o/u ; ɐ̃ ɛ̃ ɔ̃ etc. restent décomposées → entrées 2-car.) ;
#   * table ordonnée : motifs longs d'abord (la conversion est gloutonne
#     position par position, dans l'ordre de la liste) ;
#   * phonèmes sans équivalent moteur : approximations documentées
#     (ɾ→R : pas de rhotique alvéolaire dans l'inventaire ; ʔ→'' :
#     pas de coup de glotte ; t͡s→'t s' : pas d'affriquée dentale).

_TILDE = '\u0303'
_TIE = '\u0361'          # t͡ʃ (liaison affriquée)
_NONSYL = '\u032F'       # a̯ (diacritique non-syllabique)
_SYLL = '\u0329'         # m̩ (diacritique syllabique)

# --- socle commun (ASCII IPA + symboles partagés) -------------------------
_BASE_IPA_TO_KEYS: List[Tuple[str, str]] = [
    ('t' + _TIE + 'ʃ', 'tS'), ('d' + _TIE + 'ʒ', 'dZ'),
    (_TIE, ''),
    ('tʃ', 'tS'), ('dʒ', 'dZ'),
    # diphtongues descendantes écrites en voyelles pleines (Wikipron
    # es/it/pt : 'rey' → r e i ; les montantes utilisent j/w explicites)
    ('ai', 'a j'), ('ei', 'e j'), ('oi', 'o j'),
    ('au', 'a w'), ('eu', 'e w'), ('ou', 'o w'),
    ('ʃ', 'S'), ('ʒ', 'Z'), ('ŋ', 'N'), ('ɲ', 'J'), ('ʁ', 'R'),
    ('ʀ', 'R'), ('ɾ', 'R'), ('β', 'b'), ('ɣ', 'g'), ('ʝ', 'j'),
    ('ɡ', 'g'),
    ('ɛ', 'E'), ('ɔ', 'O'), ('ə', '@'), ('ɑ', 'a'), ('œ', '9'),
    ('ø', '2'), ('ɐ', '@'), ('θ', 'T'), ('ð', 'D'),
    ('ː', ''), ('ˑ', ''), ('ˈ', ''), ('ˌ', ''),
    ('(', ''), (')', ''), ('‿', ''),
    ('j', 'j'), ('w', 'w'), ('l', 'l'), ('r', 'R'), ('h', 'h'),
    ('a', 'a'), ('e', 'e'), ('i', 'i'), ('o', 'o'), ('u', 'u'),
    ('y', 'y'),
    ('p', 'p'), ('b', 'b'), ('t', 't'), ('d', 'd'), ('k', 'k'),
    ('g', 'g'), ('f', 'f'), ('v', 'v'), ('s', 's'), ('z', 'z'),
    ('m', 'm'), ('n', 'n'),
]

# --- nasales précomposées (NFC) --------------------------------------------
_NASAL_PRECOMPOSED: List[Tuple[str, str]] = [
    ('ã', 'a~'), ('ẽ', 'e~'), ('ĩ', 'i~'), ('õ', 'o~'), ('ũ', 'u~'),
    ('ɐ' + _TILDE, '@~'), ('ɛ' + _TILDE, 'E~'), ('ɔ' + _TILDE, 'O~'),
    ('ɑ' + _TILDE, 'a~'),   # pas de forme précomposée (Wikipron fra)
    ('y' + _TILDE, 'y~'), ('ø' + _TILDE, '2~'), ('œ' + _TILDE, '9~'),
    ('ə' + _TILDE, '@~'), ('i' + _TILDE, 'i~'), ('u' + _TILDE, 'u~'),
    ('o' + _TILDE, 'o~'), ('e' + _TILDE, 'e~'), ('a' + _TILDE, 'a~'),
    # glides nasaux (w̃ j̃, portugais) → glide simple (approximation :
    # la nasalité de la voyelle adjacente domine)
    ('w' + _TILDE, 'w'), ('j' + _TILDE, 'j'),
    (_TILDE, ''),
]

_FR_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + _BASE_IPA_TO_KEYS + [
        ('ç', 's'),          # notation.py : ç étranger → /s/ (français)
        ('χ', 'X'),
        ('x', 'X'),
        ('ɥ', 'ɥ'),
    ])

_ES_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + _BASE_IPA_TO_KEYS + [
        ('x', 'X'),          # j, g+e/i espagnols /x/ → fricative uvulaire
        ('t' + _TIE + 's', 't s'),
        ('ts', 't s'),
    ])

_DE_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        # diphtongues avec diacritique non-syllabique (aɪ̯ aʊ̯ …) et
        # formes plates (Wikipron écrit indifféremment aɪ̯ / aɪ)
        ('aɪ' + _NONSYL, 'a j'), ('aʊ' + _NONSYL, 'a w'),
        ('ɔɪ' + _NONSYL, 'O j'), ('ɔʏ' + _NONSYL, 'O j'),
        ('eɪ' + _NONSYL, 'e j'), ('oʊ' + _NONSYL, 'o w'),
        ('aɪ', 'a j'), ('aʊ', 'a w'), ('ɔʏ', 'O j'), ('ɔɪ', 'O j'),
        ('ɪ' + _NONSYL, 'j'), ('ʊ' + _NONSYL, 'w'),
        ('ʏ' + _NONSYL, 'j'),
        ('ɐ' + _NONSYL, 'a'),
        (_NONSYL, ''),
        # affriquées dentales allemandes (Zeit → t͡saɪt)
        ('t' + _TIE + 's', 't s'), ('d' + _TIE + 'z', 'd z'),
        # consonnes syllabiques → voyelle d'appui + consonne (le
        # moteur ne synthétise pas de nasale syllabique seule :
        # 'guten' → ɡuːtn̩ doit donner g u t @ n)
        ('n' + _SYLL, '@ n'), ('m' + _SYLL, '@ m'),
        ('l' + _SYLL, '@ l'),
        ('ç', 'C'),          # ich-laut → fricative palatale moteur 'C'
        ('x', 'X'), ('χ', 'X'),   # ach-laut → fricative uvulaire 'X'
        ('ʔ', ''),           # coup de glotte : absent de l'inventaire
        ('ɪ', 'I'), ('ʊ', 'U'), ('ʏ', 'Y'),
        ('ʋ', 'v'), ('ɱ', 'm'), ('ɘ', '@'), ('ɒ', 'O'),
        (_SYLL, ''),         # autres syllabiques résiduels
        ('̥', ''), ('ʰ', ''), ('̊', ''), ('̍', ''),
    ] + _BASE_IPA_TO_KEYS)

_IT_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        ('ao', 'a w'),       # ciao → t͡ʃao : diphtongue descendante
        # /ə/ toscan (e atone : « come » → ˈkomə) : l'italien n'a PAS de
        # schwa — la clé '@' n'existe pas dans son inventaire moteur
        ('ə', 'e'),
        ('ʎ', 'L'),          # glatéral italien → clé 'L' du moteur
        ('t' + _TIE + 's', 't s'), ('d' + _TIE + 'z', 'd z'),
        ('ts', 't s'),
    ] + _BASE_IPA_TO_KEYS)

_PT_IPA_TO_KEYS: List[Tuple[str, str]] = (
    _NASAL_PRECOMPOSED + [
        # 'ø' résiduel (quelques emprunts du TSV) : le portugais n'a pas
        # de voyelle arrondie antérieure — clé '2' absente de son
        # inventaire moteur
        ('ø', 'e'),
        ('ʎ', 'L'),
    ] + _BASE_IPA_TO_KEYS)


# ===========================================================================
# Spécification par langue
# ===========================================================================

@dataclass
class LexiconSpec:
    """Description du lexique de prononciation d'une langue.

    filename : nom du TSV dans ``vtl_synth/data/``
    env_var : variable d'environnement de surcharge du chemin
    ipa_to_keys : table ordonnée IPA → clés (motifs longs d'abord)
    source_file : fichier Wikipron d'origine (traçabilité)
    variant_policy : choix parmi les doublons du Wiktionnaire :
      * ``'short'`` (hérité fr) — éviter les artefacts de liaison,
        préférer le schwa pour les mots ≤ 3 lettres, sinon la forme
        la plus courte ;
      * ``'grapheme'`` (es, de, it, pt) — éviter les artefacts, puis
        la variante dont la longueur est la plus proche du nombre de
        graphèmes du mot (les orthographes romaniques/allemande sont
        proches d'un graphème par phonème ; ceci rejette les variantes
        clitiques élidées : it. « la » → /a/ vs /la/, pt. « bom »),
        ex æquo → la plus longue.
    """

    lang: str
    filename: str
    env_var: str
    ipa_to_keys: List[Tuple[str, str]]
    source_file: str
    display_name: str
    expected_min: int = 10000
    variant_policy: str = 'grapheme'
    # Corrections ponctuelles appliquées APRÈS chargement (données du
    # Wiktionnaire manifestement fautives ou dialectales : la variante
    # es « en » → /em/). Priorité du lexique conservée — ce sont des
    # entrées de lexique corrigées, pas des exceptions g2p.
    overrides: Dict[str, List[str]] = field(default_factory=dict)


LEXICONS: Dict[str, LexiconSpec] = {
    'fr': LexiconSpec(
        'fr', 'fr_lexicon.tsv', 'COVTL_FR_LEXICON', _FR_IPA_TO_KEYS,
        'fra_latn_broad_filtered.tsv', 'Français',
        variant_policy='short'),
    'es': LexiconSpec(
        'es', 'es_lexicon.tsv', 'COVTL_ES_LEXICON', _ES_IPA_TO_KEYS,
        'spa_latn_ca_broad_filtered.tsv', 'Español',
        overrides={'en': ['e', 'n']}),
    'de': LexiconSpec(
        'de', 'de_lexicon.tsv', 'COVTL_DE_LEXICON', _DE_IPA_TO_KEYS,
        'deu_latn_broad_filtered.tsv', 'Deutsch'),
    'it': LexiconSpec(
        'it', 'it_lexicon.tsv', 'COVTL_IT_LEXICON', _IT_IPA_TO_KEYS,
        'ita_latn_broad_filtered.tsv', 'Italiano'),
    'pt': LexiconSpec(
        'pt', 'pt_lexicon.tsv', 'COVTL_PT_LEXICON', _PT_IPA_TO_KEYS,
        'por_latn_po_broad_filtered.tsv', 'Português'),
}

_DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


# ===========================================================================
# Conversion IPA → clés
# ===========================================================================

def ipa_to_keys(ipa: str, lang: str) -> List[str]:
    """Convertit une transcription IPA (Wikipron) en clés moteur.

    La séquence est normalisée NFC puis DÉSPACÉE avant conversion :
    Wikipron sépare chaque téléphone par un espace (« rey » →
    ``r e i``), et les diphtongues descendantes s'écrivent en voyelles
    pleines séparées — la table doit donc voir ``rei`` d'un bloc pour
    appliquer ``ei → e j``. Conversion gloutonne position par position
    sur la table de la langue ; les glyphes inconnus sont silencieusement
    ignorés (même contrat que ``g2p_fr._ipa_to_keys``).

    Les marques d'accent de mot (ˈ primaire, ˌ secondaire) sont ici
    SUPPRIMÉES — utiliser :func:`ipa_to_keys_stress` pour les conserver
    (prosodie expressive : placement des accents de hauteur).
    """
    return ipa_to_keys_stress(ipa, lang)[0]


def ipa_to_keys_stress(ipa: str,
                       lang: str) -> Tuple[List[str], Optional[int]]:
    """Variante de :func:`ipa_to_keys` qui conserve l'accent de mot.

    Retourne ``(clés, index_accidentée)`` où ``index_accidentée`` est
    l'index de la syllabe accentuée (comptée en voyelles émises, la
    marque Wikipron ˈ/ˌ précédant l'attaque de la syllabe accentuée)
    ou ``None`` si la transcription ne porte aucune marque.

    Le stress voyage HORS BANDE : il n'apparaît jamais dans les clés
    moteur (l'inventaire du moteur n'est pas pollué), seulement dans
    le channel parallèle destiné à la prosodie expressive
    (``stress_for`` ci-dessous).
    """
    table = LEXICONS[lang].ipa_to_keys
    ipa = unicodedata.normalize('NFC', ipa).replace(' ', '')
    out: List[str] = []
    primary: Optional[int] = None
    secondary: Optional[int] = None
    vowel_keys = _all_vowel_keys()
    i = 0
    while i < len(ipa):
        ch = ipa[i]
        if ch == '\u02C8':                         # ˈ accent primaire
            n_vow = sum(1 for k in out if k.rstrip('~') in vowel_keys)
            primary = n_vow
            i += 1
            continue
        if ch == '\u02CC':                         # ˌ accent secondaire
            n_vow = sum(1 for k in out if k.rstrip('~') in vowel_keys)
            secondary = n_vow
            i += 1
            continue
        for pat, repl in table:
            if ipa.startswith(pat, i):
                out.extend(repl.split())
                i += len(pat)
                break
        else:
            i += 1                      # glyphe inconnu — ignoré
    stress = primary if primary is not None else secondary
    return out, stress


def _ipa_chars(lang: str) -> set:
    """Glyphes non-ASCII de la table — signe que la ligne est de l'IPA."""
    return {c for pat, _ in LEXICONS[lang].ipa_to_keys
            for c in pat if ord(c) > 127}


# ===========================================================================
# Chargement du TSV
# ===========================================================================

def _best_candidate(word: str, cands: List[List[str]],
                    policy: str = 'grapheme') -> List[str]:
    """Choisit la meilleure prononciation parmi des doublons du lexique.

    Le Wiktionnaire liste plusieurs transcriptions par graphie sans
    classement de fréquence. Politiques (cf. ``LexiconSpec``) :

    ``'short'`` (héritée de g2p_fr v2) :
      1. éviter les artefacts de liaison (clé vide) ;
      2. mots-outils monosyllabiques (≤ 3 lettres) : préférer la
         réalisation avec schwa (« de » → /də/, pas /dam/) ;
      3. sinon la réalisation la plus courte (forme canonique).

    ``'grapheme'`` (es, de, it, pt) :
      1. éviter les artefacts de liaison ;
      2. la variante la plus proche, en longueur, du nombre de
         graphèmes du mot (rejette les variantes clitiques élidées :
         it. « la » → /a/ vs /la/) ;
      3. ex æquo → la plus longue.
    """
    cands = [c for c in cands if c] or [[]]
    if len(cands) == 1:
        return cands[0]

    if policy == 'short':
        def score(c: List[str]) -> tuple:
            junk = 1 if any(k == '' for k in c) else 0
            schwa = 1 if (len(word) <= 3 and '@' in c) else 0
            return (junk, -schwa, len(c))
    else:
        def score(c: List[str]) -> tuple:
            junk = 1 if any(k == '' for k in c) else 0
            return (junk, abs(len(c) - len(word)), -len(c))

    return min(cands, key=score)


def load_lexicon(lang: str, path: Optional[Path] = None) -> dict:
    """Charge le lexique TSV de ``lang`` : ``mot<TAB>clés-ou-IPA``.

    Retourne {} si le lexique est absent ou inexploitable (dégradation
    douce : le g2p de la langue retombe sur ses règles).

    En parallèle, remplit le channel de stress hors-bande
    (``ipa_to_keys_stress``) consultable via :func:`stress_for` :
    index de syllabe accentuée par mot (None si la transcription ne
    porte pas de marque — branch « clés moteur » ou Wikipron sans
    accent).
    """
    spec = LEXICONS[lang]
    path = path or Path(os.environ.get(spec.env_var,
                                       str(_DATA_DIR / spec.filename)))
    ipa_glyphs = _ipa_chars(lang)
    candidates: dict = {}
    stress_cands: dict = {}
    n_lines = 0
    with_open = 0
    if not path.exists():
        _STRESS_CACHE[lang] = {}
        return {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            n_lines += 1
            line = line.strip()
            if not line or line.startswith('#') or '\t' not in line:
                continue
            word, _, pron = line.partition('\t')
            word = word.strip().lower().replace('’', "'")
            pron = pron.strip()
            if not word or not pron:
                continue
            tokens = pron.split()
            if (any(c in pron for c in ipa_glyphs)
                    or any(t not in _VALID_KEYS for t in tokens)):
                keys, stress = ipa_to_keys_stress(pron, lang)
            else:                                       # clés moteur
                keys = [t if t != 'r' else 'R' for t in tokens]
                stress = None
            if keys:
                candidates.setdefault(word, []).append(keys)
                stress_cands.setdefault(word, []).append(stress)
    lex = {}
    stress = {}
    for w, cands in candidates.items():
        idx = cands.index(_best_candidate(w, cands,
                                          policy=spec.variant_policy))
        lex[w] = cands[idx]
        stress[w] = stress_cands[w][idx]
    if spec.overrides:
        lex.update(spec.overrides)
    if not lex and n_lines > 0:
        # fichier présent mais rien d'exploitable — probablement une page
        # HTML enregistrée au lieu du TSV brut (erreur GitHub classique).
        print(f'[lexicon-{lang}] ATTENTION : {path} ne contient aucune '
              f'entrée TSV exploitable ({n_lines} lignes) — lexique '
              'ignoré. Vérifier que le fichier est bien le TSV brut '
              '(lien « Raw » de GitHub), cf. data/README_fr_lexicon.md')
    _STRESS_CACHE[lang] = stress
    return lex


# ===========================================================================
# Cache paresseux par langue
# ===========================================================================

_CACHE: Dict[str, Optional[dict]] = {}
# Channel de stress hors-bande (prosodie expressive) : mot → index de
# syllabe accentuée (None = non spécifié). Rempli par load_lexicon.
_STRESS_CACHE: Dict[str, dict] = {}


def lexicon_for(lang: str) -> dict:
    """Lexique de ``lang`` (singleton paresseux, None si absent).

    Retourne un dict vide si le fichier manque — les appelants doivent
    traiter cela comme « règles uniquement ».
    """
    if lang not in _CACHE:
        _CACHE[lang] = load_lexicon(lang)
    return _CACHE[lang] or {}


def stress_for(lang: str) -> dict:
    """Index d'accent de mot par mot (channel hors-bande, v1.0.8).

    ``{mot: index_syllabe_accentuée | None}`` — l'index compte les
    syllabes en voyelles émises (cf. :func:`ipa_to_keys_stress`).
    Lexique non chargé → {} (l'appelant retombe sur ses règles de
    repli par langue).
    """
    lexicon_for(lang)                    # garantit le chargement
    return _STRESS_CACHE.get(lang, {})


def lexicon_size(lang: str) -> int:
    """Nombre d'entrées chargées (0 si le lexique est absent)."""
    return len(lexicon_for(lang))


def reset_cache(lang: Optional[str] = None) -> None:
    """Invalide le cache (tests / échange de fichier)."""
    if lang is None:
        _CACHE.clear()
        _STRESS_CACHE.clear()
    else:
        _CACHE.pop(lang, None)
        _STRESS_CACHE.pop(lang, None)


def has_lexicon(lang: str) -> bool:
    """True si le fichier TSV de ``lang`` est présent sur disque."""
    spec = LEXICONS[lang]
    return (Path(os.environ.get(spec.env_var,
                                str(_DATA_DIR / spec.filename))).exists())


__all__ = [
    'LexiconSpec', 'LEXICONS', 'load_lexicon', 'lexicon_for',
    'lexicon_size', 'reset_cache', 'has_lexicon', 'ipa_to_keys',
    'ipa_to_keys_stress', 'stress_for',
]
