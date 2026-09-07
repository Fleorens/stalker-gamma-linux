"""Fin de session : reconnaître un crash **sans** crier au loup sur une partie normale.

Tous les extraits de ce module sont **réels**, copiés de deux journaux X-Ray
complets d'installs GAMMA (X-Ray Monolith 1.5.3, `'xrCore' build 9959`) :

- `.../GAMMA_ZZ/anomaly/appdata/logs/xray_steamuser.log` — 104 329 lignes, partie
  du 13/08/2026 **quittée normalement** ;
- `.../GAMMA/anomaly/appdata/logs/xray_steamuser.log` — 75 973 lignes, partie du
  26/08/2026 **plantée**, journal interrompu net.

La seule exception est notée là où elle se trouve (manque de mémoire) : aucun des
deux journaux ne contient ce cas, la ligne est donc reconstruite depuis la chaîne
de format du moteur lui-même (`Out of memory. Memory request: %lld K`, extraite
de `anomaly/bin/AnomalyDX11.exe`), et c'est dit plutôt que sous-entendu.
"""

from pathlib import Path

from stalker_gamma_linux.postmortem import logfile, outcome
from stalker_gamma_linux.postmortem.outcome import SessionOutcome

# En-tête réel du journal de la partie plantée (12 premières lignes).
REAL_HEAD = (
    "* Detected CPU: AMD Ryzen 7 5700X3D 8-Core Processor            "
    "[AuthenticAMD], F15/M1/S2, 2994.00 mhz, 26-clk 'rdtsc'\n"
    "* CPU cores/threads: 8/16\n"
    "Initializing File System...\n"
    "FS: 104985 files cached 73 archives, 34819Kb memory used.\n"
    "'xrCore' build 9959, May 15 2026\n"
    "Modded Exes MT-TEST version 2026.05.15\n"
    "Game started: 26.08.2026 21:01:50.007\n"
)

# Fin réelle de la partie quittée normalement : dump du gestionnaire de
# ressources, compteurs de références, puis fermeture du journal par le moteur.
REAL_CLEAN_TAIL = (
    "* RM_Dump: v_shaders : 122",
    "refCount:pBaseZB 1",
    "refCount:m_pSwapChain 1",
    "DeviceREF: 1",
    "refCount:m_pFactory 1",
    "[xrLogger] InternalCloseLog called, terminating thread",
)

# Fin réelle de la partie plantée : le moteur nomme le visual fautif, puis
# s'arrête sur sa trace. Pas de `InternalCloseLog` — le processus est mort là.
REAL_CRASH_TAIL = (
    "! error in stalker [sim_default_csky_2], profile "
    "[dick_sim_default_csky_2_default_34] with visual "
    "[actors\\stalker_nebo\\stalker_nebo3_exohead]",
    "# Inventory item: [grenade_rgd5] - RGD-5 Grenade",
    "# Inventory item: [bolt] - Bolt",
    "stack trace:",
    "",
    "SymInit: Symbol-SearchPath: '.;Z:\\mnt\\games_samsung\\Games\\GAMMA\\anomaly\\bin;"
    "C:\\windows;C:\\windows\\system32;', symOptions: 530, UserName: 'steamuser'",
    "OS-Version: 6.2.9200 () 0x0-0x1",
    "at address 0x0000000140B02DC1",
)

# Bloc réel d'erreurs applicatives d'Anomaly, pris **au milieu** de la partie
# quittée normalement. C'est le piège du diagnostic : une recherche naïve y
# trouve « [ERROR] » et « STACK TRACE(BACK) », et pourtant le joueur a joué
# encore une heure derrière.
REAL_BENIGN_SCRIPT_ERRORS = (
    "! [ERROR] --- Failed to load script mags_patches",
    "! [ERROR] --- Failed to load script zzz_mspizza_godis_zoom_control",
    "![axr_main callback_set] trying to set callback "
    "physic_object_on_use_callback to nil function!",
    "~ ------------------------------------------------------------------------",
    "~ STACK TRACEBACK:",
    "",
    "\t... axr_main.script (line: 259) in function 'callback_set'",
    "\t... ui_hud_dotmarks.script (line: 6536) in function 'on_game_start'",
    "~ ------------------------------------------------------------------------",
    "!MCM given bad path:EA_settings/enable_animations",
)


class TestClassify:
    def test_partie_quittee_normalement_nest_pas_un_crash(self) -> None:
        assert outcome.classify("\n".join(REAL_CLEAN_TAIL)) is SessionOutcome.CLEAN_EXIT

    def test_vraie_fin_de_crash_est_reconnue(self) -> None:
        assert outcome.classify("\n".join(REAL_CRASH_TAIL)) is SessionOutcome.ENGINE_CRASH

    def test_erreurs_de_scripts_anomaly_ne_sont_pas_un_crash(self) -> None:
        """Le cœur du sujet : 65 « [ERROR] » et 27 « stack trace » sur une partie
        parfaitement normale. Aucun ne doit compter."""
        assert outcome.classify("\n".join(REAL_BENIGN_SCRIPT_ERRORS)) is SessionOutcome.INCONCLUSIVE

    def test_erreurs_applicatives_puis_fin_propre_restent_une_fin_propre(self) -> None:
        text = "\n".join((*REAL_BENIGN_SCRIPT_ERRORS, *REAL_CLEAN_TAIL))

        assert outcome.classify(text) is SessionOutcome.CLEAN_EXIT

    def test_journal_qui_sarrete_sans_rien_ne_conclut_pas(self) -> None:
        """Partie encore en cours, ou processus tué de l'extérieur."""
        text = "Game started: 26.08.2026 21:01:50.007\n* Loading level...\n"

        assert outcome.classify(text) is SessionOutcome.INCONCLUSIVE

    def test_manque_de_memoire_prime_sur_la_trace(self) -> None:
        """Ligne reconstruite depuis la chaîne de format du moteur
        (`Out of memory. Memory request: %lld K`, relevée dans AnomalyDX11.exe) :
        aucun des deux journaux réels n'a planté de cette façon."""
        text = "Out of memory. Memory request: 2097152 K\nstack trace:\n"

        assert outcome.classify(text) is SessionOutcome.OUT_OF_MEMORY

    def test_dernier_marqueur_gagne(self) -> None:
        """Un crash suivi d'une fermeture propre décrit une fin propre."""
        text = "\n".join((*REAL_CRASH_TAIL, *REAL_CLEAN_TAIL))

        assert outcome.classify(text) is SessionOutcome.CLEAN_EXIT


class TestAnalyse:
    def test_lit_le_debut_de_session_et_la_version_du_moteur(self) -> None:
        result = outcome.analyse(REAL_HEAD, REAL_CRASH_TAIL)

        assert result.started_at == "26.08.2026 21:01:50.007"
        assert result.engine_build == "9959"

    def test_extrait_conserve_sur_un_crash_contient_la_trace_et_le_fichier(self) -> None:
        result = outcome.analyse(REAL_HEAD, REAL_CRASH_TAIL)

        excerpt = "\n".join(result.excerpt)
        assert "stack trace:" in excerpt
        assert "stalker_nebo3_exohead" in excerpt

    def test_aucun_extrait_sur_une_partie_normale(self) -> None:
        """Un extrait pris au hasard dans une partie saine ne prouverait rien."""
        result = outcome.analyse(REAL_HEAD, REAL_CLEAN_TAIL)

        assert result.outcome is SessionOutcome.CLEAN_EXIT
        assert result.excerpt == ()

    def test_les_repetitions_sont_repliees(self) -> None:
        """Le vrai journal répète la même erreur 1158 fois, par blocs de six
        lignes : sans repli, l'extrait est illisible."""
        flooded = tuple(REAL_CRASH_TAIL[:3] * 20) + REAL_CRASH_TAIL[3:]

        result = outcome.analyse(REAL_HEAD, flooded)

        assert any("repeated line(s) omitted" in line for line in result.excerpt)
        assert len(result.excerpt) < len(flooded)


class TestReadTail:
    def test_ne_lit_que_la_fin_dun_gros_journal(self, tmp_path: Path) -> None:
        """Un journal X-Ray réel fait 5 Mo : on ne le charge jamais en entier."""
        log = tmp_path / "xray_steamuser.log"
        log.write_text("bourrage\n" * 200_000 + "\n".join(REAL_CRASH_TAIL), encoding="utf-8")

        tail = logfile.read_tail(log, max_lines=10, max_bytes=4096)

        assert len(tail) <= 10
        assert "at address 0x0000000140B02DC1" in tail[-1]

    def test_la_premiere_ligne_tronquee_est_jetee(self, tmp_path: Path) -> None:
        log = tmp_path / "xray_steamuser.log"
        log.write_text("aaaaaaaaaa\nbbbb\ncccc\n", encoding="utf-8")

        assert logfile.read_tail(log, max_lines=10, max_bytes=12) == ("bbbb", "cccc")

    def test_octets_non_utf8_ne_font_pas_echouer_la_lecture(self, tmp_path: Path) -> None:
        """Constaté côté Wine (0x88) : un journal pollué doit rester lisible."""
        log = tmp_path / "xray_steamuser.log"
        log.write_bytes(b"ligne saine\n\x88\x88 ligne polluee\nstack trace:\n")

        assert logfile.read_tail(log)[-1] == "stack trace:"

    def test_journal_absent_ne_leve_pas(self, tmp_path: Path) -> None:
        assert logfile.read_tail(tmp_path / "absent.log") == ()
