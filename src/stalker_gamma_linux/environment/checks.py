"""Vérifications individuelles composant l'EnvironmentReport."""

from __future__ import annotations

import re
from pathlib import Path

from stalker_gamma_linux import sizing
from stalker_gamma_linux.environment import (
    gamemode,
    mangohud,
    system,
    vkbasalt,
    vulkan,
)
from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import Requirement, Status
from stalker_gamma_linux.i18n import _

# ⚠ À VALIDER : seuil indicatif (support Flatpak/shortcuts non-Steam robuste).
MIN_PROTONTRICKS_VERSION = (1, 10)

# La GUI s'appuie sur `Adw.Dialog`, `Adw.AlertDialog` et `Adw.AboutDialog`,
# tous apparus en libadwaita 1.5. Constaté en CI : Debian 12 livre 1.2 et la
# fenêtre échouait sur une `AttributeError` brute. Ubuntu 24.04 a 1.5 — d'où le
# remplacement d'`Adw.Spinner` (1.6) par `Gtk.Spinner` dans les vues.
MIN_LIBADWAITA_VERSION = (1, 5)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

# CVE-2022-30333 : UnRAR < 6.12 laisse une archive .rar écrire hors du dossier
# d'extraction (traversée de répertoire via un lien symbolique). gamma-launcher
# extrait des centaines d'archives tierces récupérées sur ModDB avec cette
# bibliothèque : une libunrar vulnérable est ici un risque réel, pas théorique.
#
# ⚠ Deux numérotations coexistent chez RARLAB : la version *produit* annoncée
# « 6.12 » correspond aux *sources* 6.1.7 (tarball `unrarsrc-6.1.7.tar.gz`),
# et ce sont les sources que les distributions empaquettent. Le seuil est donc
# exprimé en version sources — le comparer à « 6.12 » (soit (6, 12)) déclarerait
# saines toutes les 6.1.x vulnérables.
MIN_LIBUNRAR_VERSION = (6, 1, 7)

# Comment relever la version de la *bibliothèque* installée, par famille.
#
# Pourquoi le gestionnaire de paquets, et pas les deux autres pistes :
# - le binaire `unrar` : il n'est PAS livré avec la bibliothèque (paquets
#   distincts sur les trois familles, cf. `commands.py`) — sur la machine de dev
#   Fedora, /lib64/libunrar.so est présent et `unrar` absent, donc la piste
#   échoue précisément là où on veut une réponse ; et sa bannière annonce la
#   version produit (« UNRAR 6.12 »), incomparable au seuil sans conversion ;
# - la chaîne de version dans le .so : elle n'y est pas (`strings` sur
#   /usr/lib64/libunrar.so ne rend aucune version), et le fichier n'a pas
#   davantage de suffixe exploitable (`libunrar.so` tout court sur Fedora) ;
# - le gestionnaire de paquets, lui, rapporte la version des sources — la seule
#   directement comparable au seuil — et existe par construction sur les trois
#   familles visées par `DistroFamily`.
#
# Debian/Ubuntu : requête par motif, parce que le paquet s'appelle `libunrar5`
# sur Debian et `libunrar5t64` sur Ubuntu 24.04 (transition time64) ; un nom
# figé raterait l'une des deux.
_LIBUNRAR_VERSION_QUERIES: dict[DistroFamily, tuple[str, ...]] = {
    DistroFamily.FEDORA: ("rpm", "-q", "--queryformat", "%{VERSION}\n", "libunrar"),
    DistroFamily.ARCH: ("pacman", "-Q", "libunrar"),
    DistroFamily.DEBIAN: ("dpkg-query", "-W", "-f=${Version}\n", "libunrar*"),
}


def _flatpak_app_installed(app_id: str) -> bool:
    # L'utilisateur peut avoir Steam/protontricks installés en Flatpak plutôt
    # qu'en paquet natif — repli de détection indépendant de notre packaging.
    if system.which("flatpak") is None:
        return False
    result = system.run(["flatpak", "info", app_id])
    return result.returncode == 0


def _parse_version(text: str) -> tuple[int, ...] | None:
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return tuple(int(group) for group in match.groups() if group is not None)


def check_steam(family: DistroFamily) -> Requirement:
    if system.which("steam") is not None:
        return Requirement(name="Steam", status=Status.OK, detail=_("Native Steam detected"))
    if _flatpak_app_installed("com.valvesoftware.Steam"):
        return Requirement(name="Steam", status=Status.OK, detail=_("Steam (Flatpak) detected"))
    # Facultatif : l'installation et le jeu passent par umu (runtime autonome),
    # Proton-GE est téléchargé depuis GitHub si absent. Steam ne sert qu'au
    # confort (Steam Input, mode Gaming du Deck via « jeu non-Steam ») et comme
    # source alternative de Proton — jamais requis par le pipeline.
    return Requirement(
        name="Steam",
        status=Status.OPTIONAL,
        detail=_(
            "absent — optional: useful for Steam Input / Gaming Mode (Deck), "
            "not needed to install or play (umu handles it)"
        ),
        install_hint=INSTALL_COMMANDS["steam"].for_family(family),
        key="steam",
    )


def check_umu(family: DistroFamily) -> Requirement:
    if system.which("umu-run") is not None:
        return Requirement(name="umu-launcher", status=Status.OK, detail=_("umu-run detected"))
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail=_("umu-run not found in PATH"),
        install_hint=INSTALL_COMMANDS["umu-launcher"].for_family(family),
        key="umu-launcher",
    )


def gamemode_detail() -> str:
    """Ce que GameMode fera réellement sur cette machine, groupe polkit compris.

    Partagé entre `doctor` et la fenêtre de préférences pour que les deux disent
    exactement la même chose. Le cas « pas dans le groupe » est le piège décrit
    dans `environment.gamemode` : tout a l'air de marcher, mais le gouverneur CPU
    ne bouge jamais — autant le dire avec le `usermod` qui le débloque.
    """
    if gamemode.group_status() is gamemode.GroupStatus.MISSING:
        return _(
            "gamemoderun detected, but the CPU governor stays locked: run "
            "`sudo usermod -aG {group} $USER` — effective on the next launch "
            "(I/O and scheduling priorities work regardless)"
        ).format(group=gamemode.GAMEMODE_GROUP)
    return _(
        "gamemoderun detected — applied automatically when you play "
        "(the daemon starts on demand, « inactive » in between is normal)"
    )


def check_gamemode(family: DistroFamily) -> Requirement:
    """Feral GameMode : facultatif, appliqué automatiquement au lancement du jeu.

    On teste `gamemoderun` (le script qui *demande* le mode), pas l'état du
    daemon : celui-ci est activé à la demande par D-Bus, donc « inactive » entre
    deux parties est normal — le dire ici évite la fausse piste du
    `systemctl --user enable gamemoded` (cf. `environment.gamemode`).
    """
    if gamemode.is_available():
        return Requirement(name="GameMode", status=Status.OK, detail=gamemode_detail())
    return Requirement(
        name="GameMode",
        status=Status.OPTIONAL,
        detail=_(
            "absent — optional: performance CPU governor and priorities while "
            "you play, applied automatically once installed"
        ),
        install_hint=INSTALL_COMMANDS["gamemode"].for_family(family),
        key="gamemode",
        needed_to_install=False,
    )


# ABI du processus qui rend le jeu. Anomaly tourne en 64 bits sous Proton
# (vérifié en réel le 2026-09-08 : `AnomalyDX11.exe` est un ELF 64 bits), et
# c'est cette ABI-là que les couches Vulkan doivent servir.
GAME_ABI_BITS = 64


def _abi_gap(stem: str) -> bool:
    """La couche est installée, mais pas dans l'ABI du jeu — donc muette.

    Voir `environment.vulkan` : un manifeste présent ne garantit rien, et le
    mode d'échec est silencieux. `UNKNOWN` ne déclenche rien (ne pas savoir
    n'est pas une raison d'alarmer).
    """
    return vulkan.layer_abi_support(stem, GAME_ABI_BITS) is vulkan.AbiSupport.MISSING


def _abi_gap_requirement(
    *, name: str, key: str, manifest: Path, family: DistroFamily
) -> Requirement:
    """Verdict « manifeste là, bibliothèque de la bonne ABI absente ».

    Reste en `OPTIONAL` et non en `MISSING` : ces couches sont cosmétiques, et
    les passer en bloquant ferait sortir `doctor` en erreur pour un overlay
    absent. C'est le détail qui porte la nuance, pas le statut.
    """
    return Requirement(
        name=name,
        status=Status.OPTIONAL,
        detail=_(
            "manifest present ({manifest}) but no {bits}-bit library behind it — "
            "the game renders in a {bits}-bit process, so the layer stays unloaded "
            "and says nothing. Install the {bits}-bit package."
        ).format(manifest=manifest, bits=GAME_ABI_BITS),
        install_hint=INSTALL_COMMANDS[key].for_family(family),
        key=key,
        needed_to_install=False,
    )


def check_mangohud(family: DistroFamily) -> Requirement:
    """MangoHud : facultatif, et **jamais** actif sans que l'utilisateur l'ait demandé.

    On cherche le manifeste de la couche Vulkan, pas le script `mangohud` : c'est
    la couche qui affiche l'overlay dans un jeu Vulkan, et c'est ce fichier que
    pressure-vessel importe dans le conteneur steamrt (cf. `environment.vulkan`).
    """
    manifest = mangohud.layer_manifest()
    if manifest is not None:
        if _abi_gap(mangohud.LAYER_STEM):
            return _abi_gap_requirement(
                name="MangoHud", key="mangohud", manifest=manifest, family=family
            )
        return Requirement(
            name="MangoHud",
            status=Status.OK,
            detail=_(
                "Vulkan layer detected ({manifest}) — off unless you enable it "
                "(Preferences, or `play --mangohud`)"
            ).format(manifest=manifest),
        )
    return Requirement(
        name="MangoHud",
        status=Status.OPTIONAL,
        detail=_(
            "absent — optional: in-game FPS/frametime overlay, plus CPU/GPU/VRAM "
            "and temperatures with the full preset (the numbers to attach to an issue)"
        ),
        install_hint=INSTALL_COMMANDS["mangohud"].for_family(family),
        key="mangohud",
        needed_to_install=False,
    )


def check_vkbasalt(family: DistroFamily) -> Requirement:
    """vkBasalt : facultatif, l'équivalent Linux du ReShade que l'installation retire."""
    manifest = vkbasalt.layer_manifest()
    if manifest is not None:
        if _abi_gap(vkbasalt.LAYER_STEM):
            return _abi_gap_requirement(
                name="vkBasalt", key="vkbasalt", manifest=manifest, family=family
            )
        return Requirement(
            name="vkBasalt",
            status=Status.OK,
            detail=_(
                "Vulkan layer detected ({manifest}) — off unless you enable it; "
                "our « ReShade-like » preset is sharpening + colour grading"
            ).format(manifest=manifest),
        )
    return Requirement(
        name="vkBasalt",
        status=Status.OPTIONAL,
        detail=_(
            "absent — optional: post-processing layer, the Linux answer to the "
            "ReShade the install removes (incompatible with DXVK)"
        ),
        install_hint=INSTALL_COMMANDS["vkbasalt"].for_family(family),
        key="vkbasalt",
        needed_to_install=False,
    )


def check_protontricks(family: DistroFamily) -> Requirement:
    path = system.which("protontricks")
    if path is None:
        if _flatpak_app_installed("com.github.Matoking.protontricks"):
            return Requirement(
                name="protontricks",
                status=Status.OK,
                detail=_("protontricks (Flatpak) detected"),
            )
        # Facultatif : jamais invoqué par le pipeline (les verbs du préfixe
        # passent par umu) — seulement cité comme voie de dépannage manuelle.
        return Requirement(
            name="protontricks",
            status=Status.OPTIONAL,
            detail=_(
                "absent — optional: manual prefix troubleshooting tool, "
                "the pipeline doesn't need it (verbs are applied via umu)"
            ),
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
            key="protontricks",
        )

    result = system.run(["protontricks", "--version"])
    version = _parse_version(result.stdout or result.stderr)
    if version is None:
        return Requirement(
            name="protontricks", status=Status.OK, detail=_("detected (version unreadable)")
        )
    if version < MIN_PROTONTRICKS_VERSION:
        version_str = ".".join(str(part) for part in version)
        min_str = ".".join(str(part) for part in MIN_PROTONTRICKS_VERSION)
        return Requirement(
            name="protontricks",
            status=Status.OUTDATED,
            detail=_("version {version} detected, {minimum}+ required").format(
                version=version_str, minimum=min_str
            ),
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
            key="protontricks",
        )
    return Requirement(
        name="protontricks",
        status=Status.OK,
        detail=_("version {version} detected").format(
            version=".".join(str(part) for part in version)
        ),
    )


def check_7z(family: DistroFamily) -> Requirement:
    if system.which("7z") is not None or system.which("7zz") is not None:
        return Requirement(name="7z", status=Status.OK, detail=_("7z detected"))
    return Requirement(
        name="7z",
        status=Status.MISSING,
        detail=_("neither 7z nor 7zz found in PATH"),
        install_hint=INSTALL_COMMANDS["7z"].for_family(family),
        key="7z",
    )


def _libunrar_version(family: DistroFamily) -> tuple[int, ...] | None:
    """Version des sources de libunrar d'après le gestionnaire de paquets, ou None.

    None couvre tous les cas « on ne sait pas » : famille non reconnue,
    gestionnaire de paquets absent, bibliothèque installée hors paquet (compilée
    à la main, posée par un script tiers). L'appelant reste alors sur Status.OK :
    ne pas savoir n'est pas une raison d'alarmer.
    """
    query = _LIBUNRAR_VERSION_QUERIES.get(family)
    if query is None or system.which(query[0]) is None:
        return None
    result = system.run(list(query))
    if result.returncode != 0:
        return None
    # `pacman -Q` répond « libunrar 7.1.6-1 » et dpkg peut préfixer une epoch
    # (« 1:6.1.7-1 ») : `_parse_version` retient le premier X.Y[.Z] rencontré,
    # qui est bien le numéro de version dans les deux formes.
    return _parse_version(result.stdout)


def check_libunrar(family: DistroFamily) -> Requirement:
    """Présence *et* version de libunrar : une 6.1.6 est aussi dangereuse qu'une absence.

    Vérifier la seule présence rapportait « [ OK ] » sur une machine exposée à
    CVE-2022-30333 alors que le pipeline extrait des archives tierces avec cette
    bibliothèque (cf. MIN_LIBUNRAR_VERSION).
    """
    result = system.run(["ldconfig", "-p"])
    if "libunrar" not in result.stdout:
        return Requirement(
            name="libunrar",
            status=Status.MISSING,
            detail=_("libunrar absent from the ldconfig cache"),
            install_hint=INSTALL_COMMANDS["libunrar"].for_family(family),
            key="libunrar",
        )

    version = _libunrar_version(family)
    if version is None:
        # La bibliothèque est là, sa version nous échappe : le dire franchement
        # plutôt que de laisser croire à une vérification qui n'a pas eu lieu.
        return Requirement(
            name="libunrar", status=Status.OK, detail=_("detected (version unreadable)")
        )

    version_str = ".".join(str(part) for part in version)
    if version < MIN_LIBUNRAR_VERSION:
        # Faux positif possible : Debian et consorts rétroportent parfois le
        # correctif dans une version plus ancienne (unrar-nonfree 6.0.3-1+deb11u1).
        # On assume — pousser à mettre à jour une libunrar de 2021 ne coûte qu'une
        # commande, alors que taire une extraction hors du dossier cible coûte
        # des fichiers écrasés hors de l'installation.
        return Requirement(
            name="libunrar",
            status=Status.OUTDATED,
            detail=_(
                "version {version} detected, vulnerable to CVE-2022-30333 "
                "(a .rar archive can write outside the extraction directory); "
                "sources {minimum}+ required (upstream UnRAR 6.12)"
            ).format(version=version_str, minimum=".".join(str(p) for p in MIN_LIBUNRAR_VERSION)),
            install_hint=INSTALL_COMMANDS["libunrar"].for_family(family),
            key="libunrar",
        )
    return Requirement(
        name="libunrar",
        status=Status.OK,
        detail=_("version {version} detected").format(version=version_str),
    )


def check_vulkan(family: DistroFamily) -> Requirement:
    tool = system.which("vulkaninfo")
    has_device = False
    if tool is not None:
        result = system.run(["vulkaninfo", "--summary"])
        has_device = result.returncode == 0 and "deviceName" in result.stdout
    if has_device:
        return Requirement(
            name=_("Vulkan GPU"), status=Status.OK, detail=_("Vulkan device detected")
        )

    # Pas de device Vulkan. En VM (sans passthrough GPU) c'est normal et non
    # actionnable — le GPU ne sert qu'à *jouer*, pas à télécharger/installer —
    # donc on ne l'affiche pas comme un manque bloquant avec un faux remède.
    virt = system.detect_virtualization()
    if virt is not None:
        return Requirement(
            name=_("Vulkan GPU"),
            status=Status.UNAVAILABLE,
            detail=_("not detected (normal in a VM: {virt}) — only needed to play").format(
                virt=virt
            ),
        )

    detail = _("vulkaninfo not found in PATH") if tool is None else _("no Vulkan device detected")
    return Requirement(
        name=_("Vulkan GPU"),
        status=Status.MISSING,
        detail=detail,
        install_hint=INSTALL_COMMANDS["vulkan"].for_family(family),
        key="vulkan",
        # Le GPU ne sert qu'à *jouer* : sans pilote, l'installation (téléchargement
        # + extraction) se déroule parfaitement. Le signaler, oui ; bloquer, non.
        needed_to_install=False,
    )


def check_gtk_gui(family: DistroFamily) -> Requirement:
    """GTK4 + libadwaita + PyGObject, requis par `stalker-gamma-linux-gui` uniquement.

    N'est jamais ajouté à `build_report` (utilisé par `install`/`update`, qui
    n'en ont pas besoin) : c'est le pré-vol de l'entrée GUI (`gui/launch.py`)
    et une ligne informative de `doctor`, pas un prérequis bloquant de la CLI.
    Import différé de `gi` : `environment.checks` ne doit jamais imposer cette
    dépendance à la CLI.
    """
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk  # noqa: F401
    except (ImportError, ValueError) as error:
        return Requirement(
            name="GTK GUI",
            status=Status.MISSING,
            detail=_("GTK4/libadwaita (PyGObject) unavailable: {error}").format(error=error),
            install_hint=INSTALL_COMMANDS["gtk-gui"].for_family(family),
            key="gtk-gui",
            needed_to_install=False,
        )

    found = (Adw.get_major_version(), Adw.get_minor_version())
    if found < MIN_LIBADWAITA_VERSION:
        # Debian 12 livre libadwaita 1.2 : `Adw.Dialog`, `Adw.NavigationView` et
        # `Adw.ToolbarView` n'y existent pas, et la fenêtre mourait sur une
        # `AttributeError` illisible. Mieux vaut le dire franchement — la CLI,
        # elle, fonctionne parfaitement sur ces distributions.
        return Requirement(
            name="GTK GUI",
            status=Status.OUTDATED,
            detail=_(
                "libadwaita {found} detected, {minimum}+ required by the GUI "
                "(the CLI works regardless)"
            ).format(
                found=".".join(str(part) for part in found),
                minimum=".".join(str(part) for part in MIN_LIBADWAITA_VERSION),
            ),
            install_hint=_(
                "Your distribution is too old for the graphical launcher. Use the "
                "CLI (`stalker-gamma-linux install`), or upgrade to a release "
                "shipping libadwaita 1.5+ (Debian 13, Ubuntu 24.04+, Fedora, Arch)."
            ),
            needed_to_install=False,
        )
    return Requirement(
        name="GTK GUI", status=Status.OK, detail=_("GTK4 + libadwaita detected (PyGObject)")
    )


def _nearest_existing_ancestor(path: Path) -> Path:
    current = path
    while not system.path_exists(current):
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def check_disk_space(target: Path) -> Requirement:
    """Espace libre sur le volume qui hébergera `target`, contre le seuil bloquant.

    Même seuil que la GUI (`sizing.MINIMUM_FREE_GIB`, via `gui.space`) : les deux
    doivent rendre le même verdict sur la même machine.
    """
    probe_path = _nearest_existing_ancestor(target)
    usage = system.disk_usage(probe_path)
    free_gib = usage.free / sizing.GIB
    detail = _(
        "{free:.1f} GiB free on {path} (needs ≈ {minimum} GiB: {anomaly} base game "
        "+ {mods} modpack + {cache} download cache, plus extraction margin)"
    ).format(
        free=free_gib,
        path=probe_path,
        minimum=sizing.MINIMUM_FREE_GIB,
        anomaly=sizing.ANOMALY_GIB,
        mods=sizing.MODPACK_GIB,
        cache=sizing.CACHE_GIB,
    )
    if free_gib >= sizing.MINIMUM_FREE_GIB:
        return Requirement(name=_("Disk space"), status=Status.OK, detail=detail)
    return Requirement(
        name=_("Disk space"),
        status=Status.MISSING,
        detail=detail,
        install_hint=_("Free up space or choose another target (--target)"),
    )
