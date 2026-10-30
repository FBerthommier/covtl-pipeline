# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""
setlang.py
==========
Multilingual language registry for the covtl-pipeline.

This module is the single entry point for selecting the active language
profile of the engine. A language profile bundles together:

  * a grapheme-to-phoneme gateway (``g2p_callable``) — converts
    orthographic text into engine SAMPA, with the same signature as
    :func:`vtl_synth.utils.g2p.text_to_sampa`;
  * an optional notation alias map (``notation_alias``) — extra
    char/SAMPA substitutions layered on top of ``notation.CHAR_ALIAS``
    (useful when a language needs symbols that conflict with another
    language's conventions, e.g. 'r' → French uvular R vs English /r/
    alveolar approximant R);
  * an F0 declination profile (``f0_base``, ``onset_gain``,
    ``final_gain``) — language-specific intonation contour, consumed
    by :func:`vtl_synth.core.pipeline.apply_f0_declination`;
  * default syllabic timings (``t_cons_ms``, ``t_voy_ms``,
    ``pause_short_ms``, ``pause_long_ms``) — language-specific rhythm
    defaults (e.g. French has a flatter syllabic rhythm than English).

Six profiles are bundled (v1.0.7):

  * ``'en'`` — English (default): CMUdict g2p (delegates to
    :mod:`vtl_synth.utils.g2p`); Pierrehumbert-style ToBI-adjacent F0
    contour (mild onset rise +6 %, modest final fall −15 %).
  * ``'fr'`` — French: rule-based g2p + small exceptions dictionary
    (delegates to :mod:`vtl_synth.utils.g2p_fr`); Jun & Fougeron (2002)
    declarative contour (onset +3 %, final fall −15 %) — already the
    pipeline default; the profile makes it explicit per-language.
  * ``'es'`` — Español (castillan): lexique Wikipron + règles
    (:mod:`vtl_synth.utils.g2p_es`); montée pré-nucléaire large puis
    descente contenue (Face 2003 : onset +8 %, final −15 %).
  * ``'de'`` — Deutsch: lexique Wikipron + règles
    (:mod:`vtl_synth.utils.g2p_de`); chute nucléaire tardive et
    profonde (Grice et al. 2005 : onset +3 %, final −20 %).
  * ``'it'`` — Italiano: lexique Wikipron + règles
    (:mod:`vtl_synth.utils.g2p_it`); montée accentuelle H+ puis chute
    douce (Avesani 1995 : onset +6 %, final −15 %).
  * ``'pt'`` — Português (européen): lexique Wikipron + règles
    (:mod:`vtl_synth.utils.g2p_pt`); chute nucléaire précoce à
    terminal bas (Frota 2000 : onset +4 %, final −20 %).

The active language is selected via :func:`setlang` and queried via
:func:`get_active_lang` / :func:`get_active_profile`. The Pipeline and
CLI consult the registry, so callers can either pass ``lang='fr'``
explicitly to :meth:`Pipeline.run` or set the global default once with
``setlang('fr')``.

Extensibility
-------------
New languages can be registered at runtime:

.. code-block:: python

    from vtl_synth.utils.setlang import LangProfile, register_profile

    register_profile(LangProfile(
        lang='es',
        g2p_callable=my_spanish_g2p,
        f0_base=110.0,
        onset_gain=1.04,
        final_gain=0.85,
        notation_alias={'ñ': 'J', 'll': 'j'},
    ))
    setlang('es')

Languages that are not yet implemented should raise ``NotImplementedError``
in their ``g2p_callable`` so callers get a clear error rather than silent
fall-through to English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from vtl_synth.utils.g2p import text_to_sampa as _g2p_en

# Expressive prosody (v1.0.8, option — défaut OFF) : paramètres par
# langue (accents de hauteur, respiration syntaxique). Import non
# critique : sans numpy le profil expressif est simplement absent.
try:
    from vtl_synth.utils.prosody_f0 import (
        ExpressivityProfile as _ExpressivityProfile,
        EXPRESSIVITY_PROFILES as _EXPRESSIVITY,
    )
except Exception:                                        # pragma: no cover
    _ExpressivityProfile = None
    _EXPRESSIVITY = {}

try:
    from vtl_synth.utils.g2p_fr import text_to_sampa_fr as _g2p_fr
except ImportError:                                        # pragma: no cover
    _g2p_fr = None                                          # defensive

try:
    from vtl_synth.utils.g2p_es import text_to_sampa_es as _g2p_es
except ImportError:                                        # pragma: no cover
    _g2p_es = None

try:
    from vtl_synth.utils.g2p_de import text_to_sampa_de as _g2p_de
except ImportError:                                        # pragma: no cover
    _g2p_de = None

try:
    from vtl_synth.utils.g2p_it import text_to_sampa_it as _g2p_it
except ImportError:                                        # pragma: no cover
    _g2p_it = None

try:
    from vtl_synth.utils.g2p_pt import text_to_sampa_pt as _g2p_pt
except ImportError:                                        # pragma: no cover
    _g2p_pt = None


# ===========================================================================
# Type aliases
# ===========================================================================

#: Signature of a g2p callable. Mirrors ``utils.g2p.text_to_sampa``.
G2PCallable = Callable[..., str]


# ===========================================================================
# LangProfile dataclass
# ===========================================================================

@dataclass
class LangProfile:
    """Bundle of language-specific behaviour for the engine.

    Parameters
    ----------
    lang : str
        ISO 639-1 code (lowercase, e.g. ``'en'``, ``'fr'``).
    g2p_callable : callable
        ``(text, warnings=None, **kwargs) -> str`` — converts orthographic
        text into engine SAMPA. Must match the signature of
        :func:`vtl_synth.utils.g2p.text_to_sampa`.
    f0_base : float
        Default F0 for this language (Hz). French declination reference
        uses 102.216 Hz (JD3 resting F0); other languages may differ.
    onset_gain : float
        Multiplier applied to ``f0_base`` at phrase onset (1.0 = no boost).
    final_gain : float
        Multiplier applied to ``f0_base`` at phrase final (1.0 = no fall).
    notation_alias : dict, optional
        Extra char → engine key substitutions, layered on top of
        ``notation.CHAR_ALIAS``. Use for language-specific graphemes.
    t_cons_ms : float
        Default consonant transition duration (ms).
    t_voy_ms : float
        Default vowel transition duration (ms).
    pause_short_ms : float
        Default inter-word pause (ms).
    pause_long_ms : float
        Default end-of-sentence pause (ms).
    display_name : str
        Human-readable name (e.g. ``'English'``).
    expressivity : ExpressivityProfile, optional
        Paramètres de prosodie expressive (v1.0.8, option — défaut
        off) : accents de hauteur, respiration syntaxique. None si
        le module prosody_f0 n'est pas disponible.
    """

    lang: str
    g2p_callable: G2PCallable
    f0_base: float = 102.216
    onset_gain: float = 1.03
    final_gain: float = 0.85
    notation_alias: Dict[str, str] = field(default_factory=dict)
    t_cons_ms: float = 100.0
    t_voy_ms: float = 80.0
    pause_short_ms: float = 200.0
    pause_long_ms: float = 320.0
    display_name: str = ''
    expressivity: Optional['_ExpressivityProfile'] = None

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.lang.upper()
        # Profil expressif par défaut de la langue : None reste None
        # pour les langues sans profil (langues personnalisées ou
        # prosody_f0 indisponible).
        if self.expressivity is None and _EXPRESSIVITY:
            self.expressivity = _EXPRESSIVITY.get(self.lang)


# ===========================================================================
# Default profiles (English + French)
# ===========================================================================

def _make_en_profile() -> LangProfile:
    """English profile — delegates to the existing CMUdict g2p."""
    return LangProfile(
        lang='en',
        g2p_callable=_g2p_en,
        f0_base=102.216,
        # English declarative contour is milder than French: weak onset
        # rise (~+6 %), gentle final fall (−15 %). Reference: ToBI
        # guidelines (Beckman & Ayers 1997) — informal summary.
        onset_gain=1.06,
        final_gain=0.85,
        # English has more durational contrast than French; keep the
        # pipeline defaults (Tcons 100 ms / Tvoy 80 ms).
        t_cons_ms=100.0,
        t_voy_ms=80.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        notation_alias={},  # notation.py defaults are EN-friendly
        display_name='English',
    )


def _make_fr_profile() -> LangProfile:
    """French profile — delegates to the rule-based French g2p."""
    if _g2p_fr is None:                                     # pragma: no cover
        raise ImportError(
            "g2p_fr module not available; the French profile requires "
            "vtl_synth/utils/g2p_fr.py"
        )
    return LangProfile(
        lang='fr',
        g2p_callable=_g2p_fr,
        f0_base=102.216,
        # Jun & Fougeron (2002) French declarative contour: slight
        # initial peak (+3 %), progressive declination, low final
        # fall (−15 %). This was the pipeline default before setlang;
        # the profile makes it language-explicit.
        onset_gain=1.03,
        final_gain=0.85,
        # French syllable-timed rhythm: par défaut Tcons=140 ms et
        # Tvoy=120 ms (v1.0.5). Ces valeurs allongent les transitions
        # consonantiques et vocaliques par rapport au profil anglais
        # (100/80 ms) pour une diction plus posée, conforme au rythme
        # syllabé français. Elles éliminent aussi les clicks résiduels
        # observés aux transitions trop rapides (cf. audit v1.0.4).
        t_cons_ms=140.0,
        t_voy_ms=120.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        # French notation aliases: notation.py already maps 'r' → R
        # (uvular) and handles accents. Extra aliases can be added
        # here if a French input uses non-standard conventions.
        notation_alias={
            'œ': '9', 'Œ': '9',
            'æ': 'a', 'Æ': 'a',
        },
        display_name='Français',
    )


def _make_es_profile() -> LangProfile:
    """Spanish (Castilian) profile — Wikipron lexicon + rules g2p."""
    if _g2p_es is None:                                     # pragma: no cover
        raise ImportError(
            "g2p_es module not available; the Spanish profile requires "
            "vtl_synth/utils/g2p_es.py"
        )
    return LangProfile(
        lang='es',
        g2p_callable=_g2p_es,
        f0_base=102.216,
        # Face (2001, 2003) / Prieto & Roseano (2010): Spanish broad
        # pre-nuclear rising accents (L+H*) and a moderate final
        # descent — the onset rise is marked, the final fall remains
        # contained (no low-terminal compression like German).
        onset_gain=1.08,
        final_gain=0.85,
        # Syllable-timed rhythm: transitions à mi-chemin entre en
        # (100/80) et fr (140/120) — consonnes nettes sans allonger
        # la voyelle.
        t_cons_ms=120.0,
        t_voy_ms=100.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        notation_alias={
            'ñ': 'J', 'Ñ': 'J',
            '¿': '', '¡': '',      # ponctuation inversée
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
        },
        display_name='Español',
    )


def _make_de_profile() -> LangProfile:
    """German profile — Wikipron lexicon + rules g2p."""
    if _g2p_de is None:                                     # pragma: no cover
        raise ImportError(
            "g2p_de module not available; the German profile requires "
            "vtl_synth/utils/g2p_de.py"
        )
    return LangProfile(
        lang='de',
        g2p_callable=_g2p_de,
        f0_base=102.216,
        # Grice et al. (2005) / Féry (1993): German nuclear fall is
        # late and steep (H+L* with low terminal) — the contour stays
        # high through the accent syllable then drops sharply: mild
        # onset, deep final (−20 %).
        onset_gain=1.03,
        final_gain=0.80,
        # Stress-timed language with dense clusters: consonant
        # transitions énergiques (100 ms), voyelles légèrement plus
        # longues que l'anglais (90 ms).
        t_cons_ms=100.0,
        t_voy_ms=90.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        notation_alias={
            'ß': 's', 'ä': 'E', 'ö': '2', 'ü': 'y',
            'Ä': 'E', 'Ö': '2', 'Ü': 'y',
        },
        display_name='Deutsch',
    )


def _make_it_profile() -> LangProfile:
    """Italian profile — Wikipron lexicon + rules g2p."""
    if _g2p_it is None:                                     # pragma: no cover
        raise ImportError(
            "g2p_it module not available; the Italian profile requires "
            "vtl_synth/utils/g2p_it.py"
        )
    return LangProfile(
        lang='it',
        g2p_callable=_g2p_it,
        f0_base=102.216,
        # Avesani (1995) / D'Imperio (2002): Italian declarative has a
        # clear pre-nuclear rise on the stressed syllable (H+) and a
        # gentle terminal fall — onset rise marked like Spanish,
        # final fall contained.
        onset_gain=1.06,
        final_gain=0.85,
        # Syllable-timed, vowels sustained (no reduction): same
        # cadence as Spanish.
        t_cons_ms=120.0,
        t_voy_ms=100.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        notation_alias={
            'é': 'e', 'è': 'E', 'à': 'a', 'ì': 'i', 'ò': 'O',
            'ó': 'o', 'ù': 'u',
        },
        display_name='Italiano',
    )


def _make_pt_profile() -> LangProfile:
    """European Portuguese profile — Wikipron lexicon + rules g2p."""
    if _g2p_pt is None:                                     # pragma: no cover
        raise ImportError(
            "g2p_pt module not available; the Portuguese profile "
            "requires vtl_synth/utils/g2p_pt.py"
        )
    return LangProfile(
        lang='pt',
        g2p_callable=_g2p_pt,
        f0_base=102.216,
        # Frota (2000, 2014): European Portuguese nuclear fall is
        # early and reaches a LOW terminal (H+L* L%), flatter pre-
        # nuclear stretch than Spanish — mild onset, deep final
        # (−20 %).
        onset_gain=1.04,
        final_gain=0.80,
        # Syllable-timed avec géminées et voyelles réduites : Cf cf es.
        t_cons_ms=110.0,
        t_voy_ms=100.0,
        pause_short_ms=200.0,
        pause_long_ms=320.0,
        notation_alias={
            'ã': '@~', 'õ': 'o~',          # EP : ã = /ɐ̃/
            'ç': 's', 'á': 'a', 'à': 'a', 'â': '@',
            'é': 'e', 'ê': 'e', 'í': 'i', 'ó': 'o', 'ô': 'o', 'ú': 'u',
        },
        display_name='Português',
    )


# ===========================================================================
# Registry
# ===========================================================================

class LangRegistry:
    """Registry of available language profiles.

    The registry is a thin wrapper around a dict; it enforces lang code
    normalisation (lowercase) and provides a clean error message when a
    language is not registered.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, LangProfile] = {}
        self._active: Optional[str] = None

    def register(self, profile: LangProfile) -> None:
        """Register a new language profile (overwrites if exists)."""
        code = profile.lang.lower()
        self._profiles[code] = profile
        if self._active is None:
            self._active = code

    def unregister(self, lang: str) -> None:
        """Remove a language profile (cannot remove the active one)."""
        code = lang.lower()
        if code == self._active:
            raise ValueError(
                f"cannot unregister the active language {lang!r}; "
                f"call setlang() to switch first"
            )
        self._profiles.pop(code, None)

    def get(self, lang: Optional[str] = None) -> LangProfile:
        """Return the profile for ``lang`` (or the active one if None)."""
        if lang is None:
            if self._active is None:
                raise LookupError(
                    "no language profile registered; call setlang() first"
                )
            return self._profiles[self._active]
        code = lang.lower()
        if code not in self._profiles:
            available = ', '.join(sorted(self._profiles.keys())) or '(none)'
            raise LookupError(
                f"language {lang!r} is not registered; available: {available}"
            )
        return self._profiles[code]

    def list(self) -> list:
        """Return a sorted list of registered language codes."""
        return sorted(self._profiles.keys())

    @property
    def active(self) -> Optional[str]:
        """The currently active language code (lowercase) or None."""
        return self._active

    def set_active(self, lang: str) -> LangProfile:
        """Set the active language and return its profile."""
        code = lang.lower()
        if code not in self._profiles:
            available = ', '.join(sorted(self._profiles.keys())) or '(none)'
            raise LookupError(
                f"cannot set active language to {lang!r}: not registered. "
                f"Available: {available}"
            )
        self._active = code
        return self._profiles[code]


# ===========================================================================
# Module-level singleton + public API
# ===========================================================================

_REGISTRY: LangRegistry = LangRegistry()


def register_profile(profile: LangProfile) -> None:
    """Register a language profile in the global registry."""
    _REGISTRY.register(profile)


def unregister_profile(lang: str) -> None:
    """Remove a language profile from the global registry."""
    _REGISTRY.unregister(lang)


def setlang(lang: str) -> LangProfile:
    """Set the active language for the pipeline.

    Parameters
    ----------
    lang : str
        Language code (ISO 639-1 lowercase, e.g. ``'en'``, ``'fr'``).

    Returns
    -------
    LangProfile
        The newly active profile (for chained access).

    Raises
    ------
    LookupError
        If ``lang`` is not registered. The error message lists the
        available languages.

    Example
    -------
    >>> from vtl_synth.utils.setlang import setlang
    >>> profile = setlang('fr')
    >>> profile.display_name
    'Français'
    """
    return _REGISTRY.set_active(lang)


def get_active_lang() -> str:
    """Return the code of the currently active language.

    Raises ``LookupError`` if no language has been registered yet.
    """
    if _REGISTRY.active is None:
        raise LookupError(
            "no active language; call setlang('en') or setlang('fr') first"
        )
    return _REGISTRY.active


def get_active_profile() -> LangProfile:
    """Return the currently active language profile."""
    return _REGISTRY.get(None)


def list_languages() -> list:
    """Return a sorted list of registered language codes."""
    return _REGISTRY.list()


def get_profile(lang: Optional[str] = None) -> LangProfile:
    """Return the profile for ``lang`` (or the active one if None)."""
    return _REGISTRY.get(lang)


def text_to_sampa(text: str, warnings: list = None,
                  lang: Optional[str] = None, **kwargs) -> str:
    """Dispatch text → SAMPA via the active (or specified) language g2p.

    This is the language-aware replacement for
    :func:`vtl_synth.utils.g2p.text_to_sampa`. It looks up the active
    profile (or the one specified by ``lang``) and delegates to its
    ``g2p_callable``.

    Parameters
    ----------
    text : str
        Orthographic input in the active language.
    warnings : list, optional
        Collector for non-fatal messages; passed through to the g2p.
    lang : str, optional
        Override the active language for this call only.
    **kwargs :
        Forwarded to the g2p callable (e.g. ``homograph_resolver`` for EN).

    Returns
    -------
    str
        Engine SAMPA sequence; phrases separated by ``|``.
    """
    profile = _REGISTRY.get(lang)
    return profile.g2p_callable(text, warnings=warnings, **kwargs)


# ===========================================================================
# Bootstrap: register built-in profiles
# ===========================================================================

# Register English first so 'en' is the default active language.
register_profile(_make_en_profile())
if _g2p_fr is not None:
    register_profile(_make_fr_profile())
if _g2p_es is not None:
    register_profile(_make_es_profile())
if _g2p_de is not None:
    register_profile(_make_de_profile())
if _g2p_it is not None:
    register_profile(_make_it_profile())
if _g2p_pt is not None:
    register_profile(_make_pt_profile())
# After bootstrap: 'en' is active by default; fr, es, de, it, pt
# available via setlang().
