# logger.py
import logging
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
LOG_FILE = BASE_DIR / "hata.log.txt"

_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("DPI")
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    _logger.addHandler(ch)

    return _logger