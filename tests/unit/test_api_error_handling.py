"""Tests for the API's structured logging and unhandled-exception handler."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.logging_config import configure_logging


@pytest.fixture
def restore_logging():
    """Undo any root-logger changes a test makes."""
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def test_unhandled_exception_returns_standard_envelope(restore_logging):
    app = create_app()

    @app.get("/__boom")
    def boom():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error"}
    }


def test_unhandled_exception_does_not_leak_the_traceback(restore_logging):
    app = create_app()

    @app.get("/__boom_secret")
    def boom():
        raise RuntimeError("secret-internal-detail")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__boom_secret")

    assert response.status_code == 500
    assert "secret-internal-detail" not in response.text


def test_unhandled_exception_is_logged_as_json(restore_logging, capsys):
    configure_logging("INFO", force=True)
    app = create_app()

    @app.get("/__boom_log")
    def boom():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/__boom_log").status_code == 500

    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    assert any(payload.get("message") == "unhandled error" for payload in payloads)


def test_configure_logging_emits_single_json_lines(restore_logging, capsys):
    configure_logging("INFO", force=True)
    logging.getLogger("backend.api.test").info("hello world")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["message"] == "hello world"
    assert payload["levelname"] == "INFO"
    assert payload["name"] == "backend.api.test"


def test_configure_logging_is_idempotent(restore_logging):
    configure_logging("INFO", force=True)
    first = logging.getLogger().handlers
    configure_logging("INFO")
    assert logging.getLogger().handlers == first
