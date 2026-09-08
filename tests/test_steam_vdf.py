"""Le codec VDF binaire : round-trip exact, et refus plutôt que devinette.

Le fichier de référence `tests/data/shortcuts-real.vdf` vient d'un vrai
`shortcuts.vdf` écrit par Steam sur la machine de développement (relevé le
2026-09-08). Il est anonymisé par substitution d'octets **de même longueur**
(le nom du disque) et son `LastPlayTime` a été remis à zéro : le tracé
d'octets — ordre des champs, types, chaînes vides, map `tags`, les quatre
`0x08` de fin — est donc exactement celui que Steam produit, ce qu'aucun
fichier fabriqué à la main ne peut garantir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.steam import vdf
from stalker_gamma_linux.steam.errors import VdfFormatError

REAL_FILE = Path(__file__).parent / "data" / "shortcuts-real.vdf"


def test_round_trip_octet_a_octet_sur_un_fichier_reel() -> None:
    """Le critère bloquant de T19 : relire et réécrire ne doit rien changer."""
    data = REAL_FILE.read_bytes()

    assert vdf.serialize(vdf.parse(data, path=REAL_FILE)) == data


def test_le_fichier_reel_se_lit_comme_un_raccourci_complet() -> None:
    document = vdf.parse(REAL_FILE.read_bytes())

    (root,) = document.nodes
    assert isinstance(root, vdf.VdfMap)
    assert root.key == "shortcuts"
    (entry,) = root.children
    assert isinstance(entry, vdf.VdfMap)
    assert entry.key == "0"
    fields = {child.key: child for child in entry.children}
    # `appid` est stocké SIGNÉ : le bit de poids fort des raccourcis non-Steam
    # rend la valeur négative (cf. steam/appid.py).
    assert fields["appid"] == vdf.VdfInt(key="appid", value=-915409416)
    assert isinstance(fields["AppName"], vdf.VdfString)
    assert isinstance(fields["tags"], vdf.VdfMap)


@pytest.mark.parametrize(
    "sample",
    [
        b"",
        bytes([vdf.TYPE_END]),
        # Deux terminateurs, ou aucun : la queue du fichier ressort telle quelle.
        bytes([vdf.TYPE_END, vdf.TYPE_END]),
        b"\x01key\0value\0",
        b"\x01key\0value\0\x08",
        b"\x00map\0\x02n\0\x01\x00\x00\x00\x08\x08",
    ],
)
def test_round_trip_sur_des_fichiers_fabriques(sample: bytes) -> None:
    assert vdf.serialize(vdf.parse(sample)) == sample


def test_les_octets_non_utf8_survivent_au_round_trip() -> None:
    """`surrogateescape` : un nom de raccourci mal encodé ne doit pas être « réparé »."""
    sample = b"\x01AppName\0caf\xe9\0\x08"

    assert vdf.serialize(vdf.parse(sample)) == sample


def test_un_type_inconnu_est_refuse_avec_son_offset() -> None:
    """Deviner la longueur d'un champ inconnu rendrait illisible tout ce qui suit."""
    with pytest.raises(VdfFormatError) as raised:
        vdf.parse(b"\x01ok\0v\0\x7fmystery\0")

    assert raised.value.offset == 6
    assert "0x7f" in str(raised.value)


@pytest.mark.parametrize(
    "sample",
    [
        b"\x01unterminated",  # chaîne sans NUL
        b"\x02key\0\x01\x02",  # entier tronqué
        b"\x00map\0\x01key\0",  # valeur manquante
    ],
)
def test_un_fichier_tronque_est_refuse(sample: bytes) -> None:
    with pytest.raises(VdfFormatError):
        vdf.parse(sample)


def test_une_imbrication_absurde_est_refusee() -> None:
    """Garde-fou de pile : un fichier fabriqué ne doit pas faire tomber le processus."""
    sample = b"\x00m\0" * 200

    with pytest.raises(VdfFormatError):
        vdf.parse(sample)


def test_un_champ_de_type_connu_mais_opaque_est_conserve_verbatim() -> None:
    """`0x07` (64 bits) : on sait le traverser, pas l'interpréter — il ressort intact."""
    sample = b"\x07big\0\x01\x02\x03\x04\x05\x06\x07\x08\x08"

    document = vdf.parse(sample)

    (node,) = document.nodes
    assert isinstance(node, vdf.VdfOpaque)
    assert node.payload == b"\x01\x02\x03\x04\x05\x06\x07\x08"
    assert vdf.serialize(document) == sample
