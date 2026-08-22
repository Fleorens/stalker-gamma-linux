"""Garde-fous de chemin avant toute suppression (`uninstall --game-data`, `verify --repair`).

Deux familles de cibles, deux niveaux de garde :

1. **La racine d'installation** (`--target` d'`uninstall --game-data`) est
   fournie par l'utilisateur sans aucune contrainte de forme : une faute de
   frappe (`~` au lieu du bon dossier, un `..` de trop, un lien symbolique qui
   pointe ailleurs) ne doit jamais pouvoir faire disparaître autre chose qu'une
   install GAMMA réelle. Voir `tasks/T11-securite-suppression-chemins.md`.
2. **Une entrée nommée sous un dossier connu** (le dossier d'un mod sous
   `gamma/mods/`, son archive sous `gamma/downloads/`) ne vient pas non plus de
   nous : le nom sort de la liste modpack amont ou du `meta.ini` écrit par le
   moteur. Un `..`, un séparateur de chemin ou un lien symbolique suffirait à
   faire sortir le `rmtree` du dossier prévu. Voir
   `tasks/T12-integrite-mods-installes.md`.

Dans les deux cas le refus doit être **structurel** — un ensemble de règles
qu'aucune valeur ne peut contourner — et non une convention d'interface
(`--dry-run`, l'affichage du plan) que l'utilisateur peut accepter par réflexe.

Toutes les fonctions de décision ci-dessous sont pures et testables sans
toucher au disque au-delà de `resolve`/`is_symlink`/`is_dir`/`exists` : aucune
lecture de contenu de fichier, aucun parcours d'arborescence.
"""

from __future__ import annotations

import sys
from pathlib import Path

from stalker_gamma_linux.i18n import _

# Racines système : les supprimer emporterait le système d'exploitation, pas
# une install GAMMA.
_SYSTEM_ROOTS: frozenset[str] = frozenset(
    {
        "/",
        "/home",
        "/root",
        "/usr",
        "/etc",
        "/var",
        "/opt",
        "/boot",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/srv",
        "/mnt",
        "/media",
        "/tmp",
    }
)

# Une install GAMMA réelle est nichée sous `gamma-launcher` (`anomaly/`,
# `gamma/`, `prefix/`) ou l'instance MO2 portable (`gamma/mods/`, exposée ici
# aussi en marqueur direct pour tolérer un `--target` pointant sur l'instance
# elle-même). Un dossier qui ne contient AUCUN de ces marqueurs — quelle que
# soit sa profondeur — n'est pas structurellement distinguable d'un dossier
# étranger, donc refusé.
_INSTALL_MARKER_DIRS: tuple[str, ...] = ("anomaly", "gamma", "mods", "prefix")
_INSTALL_STATE_FILENAME = "install-state.toml"


class UnsafeWipeTargetError(Exception):
    """`--target` résolu ne ressemble structurellement pas à une install GAMMA.

    Porte le chemin concerné et la raison du refus, pour un message clair côté
    CLI/GUI sans que l'appelant ait à reconstruire le contexte.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(_("Refusing to delete {path}: {reason}").format(path=path, reason=reason))


def resolve_wipe_target(raw: Path) -> Path | None:
    """Résout `raw` en chemin absolu réel, ou `None` s'il ne peut pas l'être.

    `strict=True` : une cible manquante n'est jamais « acceptée faute de
    mieux » — elle n'a rien à distinguer d'un dossier étranger inexistant.
    """
    try:
        return raw.resolve(strict=True)
    except OSError:
        return None


def _repo_root() -> Path | None:
    """Racine du dépôt d'où tourne le code, si on tourne depuis un checkout source."""
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def _has_install_marker(resolved: Path) -> bool:
    if any((resolved / name).is_dir() for name in _INSTALL_MARKER_DIRS):
        return True
    return (resolved / _INSTALL_STATE_FILENAME).is_file()


def unsafe_reason(raw: Path, resolved: Path) -> str | None:
    """Motif du refus de `resolved` comme cible de `rmtree`, ou `None` si sûr.

    Source unique de vérité derrière `is_safe_wipe_target` : gardée publique
    pour que l'appelant puisse construire un `UnsafeWipeTargetError` explicite
    sans redériver la même logique.
    """
    if not raw.is_absolute():
        return _("relative path")
    if ".." in raw.parts:
        return _("path contains '..'")
    if raw.is_symlink():
        # `resolved` a déjà suivi le lien : supprimer `resolved` emporterait
        # une arborescence qui n'a rien à voir avec `raw`.
        return _("symlink — deleting through it would remove an unrelated directory")

    home = Path.home()
    if str(resolved) in _SYSTEM_ROOTS:
        return _("a protected system directory")
    if resolved == home:
        return _("your home directory")
    if resolved == home.parent:
        return _("the parent of your home directory")
    if resolved.parent == home.parent:
        return _("a sibling of your home directory")
    if resolved == Path.cwd():
        return _("the current working directory")
    repo_root = _repo_root()
    if repo_root is not None and resolved == repo_root:
        return _("the repository this tool is running from")
    if resolved == Path(sys.prefix).resolve():
        return _("the virtual environment this tool is running from")
    if len(resolved.parts) < 3:
        return _("too shallow to be a real install directory")
    if not resolved.is_dir():
        return _("does not exist")
    if not _has_install_marker(resolved):
        return _(
            "does not contain a GAMMA install marker (anomaly/, gamma/, mods/, prefix/, "
            "or an install state file)"
        )
    return None


def is_safe_wipe_target(raw: Path, resolved: Path) -> bool:
    """`True` si `resolved` peut être passé à `rmtree` sans emporter autre chose."""
    return unsafe_reason(raw, resolved) is None


def validate_wipe_target(raw: Path) -> Path:
    """Résout et valide `raw` en une seule opération. Lève `UnsafeWipeTargetError` sinon.

    Point d'entrée que les appelants (CLI, `apply_plan`) doivent utiliser : le
    chemin qu'il retourne est celui qui a été validé, et c'est **exactement**
    celui-là qu'il faut supprimer — ne jamais ré-appeler `resolve()` entre ce
    contrôle et le `rmtree`, sous peine de réintroduire le TOCTOU que ce
    module existe pour fermer.
    """
    resolved = resolve_wipe_target(raw)
    if resolved is None:
        raise UnsafeWipeTargetError(raw, _("target does not exist"))
    reason = unsafe_reason(raw, resolved)
    if reason is not None:
        raise UnsafeWipeTargetError(resolved, reason)
    return resolved


# Caractères qui font sortir un nom de son dossier parent. `\` n'a rien de
# spécial sous Linux, mais les noms qu'on reçoit viennent d'un modpack Windows :
# le tolérer reviendrait à accepter un séparateur de chemin déguisé.
_PATH_SEPARATOR_CHARS: tuple[str, ...] = ("/", "\\", "\0")


def unsafe_child_name_reason(name: str) -> str | None:
    """Motif de refus d'un `name` comme entrée à supprimer, ou `None` s'il est sûr.

    Pure : ne regarde que la chaîne. Un nom qui passe ici désigne forcément une
    entrée *dans* le dossier parent — reste à vérifier sur le disque qu'il n'y a
    pas de lien symbolique en travers (`validate_removable_child`).
    """
    if not name or not name.strip():
        return _("empty name")
    if name in (".", ".."):
        return _("'.' or '..'")
    if any(char in name for char in _PATH_SEPARATOR_CHARS):
        return _("contains a path separator")
    return None


def validate_removable_child(parent: Path, name: str) -> Path | None:
    """Chemin résolu de `<parent>/<name>`, garanti enfant **direct** de `parent`.

    Retourne `None` si l'entrée n'existe pas — supprimer ce qui est déjà parti
    n'est pas une erreur (archive déjà purgée, mod déjà retiré à la main). Lève
    `UnsafeWipeTargetError` dès que le nom, ou ce qu'il désigne réellement sur
    le disque, sortirait de `parent` :

    - nom vide, `.`/`..`, ou contenant un séparateur de chemin ;
    - lien symbolique : `resolve()` l'a déjà suivi, supprimer à travers
      emporterait une arborescence qui n'a rien à voir avec `parent` ;
    - cible dont le parent résolu n'est pas `parent` résolu (dernier filet,
      indépendant de la forme du nom).

    Comme `validate_wipe_target`, le chemin retourné est **exactement** celui
    qu'il faut supprimer : ne jamais re-résoudre entre ce contrôle et le
    `rmtree`/`unlink`.
    """
    reason = unsafe_child_name_reason(name)
    if reason is not None:
        raise UnsafeWipeTargetError(parent / name, reason)

    candidate = parent / name
    if candidate.is_symlink():
        # Testé avant `exists()` : un lien cassé doit être refusé, pas confondu
        # avec « rien à supprimer » (`exists()` suit le lien et répond False).
        raise UnsafeWipeTargetError(
            candidate, _("symlink — deleting through it would remove an unrelated directory")
        )
    if not candidate.exists():
        return None

    try:
        resolved = candidate.resolve(strict=True)
        resolved_parent = parent.resolve(strict=True)
    except OSError as error:
        raise UnsafeWipeTargetError(
            candidate, _("cannot be resolved: {error}").format(error=error)
        ) from error
    if resolved.parent != resolved_parent:
        raise UnsafeWipeTargetError(
            resolved, _("not a direct child of {parent}").format(parent=resolved_parent)
        )
    return resolved
