"""L'identifiant d'un raccourci non-Steam : signé/non signé, et déterminisme."""

from __future__ import annotations

from stalker_gamma_linux.steam import appid


def test_les_deux_lectures_des_memes_32_bits() -> None:
    """Le piège documenté par T19 : le VDF stocke signé, l'artwork nomme non signé.

    Valeurs relevées sur le `shortcuts.vdf` réel de la machine (2026-09-08) :
    le champ `appid` y vaut -915409416, et les journaux Steam parlent du même
    raccourci sous 3379557880.
    """
    assert appid.to_unsigned(-915409416) == 3379557880
    assert appid.to_signed(3379557880) == -915409416
    assert appid.to_signed(appid.to_unsigned(-915409416)) == -915409416


def test_un_identifiant_derive_porte_le_bit_hors_bibliotheque() -> None:
    value = appid.derive_appid('"/opt/venv/bin/stalker-gamma-linux"', "S.T.A.L.K.E.R. G.A.M.M.A.")

    assert value & 0x80000000
    assert value <= 0xFFFFFFFF


def test_la_derivation_est_deterministe() -> None:
    """Recréer le raccourci doit retomber sur le même artwork, pas en accumuler."""
    first = appid.derive_appid("/a", "name")
    second = appid.derive_appid("/a", "name")

    assert first == second
    assert appid.derive_appid("/b", "name") != first


def test_zero_nest_pas_un_identifiant_utilisable() -> None:
    """Steam remplace un `appid` invalide par une valeur imprévisible : jamais 0."""
    assert not appid.is_valid_appid(0)
    assert appid.is_valid_appid(-915409416)


def test_une_collision_decale_au_lieu_decraser_le_voisin() -> None:
    natural = appid.derive_appid("/a", "name")

    chosen = appid.next_free_appid("/a", "name", frozenset({natural}))

    assert chosen != natural
    assert chosen & 0x80000000
    assert appid.next_free_appid("/a", "name", frozenset()) == natural
