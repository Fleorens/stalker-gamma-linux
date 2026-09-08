"""Garde-fous sur les chemins que l'utilisateur nous confie.

Trois familles de cibles, trois niveaux de garde :

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
3. **Le chemin d'installation lui-même** (`--target`, le `source` d'`import`, le
   sélecteur de dossier de la GUI) n'est pas seulement une cible de suppression :
   il est recopié dans des formats ligne à ligne (`.desktop`, `ModOrganizer.ini`)
   où un caractère de contrôle ouvre une clé supplémentaire, et dans un format
   binaire (`shortcuts.vdf`) où un `\0` *termine* une valeur. Voir
   `validate_install_target` en fin de module.

Dans les trois cas le refus doit être **structurel** — un ensemble de règles
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


# Caractères de contrôle C0 (`\x00`-`\x1f`, dont `\n` et `\r`) et DEL (`\x7f`).
# Le noyau Linux n'interdit dans un nom de fichier que `/` et `\0` : un chemin
# porteur d'un `\n` est parfaitement créable et manipulable, et arrive tel quel
# jusqu'à nous par `--target` (argv accepte `\n`) ou par le sélecteur de dossier
# de la GUI. `\0` ne peut pas venir d'argv (execve coupe à la première), mais
# vient du TOML des préférences ou d'un appelant programmatique : les deux sont
# traités ici de la même façon, un caractère de contrôle n'ayant aucun usage
# légitime dans un chemin d'installation.
_CONTROL_CHARS: frozenset[str] = frozenset(chr(code) for code in (*range(0x20), 0x7F))

# Échappe UNIQUEMENT les caractères de contrôle : un `é` dans le chemin doit
# rester lisible dans le message d'erreur, seul l'invisible doit devenir visible.
_CONTROL_ESCAPE_TABLE = str.maketrans(
    {char: char.encode("unicode_escape").decode("ascii") for char in _CONTROL_CHARS}
)


def _escape_control_chars(text: str) -> str:
    """`text` avec ses caractères de contrôle rendus visibles (`\\n`, `\\x00`)."""
    return text.translate(_CONTROL_ESCAPE_TABLE)


class UnsafeInstallTargetError(Exception):
    """Chemin d'installation porteur d'un caractère qu'aucun de ses puits ne sait écrire.

    Porte le chemin concerné et la raison du refus, comme `UnsafeWipeTargetError`,
    pour un message clair côté CLI/GUI sans que l'appelant ait à reconstruire le
    contexte.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        # Le message échappe le chemin : le réafficher brut rejouerait le saut
        # de ligne qu'on est justement en train de refuser — le terminal et le
        # fichier de log sont eux aussi des formats ligne à ligne.
        super().__init__(
            _("Refusing install path {path}: {reason}").format(
                path=_escape_control_chars(str(path)), reason=reason
            )
        )


def unsafe_install_target_reason(raw: Path) -> str | None:
    """Motif du refus de `raw` comme chemin d'installation, ou `None` s'il est sûr.

    Pure : ne regarde que la chaîne, jamais le disque. Source unique de vérité
    derrière `validate_install_target`, gardée publique pour que l'appelant
    puisse décider sans lever d'exception (la GUI grise un bouton là où la CLI
    sort en erreur).
    """
    for char in str(raw):
        if char in _CONTROL_CHARS:
            return _("contains a control character ({escaped})").format(
                escaped=_escape_control_chars(char)
            )
    return None


def validate_install_target(raw: Path) -> Path:
    """Retourne `raw` inchangé, ou lève `UnsafeInstallTargetError`.

    Le chemin d'installation choisi par l'utilisateur (`--target` de la CLI, le
    `source` d'`import`, le sélecteur de dossier de la GUI) finit recopié tel
    quel dans deux formats **ligne à ligne** qui n'ont aucune notion
    d'échappement du saut de ligne :

    - `desktop/entry.py` écrit `Path=` et `Icon=` par simple interpolation, et
      le quoting `Exec=` de la spec freedesktop couvre `\\ " ` $ %` — mais pas
      `\\n`, qui n'a tout simplement aucune représentation dans une valeur ;
    - `mo2/ini.py:set_key` écrit la valeur verbatim après le `=`.

    Un `\\n` dans le chemin y ouvre donc une **seconde clé** : un `--target`
    fabriqué injecte un `Exec=` supplémentaire dans le `.desktop`, fichier que
    `desktop/install.py` rend ensuite exécutable (`chmod 0o755`) et enregistre
    dans le menu applications — exécution de commande arbitraire au prochain
    clic (CWE-74).

    S'y ajoute depuis T19 un puits **binaire**, `steam/vdf.py`, où les chaînes
    sont terminées par `NUL` : un `\\0` dans le chemin y couperait la valeur en
    deux et décalerait la lecture de tout ce qui suit — dans un fichier qui
    contient les autres raccourcis de l'utilisateur. `steam/install.py` valide
    donc la cible avant d'écrire, comme les deux autres puits.

    Le refus est placé **à la frontière** plutôt qu'en échappement dans chaque
    puits : les puits sont nombreux et le resteront, l'entrée est unique. Et il
    ne coûte rien à personne — un dossier d'installation légitime n'a aucune
    raison de contenir un caractère de contrôle.

    Contrairement à `validate_wipe_target`, ne touche pas au disque : utilisable
    avant même que la cible existe (c'est le cas d'`install`).
    """
    reason = unsafe_install_target_reason(raw)
    if reason is not None:
        raise UnsafeInstallTargetError(raw, reason)
    return raw
