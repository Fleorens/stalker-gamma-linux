"""Groupe « Performance » de la fenêtre Préférences : GameMode, MangoHud, vkBasalt.

Sorti de `preferences.py` parce que c'est le seul groupe qui a un état
composite : les autres réglages sont une valeur par ligne, celui-ci assemble un
`environment.performance.Settings` complet à partir de huit widgets. La logique
d'assemblage vit donc avec les widgets, et `preferences.py` ne connaît que la
propriété `settings`.

Chaque interrupteur reste actionnable même si l'outil n'est pas installé : la
préférence est persistée et s'appliquera dès que le paquet sera là. Le
sous-titre donne alors la commande d'installation de la distribution courante,
plutôt qu'une ligne grisée qui n'explique rien — même parti pris que pour
GameMode depuis T08.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from stalker_gamma_linux.environment import checks, gamemode  # noqa: E402
from stalker_gamma_linux.environment import mangohud as mangohud_layer  # noqa: E402
from stalker_gamma_linux.environment import vkbasalt as vkbasalt_layer  # noqa: E402
from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS  # noqa: E402
from stalker_gamma_linux.environment.distro import detect_distro  # noqa: E402
from stalker_gamma_linux.environment.performance import Settings  # noqa: E402
from stalker_gamma_linux.i18n import _  # noqa: E402

_PRESET_ORDER = (mangohud_layer.Preset.LIGHT, mangohud_layer.Preset.FULL)


def _install_hint(key: str) -> str | None:
    return INSTALL_COMMANDS[key].for_family(detect_distro().family)


def _subtitle(*, available: bool, description: str, key: str) -> str:
    """Ce que fait la couche, et — si elle manque — comment l'installer."""
    if available:
        return description
    hint = _install_hint(key)
    missing = _("{description} Not installed yet.").format(description=description)
    return f"{missing} {hint}" if hint else missing


def _gamemode_subtitle() -> str:
    """Sous-titre de GameMode : la même phrase que `doctor`, groupe polkit compris."""
    if gamemode.is_available():
        # Un utilisateur qui a lu `doctor` ne doit pas découvrir un état
        # différent ici (cf. `checks.gamemode_detail`).
        return checks.gamemode_detail()
    return _subtitle(
        available=False,
        description=_("Performance CPU governor and priorities while you play."),
        key="gamemode",
    )


class PerformanceGroup(Adw.PreferencesGroup):
    """Les trois couches, et la seule règle qui les gouverne : rien sans demande."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            title=_("Performance"),
            description=_(
                "Off by default, on purpose: these layers change how the game renders "
                "and performs, and « nothing enabled » must stay something you can say "
                "without checking. GameMode is the exception — it only raises system "
                "priorities while you play."
            ),
        )
        self._gamemode_row = Adw.SwitchRow(
            title=_("GameMode while playing"),
            subtitle=_gamemode_subtitle(),
            active=settings.gamemode,
        )
        self.add(self._gamemode_row)
        self.add(self._build_mangohud(settings))
        self._vkbasalt_row = Adw.SwitchRow(
            title="vkBasalt",
            subtitle=_subtitle(
                available=vkbasalt_layer.is_available(),
                description=_(
                    "« ReShade-like » preset: CAS sharpening plus a bit of colour "
                    "grading — the Linux answer to the ReShade the install removes. "
                    "The Home key toggles it in game."
                ),
                key="vkbasalt",
            ),
            active=settings.vkbasalt,
        )
        self.add(self._vkbasalt_row)

    def _build_mangohud(self, settings: Settings) -> Adw.ExpanderRow:
        self._mangohud_row = Adw.ExpanderRow(
            title="MangoHud",
            subtitle=_subtitle(
                available=mangohud_layer.is_available(),
                description=_("In-game overlay. Shift_R+F12 hides it without leaving the game."),
                key="mangohud",
            ),
            show_enable_switch=True,
            enable_expansion=settings.mangohud,
        )
        self._preset_row = Adw.ComboRow(
            title=_("Preset"),
            model=Gtk.StringList.new(
                [
                    _("Light — FPS and frametime"),
                    _("Full — CPU, GPU, VRAM, temperatures"),
                ]
            ),
            selected=_PRESET_ORDER.index(settings.mangohud_preset),
        )
        self._mangohud_row.add_row(self._preset_row)
        return self._mangohud_row

    @property
    def settings(self) -> Settings:
        """Réglages tels que les widgets les décrivent à cet instant."""
        return Settings(
            gamemode=self._gamemode_row.get_active(),
            mangohud=self._mangohud_row.get_enable_expansion(),
            mangohud_preset=_PRESET_ORDER[self._preset_row.get_selected()],
            vkbasalt=self._vkbasalt_row.get_active(),
        )
