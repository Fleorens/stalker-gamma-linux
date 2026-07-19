from stalker_gamma_linux.engine.errors import (
    EngineExecutionError,
    EngineNotFoundError,
    VerificationError,
)


def test_engine_not_found_error_message_is_actionable() -> None:
    error = EngineNotFoundError()

    assert "PATH" in str(error)
    assert "pip install" in str(error)


def test_execution_error_includes_known_hint_for_moddb_mirror_issue() -> None:
    error = EngineExecutionError("full-install", 1, "ModDB download link not found")

    assert "issue #167" in str(error)


def test_execution_error_falls_back_to_generic_resume_hint() -> None:
    error = EngineExecutionError("full-install", 1, "some unrelated failure")

    assert "cache déjà téléchargé" in str(error)


def test_verification_error_is_an_execution_error_subtype() -> None:
    error = VerificationError("check-md5", 1, "Invalid file(s) detected")

    assert isinstance(error, EngineExecutionError)
    assert error.subcommand == "check-md5"
    assert error.returncode == 1
