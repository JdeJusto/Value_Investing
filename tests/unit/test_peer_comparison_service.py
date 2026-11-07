"""Peer comparison service (hermetic): subject first, same-sector peers only."""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.peer_comparison_service import PeerComparisonService
from backend.services.scorecard_service import DIMENSION_ORDER


def _card(sector="Technology", industry="Consumer Electronics", scores=None):
    scores = scores or {}
    return SimpleNamespace(
        sector=sector,
        industry=industry,
        dimensions=[
            SimpleNamespace(key=key, score=scores.get(key)) for key in DIMENSION_ORDER
        ],
    )


class _Repository:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls: list[dict] = []

    def list_peer_tickers(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.candidates)


class _Prices:
    def __init__(self, caps=None):
        self.caps = caps or {}

    def get_market_snapshots(self, tickers):
        return {ticker: {"marketCap": self.caps.get(ticker)} for ticker in tickers}


class _Scorecards:
    def __init__(self, cards):
        self.cards = cards
        self.built: list[str] = []

    def build(self, ticker):
        self.built.append(ticker)
        return self.cards.get(ticker)


def _service(cards, candidates, caps=None):
    repository = _Repository(candidates)
    return (
        PeerComparisonService(
            repository=repository,
            scorecard_service=_Scorecards(cards),
            price_service=_Prices(caps),
        ),
        repository,
    )


def test_returns_n_peers_with_the_subject_first():
    cards = {
        "AAPL": _card(scores={"growth": 7, "valuation": 2}),
        "MSFT": _card(scores={"growth": 8}),
        "NVDA": _card(scores={"growth": 10}),
        "AVGO": _card(scores={"growth": 9}),
        "AMD": _card(scores={"growth": 6}),
    }
    service, _ = _service(cards, ["MSFT", "NVDA", "AVGO", "AMD"])
    payload = service.get_peer_dimensions("aapl", n_peers=3)

    assert next(iter(payload)) == "AAPL"
    assert len(payload) == 4  # subject + 3 peers
    assert set(payload["AAPL"]) == set(DIMENSION_ORDER)


def test_asks_the_repository_for_the_subjects_sector():
    cards = {"AAPL": _card(), "MSFT": _card(scores={"growth": 8})}
    service, repository = _service(cards, ["MSFT"])

    service.get_peer_dimensions("AAPL", n_peers=5)

    assert repository.calls == [
        {
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exclude": "AAPL",
            "limit": 15,
        }
    ]


def test_na_peers_are_skipped_and_do_not_consume_a_slot():
    cards = {
        "AAPL": _card(scores={"growth": 7}),
        "JPM": _card(sector="Financial Services", scores={}),  # all None
        "MSFT": _card(scores={"growth": 8}),
    }
    service, _ = _service(cards, ["JPM", "MSFT"])
    payload = service.get_peer_dimensions("AAPL", n_peers=1)

    assert list(payload) == ["AAPL", "MSFT"]


def test_fewer_peers_than_requested_returns_the_available_ones():
    cards = {"AAPL": _card(scores={"growth": 7}), "MSFT": _card(scores={"growth": 8})}
    service, _ = _service(cards, ["MSFT"])

    assert len(service.get_peer_dimensions("AAPL", n_peers=5)) == 2


def test_missing_subject_scorecard_returns_empty():
    service, repository = _service({}, ["MSFT"])
    assert service.get_peer_dimensions("AAPL") == {}
    assert repository.calls == []


def test_industry_is_the_fallback_group():
    cards = {"AAPL": _card(sector=None, scores={"growth": 7})}
    service, repository = _service(cards, [])

    service.get_peer_dimensions("AAPL")

    assert repository.calls[0]["sector"] is None
    assert repository.calls[0]["industry"] == "Consumer Electronics"


def test_candidates_are_ordered_by_market_cap():
    """Total assets are in filing currency; market cap is the comparable size."""
    cards = {
        "AAPL": _card(scores={"growth": 7}),
        "SMALL": _card(scores={"growth": 5}),
        "BIG": _card(scores={"growth": 9}),
    }
    service, _ = _service(cards, ["SMALL", "BIG"], caps={"SMALL": 10.0, "BIG": 900.0})

    payload = service.get_peer_dimensions("AAPL", n_peers=1)

    assert list(payload) == ["AAPL", "BIG"]
