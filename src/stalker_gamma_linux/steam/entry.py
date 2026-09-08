"""Notre raccourci **dans** le document `shortcuts.vdf` : le reconnaître, l'écrire, le retirer.

Toutes les fonctions sont pures — elles reçoivent un `VdfDocument` et en
rendent un **nouveau**. Rien ici ne touche au disque : c'est ce qui permet de
tester la déduplication et la préservation des voisins sans Steam ni fichier.

Trois règles portent tout le module.

**On reconnaît notre entrée à son `Exe`**, pas à son nom : l'utilisateur peut
renommer un raccourci dans Steam, il ne peut pas changer l'exécutable qu'il
pointe sans en faire autre chose. Conséquence voulue : l'entrée créée à la main
via *Ajouter un jeu non-Steam* — la manipulation que T06 recommandait — est
**reconnue comme la nôtre** et mise à jour, au lieu d'être doublée.

**On garde l'`appid` d'une entrée existante.** Steam ne le recalcule pas (voir
`steam.appid`) ; le changer déplacerait l'artwork, la configuration manette et
le temps de jeu de l'entrée sous un nouvel identifiant.

**On ne normalise pas le fichier des autres.** Les champs qu'on ne comprend pas
— ceux que Steam a ajoutés, ceux des autres raccourcis — ressortent tels quels,
à leur place, comme pour `ModOrganizer.ini` dans `mo2.ini`. On ne réécrit que
les clés qu'on possède, et seulement dans notre entrée.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Sequence
from pathlib import Path

from stalker_gamma_linux.steam import appid as appid_module
from stalker_gamma_linux.steam.vdf import VdfDocument, VdfInt, VdfMap, VdfNode, VdfString

# Nom du bloc racine dans `shortcuts.vdf` (Steam l'écrit en minuscules ; la
# comparaison reste insensible à la casse, la clé d'origine est préservée).
_ROOT_KEY = "shortcuts"

# Nom du script console du paquet — c'est lui qui identifie notre entrée, quel
# que soit le venv d'où il tourne.
CONSOLE_SCRIPT = "stalker-gamma-linux"

# Pas de `_()` : c'est le titre du jeu, pas une phrase d'interface.
APP_NAME = "S.T.A.L.K.E.R. G.A.M.M.A."

_APPID = "appid"
_APP_NAME = "AppName"
_EXE = "Exe"
_START_DIR = "StartDir"
_ICON = "icon"
_LAUNCH_OPTIONS = "LaunchOptions"


def _matches(key: str, wanted: str) -> bool:
    return key.lower() == wanted.lower()


def _find(nodes: tuple[VdfNode, ...], key: str) -> VdfNode | None:
    return next((node for node in nodes if _matches(node.key, key)), None)


def string_field(entry: VdfMap, key: str) -> str | None:
    node = _find(entry.children, key)
    return node.value if isinstance(node, VdfString) else None


def int_field(entry: VdfMap, key: str) -> int | None:
    node = _find(entry.children, key)
    return node.value if isinstance(node, VdfInt) else None


def shortcuts_map(document: VdfDocument) -> VdfMap | None:
    """Le bloc `shortcuts` de premier niveau, ou `None` si le document n'en a pas."""
    node = _find(document.nodes, _ROOT_KEY)
    return node if isinstance(node, VdfMap) else None


def entries(document: VdfDocument) -> tuple[VdfMap, ...]:
    """Les raccourcis du document, dans l'ordre du fichier."""
    root = shortcuts_map(document)
    if root is None:
        return ()
    return tuple(child for child in root.children if isinstance(child, VdfMap))


def unquote(value: str) -> str:
    """Retire les guillemets dont Steam entoure `Exe` (il les écrit, pas toujours)."""
    return value.strip().strip('"')


def quote(path: Path | str) -> str:
    """Un chemin tel que Steam écrit `Exe` : entre guillemets, comme le fichier réel."""
    return f'"{path}"'


def is_ours(entry: VdfMap) -> bool:
    """`True` si cette entrée pointe sur notre script console (voir le docstring)."""
    exe = string_field(entry, _EXE)
    if not exe:
        return False
    return Path(unquote(exe)).name == CONSOLE_SCRIPT


def find_ours(document: VdfDocument) -> VdfMap | None:
    return next((entry for entry in entries(document) if is_ours(entry)), None)


def taken_appids(document: VdfDocument) -> frozenset[int]:
    """Identifiants (non signés) déjà employés par les raccourcis du document."""
    found = (int_field(entry, _APPID) for entry in entries(document))
    return frozenset(appid_module.to_unsigned(value) for value in found if value is not None)


def launch_options(arguments: Sequence[str]) -> str:
    """Arguments passés par Steam à notre script console, quotés comme un shell.

    **Pas de `gamemoderun %command%` ici** : `play` enveloppe déjà le lancement
    dans `gamemoderun` (`environment.gamemode`). Le remettre côté Steam
    produirait deux niveaux d'enveloppe pour le même effet.

    `shlex.join` plutôt qu'une f-string : Steam découpe ce champ à la manière
    d'un shell, et un chemin d'installation avec un espace doit y survivre.
    """
    return shlex.join(str(argument) for argument in arguments)


def _owned_fields(
    *, signed_appid: int, exe: Path, target: Path, arguments: Sequence[str], icon: Path | None
) -> dict[str, VdfNode]:
    """Les seules clés qu'on écrit — dans notre entrée, et nulle part ailleurs."""
    fields: dict[str, VdfNode] = {
        _APPID: VdfInt(key=_APPID, value=signed_appid),
        _APP_NAME: VdfString(key=_APP_NAME, value=APP_NAME),
        _EXE: VdfString(key=_EXE, value=quote(exe)),
        # Non quoté, avec un séparateur final : la forme observée dans le
        # `shortcuts.vdf` réel. Steam lit ce champ comme un chemin, pas comme
        # une ligne de commande — un espace n'y a donc pas besoin d'échappement.
        _START_DIR: VdfString(key=_START_DIR, value=f"{target}/"),
        _LAUNCH_OPTIONS: VdfString(key=_LAUNCH_OPTIONS, value=launch_options(arguments)),
    }
    if icon is not None:
        fields[_ICON] = VdfString(key=_ICON, value=str(icon))
    return fields


# Les champs restants d'une entrée neuve, dans l'ordre exact du `shortcuts.vdf`
# écrit par Steam. Les valeurs sont celles d'un raccourci non-Steam ordinaire :
# visible, overlay et configuration manette actives (c'est tout l'intérêt en
# mode Gaming), rien de VR ni de devkit.
_NEW_ENTRY_LAYOUT: tuple[tuple[str, VdfNode], ...] = (
    ("ShortcutPath", VdfString(key="ShortcutPath", value="")),
    ("IsHidden", VdfInt(key="IsHidden", value=0)),
    ("AllowDesktopConfig", VdfInt(key="AllowDesktopConfig", value=1)),
    ("AllowOverlay", VdfInt(key="AllowOverlay", value=1)),
    ("OpenVR", VdfInt(key="OpenVR", value=0)),
    ("Devkit", VdfInt(key="Devkit", value=0)),
    ("DevkitGameID", VdfString(key="DevkitGameID", value="")),
    ("DevkitOverrideAppID", VdfInt(key="DevkitOverrideAppID", value=0)),
    ("LastPlayTime", VdfInt(key="LastPlayTime", value=0)),
    ("FlatpakAppID", VdfString(key="FlatpakAppID", value="")),
    ("tags", VdfMap(key="tags", children=())),
)

# Ordre des clés possédées dans une entrée neuve (celui du fichier réel).
_OWNED_ORDER: tuple[str, ...] = (_APPID, _APP_NAME, _EXE, _START_DIR, _ICON, _LAUNCH_OPTIONS)


def build_entry(key: str, fields: dict[str, VdfNode]) -> VdfMap:
    """Entrée neuve : nos champs d'abord, puis ceux d'un raccourci non-Steam ordinaire."""
    children = [fields[name] for name in _OWNED_ORDER if name in fields]
    children.extend(node for _name, node in _NEW_ENTRY_LAYOUT)
    return VdfMap(key=key, children=tuple(children))


def update_entry(existing: VdfMap, fields: dict[str, VdfNode]) -> VdfMap:
    """Entrée existante avec nos champs réécrits **à leur place**, le reste intact.

    Une clé qu'on possède mais qui manque est ajoutée à la fin ; toutes les
    autres — connues de Steam ou non — gardent leur position, leur type et leur
    valeur.
    """
    remaining = dict(fields)
    children: list[VdfNode] = []
    for child in existing.children:
        replacement = next((name for name in remaining if _matches(child.key, name)), None)
        if replacement is None:
            children.append(child)
            continue
        # La clé d'origine est conservée : Steam écrit `appid` en minuscules,
        # d'autres outils `AppID` — ce n'est pas à nous de trancher.
        node = remaining.pop(replacement)
        children.append(_rekeyed(node, child.key))
    children.extend(remaining[name] for name in _OWNED_ORDER if name in remaining)
    return VdfMap(key=existing.key, children=tuple(children))


def _rekeyed(node: VdfNode, key: str) -> VdfNode:
    if isinstance(node, VdfString):
        return VdfString(key=key, value=node.value)
    if isinstance(node, VdfInt):
        return VdfInt(key=key, value=node.value)
    return node


def _renumbered(children: tuple[VdfNode, ...]) -> tuple[VdfNode, ...]:
    """Réindexe les raccourcis en `0..n-1`, dans l'ordre, sans toucher à leur contenu.

    Les clés du bloc `shortcuts` sont des indices, pas des noms : c'est ainsi
    que Steam les réécrit lui-même. Retirer une entrée sans réindexer laisserait
    un trou dans la suite — le contenu des voisins, lui, n'est jamais modifié.
    """
    index = 0
    result: list[VdfNode] = []
    for child in children:
        if isinstance(child, VdfMap):
            result.append(VdfMap(key=str(index), children=child.children))
            index += 1
        else:
            result.append(child)
    return tuple(result)


def _with_root(document: VdfDocument, root: VdfMap) -> VdfDocument:
    if shortcuts_map(document) is None:
        return VdfDocument(nodes=(*document.nodes, root), trailer=document.trailer)
    nodes = tuple(
        root if isinstance(node, VdfMap) and _matches(node.key, _ROOT_KEY) else node
        for node in document.nodes
    )
    return VdfDocument(nodes=nodes, trailer=document.trailer)


def add_or_update(
    document: VdfDocument,
    *,
    exe: Path,
    target: Path,
    arguments: Sequence[str],
    icon_for: Callable[[int], Path] | None,
) -> tuple[VdfDocument, int, bool]:
    """Document avec notre raccourci à jour, son `appid` non signé, et « créé ? ».

    `icon_for` reçoit l'`appid` non signé retenu et rend le chemin d'icône à
    inscrire (l'icône est nommée d'après l'identifiant, qui n'est connu qu'ici) ;
    `None` = pas de champ `icon`.
    """
    existing = find_ours(document)
    quoted_exe = quote(exe)
    if existing is not None and appid_module.is_valid_appid(int_field(existing, _APPID) or 0):
        unsigned = appid_module.to_unsigned(int_field(existing, _APPID) or 0)
    else:
        unsigned = appid_module.next_free_appid(quoted_exe, APP_NAME, taken_appids(document))

    fields = _owned_fields(
        signed_appid=appid_module.to_signed(unsigned),
        exe=exe,
        target=target,
        arguments=arguments,
        icon=icon_for(unsigned) if icon_for is not None else None,
    )

    root = shortcuts_map(document) or VdfMap(key=_ROOT_KEY, children=())
    if existing is not None:
        updated = update_entry(existing, fields)
        children = tuple(updated if child is existing else child for child in root.children)
        return _with_root(document, VdfMap(key=root.key, children=children)), unsigned, False

    used = {child.key for child in root.children}
    index = 0
    while str(index) in used:
        index += 1
    new_entry = build_entry(str(index), fields)
    root = VdfMap(key=root.key, children=(*root.children, new_entry))
    return _with_root(document, root), unsigned, True


def remove_ours(document: VdfDocument) -> tuple[VdfDocument, tuple[int, ...]]:
    """Document sans notre raccourci, et les `appid` non signés retirés (pour l'artwork)."""
    root = shortcuts_map(document)
    if root is None:
        return document, ()
    removed: list[int] = []
    kept: list[VdfNode] = []
    for child in root.children:
        if isinstance(child, VdfMap) and is_ours(child):
            value = int_field(child, _APPID)
            if value is not None:
                removed.append(appid_module.to_unsigned(value))
            continue
        kept.append(child)
    if not removed:
        return document, ()
    return _with_root(document, VdfMap(key=root.key, children=_renumbered(tuple(kept)))), tuple(
        removed
    )
