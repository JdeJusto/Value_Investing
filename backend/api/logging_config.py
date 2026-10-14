"""Structured (JSON) logging for the API server.

Every log line is a JSON object, so a log collector can index the fields
without parsing prose. The full traceback of an unhandled exception still goes
to the log (see ``backend.api.app``); only the client-facing body is generic.

``configure_logging`` is idempotent: ``create_app()`` calls it, and the test
session builds many apps, so it only installs its handler when the root logger
has none yet (or ``force=True``) and never hijacks pytest's own capture.
"""

from __future__ import annotations

import logging
import sys

try:  # python-json-logger >= 3
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - python-json-logger < 3
    from pythonjsonlogger.jsonlogger import JsonFormatter

_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"


def configure_logging(level: str = "INFO", *, force: bool = False) -> None:
    """Install the JSON formatter on the root logger.

    Acts only when the root logger has no handlers yet (or ``force=True``).
    """
    root = logging.getLogger()
    if not root.handlers or force:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(_JSON_FORMAT))
        root.handlers = [handler]
    root.setLevel(level)
