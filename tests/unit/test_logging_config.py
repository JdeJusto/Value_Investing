"""Tests for the shared structured (JSON) logging configuration."""

from __future__ import annotations

import json
import logging

import pytest

from backend.logging_config import configure_logging


@pytest.fixture
def restore_logging():
    """Undo any root-logger changes a test makes."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def test_configure_logging_emits_single_json_lines(restore_logging, capsys):
    configure_logging("INFO", force=True)
    logging.getLogger("backend.logging_config.test").info("hello world")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["message"] == "hello world"
    assert payload["levelname"] == "INFO"
    assert payload["name"] == "backend.logging_config.test"


def test_configure_logging_is_idempotent(restore_logging):
    configure_logging("INFO", force=True)
    first = logging.getLogger().handlers
    configure_logging("INFO")
    assert logging.getLogger().handlers == first
