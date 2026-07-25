"""Identité visuelle de la GUI : palette « Zone », feuille de style, assets.

Tout le style vit ici (aucun CSS inline dans les vues) : les vues posent des
classes (`hero-title`, `chip`, `console`, …) et ce module décide de leur
rendu. Thème sombre forcé — un installeur de modpack post-apo, pas une app
bureautique claire.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

# Palette centrale — reprise par la feuille de style ci-dessous.
ACCENT = "#8fc93a"  # vert toxique, plus lumineux que le libadwaita générique
ACCENT_DIM = "#5f8a2b"
FOREGROUND = "#e6f0d8"

_STYLE = f"""
@define-color accent_bg_color {ACCENT_DIM};
@define-color accent_fg_color #f4ffe6;
@define-color accent_color {ACCENT};

window.background {{ background-color: #10130c; }}

/* Header transparent : la fenêtre est un launcher, l'artwork passe dessous. */
.over-artwork headerbar {{
  background: none;
  box-shadow: none;
  border: none;
}}

/* Voile de lisibilité au-dessus de l'artwork, sous le contenu. */
.scrim {{
  background: linear-gradient(
    to bottom,
    alpha(#0b0e08, 0.55) 0%,
    alpha(#0b0e08, 0.10) 35%,
    alpha(#0b0e08, 0.42) 72%,
    alpha(#0b0e08, 0.88) 100%
  );
}}

.hero-title {{
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 4px;
  color: {FOREGROUND};
  text-shadow: 0 2px 14px alpha(black, 0.85);
}}

.hero-subtitle {{
  font-size: 13px;
  color: alpha({FOREGROUND}, 0.72);
  text-shadow: 0 1px 8px alpha(black, 0.9);
}}

/* Puce d'état système (accueil) et badges d'espace disque (dialog install). */
.chip {{
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
  background-color: alpha(white, 0.08);
  border: 1px solid alpha(white, 0.12);
  color: alpha({FOREGROUND}, 0.85);
}}
.chip-ok {{
  background-color: alpha({ACCENT}, 0.16);
  border-color: alpha({ACCENT}, 0.45);
  color: #c4e88e;
}}
.chip-warn {{
  background-color: alpha(#e5a50a, 0.16);
  border-color: alpha(#e5a50a, 0.45);
  color: #f5c211;
}}
.chip-error {{
  background-color: alpha(#e01b24, 0.16);
  border-color: alpha(#e01b24, 0.45);
  color: #f66151;
}}

/* Bouton principal JOUER / INSTALLER : le seul élément volontairement criard. */
.action-play {{
  background-image: linear-gradient(160deg, #9ad14b 0%, {ACCENT_DIM} 100%);
  color: #101505;
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 2px;
  border-radius: 999px;
  box-shadow: 0 4px 28px alpha({ACCENT}, 0.35), inset 0 1px 0 alpha(white, 0.25);
}}
.action-play:hover {{
  background-image: linear-gradient(160deg, #a9e05a 0%, #6f9e35 100%);
  box-shadow: 0 4px 36px alpha({ACCENT}, 0.55), inset 0 1px 0 alpha(white, 0.25);
}}
.action-play:active {{ background-image: linear-gradient(160deg, #86bd3d 0%, #567d27 100%); }}
.action-play:disabled {{
  background-image: none;
  background-color: alpha(white, 0.10);
  color: alpha(white, 0.35);
  box-shadow: none;
}}

/* Actions secondaires (MO2, mise à jour…) : verre sombre discret. */
.action-secondary {{
  background-color: alpha(white, 0.07);
  border: 1px solid alpha(white, 0.13);
  color: {FOREGROUND};
  font-weight: 700;
  border-radius: 999px;
}}
.action-secondary:hover {{ background-color: alpha(white, 0.13); }}

/* Carte « verre » posée sur l'artwork (timeline de phases, résumés). */
.glass {{
  background-color: alpha(#141a0e, 0.78);
  border: 1px solid alpha({ACCENT}, 0.14);
  border-radius: 14px;
}}

/* Console de log, façon terminal embarqué. */
.console {{
  background-color: alpha(black, 0.55);
  border: 1px solid alpha({ACCENT}, 0.12);
  border-radius: 10px;
}}
.console textview, .console text {{
  background-color: transparent;
  color: #a9c987;
  font-size: 12px;
}}

/* Timeline de phases (vue progression). */
.phase-pending {{ color: alpha({FOREGROUND}, 0.38); }}
.phase-running {{ color: {FOREGROUND}; font-weight: 700; }}
.phase-done {{ color: alpha(#c4e88e, 0.9); }}
.phase-skipped {{ color: alpha({FOREGROUND}, 0.55); }}
.phase-failed {{ color: #f66151; font-weight: 700; }}
/* Posé sur le label de détail lui-même : prime sur la classe d'état héritée
   de la ligne (couleur et graisse), quel que soit l'état de la phase. */
.phase-detail {{ font-size: 11px; font-weight: normal; color: alpha({FOREGROUND}, 0.5); }}

.progress-percent {{
  font-size: 13px;
  font-weight: 800;
  color: {ACCENT};
}}
.elapsed {{ font-size: 12px; color: alpha({FOREGROUND}, 0.55); }}

progressbar > trough {{ background-color: alpha(white, 0.10); }}
progressbar > trough > progress {{
  background-image: linear-gradient(90deg, {ACCENT_DIM}, {ACCENT});
  box-shadow: 0 0 10px alpha({ACCENT}, 0.5);
}}

/* Les PreferencesPage (Diagnostic) laissent voir le fond de fenêtre sombre. */
.over-artwork preferencespage scrolledwindow,
.over-artwork preferencespage viewport {{ background: transparent; }}
"""


def asset(name: str) -> Path:
    """Chemin d'un asset embarqué du paquet (icône, artwork de fond)."""
    return Path(str(importlib.resources.files("stalker_gamma_linux") / "assets" / name))


def install_theme() -> None:
    """Force le thème sombre et installe la feuille de style sur l'affichage.

    À appeler une fois au démarrage (`Application.do_startup`), après
    l'initialisation de GTK. Sans affichage (tests headless), ne fait rien.
    """
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(_STYLE)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
