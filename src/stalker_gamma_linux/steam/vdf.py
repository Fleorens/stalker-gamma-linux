"""Lecture/écriture du VDF binaire (`shortcuts.vdf`), en round-trip octet à octet.

Format relevé sur un vrai fichier de la machine (Steam natif, 2026-09-08), pas
sur une spécification — Valve n'en publie aucune. Une séquence de champs typés,
chacun préfixé d'un octet de type, suivi d'une clé terminée par `NUL` :

- `0x00` — ouvre une map ; ses enfants suivent, jusqu'à un `0x08` ;
- `0x01` — chaîne terminée par `NUL` ;
- `0x02` — entier 32 bits little-endian, **signé** (c'est ainsi que Steam
  stocke `appid` : le nôtre a le bit de poids fort à 1, donc négatif — voir
  `steam.appid`) ;
- `0x08` — fin de bloc.

Deux exigences dictent la forme de ce module.

**Le round-trip doit être exact.** Ce fichier contient *les autres* raccourcis
de l'utilisateur : le relire et le réécrire sans le modifier doit rendre les
mêmes octets. D'où (a) `VdfOpaque`, qui conserve tel quel tout champ typé qu'on
ne sait pas interpréter au lieu de le perdre ou de le normaliser, (b) le
`trailer` du document, qui garde la queue du fichier verbatim (le fichier réel
se termine par quatre `0x08` : trois fermetures de blocs et un terminateur de
document), et (c) `surrogateescape` sur les chaînes, qui fait survivre une
séquence non-UTF-8 dans un nom de raccourci exotique au lieu de la remplacer.

**Un fichier douteux doit être refusé, pas deviné.** Un type inconnu de largeur
inconnue rendrait tout ce qui suit illisible : on lève `VdfFormatError` avec
l'offset plutôt que de resynchroniser au hasard sur un fichier qu'on s'apprête
à réécrire.

Toutes les fonctions sont pures : `parse` prend des octets et rend une
structure immuable, `serialize` fait l'inverse. Aucun accès disque ici.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.steam.errors import VdfFormatError

TYPE_MAP = 0x00
TYPE_STRING = 0x01
TYPE_INT32 = 0x02
TYPE_END = 0x08

# Types à charge utile de largeur fixe qu'on n'interprète pas mais qu'on sait
# traverser : float32/pointeur/couleur (4 octets), uint64/int64 (8). Absents des
# `shortcuts.vdf` observés, mais les traverser coûte une ligne et évite qu'un
# fichier écrit par une future version de Steam devienne illisible.
_OPAQUE_WIDTHS: dict[int, int] = {0x03: 4, 0x04: 4, 0x06: 4, 0x07: 8, 0x0A: 8}

# Un `shortcuts.vdf` est une liste plate de raccourcis : deux niveaux de map en
# usage réel, `tags` en troisième. La borne n'est pas une limite fonctionnelle
# mais un garde-fou contre un fichier fabriqué qui ferait exploser la pile.
_MAX_DEPTH = 32

# `surrogateescape` : tout octet non décodable devient un point de code de
# substitution, ré-encodé à l'identique. C'est ce qui rend le round-trip exact
# sur un nom de raccourci mal encodé, au lieu de le remplacer par `?`.
_ENCODING = "utf-8"
_ERRORS = "surrogateescape"


@dataclass(frozen=True, slots=True)
class VdfString:
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class VdfInt:
    """Entier 32 bits **signé**, tel que Steam l'écrit (`appid` compris)."""

    key: str
    value: int


@dataclass(frozen=True, slots=True)
class VdfOpaque:
    """Champ typé conservé octet pour octet : on sait le traverser, pas le lire."""

    key: str
    type_id: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class VdfMap:
    key: str
    children: tuple[VdfNode, ...]


VdfNode = VdfString | VdfInt | VdfOpaque | VdfMap


@dataclass(frozen=True, slots=True)
class VdfDocument:
    """Champs de premier niveau, plus la queue du fichier gardée verbatim.

    `trailer` n'est pas un détail cosmétique : sans lui, réécrire un fichier
    non modifié changerait ses octets de fin, et le round-trip ne prouverait
    plus rien.
    """

    nodes: tuple[VdfNode, ...]
    trailer: bytes = bytes([TYPE_END])

    @classmethod
    def empty(cls) -> VdfDocument:
        """Document neuf, terminé comme ceux que Steam écrit (le `0x08` final)."""
        return cls(nodes=())


class _Reader:
    """Curseur sur les octets. Chaque lecture qui déborde lève `VdfFormatError`."""

    def __init__(self, data: bytes, path: Path | None) -> None:
        self._data = data
        self._path = path
        self.offset = 0

    def fail(self, offset: int, reason: str) -> VdfFormatError:
        return VdfFormatError(self._path, offset, reason)

    @property
    def exhausted(self) -> bool:
        return self.offset >= len(self._data)

    def peek(self) -> int:
        if self.exhausted:
            raise self.fail(self.offset, _("unexpected end of file"))
        return self._data[self.offset]

    def take(self, count: int) -> bytes:
        end = self.offset + count
        if end > len(self._data):
            raise self.fail(self.offset, _("unexpected end of file"))
        chunk = self._data[self.offset : end]
        self.offset = end
        return chunk

    def take_cstring(self) -> str:
        start = self.offset
        end = self._data.find(b"\0", start)
        if end < 0:
            raise self.fail(start, _("unterminated string"))
        self.offset = end + 1
        return self._data[start:end].decode(_ENCODING, _ERRORS)

    def rest(self) -> bytes:
        chunk = self._data[self.offset :]
        self.offset = len(self._data)
        return chunk


def _read_field(reader: _Reader, depth: int) -> VdfNode:
    """Un champ typé, `0x08` exclu (l'appelant l'a déjà écarté)."""
    type_offset = reader.offset
    type_id = reader.take(1)[0]
    key = reader.take_cstring()
    if type_id == TYPE_MAP:
        return VdfMap(key=key, children=_read_nodes(reader, depth + 1))
    if type_id == TYPE_STRING:
        return VdfString(key=key, value=reader.take_cstring())
    if type_id == TYPE_INT32:
        (value,) = struct.unpack("<i", reader.take(4))
        return VdfInt(key=key, value=value)
    if type_id in _OPAQUE_WIDTHS:
        return VdfOpaque(key=key, type_id=type_id, payload=reader.take(_OPAQUE_WIDTHS[type_id]))
    raise reader.fail(
        type_offset,
        _("unknown field type 0x{type_id:02x} — refusing to guess its length").format(
            type_id=type_id
        ),
    )


def _read_nodes(reader: _Reader, depth: int) -> tuple[VdfNode, ...]:
    """Champs jusqu'au `0x08` de fin de bloc (consommé) ou la fin des octets."""
    if depth > _MAX_DEPTH:
        raise reader.fail(
            reader.offset, _("nesting deeper than {limit} levels").format(limit=_MAX_DEPTH)
        )
    nodes: list[VdfNode] = []
    while not reader.exhausted:
        if reader.peek() == TYPE_END:
            reader.take(1)
            break
        nodes.append(_read_field(reader, depth))
    return tuple(nodes)


def parse(data: bytes, *, path: Path | None = None) -> VdfDocument:
    """Décode un `shortcuts.vdf`. `path` n'est là que pour les messages d'erreur.

    Le `0x08` qui ferme le bloc de premier niveau et tout ce qui le suit partent
    dans `trailer` **tels quels** : un fichier qui s'arrête sans terminateur est
    réécrit sans terminateur, un fichier qui en porte deux les garde tous les
    deux. C'est ce qui rend `serialize(parse(x)) == x` vrai sans condition.
    """
    reader = _Reader(data, path)
    nodes: list[VdfNode] = []
    terminator = b""
    while not reader.exhausted:
        if reader.peek() == TYPE_END:
            reader.take(1)
            terminator = bytes([TYPE_END])
            break
        nodes.append(_read_field(reader, depth=0))
    return VdfDocument(nodes=tuple(nodes), trailer=terminator + reader.rest())


def _write_node(node: VdfNode, out: bytearray) -> None:
    key = node.key.encode(_ENCODING, _ERRORS)
    if isinstance(node, VdfMap):
        out += bytes([TYPE_MAP]) + key + b"\0"
        for child in node.children:
            _write_node(child, out)
        out += bytes([TYPE_END])
    elif isinstance(node, VdfString):
        out += bytes([TYPE_STRING]) + key + b"\0" + node.value.encode(_ENCODING, _ERRORS) + b"\0"
    elif isinstance(node, VdfInt):
        out += bytes([TYPE_INT32]) + key + b"\0" + struct.pack("<i", node.value)
    else:
        out += bytes([node.type_id]) + key + b"\0" + node.payload


def serialize(document: VdfDocument) -> bytes:
    """Ré-encode un document. `parse` puis `serialize` doit rendre les octets d'entrée."""
    out = bytearray()
    for node in document.nodes:
        _write_node(node, out)
    out += document.trailer
    return bytes(out)
