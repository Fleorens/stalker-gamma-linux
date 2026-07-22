import logging
from pathlib import Path

from stalker_gamma_linux import logging_setup


def test_configure_logging_creates_rotating_file_under_state_dir(tmp_path: Path) -> None:
    path = logging_setup.configure_logging(verbose=False)

    assert path == logging_setup.state_dir() / "stalker-gamma-linux.log"
    assert path.parent.exists()

    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    logger.info("hello")
    assert path.exists()
    assert "hello" in path.read_text(encoding="utf-8")


def test_configure_logging_console_level_follows_verbose_flag() -> None:
    logging_setup.configure_logging(verbose=False)
    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    console_handler = next(h for h in logger.handlers if type(h) is logging.StreamHandler)
    assert console_handler.level == logging.WARNING

    logging_setup.configure_logging(verbose=True)
    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    console_handler = next(h for h in logger.handlers if type(h) is logging.StreamHandler)
    assert console_handler.level == logging.DEBUG
