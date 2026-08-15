from pathlib import Path

from stalker_gamma_linux.engine.errors import (
    EngineExecutionError,
    EngineNotFoundError,
    VerificationError,
)

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
