import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger("backend")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"backend.{name}")
