"""Du fichier nommé par le moteur au mod qui le fournit.

Le cas de référence est **réel**, tiré de la partie plantée du 26/08/2026 : le
moteur s'arrête après avoir nommé le visual `actors\\stalker_nebo\\
stalker_nebo3_exohead`, et le fichier correspondant
(`gamedata/meshes/actors/stalker_nebo/stalker_nebo3_exohead.ogf`) est fourni, sur
l'install mesurée, par le mod `29- Dux's Innemurable Characters Kit - DuxFortis`.
Les noms de mods et les chemins de ce module viennent tous de cette install
(761 mods) — pas d'arborescence inventée pour la circonstance.
"""

from pathlib import Path

from stalker_gamma_linux.postmortem import attribution

# Ligne réelle, celle qui précède le `stack trace:` du journal planté.
REAL_VISUAL_ERROR = (
    "! error in stalker [sim_default_csky_2], profile "
    "[dick_sim_default_csky_2_default_34] with visual "
    "[actors\\stalker_nebo\\stalker_nebo3_exohead]"
)

# Noms de mods réels de l'install mesurée.
DUX_KIT = "29- Dux's Innemurable Characters Kit - DuxFortis"
DUX_VOICES = "305- Dux Characters Kit Voices Pack - Demonized"
FIXED_MODELS = "31- Fixed Vanilla Models and Textures - Blackgrowl"

CRASHING_VISUAL = "gamedata/meshes/actors/stalker_nebo/stalker_nebo3_exohead.ogf"
SHARED_CONFIG = "gamedata/configs/gameplay/character_desc_general_csky_dux.xml"


def _mod_file(mods: Path, mod: str, relative: str) -> Path:
    path = mods / mod / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


class TestReferences:
    def test_visual_reel_est_extrait(self) -> None:
        found = attribution.references([REAL_VISUAL_ERROR])

        assert [reference.raw for reference in found] == [
            "actors/stalker_nebo/stalker_nebo3_exohead"
        ]

    def test_un_visual_est_cherche_comme_un_modele(self) -> None:
        (reference,) = attribution.references([REAL_VISUAL_ERROR])

        assert CRASHING_VISUAL in reference.candidates

    def test_script_nomme_dans_une_trace_lua(self) -> None:
        """Ligne réelle d'un `STACK TRACEBACK` du journal mesuré."""
        line = "\t... ui_hud_dotmarks.script (line: 6536) in function 'on_game_start'"

        (reference,) = attribution.references([line])

        assert reference.raw == "ui_hud_dotmarks.script"
        assert "gamedata/scripts/ui_hud_dotmarks.script" in reference.candidates

    def test_chemin_gamedata_complet(self) -> None:
        line = (
            "LUA error: ...\\gamedata\\scripts\\mags_patches.script:12: "
            "attempt to index a nil value"
        )

        raws = [reference.raw for reference in attribution.references([line])]

        assert "scripts/mags_patches.script" in raws

    def test_les_sources_du_moteur_ne_sont_pas_des_ressources(self) -> None:
        """`[error]File : ..\\xrServerEntities\\script_engine.cpp` désigne le code
        du moteur, pas un mod : en faire un suspect serait une invention."""
        line = "[error]File          : ..\\xrServerEntities\\script_engine.cpp"

        assert attribution.references([line]) == ()

    def test_pas_de_doublon(self) -> None:
        found = attribution.references([REAL_VISUAL_ERROR] * 20)

        assert len(found) == 1


class TestAttribute:
    def test_nomme_le_mod_qui_fournit_le_fichier(self, tmp_path: Path) -> None:
        mods = tmp_path / "mods"
        _mod_file(mods, DUX_KIT, CRASHING_VISUAL)
        _mod_file(mods, FIXED_MODELS, "gamedata/meshes/actors/stalker_nebo/stalker_nebo3a.ogf")

        result = attribution.attribute(attribution.references([REAL_VISUAL_ERROR]), mods)

        assert [suspect.mod for suspect in result.suspects] == [DUX_KIT]
        assert result.suspects[0].within_mod == CRASHING_VISUAL

    def test_deux_mods_fournissant_le_meme_fichier_sont_tous_deux_suspects(
        self, tmp_path: Path
    ) -> None:
        """Cas réel : deux mods livrent `character_desc_general_csky_dux.xml`.
        Taire le second reviendrait à désigner un coupable au hasard."""
        mods = tmp_path / "mods"
        _mod_file(mods, DUX_KIT, SHARED_CONFIG)
        _mod_file(mods, DUX_VOICES, SHARED_CONFIG)
        line = "! bad section in gamedata\\configs\\gameplay\\character_desc_general_csky_dux.xml"

        result = attribution.attribute(attribution.references([line]), mods)

        assert sorted(suspect.mod for suspect in result.suspects) == sorted([DUX_KIT, DUX_VOICES])

    def test_fichier_de_la_base_anomaly_est_signale_comme_tel(self, tmp_path: Path) -> None:
        mods = tmp_path / "mods"
        mods.mkdir()
        anomaly = tmp_path / "anomaly"
        (anomaly / "gamedata" / "scripts").mkdir(parents=True)
        (anomaly / "gamedata" / "scripts" / "_g.script").write_bytes(b"")
        line = "\t... _g.script (line: 82) in function <... _g.script:73>"

        result = attribution.attribute(attribution.references([line]), mods, anomaly=anomaly)

        assert result.suspects == ()
        assert result.base_game == ("_g.script",)

    def test_fichier_introuvable_est_dit_introuvable_pas_attribue(self, tmp_path: Path) -> None:
        """La base Anomaly livre l'essentiel empaqueté dans `db/` : « pas trouvé »
        n'autorise à accuser personne."""
        mods = tmp_path / "mods"
        _mod_file(mods, FIXED_MODELS, "gamedata/meshes/actors/stalker_nebo/stalker_nebo3a.ogf")

        result = attribution.attribute(attribution.references([REAL_VISUAL_ERROR]), mods)

        assert result.suspects == ()
        assert result.unattributed == ("actors/stalker_nebo/stalker_nebo3_exohead",)

    def test_casse_differente_sur_le_disque(self, tmp_path: Path) -> None:
        """Les mods viennent d'archives Windows : `Meshes/` existe pour de vrai,
        et le moteur, lui, écrit tout en minuscules."""
        mods = tmp_path / "mods"
        _mod_file(mods, DUX_KIT, "GameData/Meshes/Actors/Stalker_Nebo/Stalker_Nebo3_ExoHead.ogf")

        result = attribution.attribute(attribution.references([REAL_VISUAL_ERROR]), mods)

        assert [suspect.mod for suspect in result.suspects] == [DUX_KIT]

    def test_dossier_de_mods_absent_ne_leve_pas(self, tmp_path: Path) -> None:
        result = attribution.attribute(
            attribution.references([REAL_VISUAL_ERROR]), tmp_path / "absent"
        )

        assert result.suspects == ()
