"""Priorité des diagnostics, et refus de conclure quand il n'y a rien à lire.

Un seul diagnostic principal est affiché, dans cet ordre :

    échec de lancement > manque de mémoire > crash moteur > USVFS mort > session normale

Les journaux montés ici sont de vrais extraits (voir `test_postmortem_outcome`
pour leur provenance) ; seules l'arborescence et les dates sont fabriquées, parce
que c'est précisément ce que les tests doivent faire varier.
"""

import os
from pathlib import Path

from stalker_gamma_linux.postmortem import analysis, report
from stalker_gamma_linux.postmortem.result import Finding
from tests.test_postmortem_attribution import CRASHING_VISUAL, DUX_KIT
from tests.test_postmortem_outcome import REAL_CLEAN_TAIL, REAL_CRASH_TAIL, REAL_HEAD

# Journal de lancement réel d'une partie qui a bien démarré (première ligne
# écrite par `run_detached`, puis le bavardage habituel d'umu/Proton).
HEALTHY_LAUNCH_LOG = (
    "$ /usr/bin/gamemoderun /home/x/.local/bin/umu-run "
    "/mnt/games/GAMMA/gamma/ModOrganizer.exe moshortcut://:Anomaly (DX11)\n"
    "Proton: Executable is a unix path, launching with 'umu.exe'.\n"
    "ntsync: up and running.\n"
)

# Échec en amont : le processus cible ne démarre pas du tout.
CONCRT140_LAUNCH_LOG = (
    "$ umu-run ModOrganizer.exe\n"
    "0009:err:module:import_dll Library concrt140.dll (which is needed by "
    'L"Z:\\\\mnt\\\\GAMMA\\\\gamma\\\\ModOrganizer.exe") not found\n'
)

# Faux positif documenté (mesuré en T16, docs/MO2-PROTON-COMPAT.md) : Proton
# écrit ceci **puis lance le jeu quand même**.
NON_FATAL_PREFIX_WARNING = (
    "$ umu-run ModOrganizer.exe moshortcut://:Anomaly (DX11)\n"
    "Proton: Upgrading prefix from GE-Proton11-3 to GE-Proton9-20 (.../prefix/)\n"
    "Proton: Prefix has an invalid version?! You may want to back up user files "
    "and delete this prefix.\n"
)

LIVE_USVFS_LOG = (
    "usvfs dll 0.5.6.1 initialized in process 324\n"
    "inithooks in process 692 successful\n"
    "mapping file in vfs: z:\\mnt\\...\\anomaly\\appdata\\..., Z:\\mnt\\...\n"
)


def _install(
    tmp_path: Path,
    *,
    engine_log: str | None = None,
    launch_log: str | None = None,
    usvfs_log: str | None = LIVE_USVFS_LOG,
    modlist: str = "+Mod A\n+Mod B\n",
    crashing_mod: bool = False,
) -> Path:
    """Arborescence minimale d'une install, avec les journaux demandés."""
    root = tmp_path / "GAMMA"
    profile = root / "gamma" / "profiles" / "G.A.M.M.A"
    profile.mkdir(parents=True)
    (profile / "modlist.txt").write_text(modlist, encoding="utf-8")
    (root / "gamma" / "mods").mkdir(parents=True)

    if crashing_mod:
        asset = root / "gamma" / "mods" / DUX_KIT / CRASHING_VISUAL
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"")
    if engine_log is not None:
        logs = root / "anomaly" / "appdata" / "logs"
        logs.mkdir(parents=True)
        (logs / "xray_steamuser.log").write_text(engine_log, encoding="utf-8")
    if launch_log is not None:
        (root / "logs").mkdir(parents=True)
        (root / "logs" / "mo2-game.log").write_text(launch_log, encoding="utf-8")
    if usvfs_log is not None:
        instance_logs = root / "gamma" / "logs"
        instance_logs.mkdir(parents=True, exist_ok=True)
        (instance_logs / "usvfs-2026-08-26_19-00-31.log").write_text(usvfs_log, encoding="utf-8")
    return root


def _age(path: Path, seconds: float) -> None:
    """Fait reculer la date de modification de `path` de `seconds`."""
    stamp = path.stat().st_mtime - seconds
    os.utime(path, (stamp, stamp))


CRASHED_LOG = REAL_HEAD + "\n".join(REAL_CRASH_TAIL) + "\n"
CLEAN_LOG = REAL_HEAD + "\n".join(REAL_CLEAN_TAIL) + "\n"


class TestFindings:
    def test_crash_reel_nomme_le_mod_suspect(self, tmp_path: Path) -> None:
        root = _install(
            tmp_path,
            engine_log=CRASHED_LOG,
            launch_log=HEALTHY_LAUNCH_LOG,
            crashing_mod=True,
        )

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.ENGINE_CRASH
        assert [suspect.mod for suspect in postmortem.attribution.suspects] == [DUX_KIT]
        assert "stack trace:" in "\n".join(postmortem.excerpt)

    def test_crash_sans_mod_correspondant_le_dit_au_lieu_dinventer(self, tmp_path: Path) -> None:
        root = _install(tmp_path, engine_log=CRASHED_LOG, launch_log=HEALTHY_LAUNCH_LOG)

        postmortem = analysis.build_postmortem(root)
        rendered = report.format_postmortem(postmortem)

        assert postmortem.finding is Finding.ENGINE_CRASH
        assert postmortem.attribution.suspects == ()
        assert "No mod could be named" in rendered

    def test_partie_quittee_normalement_ne_crie_pas_au_crash(self, tmp_path: Path) -> None:
        root = _install(tmp_path, engine_log=CLEAN_LOG, launch_log=HEALTHY_LAUNCH_LOG)

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.CLEAN_SESSION
        assert postmortem.excerpt == ()
        assert "no crash" in report.format_postmortem(postmortem)

    def test_usvfs_mort_prime_sur_une_session_normale(self, tmp_path: Path) -> None:
        root = _install(tmp_path, engine_log=CLEAN_LOG, usvfs_log="rien d'utile\n")

        assert analysis.build_postmortem(root).finding is Finding.USVFS_INACTIVE

    def test_install_jamais_lancee_ne_conclut_pas_a_un_usvfs_mort(self, tmp_path: Path) -> None:
        """Ni journal du moteur ni journal USVFS : rien n'a tourné. Dire « les
        mods n'étaient pas montés » affirmerait plus qu'on ne lit."""
        root = _install(tmp_path, usvfs_log=None)

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.NO_ENGINE_LOG

    def test_journal_moteur_absent_donne_un_message_actionnable(self, tmp_path: Path) -> None:
        root = _install(tmp_path, launch_log=HEALTHY_LAUNCH_LOG)

        postmortem = analysis.build_postmortem(root)
        rendered = report.format_postmortem(postmortem)

        assert postmortem.finding is Finding.NO_ENGINE_LOG
        assert postmortem.attribution.suspects == ()
        assert "appdata/logs" in rendered

    def test_journal_moteur_vide_ne_produit_aucun_faux_positif(self, tmp_path: Path) -> None:
        root = _install(tmp_path, engine_log="", launch_log=HEALTHY_LAUNCH_LOG)

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.NO_ENGINE_LOG
        assert "empty" in report.format_postmortem(postmortem)

    def test_journal_qui_sarrete_sans_conclusion(self, tmp_path: Path) -> None:
        """Partie encore en cours, ou processus tué : on ne conclut pas."""
        root = _install(tmp_path, engine_log=REAL_HEAD + "* Loading level...\n")

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.INCONCLUSIVE
        assert "cannot conclude" in report.format_postmortem(postmortem)


class TestPriority:
    def test_echec_de_lancement_prime_sur_le_post_mortem_du_moteur(self, tmp_path: Path) -> None:
        """`concrt140.dll` : le jeu n'a pas démarré, le vieux journal du moteur
        décrit une autre partie et ne doit pas être raconté à sa place."""
        root = _install(
            tmp_path,
            engine_log=CRASHED_LOG,
            launch_log=CONCRT140_LAUNCH_LOG,
            crashing_mod=True,
        )
        _age(root / "anomaly" / "appdata" / "logs" / "xray_steamuser.log", 3 * 3600)

        postmortem = analysis.build_postmortem(root)
        rendered = report.format_postmortem(postmortem)

        assert postmortem.finding is Finding.LAUNCH_FAILURE
        assert "prefix-doctor --repair" in rendered
        assert "stack trace:" not in rendered
        assert DUX_KIT not in rendered

    def test_avertissement_de_prefixe_non_fatal_ne_masque_pas_le_crash(
        self, tmp_path: Path
    ) -> None:
        """Faux positif documenté : Proton annonce un préfixe d'une autre version
        puis lance le jeu. Le moteur a tourné et il a planté — c'est ça,
        l'histoire de cette partie."""
        root = _install(
            tmp_path,
            engine_log=CRASHED_LOG,
            launch_log=NON_FATAL_PREFIX_WARNING,
            crashing_mod=True,
        )

        postmortem = analysis.build_postmortem(root)

        assert postmortem.finding is Finding.ENGINE_CRASH
        assert postmortem.launch_failure is not None  # conservé, mais pas retenu

    def test_journal_de_lancement_append_seule_la_derniere_partie_compte(
        self, tmp_path: Path
    ) -> None:
        """`run_detached` écrit en append : l'échec d'il y a trois semaines ne
        doit pas ressortir comme s'il venait d'arriver."""
        root = _install(
            tmp_path,
            engine_log=CLEAN_LOG,
            launch_log=CONCRT140_LAUNCH_LOG + HEALTHY_LAUNCH_LOG,
        )

        assert analysis.build_postmortem(root).finding is Finding.CLEAN_SESSION


class TestSameSession:
    def test_sans_journal_de_lancement_on_fait_confiance_au_moteur(self, tmp_path: Path) -> None:
        engine = tmp_path / "xray.log"
        engine.write_text("x", encoding="utf-8")

        assert analysis.describes_same_session(engine, None) is True

    def test_journal_moteur_beaucoup_plus_vieux_decrit_une_autre_partie(
        self, tmp_path: Path
    ) -> None:
        engine = tmp_path / "xray.log"
        launch = tmp_path / "mo2-game.log"
        engine.write_text("x", encoding="utf-8")
        launch.write_text("y", encoding="utf-8")
        _age(engine, 3 * 3600)

        assert analysis.describes_same_session(engine, launch) is False

    def test_sans_journal_moteur_rien_a_recouper(self, tmp_path: Path) -> None:
        assert analysis.describes_same_session(None, tmp_path / "mo2-game.log") is False
