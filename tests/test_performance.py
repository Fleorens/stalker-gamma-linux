"""Couches de performance (T20) : composition, configuration, diagnostic.

Ce que ces tests protègent, dans l'ordre d'importance :

1. **l'ordre d'emboîtement** — gamemoderun au contact d'umu-run, les couches
   Vulkan dans l'environnement et nulle part ailleurs. Une inversion ici ne se
   voit qu'à l'écran, sur une vraie machine ;
2. **l'absence d'effet de bord** — ni la commande, ni `os.environ` ne bougent ;
3. **le silence quand l'outil manque** — c'est la promesse de GameMode depuis
   T02, étendue aux trois nouveaux outils ;
4. **le format des fichiers que nous écrivons**, que seule une lecture attentive
   des parseurs amont permet de vérifier sans lancer le jeu.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.environment import (
    checks,
    mangohud,
    performance,
    system,
    vkbasalt,
    vulkan,
)
from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import Status
from stalker_gamma_linux.environment.performance import Settings
from stalker_gamma_linux.mo2 import launch, session
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths

UMU = "/usr/bin/umu-run"
GAMEMODERUN = "/usr/bin/gamemoderun"
COMMAND = (UMU, "ModOrganizer.exe", "moshortcut://:Anomaly (DX11)")

_BINARIES = {"gamemoderun": GAMEMODERUN, "umu-run": UMU}


@pytest.fixture
def equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Machine où les trois outils sont installés."""
    monkeypatch.setattr(system, "which", lambda command: _BINARIES.get(command))
    monkeypatch.setattr(
        vulkan,
        "find_implicit_layer",
        lambda stem, environ=None: Path(f"/usr/share/vulkan/implicit_layer.d/{stem}.json"),
    )
    # Sans ça, `checks._abi_gap` interrogerait le vrai système : le verdict
    # dépendrait des paquets de la machine qui fait tourner les tests.
    monkeypatch.setattr(
        vulkan, "layer_abi_support", lambda stem, bits=64, environ=None: vulkan.AbiSupport.PRESENT
    )


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> None:
    """Machine où seul umu-run est installé — le cas de la plupart des joueurs."""
    monkeypatch.setattr(system, "which", lambda command: UMU if command == "umu-run" else None)
    monkeypatch.setattr(vulkan, "find_implicit_layer", lambda stem, environ=None: None)


def _all_layers() -> Settings:
    return Settings(mangohud=True, vkbasalt=True)


# --- Ordre d'emboîtement ----------------------------------------------------


@pytest.mark.usefixtures("equipped")
@pytest.mark.parametrize("mango", [False, True])
@pytest.mark.parametrize("basalt", [False, True])
def test_the_four_combinations_nest_in_the_documented_order(
    tmp_path: Path, mango: bool, basalt: bool
) -> None:
    """gamemoderun au contact d'umu-run, les couches Vulkan en variables."""
    settings = Settings(mangohud=mango, vkbasalt=basalt)

    layers = performance.compose(COMMAND, {}, settings, directory=tmp_path)

    assert list(layers.command) == [GAMEMODERUN, *COMMAND]
    # Les couches Vulkan ne touchent JAMAIS à la commande.
    assert mangohud.CONFIG_FILENAME not in " ".join(layers.command)
    assert (mangohud.ENABLE_VARIABLE in layers.environment) is mango
    assert (vkbasalt.ENABLE_VARIABLE in layers.environment) is basalt


@pytest.mark.usefixtures("equipped")
def test_gamemode_stays_at_the_contact_of_umu_run(tmp_path: Path) -> None:
    # C'est lui qui pose `libgamemodeauto.so.0` en LD_PRELOAD puis exec la
    # suite : il doit rester au contact du processus dont il veut la descendance.
    layers = performance.compose(COMMAND, {}, _all_layers(), directory=tmp_path)

    command = list(layers.command)
    assert command[0] == GAMEMODERUN
    assert command[1] == UMU


@pytest.mark.usefixtures("equipped")
def test_gamemode_can_be_turned_off_while_the_other_layers_stay(tmp_path: Path) -> None:
    settings = _all_layers().with_gamemode(False)

    layers = performance.compose(COMMAND, {}, settings, directory=tmp_path)

    assert GAMEMODERUN not in layers.command
    assert layers.command[0] == UMU
    assert mangohud.ENABLE_VARIABLE in layers.environment


# --- Aucune mutation --------------------------------------------------------


@pytest.mark.usefixtures("equipped")
def test_compose_mutates_neither_the_command_nor_the_environment(tmp_path: Path) -> None:
    command = list(COMMAND)
    environment = {"WINEPREFIX": "/prefix"}

    layers = performance.compose(command, environment, _all_layers(), directory=tmp_path)

    assert command == list(COMMAND)
    assert environment == {"WINEPREFIX": "/prefix"}
    assert layers.environment["WINEPREFIX"] == "/prefix"


@pytest.mark.usefixtures("equipped")
def test_compose_never_touches_os_environ(tmp_path: Path) -> None:
    before = dict(os.environ)

    performance.compose(COMMAND, {}, _all_layers(), directory=tmp_path)

    assert dict(os.environ) == before
    assert mangohud.ENABLE_VARIABLE not in os.environ


@pytest.mark.usefixtures("equipped")
def test_container_share_keeps_what_the_user_already_set(tmp_path: Path) -> None:
    # `PRESSURE_VESSEL_FILESYSTEMS_RO` est une liste façon PATH : écraser celle
    # de l'utilisateur lui retirerait l'accès à ses propres dossiers.
    environment = {performance.CONTAINER_SHARE_VARIABLE: "/hdd:/archives"}

    layers = performance.compose(COMMAND, environment, _all_layers(), directory=tmp_path)

    shared = layers.environment[performance.CONTAINER_SHARE_VARIABLE].split(":")
    assert shared[:2] == ["/hdd", "/archives"]
    assert str(tmp_path / mangohud.CONFIG_FILENAME) in shared
    assert str(tmp_path / vkbasalt.LUT_FILENAME) in shared


# --- Outils absents ---------------------------------------------------------


@pytest.mark.usefixtures("bare")
def test_every_layer_is_a_no_op_when_its_tool_is_missing(tmp_path: Path) -> None:
    layers = performance.compose(COMMAND, {"HOME": "/home/x"}, _all_layers(), directory=tmp_path)

    assert list(layers.command) == list(COMMAND)
    assert layers.environment == {"HOME": "/home/x"}


@pytest.mark.usefixtures("bare")
def test_write_configs_writes_nothing_for_a_missing_layer(tmp_path: Path) -> None:
    performance.write_configs(_all_layers(), tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("equipped")
def test_write_configs_only_writes_what_is_enabled(tmp_path: Path) -> None:
    performance.write_configs(Settings(mangohud=True), tmp_path)

    assert (tmp_path / mangohud.CONFIG_FILENAME).is_file()
    assert not (tmp_path / vkbasalt.CONFIG_FILENAME).exists()


# --- MangoHud ---------------------------------------------------------------


def test_mangohud_presets_differ_where_it_matters() -> None:
    light = mangohud.config_text(mangohud.Preset.LIGHT)
    full = mangohud.config_text(mangohud.Preset.FULL)

    # « fps + frametime » demande de *désactiver* ce que MangoHud affiche par
    # défaut : sans ces `=0`, le préset léger afficherait CPU et GPU.
    assert "cpu_stats=0" in light and "gpu_stats=0" in light
    assert "gpu_temp" in full and "vram" in full
    assert "cpu_stats=0" not in full


def test_mangohud_environment_points_at_our_file_only(tmp_path: Path) -> None:
    config = tmp_path / mangohud.CONFIG_FILENAME

    variables = mangohud.environment(config)

    assert variables == {"MANGOHUD": "1", "MANGOHUD_CONFIGFILE": str(config)}


def test_mangohud_config_says_it_is_generated(tmp_path: Path) -> None:
    # Le fichier est réécrit à chaque lancement : celui qui l'ouvre doit
    # l'apprendre là, pas en constatant que ses modifications disparaissent.
    written = mangohud.write_config(mangohud.Preset.FULL, tmp_path / "sub" / "mangohud.conf")

    assert written.read_text(encoding="utf-8").startswith("# Généré par stalker-gamma-linux")


@pytest.mark.usefixtures("equipped")
def test_the_global_mangohud_conf_is_never_touched(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    (home / ".config" / "MangoHud").mkdir(parents=True)
    user_config = home / ".config" / "MangoHud" / "MangoHud.conf"
    user_config.write_text("fps_limit=60\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    performance.write_configs(Settings(mangohud=True), tmp_path / "ours")

    assert user_config.read_text(encoding="utf-8") == "fps_limit=60\n"


# --- vkBasalt ---------------------------------------------------------------


def test_vkbasalt_config_chains_sharpening_then_grading(tmp_path: Path) -> None:
    lut = tmp_path / vkbasalt.LUT_FILENAME

    text = vkbasalt.config_text(lut)

    assert "effects = cas:lut" in text
    # Guillemets obligatoires : le parseur amont ignore les espaces hors chaîne,
    # et un dossier personnel peut en contenir.
    assert f'lutFile = "{lut}"' in text
    # Le piège documenté par Valve : un chemin de shaders introuvable dans le
    # conteneur fait crasher la couche. On n'en désigne aucun.
    assert "reshadeIncludePath" not in text
    assert "reshadeTexturePath" not in text


def test_vkbasalt_lut_follows_the_cube_format() -> None:
    text = vkbasalt.lut_text(size=5)
    lines = text.splitlines()
    data = [line for line in lines if line and not line.startswith("#")]

    assert data[0] == "LUT_3D_SIZE 5"
    assert len(data) == 1 + 5**3
    # Le parseur amont ne reconnaît une ligne de données qu'à son premier
    # caractère numérique : un « .5 » sans zéro devant serait ignoré.
    assert all(line[0].isdigit() for line in data[1:])
    assert all(0.0 <= float(value) <= 1.0 for line in data[1:] for value in line.split())


def test_vkbasalt_lut_keeps_black_grey_and_white_neutral() -> None:
    data = [
        line
        for line in vkbasalt.lut_text(size=17).splitlines()
        if line and not line.startswith("#") and line[0].isdigit()
    ]

    assert data[0].split() == ["0.000000"] * 3
    assert data[-1].split() == ["1.000000"] * 3
    # Nœud central (8, 8, 8) du cube 17³ : le gris moyen ne doit ni virer ni
    # changer de niveau — la courbe de contraste est fixe en 0,5.
    middle = data[(8 * 17 + 8) * 17 + 8].split()
    assert middle[0] == middle[1] == middle[2]
    assert abs(float(middle[0]) - 0.5) < 1e-6


def test_vkbasalt_lut_actually_adds_contrast() -> None:
    data = [
        line
        for line in vkbasalt.lut_text(size=17).splitlines()
        if line and not line.startswith("#") and line[0].isdigit()
    ]
    quarter = data[(4 * 17 + 4) * 17 + 4].split()

    # Un gris à 25 % doit ressortir plus sombre : c'est la courbe en S.
    assert float(quarter[0]) < 0.25


def test_vkbasalt_environment_points_at_our_file_only(tmp_path: Path) -> None:
    config = tmp_path / vkbasalt.CONFIG_FILENAME

    assert vkbasalt.environment(config) == {
        "ENABLE_VKBASALT": "1",
        "VKBASALT_CONFIG_FILE": str(config),
    }


@pytest.mark.usefixtures("equipped")
def test_the_vkbasalt_preset_ships_its_own_lut(tmp_path: Path) -> None:
    performance.write_configs(Settings(vkbasalt=True), tmp_path)

    lut = tmp_path / vkbasalt.LUT_FILENAME
    assert lut.is_file()
    assert str(lut) in (tmp_path / vkbasalt.CONFIG_FILENAME).read_text(encoding="utf-8")


# --- Découverte des couches Vulkan ------------------------------------------


def test_implicit_layer_dirs_follow_the_loader_search_path() -> None:
    directories = vulkan.implicit_layer_dirs(
        {"XDG_DATA_HOME": "/home/x/.local/share", "XDG_DATA_DIRS": "/usr/local/share:/usr/share"}
    )

    home = Path("/home/x/.local/share/vulkan/implicit_layer.d")
    system_wide = Path("/usr/share/vulkan/implicit_layer.d")

    assert home in directories
    assert system_wide in directories
    # Ordre significatif : le loader retient le premier manifeste trouvé.
    assert directories.index(home) < directories.index(system_wide)


def test_find_implicit_layer_matches_the_upstream_casing(tmp_path: Path) -> None:
    # Le nom du manifeste suit le projet amont (`MangoHud.x86.json`), pas la
    # casse de la distribution : chercher « mangohud » doit le trouver.
    directory = tmp_path / "share" / "vulkan" / "implicit_layer.d"
    directory.mkdir(parents=True)
    (directory / "MangoHud.x86.json").write_text("{}", encoding="utf-8")

    found = vulkan.find_implicit_layer("mangohud", {"XDG_DATA_DIRS": str(tmp_path / "share")})

    assert found == directory / "MangoHud.x86.json"


def test_find_implicit_layer_returns_none_without_the_directory(tmp_path: Path) -> None:
    assert vulkan.find_implicit_layer("vkBasalt", {"XDG_DATA_DIRS": str(tmp_path)}) is None


# --- Diagnostic (`doctor`) --------------------------------------------------


@pytest.mark.usefixtures("equipped")
def test_the_three_tools_are_reported_as_available() -> None:
    for requirement in (
        checks.check_mangohud(DistroFamily.FEDORA),
        checks.check_vkbasalt(DistroFamily.FEDORA),
    ):
        assert requirement.status is Status.OK


@pytest.mark.usefixtures("bare")
@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (checks.check_mangohud, "sudo dnf install mangohud"),
        (checks.check_vkbasalt, "sudo dnf install vkBasalt"),
    ],
)
def test_absent_tools_are_optional_never_blocking(check: Any, expected: str) -> None:
    requirement = check(DistroFamily.FEDORA)

    assert requirement.status is Status.OPTIONAL
    assert not requirement.blocks_install
    assert requirement.install_hint is not None
    assert requirement.install_hint.startswith(expected)


@pytest.mark.usefixtures("bare")
def test_arch_gets_the_aur_route_for_vkbasalt() -> None:
    # `pacman -S vkbasalt` n'existe pas : ni extra ni multilib ne l'empaquettent.
    hint = checks.check_vkbasalt(DistroFamily.ARCH).install_hint

    assert hint is not None
    assert "pacman" not in hint
    assert "AUR" in hint


@pytest.mark.usefixtures("bare")
def test_arch_gets_the_32_bit_mangohud_package() -> None:
    hint = checks.check_mangohud(DistroFamily.ARCH).install_hint

    assert hint is not None
    assert hint.startswith("sudo pacman -S mangohud lib32-mangohud")


# --- ABI de la couche (le manifeste ne suffit pas) ---------------------------
#
# Régression du 2026-09-08 : sur la machine de dev, seul `vkBasalt.i686` était
# installé. Le manifeste — unique et partagé entre les deux RPM — était bien là,
# `doctor` annonçait « [ OK ] vkBasalt », et la couche ne se chargeait pas :
# le jeu est un processus 64 bits, et `/usr/lib64/vkbasalt/` n'existait pas.
# Échec strictement silencieux, mesuré dans le conteneur (zéro occurrence de
# `VK_LAYER_VKBASALT`).


def _elf(path: Path, bits: int) -> Path:
    """Fichier réduit à son en-tête ELF — c'est tout ce que `elf_bits` lit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x7fELF" + bytes([2 if bits == 64 else 1]) + b"\x00" * 11)
    return path


def _manifest(directory: Path, name: str, library: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        json.dumps({"layer": {"name": "VK_LAYER_X", "library_path": library}}), encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(("bits", "expected"), [(32, 32), (64, 64)])
def test_elf_bits_reads_the_class_byte(tmp_path: Path, bits: int, expected: int) -> None:
    assert vulkan.elf_bits(_elf(tmp_path / "lib.so", bits)) == expected


def test_elf_bits_is_none_for_anything_that_is_not_an_elf(tmp_path: Path) -> None:
    text = tmp_path / "not-elf.so"
    text.write_text("#!/bin/sh\n", encoding="utf-8")

    assert vulkan.elf_bits(text) is None
    assert vulkan.elf_bits(tmp_path / "absent.so") is None


def test_lib_token_expands_to_every_known_layout(tmp_path: Path) -> None:
    # `$LIB` vaut `lib64` sur Fedora/Arch et `lib/x86_64-linux-gnu` sur Debian :
    # on ne devine pas, on essaie: c'est la classe ELF qui tranchera.
    manifest = _manifest(tmp_path, "vkBasalt.json", "/usr/$LIB/vkbasalt/libvkbasalt.so")

    candidates = vulkan.library_candidates(manifest, "/usr/$LIB/vkbasalt/libvkbasalt.so")

    assert Path("/usr/lib64/vkbasalt/libvkbasalt.so") in candidates
    assert Path("/usr/lib/x86_64-linux-gnu/vkbasalt/libvkbasalt.so") in candidates


def test_a_bare_soname_yields_no_candidate(tmp_path: Path) -> None:
    # `libVkLayer_MESA_device_select.so` : c'est l'éditeur de liens qui résout.
    # On ne peut rien affirmer, donc on ne propose rien (→ UNKNOWN plus loin).
    manifest = _manifest(tmp_path, "x.json", "libfoo.so")

    assert vulkan.library_candidates(manifest, "libfoo.so") == ()


def test_a_relative_library_resolves_against_the_manifest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, "x.json", "./libfoo.so")

    assert vulkan.library_candidates(manifest, "./libfoo.so") == (tmp_path / "libfoo.so",)


def test_manifest_library_reads_both_upstream_shapes(tmp_path: Path) -> None:
    single = tmp_path / "single.json"
    single.write_text('{"layer": {"library_path": "/a.so"}}', encoding="utf-8")
    plural = tmp_path / "plural.json"
    plural.write_text('{"layers": [{"library_path": "/b.so"}]}', encoding="utf-8")

    assert vulkan.manifest_library(single) == "/a.so"
    assert vulkan.manifest_library(plural) == "/b.so"


@pytest.mark.parametrize("content", ["not json", "[]", "{}", '{"layer": {}}'])
def test_manifest_library_never_raises_on_junk(tmp_path: Path, content: str) -> None:
    path = tmp_path / "junk.json"
    path.write_text(content, encoding="utf-8")

    assert vulkan.manifest_library(path) is None


def test_abi_support_is_present_when_the_right_class_exists(tmp_path: Path) -> None:
    layers = tmp_path / "share" / "vulkan" / "implicit_layer.d"
    _manifest(layers, "MangoHud.x86.json", str(_elf(tmp_path / "lib" / "m.so", 32)))
    _manifest(layers, "MangoHud.x86_64.json", str(_elf(tmp_path / "lib64" / "m.so", 64)))
    environ = {"XDG_DATA_DIRS": str(tmp_path / "share")}

    assert vulkan.layer_abi_support("MangoHud", 64, environ) is vulkan.AbiSupport.PRESENT
    assert vulkan.layer_abi_support("MangoHud", 32, environ) is vulkan.AbiSupport.PRESENT


def test_abi_support_is_missing_when_only_the_other_class_is_installed(tmp_path: Path) -> None:
    # Le cas exact de la régression : manifeste présent, 32 bits seulement.
    layers = tmp_path / "share" / "vulkan" / "implicit_layer.d"
    _manifest(layers, "vkBasalt.json", str(_elf(tmp_path / "lib" / "vkbasalt.so", 32)))
    environ = {"XDG_DATA_DIRS": str(tmp_path / "share")}

    assert vulkan.layer_abi_support("vkBasalt", 64, environ) is vulkan.AbiSupport.MISSING


def test_abi_support_stays_unknown_when_nothing_can_be_resolved(tmp_path: Path) -> None:
    # Ne pas savoir n'est pas une raison d'alarmer : un soname nu ne prouve rien.
    layers = tmp_path / "share" / "vulkan" / "implicit_layer.d"
    _manifest(layers, "vkBasalt.json", "libvkbasalt.so")
    environ = {"XDG_DATA_DIRS": str(tmp_path / "share")}

    assert vulkan.layer_abi_support("vkBasalt", 64, environ) is vulkan.AbiSupport.UNKNOWN


def test_doctor_reports_the_abi_gap_instead_of_a_green_light(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vulkan,
        "find_implicit_layer",
        lambda stem, environ=None: Path(f"/usr/share/vulkan/implicit_layer.d/{stem}.json"),
    )
    monkeypatch.setattr(
        vulkan, "layer_abi_support", lambda stem, bits=64, environ=None: vulkan.AbiSupport.MISSING
    )

    requirement = checks.check_vkbasalt(DistroFamily.FEDORA)

    assert requirement.status is Status.OPTIONAL
    assert "64-bit" in requirement.detail
    # Cosmétique : signalé, jamais bloquant pour l'installation.
    assert not requirement.blocks_install
    assert requirement.install_hint is not None
    assert requirement.install_hint.startswith("sudo dnf install vkBasalt")


def test_an_unknown_abi_never_downgrades_the_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vulkan,
        "find_implicit_layer",
        lambda stem, environ=None: Path(f"/usr/share/vulkan/implicit_layer.d/{stem}.json"),
    )
    monkeypatch.setattr(
        vulkan, "layer_abi_support", lambda stem, bits=64, environ=None: vulkan.AbiSupport.UNKNOWN
    )

    assert checks.check_mangohud(DistroFamily.FEDORA).status is Status.OK


# --- Sérialisation des préférences ------------------------------------------


def test_settings_round_trip_through_a_mapping() -> None:
    settings = Settings(
        gamemode=False,
        mangohud=True,
        mangohud_preset=mangohud.Preset.FULL,
        vkbasalt=True,
    )

    assert performance.from_mapping(performance.as_mapping(settings)) == settings


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"mangohud_preset": "moche"},
        {"gamemode": "oui"},
        # Clés d'une version antérieure : ignorées, jamais une exception.
        {"gamescope": True, "gamescope_render": "1280x720"},
    ],
)
def test_a_hand_edited_file_never_raises(data: dict[str, object]) -> None:
    settings = performance.from_mapping(data)

    assert isinstance(settings, Settings)


def test_from_mapping_falls_back_field_by_field() -> None:
    base = Settings(gamemode=False, vkbasalt=True)

    settings = performance.from_mapping({"mangohud": True}, base)

    assert settings.mangohud
    assert settings.gamemode is False
    assert settings.vkbasalt is True


# --- Câblage jusqu'au lancement ---------------------------------------------


class _FakePopen:
    def __init__(self, command: list[str], **kwargs: Any) -> None:
        self.command = command
        self.kwargs = kwargs


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> list[_FakePopen]:
    calls: list[_FakePopen] = []

    def factory(command: list[str], **kwargs: Any) -> _FakePopen:
        calls.append(_FakePopen(command, **kwargs))
        return calls[-1]

    monkeypatch.setattr(subprocess, "Popen", factory)
    return calls


@pytest.mark.usefixtures("equipped")
def test_run_detached_applies_the_layers_and_logs_the_variables(
    tmp_path: Path, popen: list[_FakePopen], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(performance, "config_dir", lambda: tmp_path / "config")
    prefix = PrefixPaths.under(tmp_path)

    log_path = process.run_detached(
        "ModOrganizer.exe",
        paths=prefix,
        proton_path=tmp_path / "GE",
        performance=Settings(mangohud=True),
    )

    assert popen[0].command[0] == GAMEMODERUN
    assert popen[0].kwargs["env"]["MANGOHUD"] == "1"
    # Le journal porte les variables : « l'overlay ne s'affiche pas » se
    # diagnostique d'abord en vérifiant qu'elles ont bien été posées.
    log = log_path.read_text(encoding="utf-8")
    assert "# MANGOHUD=1" in log
    assert log.count("$ ") == 1


@pytest.mark.usefixtures("equipped")
def test_install_steps_never_get_a_performance_layer(
    tmp_path: Path, popen: list[_FakePopen]
) -> None:
    # Même frontière que GameMode : un compositeur ou un overlay pendant un
    # téléchargement de 146 Gio n'a aucun sens.
    process.run_detached(
        "createprefix", paths=PrefixPaths.under(tmp_path), proton_path=tmp_path / "GE"
    )

    assert popen[0].command[0] == UMU
    assert "MANGOHUD" not in popen[0].kwargs["env"]


@pytest.mark.usefixtures("equipped")
def test_opening_mo2_alone_never_gets_a_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: dict[str, Any] = {}
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    mo2.executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        process,
        "run_in_prefix",
        lambda exe, args=(), **kw: recorded.update(kw) or Path("/logs/mo2.log"),
    )

    launch.launch_mo2(mo2, PrefixPaths.under(tmp_path), tmp_path / "GE")

    assert "performance" not in recorded


# --- Messages de lancement --------------------------------------------------


@pytest.mark.usefixtures("equipped")
def test_notices_only_mention_the_layers_that_were_asked_for() -> None:
    notices = "\n".join(session.performance_notices(Settings()))

    assert "GameMode" in notices
    assert "MangoHud" not in notices
    assert "vkBasalt" not in notices


@pytest.mark.usefixtures("bare")
def test_a_requested_but_missing_layer_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sans ce message, une case cochée et aucun overlay à l'écran = une heure
    # perdue à chercher du côté du jeu.
    monkeypatch.setattr(
        session,
        "detect_distro",
        lambda: Distro(family=DistroFamily.FEDORA, pretty_name="Fedora Linux 44"),
    )

    notices = "\n".join(session.performance_notices(_all_layers()))

    assert "sudo dnf install mangohud" in notices
    assert "sudo dnf install vkBasalt" in notices
