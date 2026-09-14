from pathlib import Path

from stalker_gamma_linux.engine.errors import (
    DepositMismatchError,
    EngineExecutionError,
    EngineNotFoundError,
    VerificationError,
)
from stalker_gamma_linux.engine.markers import FailureCause

# Sortie réelle d'un refus ModDB : gamma-launcher ne rattrape pas
# `ModDBDownloadError`, on reçoit donc sa traceback telle quelle. Le test
# précédent s'appuyait sur « ModDB download link not found », une paraphrase
# absente du code amont : l'indice ne s'était jamais déclenché en vrai.
_MODDB_FAILURE = (
    "Traceback (most recent call last):\n"
    '  File ".../launcher/mods/downloader/moddb.py", line 52, in _get_download_url\n'
    "launcher.exceptions.ModDBDownloadError: Download link not found when requesting "
    "https://www.moddb.com/mods/stalker-anomaly/addons/boomsticks-and-sharpsticks"
)


def test_engine_not_found_error_message_is_actionable() -> None:
    error = EngineNotFoundError()

    assert "PATH" in str(error)
    assert "pip install" in str(error)


def test_moddb_refusal_gives_the_manual_download_procedure() -> None:
    error = EngineExecutionError("full-install", 1, _MODDB_FAILURE, Path("/games/gamma/downloads"))

    message = str(error)

    # L'utilisateur doit repartir avec les trois éléments : quelle page ouvrir,
    # où déposer le fichier, et le fait que relancer reprend sans retélécharger.
    assert "https://www.moddb.com/mods/stalker-anomaly/addons/boomsticks-and-sharpsticks" in message
    assert "/games/gamma/downloads" in message
    assert "not downloaded a second time" in message


def test_moddb_hint_stays_useful_without_a_known_download_folder() -> None:
    error = EngineExecutionError("full-install", 1, _MODDB_FAILURE)

    assert "downloads folder of your install" in str(error)


def test_execution_error_falls_back_to_generic_resume_hint() -> None:
    error = EngineExecutionError("full-install", 1, "some unrelated failure")

    assert "cache already downloaded" in str(error)


def test_verification_error_is_an_execution_error_subtype() -> None:
    error = VerificationError("check-md5", 1, "Invalid file(s) detected")

    assert isinstance(error, EngineExecutionError)
    assert error.subcommand == "check-md5"
    assert error.returncode == 1


def test_moddb_hint_names_the_mod_file_and_folder_when_known() -> None:
    # Critère d'acceptation T22 : jamais une traceback nue, toujours le nom du
    # mod, l'URL, le fichier attendu et le dossier de dépôt.
    error = EngineExecutionError(
        "full-install",
        1,
        _MODDB_FAILURE,
        Path("/games/gamma/downloads"),
        mod_name="Boomsticks and Sharpsticks",
        archive_name="Boomsticks_and_Sharpsticks_1.4.7z",
    )

    message = str(error)

    assert "Boomsticks and Sharpsticks" in message
    assert "Boomsticks_and_Sharpsticks_1.4.7z" in message
    assert "https://www.moddb.com/mods/stalker-anomaly/addons/boomsticks-and-sharpsticks" in message
    assert "/games/gamma/downloads" in message
    # Le message contient toujours la trace brute (contexte pour une issue),
    # mais jamais *seulement* elle : le hint actionnable est ajouté derrière.
    assert "→" in message


def test_execution_error_classifies_the_recognized_cause() -> None:
    error = EngineExecutionError("full-install", 1, _MODDB_FAILURE)

    assert error.cause is FailureCause.MOD_LINK_BROKEN


def test_execution_error_cause_is_none_when_unrecognized() -> None:
    error = EngineExecutionError("full-install", 1, "some unrelated failure")

    assert error.cause is None


def test_local_corruption_hint_points_to_retry_failed_without_asking_for_a_manual_fetch() -> None:
    error = EngineExecutionError(
        "full-install",
        1,
        "Hash verification failed for GAMMA_RC3.7z",
        Path("/games/gamma/downloads"),
        mod_name="GAMMA Core",
        archive_name="GAMMA_RC3.7z",
    )

    message = str(error)

    assert error.cause is FailureCause.LOCAL_CORRUPTION
    assert "GAMMA Core" in message
    assert "GAMMA_RC3.7z" in message
    assert "install --retry-failed" in message
    assert "open" not in message.lower()  # pas de consigne de dépôt manuel ici


def test_network_unreachable_hint_says_to_wait_not_to_fetch_manually() -> None:
    output = (
        "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='www.moddb.com', "
        "port=443): Max retries exceeded with url: /downloads/start/277404"
    )
    error = EngineExecutionError("anomaly-install", 1, output, mod_name="Anomaly base")

    message = str(error)

    assert error.cause is FailureCause.NETWORK_UNREACHABLE
    assert "was installing Anomaly base" in message
    assert "wait a few minutes" in message
    assert "open" not in message.lower()  # pas de consigne de dépôt manuel ici


class TestDepositMismatchError:
    def test_message_names_mod_path_and_both_hashes(self) -> None:
        error = DepositMismatchError(
            "Boomsticks and Sharpsticks",
            Path("/games/gamma/downloads/Boomsticks_and_Sharpsticks_1.4.7z"),
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )

        message = str(error)

        assert "Boomsticks and Sharpsticks" in message
        assert "/games/gamma/downloads/Boomsticks_and_Sharpsticks_1.4.7z" in message
        assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in message
        assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in message
