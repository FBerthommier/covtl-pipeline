# SPDX-FileCopyrightText: 2026 Frédéric Berthommier
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Utilities: g2p gateway (CMUdict -> engine SAMPA) and helpers.

Multilingual support (v1.0.7): the :mod:`vtl_synth.utils.setlang`
module provides a language registry (``LangProfile`` +
``setlang(lang)``) that dispatches the g2p gateway, the F0
declination profile and the syllabic timings per language. Built-in
profiles: ``en`` (CMUdict), ``fr`` (lexique Wikipron + rules),
``es``, ``de``, ``it``, ``pt`` (lexique Wikipron + rules each).

To avoid the function/module name collision, the `setlang` function
is NOT re-exported at the package level. Access it via the module::

    from vtl_synth.utils.setlang import setlang, LangProfile
    setlang('fr')

or::

    from vtl_synth.utils import setlang as lang_module
    lang_module.setlang('fr')

This is the standard Python convention when a public function shares
its name with the containing module.
"""

# Re-export the multilingual API (but NOT setlang — it shadows the module).
from vtl_synth.utils.setlang import (
    LangProfile,
    LangRegistry,
    get_active_lang,
    get_active_profile,
    get_profile,
    list_languages,
    register_profile,
    unregister_profile,
    text_to_sampa as text_to_sampa_lang,
)
