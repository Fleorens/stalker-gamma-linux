"""Où vit Steam sur cette machine, et quels comptes y ont des raccourcis.

Deux installations coexistent couramment — le paquet natif de la distribution
et le Flatpak `com.valvesoftware.Steam` (Bazzite, Fedora, Silverblue) — et les
deux sont réelles : chacune a ses propres `userdata/`. On les cherche donc
toutes les deux, et on écrit dans toutes celles qu'on trouve.

Les racines candidates se recouvrent largement : sur la machine de référence
`~/.steam/steam` et `~/.steam/root` sont deux liens symboliques vers
`~/.local/share/Steam`. D'où la déduplication par chemin **résolu** : sans
elle, on écrirait trois fois dans le même fichier, dont deux fois par-dessus la
sauvegarde `.bak` qu'on venait de prendre.

Les raccourcis sont **par compte** : `userdata/<id>/config/shortcuts.vdf`, et
l'artwork à côté dans `userdata/<id>/config/grid/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Racines Steam natives. `debian-installation` est le chemin du paquet Debian/
# Ubuntu, qui n'utilise ni `~/.local/share/Steam` ni le lien `~/.steam/steam`.
_NATIVE_ROOTS: tuple[tuple[str, ...], ...] = (
    (".local", "share", "Steam"),
    (".steam", "steam"),
    (".steam", "root"),
    (".steam", "debian-installation"),
)

# Racine Flatpak : le sandbox redirige `$XDG_DATA_HOME` sous `~/.var/app/<id>`,
# mais l'arborescence interne est identique.
_FLATPAK_ID = "com.valvesoftware.Steam"
_FLATPAK_ROOTS: tuple[tuple[str, ...], ...] = (
    (".var", "app", _FLATPAK_ID, ".local", "share", "Steam"),
    (".var", "app", _FLATPAK_ID, ".steam", "steam"),
)

_USERDATA = "userdata"
_CONFIG = "config"
SHORTCUTS_FILENAME = "shortcuts.vdf"
GRID_DIRNAME = "grid"

# `shortcuts.vdf` fait quelques centaines d'octets à quelques kilo-octets. La
# borne n'est pas fonctionnelle : elle évite de charger en mémoire — et de
# réécrire — un fichier qui n'en est manifestement pas un.
MAX_SHORTCUTS_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SteamInstall:
    """Une installation Steam trouvée sur le disque (native ou Flatpak)."""

    root: Path
    flatpak: bool

    @property
    def userdata_dir(self) -> Path:
        return self.root / _USERDATA

    @property
    def label(self) -> str:
        return "Steam (Flatpak)" if self.flatpak else "Steam"

    def as_steam_sees(self, host_path: Path, *, home: Path | None = None) -> Path:
        """`host_path` tel que CE Steam le lit — identique en natif, retraduit en Flatpak.

        Le sandbox Flatpak monte `~/.var/app/<id>/` à la place de `~/` : un
        chemin absolu écrit dans `shortcuts.vdf` (le champ `icon`) doit donc
        être donné dans la vue de Steam, pas dans la nôtre, sinon il ne désigne
        rien une fois dans le bac à sable.
        """
        if not self.flatpak:
            return host_path
        base = home if home is not None else Path.home()
        prefix = base / ".var" / "app" / _FLATPAK_ID
        try:
            return base / host_path.relative_to(prefix)
        except ValueError:
            # Racine résolue hors du préfixe attendu (lien symbolique, montage
            # exotique) : mieux vaut le chemin hôte, faux dans le sandbox, qu'un
            # chemin inventé — au pire l'icône manque, rien n'est cassé.
            return host_path


@dataclass(frozen=True, slots=True)
class SteamAccount:
    """Un compte Steam local : c'est lui qui porte les raccourcis et l'artwork."""

    install: SteamInstall
    account_id: str

    @property
    def config_dir(self) -> Path:
        return self.install.userdata_dir / self.account_id / _CONFIG

    @property
    def shortcuts_file(self) -> Path:
        return self.config_dir / SHORTCUTS_FILENAME

    @property
    def grid_dir(self) -> Path:
        return self.config_dir / GRID_DIRNAME

    @property
    def label(self) -> str:
        return f"{self.install.label} · {self.account_id}"


def _candidate_roots(home: Path) -> list[tuple[Path, bool]]:
    native = [(home.joinpath(*parts), False) for parts in _NATIVE_ROOTS]
    flatpak = [(home.joinpath(*parts), True) for parts in _FLATPAK_ROOTS]
    return native + flatpak


def discover_installs(home: Path | None = None) -> tuple[SteamInstall, ...]:
    """Installations Steam présentes, dédupliquées par chemin résolu.

    Une racine sans `userdata/` n'est pas retenue : Steam n'y a jamais ouvert de
    session, il n'y a donc aucun raccourci à y écrire.
    """
    base = home if home is not None else Path.home()
    seen: set[Path] = set()
    installs: list[SteamInstall] = []
    for root, flatpak in _candidate_roots(base):
        if not (root / _USERDATA).is_dir():
            continue
        try:
            resolved = root.resolve(strict=True)
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        installs.append(SteamInstall(root=resolved, flatpak=flatpak))
    return tuple(installs)


def discover_accounts(home: Path | None = None) -> tuple[SteamAccount, ...]:
    """Comptes locaux de toutes les installations, triés (installation, id).

    Un dossier de `userdata/` n'est retenu que s'il porte un identifiant
    numérique non nul et un sous-dossier `config/` : `userdata/0` est le
    pseudo-compte hors ligne de Steam, et un dossier sans `config/` est un
    résidu, pas une session.
    """
    accounts: list[SteamAccount] = []
    for install in discover_installs(home):
        try:
            entries = sorted(install.userdata_dir.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.name.isdigit() or entry.name == "0":
                continue
            if not (entry / _CONFIG).is_dir():
                continue
            accounts.append(SteamAccount(install=install, account_id=entry.name))
    return tuple(accounts)
