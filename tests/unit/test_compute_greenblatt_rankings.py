"""Safety-guard tests for the Greenblatt ranking writer."""

from __future__ import annotations

import json

from scripts import compute_greenblatt_rankings as script


def test_empty_ranking_writes_failed_not_overwrite(tmp_path):
    existing = tmp_path / "greenblatt_2026-09-30.json"
    existing.write_text('{"universe_size": 270, "rankings": {"AAPL": {"rank_roc": 1}}}')
    target = tmp_path / "greenblatt_2026-11-06.json"

    ok = script._write_ranking_safe(target, 0, {}, {"date": "2026-11-06"})

    assert ok is False
    assert not target.exists()
    failed = tmp_path / "greenblatt_2026-11-06.failed.json"
    assert failed.exists()
    payload = json.loads(failed.read_text())
    assert payload["error"] == "empty ranking, not overwriting last valid"
    assert payload["failed_at"]
    assert json.loads(existing.read_text())["rankings"] != {}


def test_valid_ranking_written(tmp_path):
    target = tmp_path / "greenblatt_2026-11-06.json"

    ok = script._write_ranking_safe(
        target, 500, {"AAPL": {"rank_roc": 1}}, {"date": "2026-11-06"}
    )

    assert ok is True
    data = json.loads(target.read_text())
    assert data["universe_size"] == 500
    assert "AAPL" in data["rankings"]
    assert data["date"] == "2026-11-06"


def test_main_returns_nonzero_for_empty_ranking(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "load_universe", lambda _spec: ["AAPL"])
    monkeypatch.setattr(
        script,
        "compute_rankings",
        lambda *_args, **_kwargs: {
            "date": "2026-11-06",
            "universe_size": 0,
            "rankings": {},
        },
    )

    code = script.main(["--universe", "sp500", "--output-dir", str(tmp_path)])

    assert code == 1
    assert (tmp_path / "greenblatt_2026-11-06.failed.json").exists()
    assert not (tmp_path / "greenblatt_2026-11-06.json").exists()
