"""Phase 5B unit tests: reading the peer-stats artifact.

The artifact is written by ``scripts/build_peer_stats.py``; here it is a real
one, built into a temporary directory, so the reader and the writer are pinned
against the same on-disk contract. Everything degrades to ``None``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.analytics.peer_stats import MIN_GROUP_COMPANIES
from backend.services.peer_stats_service import PeerStatsService
from scripts.build_peer_stats import PeerCompany, build_artifacts

GENERATED_AT = "2026-10-15T08:00:00Z"


def artifact_dir(tmp_path: Path, count: int = 12) -> Path:
    """A real artifact: ``count`` companies, P/E 10..(10+count-1)."""
    companies = [
        PeerCompany(
            ticker=f"T{index:02d}",
            sector="Technology",
            industry="Widgets",
            metrics={"pe_ratio": 10.0 + index, "net_margin": 0.05 + index / 100},
        )
        for index in range(count)
    ]
    build_artifacts(companies, generated_at=GENERATED_AT, out_dir=tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# resolution: industry first, sector fallback, thin groups skipped
# ---------------------------------------------------------------------------
def test_group_for_prefers_the_industry(tmp_path: Path):
    peers = PeerStatsService(artifact_dir(tmp_path))
    group = peers.group_for(sector="Technology", industry="Widgets")
    assert group is not None
    assert (group.level, group.name, group.size) == ("industry", "Widgets", 12)


def test_group_for_falls_back_to_the_sector(tmp_path: Path):
    peers = PeerStatsService(artifact_dir(tmp_path))
    # "Gadgets" has no artifact of its own, so the sector bucket applies.
    group = peers.group_for(sector="Technology", industry="Gadgets")
    assert group is not None
    assert (group.level, group.name) == ("sector", "Technology")
    assert group.size == 12


def test_group_for_is_none_without_any_artifact(tmp_path: Path):
    peers = PeerStatsService(tmp_path)
    assert peers.group_for(sector="Technology", industry="Widgets") is None
    assert peers.group_for(sector=None, industry=None) is None


def test_a_thin_group_is_rejected_even_if_the_file_exists(tmp_path: Path):
    artifact_dir(tmp_path)
    (tmp_path / "industry_thin.json").write_text(
        json.dumps(
            {
                "level": "industry",
                "group": "Thin",
                "company_count": MIN_GROUP_COMPANIES - 1,
                "metrics": {"pe_ratio": {"n": 1, "median": 10.0, "values": [10.0]}},
            }
        ),
        encoding="utf-8",
    )
    peers = PeerStatsService(tmp_path)
    assert peers.for_group("industry", "Thin") is not None  # the file is readable
    assert peers.group_for(sector=None, industry="Thin") is None  # but unusable


def test_missing_and_malformed_artifacts_degrade_to_none(tmp_path: Path):
    (tmp_path / "industry_broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "industry_empty.json").write_text("{}", encoding="utf-8")
    peers = PeerStatsService(tmp_path)
    assert peers.for_group("industry", "Broken") is None
    assert peers.for_group("industry", "Empty") is None
    assert peers.for_group("industry", "") is None
    assert peers.metric("industry", "Broken", "pe_ratio") is None
    assert peers.median("industry", "Broken", "pe_ratio") is None
    assert peers.percentile("industry", "Broken", "pe_ratio", 10.0) is None


# ---------------------------------------------------------------------------
# median and percentile
# ---------------------------------------------------------------------------
def test_median_comes_from_the_artifact(tmp_path: Path):
    peers = PeerStatsService(artifact_dir(tmp_path))
    # P/E 10..21 -> the median is the midpoint of 15 and 16.
    assert peers.median("industry", "Widgets", "pe_ratio") == pytest.approx(15.5)
    assert peers.metric("industry", "Widgets", "pe_ratio")["n"] == 12
    assert peers.median("industry", "Widgets", "pb_ratio") is None


def test_percentile_ranks_inside_the_stored_distribution(tmp_path: Path):
    peers = PeerStatsService(artifact_dir(tmp_path))
    # 12 peers at P/E 10..21: nothing is below 10, everything is below 21.
    assert peers.percentile("industry", "Widgets", "pe_ratio", 5.0) == 0.0
    assert peers.percentile("industry", "Widgets", "pe_ratio", 99.0) == 1.0
    # A value equal to the median reads ~0.5.
    assert peers.percentile("industry", "Widgets", "pe_ratio", 15.5) == pytest.approx(
        0.5
    )
    # Two of twelve strictly below 12 -> (2 + 0.5) / 12 with the tie at 12.
    assert peers.percentile("industry", "Widgets", "pe_ratio", 12.0) == pytest.approx(
        2.5 / 12
    )


def test_percentile_is_none_for_a_missing_value(tmp_path: Path):
    peers = PeerStatsService(artifact_dir(tmp_path))
    assert peers.percentile("industry", "Widgets", "pe_ratio", None) is None


def test_percentile_falls_back_to_quantiles_without_a_values_array(tmp_path: Path):
    (tmp_path / "industry_quantiled.json").write_text(
        json.dumps(
            {
                "level": "industry",
                "group": "Quantiled",
                "company_count": 40,
                "metrics": {
                    "pe_ratio": {
                        "n": 40,
                        "min": 5.0,
                        "p10": 10.0,
                        "p25": 15.0,
                        "median": 20.0,
                        "p75": 30.0,
                        "p90": 40.0,
                        "max": 50.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    peers = PeerStatsService(tmp_path)
    assert peers.percentile("industry", "Quantiled", "pe_ratio", 20.0) == pytest.approx(
        0.5
    )
    assert peers.percentile("industry", "Quantiled", "pe_ratio", 25.0) == pytest.approx(
        0.625
    )
    assert peers.percentile("industry", "Quantiled", "pe_ratio", 1.0) == 0.0
    assert peers.percentile("industry", "Quantiled", "pe_ratio", 100.0) == 1.0


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------
def test_artifacts_are_parsed_once_and_cached(tmp_path: Path):
    directory = artifact_dir(tmp_path)
    peers = PeerStatsService(directory)
    first = peers.for_group("industry", "Widgets")
    assert peers.for_group("industry", "Widgets") is peers.for_group(
        "industry", "Widgets"
    )
    # A later on-disk change is not seen until the cache is cleared (the
    # artifact is regenerated weekly, not per request).
    (directory / "industry_widgets.json").write_text("{}", encoding="utf-8")
    assert peers.for_group("industry", "Widgets") is first
    peers.clear_cache()
    assert peers.for_group("industry", "Widgets") is None
