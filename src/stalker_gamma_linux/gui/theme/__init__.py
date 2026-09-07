"""Identité visuelle de la GUI : feuille de style, artworks, thème sombre.

La feuille elle-même vit dans `style.css`, à côté de ce fichier — du vrai CSS
relu comme du CSS, et non une chaîne Python où chaque accolade doit être
doublée. Ce module ne fait que la charger et exposer les assets.

Thème sombre forcé : c'est un launcher de modpack post-apo, pas une application
bureautique claire.
"""

from __future__ import annotations

import importlib.resources
import logging
from functools import lru_cache
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from stalker_gamma_linux.logging_setup import LOGGER_NAME  # noqa: E402

__all__ = ["asset", "install_theme", "parse_errors", "stylesheet", "texture"]

_LOGGER = logging.getLogger(LOGGER_NAME)

# Artwork de l'accueil, et sa variante d'ambiance pour les pages de contenu
# (floutée et assombrie à la génération, cf. `scripts/generate_background.py`).
BACKGROUND = "background.jpg"
BACKGROUND_BLUR = "background-blur.jpg"


def asset(name: str) -> Path:
    """Chemin d'un asset embarqué du paquet (icône, logo, artwork)."""
    return Path(str(importlib.resources.files("stalker_gamma_linux") / "assets" / name))


@lru_cache(maxsize=8)
def texture(name: str) -> Gdk.Texture | None:
    """Artwork décodé **une fois** pour toute l'application, ou `None` s'il manque.

    Chaque page posée sur l'artwork en affichait sa propre copie : trois
    `Gtk.Picture.new_for_filename` = trois décodages du même JPEG et trois
    textures de plusieurs Mio en mémoire, réinstanciées à chaque navigation.
    Le cache rend le partage explicite — une texture GDK est immuable, donc
    sûre à réutiliser dans autant de widgets qu'on veut.
    """
    path = asset(name)
    try:
        return Gdk.Texture.new_from_filename(str(path))
    except GLib.Error as error:
        # Paquet incomplet : les vues retombent sur le fond uni du thème.
        _LOGGER.warning("artwork illisible (%s) : %s", path, error.message)
        return None


def stylesheet() -> str:
    """Le CSS embarqué, tel qu'il sera chargé."""
    return (
        importlib.resources.files("stalker_gamma_linux.gui.theme")
        .joinpath("style.css")
        .read_text(encoding="utf-8")
    )


def _provider() -> tuple[Gtk.CssProvider, list[str]]:
    """Provider chargé, et les erreurs de syntaxe rencontrées en le chargeant.

    GTK n'échoue pas sur un CSS invalide : il ignore la déclaration fautive et
    continue. Sans écoute de `parsing-error`, une propriété mal orthographiée
    ne se voit qu'à l'œil, sur l'écran qu'on n'a pas rouvert.
    """
    errors: list[str] = []
    provider = Gtk.CssProvider()
    provider.connect(
        "parsing-error",
        lambda _provider, section, error: errors.append(f"{section.to_string()} : {error.message}"),
    )
    provider.load_from_string(stylesheet())
    return provider, errors


def parse_errors() -> tuple[str, ...]:
    """Erreurs de syntaxe de la feuille de style — vide si tout va bien."""
    return tuple(_provider()[1])


def install_theme() -> None:
    """Force le thème sombre et installe la feuille de style sur l'affichage.

    À appeler une fois au démarrage (`Application.do_startup`), après
    l'initialisation de GTK. Sans affichage (tests headless), ne fait rien.
    """
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider, errors = _provider()
    for error in errors:
        _LOGGER.warning("feuille de style : %s", error)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
