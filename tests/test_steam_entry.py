"""Notre raccourci dans le document : déduplication, préservation, réversibilité.

Tout est pur ici — pas un fichier n'est touché. C'est ce qui permet de vérifier
« les autres raccourcis sont intacts » **champ à champ**, pas à l'œil.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.steam import appid as appid_module
from stalker_gamma_linux.steam import entry, vdf

REAL_FILE = Path(__file__).parent / "data" / "shortcuts-real.vdf"

EXE = Path("/opt/venv/bin/stalker-gamma-linux")
TARGET = Path("/games/gamma")
ARGUMENTS = ["play", "--target", str(TARGET)]


def _real_document() -> vdf.VdfDocument:
    return vdf.parse(REAL_FILE.read_bytes())


def _add(document: vdf.VdfDocument) -> tuple[vdf.VdfDocument, int, bool]:
    return entry.add_or_update(
        document,
        exe=EXE,
        target=TARGET,
        arguments=ARGUMENTS,
        icon_for=lambda value: Path(f"/grid/{value}_icon.png"),
    )


def test_ajout_dans_un_document_vide() -> None:
    document, appid, created = _add(vdf.VdfDocument(nodes=(), trailer=b""))

    assert created
    (ours,) = entry.entries(document)
    assert entry.string_field(ours, "AppName") == entry.APP_NAME
    assert entry.string_field(ours, "Exe") == f'"{EXE}"'
    assert entry.string_field(ours, "StartDir") == f"{TARGET}/"
    assert entry.int_field(ours, "appid") == appid_module.to_signed(appid)


def test_les_options_de_lancement_ne_remettent_pas_gamemoderun() -> None:
    """`play` enveloppe déjà dans `gamemoderun` : deux niveaux seraient un bug (T19 §8)."""
    document, _appid, _created = _add(vdf.VdfDocument(nodes=(), trailer=b""))

    (ours,) = entry.entries(document)
    options = entry.string_field(ours, "LaunchOptions") or ""
    assert "gamemoderun" not in options
    assert "%command%" not in options
    assert options.startswith("play --target")


def test_un_chemin_avec_espaces_est_quote_dans_les_options() -> None:
    spaced = Path("/games/my gamma")

    document, _appid, _created = entry.add_or_update(
        vdf.VdfDocument(nodes=(), trailer=b""),
        exe=EXE,
        target=spaced,
        arguments=["play", "--target", str(spaced)],
        icon_for=None,
    )

    (ours,) = entry.entries(document)
    assert entry.string_field(ours, "LaunchOptions") == "play --target '/games/my gamma'"


def test_relancer_met_a_jour_au_lieu_de_dupliquer() -> None:
    once, first_appid, created_first = _add(_real_document())
    twice, second_appid, created_second = _add(once)

    assert created_first and not created_second
    assert first_appid == second_appid
    assert len(entry.entries(twice)) == len(entry.entries(once)) == 2


def test_les_autres_raccourcis_sont_intacts_champ_a_champ() -> None:
    before = _real_document()
    (neighbour_before,) = entry.entries(before)

    after, _appid, _created = _add(before)

    neighbour_after = entry.entries(after)[0]
    assert neighbour_after == neighbour_before


def test_une_entree_creee_a_la_main_est_adoptee_pas_doublee() -> None:
    """Le raccourci que T06 faisait créer à la main pointe déjà sur notre script."""
    manual = vdf.VdfMap(
        key="0",
        children=(
            vdf.VdfInt(key="appid", value=-42),
            vdf.VdfString(key="AppName", value="stalker-gamma-linux"),
            vdf.VdfString(key="Exe", value='"/other/venv/bin/stalker-gamma-linux"'),
            vdf.VdfString(key="MysteryFutureKey", value="keep me"),
        ),
    )
    document = vdf.VdfDocument(
        nodes=(vdf.VdfMap(key="shortcuts", children=(manual,)),), trailer=b"\x08"
    )

    updated, appid, created = _add(document)

    assert not created
    (ours,) = entry.entries(updated)
    # L'identifiant existant est repris : le changer déplacerait l'artwork, la
    # configuration manette et le temps de jeu de l'entrée.
    assert appid == appid_module.to_unsigned(-42)
    assert entry.int_field(ours, "appid") == -42
    assert entry.string_field(ours, "Exe") == f'"{EXE}"'
    # Clé inconnue : préservée, comme dans `mo2/ini.py`.
    assert entry.string_field(ours, "MysteryFutureKey") == "keep me"


def test_un_appid_invalide_est_remplace() -> None:
    """0 = ce que Steam remplacerait lui-même par une valeur imprévisible."""
    existing = vdf.VdfMap(
        key="0",
        children=(
            vdf.VdfInt(key="appid", value=0),
            vdf.VdfString(key="Exe", value='"/x/stalker-gamma-linux"'),
        ),
    )
    document = vdf.VdfDocument(
        nodes=(vdf.VdfMap(key="shortcuts", children=(existing,)),), trailer=b"\x08"
    )

    updated, appid, _created = _add(document)

    assert appid != 0
    (ours,) = entry.entries(updated)
    assert entry.int_field(ours, "appid") == appid_module.to_signed(appid)


def test_le_retrait_rend_le_fichier_doctet_pour_octet() -> None:
    """Critère d'acceptation T19 : `--remove` laisse le fichier tel qu'avant l'ajout."""
    original = REAL_FILE.read_bytes()

    added, _appid, _created = _add(vdf.parse(original))
    removed, appids = entry.remove_ours(added)

    assert len(appids) == 1
    assert vdf.serialize(removed) == original


def test_le_retrait_dun_document_sans_notre_entree_ne_change_rien() -> None:
    document = _real_document()

    removed, appids = entry.remove_ours(document)

    assert appids == ()
    assert removed is document


def test_le_retrait_reindexe_les_voisins() -> None:
    """Les clés du bloc `shortcuts` sont des indices : on ne laisse pas de trou."""
    document, _appid, _created = _add(vdf.VdfDocument(nodes=(), trailer=b""))
    with_neighbour = vdf.VdfDocument(
        nodes=(
            vdf.VdfMap(
                key="shortcuts",
                children=(
                    *entry.entries(document),
                    vdf.VdfMap(
                        key="1",
                        children=(vdf.VdfString(key="Exe", value='"/usr/bin/other-game"'),),
                    ),
                ),
            ),
        ),
        trailer=b"\x08",
    )

    removed, _appids = entry.remove_ours(with_neighbour)

    (survivor,) = entry.entries(removed)
    assert survivor.key == "0"
    assert entry.string_field(survivor, "Exe") == '"/usr/bin/other-game"'


def test_la_casse_de_la_cle_dorigine_est_conservee() -> None:
    """Steam écrit `appid`, d'autres outils `AppID` : ce n'est pas à nous de trancher."""
    existing = vdf.VdfMap(
        key="0",
        children=(
            vdf.VdfInt(key="AppID", value=-42),
            vdf.VdfString(key="exe", value='"/x/stalker-gamma-linux"'),
        ),
    )
    document = vdf.VdfDocument(
        nodes=(vdf.VdfMap(key="shortcuts", children=(existing,)),), trailer=b"\x08"
    )

    updated, _appid, _created = _add(document)

    (ours,) = entry.entries(updated)
    assert [child.key for child in ours.children][:2] == ["AppID", "exe"]
