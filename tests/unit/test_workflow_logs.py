"""The workflow logs through the API's structured (JSON) logging config."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

try:  # python-json-logger >= 3 (same import dance as backend.api.logging_config)
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - python-json-logger < 3
    from pythonjsonlogger.jsonlogger import JsonFormatter

from backend.api import logging_config
from scripts import daily_workflow


@pytest.fixture
def json_logging(monkeypatch):
    """Install the JSON handler through the workflow's own entry point.

    ``configure_logging`` is idempotent and refuses to hijack pytest's own
    capture, so the test forces it (as a real CLI process effectively would,
    having no handler yet) and restores the root logger afterwards.
    """
    real = logging_config.configure_logging
    monkeypatch.setattr(
        daily_workflow,
        "configure_logging",
        lambda level="INFO", **_: real(level, force=True),
    )
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield root
    root.handlers = saved_handlers
    root.setLevel(saved_level)


def test_workflow_installs_a_json_handler(json_logging):
    daily_workflow._configure_logging(verbose=False)
    handler = json_logging.handlers[-1]
    assert isinstance(handler.formatter, JsonFormatter)


def test_logger_output_is_json_with_the_minimum_keys(json_logging):
    daily_workflow._configure_logging(verbose=False)
    handler = json_logging.handlers[-1]

    record = logging.LogRecord(
        "daily_workflow", logging.WARNING, __file__, 12, "hello", None, None
    )
    payload = json.loads(handler.formatter.format(record))

    # The minimum fields a log collector needs from every line.
    assert payload["message"] == "hello"
    assert payload["levelname"] == "WARNING"
    assert payload["name"] == "daily_workflow"


def test_workflow_default_level_is_info():
    daily_workflow._configure_logging(verbose=False)
    assert logging.getLogger().level == logging.INFO


def test_workflow_verbose_level_is_debug():
    daily_workflow._configure_logging(verbose=True)
    assert logging.getLogger().level == logging.DEBUG


def test_workflow_does_not_use_plain_basic_config():
    """The workflow must reuse the JSON logger, not install its own handler."""
    text = Path(daily_workflow.__file__).read_text(encoding="utf-8")
    assert "logging.basicConfig" not in text
    assert "configure_logging" in text
