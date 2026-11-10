"""Tests for the guided menu prompts (selectors, fields, cancellation)."""

from __future__ import annotations

import pytest

from backend.services import cli_output
from cli import menu_prompts, theme
from cli.menu_prompts import (
    PromptCancelled,
    ask_choice,
    ask_int,
    ask_methodology,
    ask_text,
    ask_ticker,
    ask_universe,
    ask_yes_no,
)


def _answers(monkeypatch, *values: str) -> None:
    responses = iter(values)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))


# ---------------------------------------------------------------------------
# ask_choice
# ---------------------------------------------------------------------------
def test_ask_choice_returns_the_selected_value(monkeypatch):
    _answers(monkeypatch, "2")
    assert ask_choice("Pick", [("A", "a"), ("B", "b"), ("C", "c")]) == "b"


def test_ask_choice_uses_the_default_on_empty_input(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_choice("Pick", [("A", "a"), ("B", "b")], default_index=1) == "b"


def test_ask_choice_retries_after_invalid_input(monkeypatch):
    _answers(monkeypatch, "99", "abc", "2")
    assert ask_choice("Pick", [("A", "a"), ("B", "b")]) == "b"


def test_ask_choice_cancels_on_q(monkeypatch):
    _answers(monkeypatch, "q")
    with pytest.raises(PromptCancelled):
        ask_choice("Pick", [("A", "a")])


def test_ask_choice_cancels_on_back(monkeypatch):
    _answers(monkeypatch, "back")
    with pytest.raises(PromptCancelled):
        ask_choice("Pick", [("A", "a")])


def test_ask_choice_cancels_on_ctrl_c(monkeypatch):
    def _boom(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _boom)
    with pytest.raises(PromptCancelled):
        ask_choice("Pick", [("A", "a")])


# ---------------------------------------------------------------------------
# ask_int
# ---------------------------------------------------------------------------
def test_ask_int_uses_the_default(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_int("Num", default=10) == 10


def test_ask_int_enforces_the_range(monkeypatch):
    _answers(monkeypatch, "100", "5")
    assert ask_int("Num", min_val=1, max_val=10) == 5


def test_ask_int_requires_a_value_without_a_default(monkeypatch):
    _answers(monkeypatch, "", "7")
    assert ask_int("Num", min_val=1, max_val=10) == 7


def test_ask_int_rejects_non_integers(monkeypatch):
    _answers(monkeypatch, "abc", "4")
    assert ask_int("Num", min_val=1) == 4


# ---------------------------------------------------------------------------
# ask_text
# ---------------------------------------------------------------------------
def test_ask_text_returns_the_default(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_text("Ticker", default="AAPL") == "AAPL"


def test_ask_text_validator_reprompts(monkeypatch):
    _answers(monkeypatch, "bad", "good")
    result = ask_text(
        "Value",
        validator=lambda value: value == "good",
        validator_error="not good",
    )
    assert result == "good"


def test_ask_text_allow_empty(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_text("Optional", allow_empty=True) == ""


def test_ask_text_requires_a_value(monkeypatch):
    _answers(monkeypatch, "", "AAPL")
    assert ask_text("Ticker") == "AAPL"


def test_ask_text_cancel_token(monkeypatch):
    _answers(monkeypatch, "q")
    with pytest.raises(PromptCancelled):
        ask_text("Ticker")


# ---------------------------------------------------------------------------
# ask_yes_no
# ---------------------------------------------------------------------------
def test_ask_yes_no_default_is_no(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_yes_no("Continue?") is False


def test_ask_yes_no_accepts_y_and_n(monkeypatch):
    _answers(monkeypatch, "y")
    assert ask_yes_no("Continue?") is True
    _answers(monkeypatch, "n")
    assert ask_yes_no("Continue?", default=True) is False


def test_ask_yes_no_reprompts(monkeypatch):
    _answers(monkeypatch, "maybe", "yes")
    assert ask_yes_no("Continue?") is True


# ---------------------------------------------------------------------------
# ask_ticker
# ---------------------------------------------------------------------------
def test_ask_ticker_rejects_unknown_tickers(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker",
        lambda ticker: ticker.upper() if ticker.upper() in {"AAPL", "MSFT"} else None,
    )
    _answers(monkeypatch, "WRONG", "aapl")
    assert ask_ticker() == "AAPL"


def test_ask_ticker_accepts_when_the_database_is_down(monkeypatch):
    def _boom(_ticker):
        raise RuntimeError("database down")

    monkeypatch.setattr("backend.services.ticker_resolver.resolve_ticker", _boom)
    _answers(monkeypatch, "AAPL")
    assert ask_ticker() == "AAPL"


# ---------------------------------------------------------------------------
# ask_methodology
# ---------------------------------------------------------------------------
def test_ask_methodology_single(monkeypatch):
    _answers(monkeypatch, "1")
    methods, strategy = ask_methodology()
    assert len(methods) == 1
    assert strategy is None


def test_ask_methodology_combine(monkeypatch):
    # [c] Combine -> graham (4) + lynch_garp (7) -> AND
    _answers(monkeypatch, "c", "4,7", "1")
    methods, strategy = ask_methodology(include_combine=True)
    assert methods == ["graham", "lynch_garp"]
    assert strategy == "and"


def test_ask_methodology_combine_only_requires_two(monkeypatch):
    _answers(monkeypatch, "4", "4,7", "2")
    methods, strategy = ask_methodology(combine_only=True)
    assert methods == ["graham", "lynch_garp"]
    assert strategy == "or"


def test_ask_methodology_combine_rejects_out_of_range(monkeypatch):
    _answers(monkeypatch, "c", "99", "4,7", "1")
    methods, strategy = ask_methodology(include_combine=True)
    assert len(methods) == 2
    assert strategy == "and"


def test_ask_universe_defaults_to_sp500(monkeypatch):
    _answers(monkeypatch, "")
    assert ask_universe() == "sp500"


# ---------------------------------------------------------------------------
# style
# ---------------------------------------------------------------------------
def test_prompts_are_plain_without_color(monkeypatch, capsys):
    cli_output.reset_no_color()
    monkeypatch.setattr(theme, "is_enabled", lambda: False)
    _answers(monkeypatch, "1")
    ask_choice("Pick", [("A", "a"), ("B", "b")])
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "[1] A" in out
    assert "(q to cancel)" in out


def test_prompts_emit_the_synthwave_palette_when_enabled(monkeypatch, capsys):
    cli_output.reset_no_color()
    monkeypatch.setattr(theme, "is_enabled", lambda: True)
    _answers(monkeypatch, "1")
    ask_choice("Pick", [("A", "a")])
    out = capsys.readouterr().out
    assert theme.NEON_CYAN in out
    assert theme.GOLD in out


def test_prompt_cancelled_is_an_exception():
    assert issubclass(PromptCancelled, Exception)
    assert menu_prompts._CANCEL_TOKENS == {"q", "back"}
