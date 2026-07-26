"""Internationalisation (gettext) : anglais par défaut, autres langues en opt-in.

Le texte source du code (msgid) est en anglais, et c'est **toujours** la
langue affichée par défaut : contrairement au comportement standard de
`gettext.translation`, on ne suit PAS la locale système (`LANG`/`LC_ALL`/
`LC_MESSAGES`) — sinon un poste en `fr_FR.UTF-8` afficherait du français sans
que l'utilisateur l'ait demandé. Seule la variable `LANGUAGE` (override GNU
explicite) change la langue, ex. `LANGUAGE=fr stalker-gamma-linux doctor`.
Sans elle, `.mo` recherché pour `en` (qui n'existe pas, l'anglais étant déjà
le texte source) → repli `NullTranslations` → `msgid` retourné tel quel.

Traductions disponibles : voir `locale/<code>/LC_MESSAGES/stalker-gamma-linux.po`
(compilées en `.mo` par `make compile-messages`, voir docs/ARCHITECTURE.md).

Usage : `from stalker_gamma_linux.i18n import _` puis `_("Texte anglais")`.
"""

from __future__ import annotations

import gettext
import importlib.resources
import os
from collections.abc import Callable

DOMAIN = "stalker-gamma-linux"


def _locale_dir() -> str:
    """Répertoire `locale/` embarqué dans le paquet installé."""
    return str(importlib.resources.files("stalker_gamma_linux") / "locale")


def _requested_languages() -> list[str]:
    """`LANGUAGE` explicite si présent, sinon anglais — jamais `LANG`/`LC_ALL`."""
    override = os.environ.get("LANGUAGE")
    return override.split(":") if override else ["en"]


def _load_translation() -> gettext.NullTranslations:
    """`NullTranslations` (= identité, donc anglais) si aucune langue demandée n'a de `.mo`."""
    return gettext.translation(
        DOMAIN, localedir=_locale_dir(), languages=_requested_languages(), fallback=True
    )


_translation = _load_translation()

gettext_: Callable[[str], str] = _translation.gettext
ngettext: Callable[[str, str, int], str] = _translation.ngettext

# Alias conventionnel (`_`) : import explicite requis (`from ... import _`),
# jamais installé globalement (`install()`) pour rester grep-able/testable.
_ = gettext_
