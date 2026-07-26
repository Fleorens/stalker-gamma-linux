"""Internationalisation (gettext) : anglais par défaut, autres langues en traduction.

Le texte source du code (msgid) est en anglais — c'est donc la langue de
repli automatique dès qu'aucune traduction n'est chargée ou que la locale
demandée n'a pas de fichier `.mo` correspondant (comportement standard de
`gettext.translation(..., fallback=True)`). La locale effective suit les
variables d'environnement POSIX usuelles (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`,
`LANG`), sans configuration supplémentaire — comme n'importe quelle appli
GTK/gettext.

Traductions disponibles : voir `locale/<code>/LC_MESSAGES/stalker-gamma-linux.po`
(compilées en `.mo` par `make compile-messages`, voir docs/ARCHITECTURE.md).

Usage : `from stalker_gamma_linux.i18n import _` puis `_("Texte anglais")`.
"""

from __future__ import annotations

import gettext
import importlib.resources
from collections.abc import Callable

DOMAIN = "stalker-gamma-linux"


def _locale_dir() -> str:
    """Répertoire `locale/` embarqué dans le paquet installé."""
    return str(importlib.resources.files("stalker_gamma_linux") / "locale")


def _load_translation() -> gettext.NullTranslations:
    """`NullTranslations` (= identité) si aucun `.mo` ne correspond à la locale courante."""
    return gettext.translation(
        DOMAIN, localedir=_locale_dir(), languages=None, fallback=True
    )


_translation = _load_translation()

gettext_: Callable[[str], str] = _translation.gettext
ngettext: Callable[[str, str, int], str] = _translation.ngettext

# Alias conventionnel (`_`) : import explicite requis (`from ... import _`),
# jamais installé globalement (`install()`) pour rester grep-able/testable.
_ = gettext_
