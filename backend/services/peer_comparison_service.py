"""Peer comparison: the six scorecard dimensions of a company and its peers.

Design: ``docs/circle_chart_design.md``. The service is read-only and
deterministic: peers are active listings in the subject's sector (industry
fallback) ordered by latest total assets, and every score comes from
:class:`ScorecardService` — no new financial model and no prices persisted.
"""

from __future__ import annotations

from typing import Any

from backend.services.scorecard_service import DIMENSION_ORDER, ScorecardService

#: How many candidates to inspect beyond N peers: some have no scored
#: dimensions (banks, REITs, early-stage filers) and are skipped.
_CANDIDATE_MULTIPLIER = 3


class PeerComparisonService:
    """Build the six-dimension matrix for a ticker and its same-sector peers."""

    def __init__(
        self,
        repository: Any = None,
        scorecard_service: Any = None,
        price_service: Any = None,
    ) -> None:
        self._repository = repository
        self._scorecards = scorecard_service
        self._price_service = price_service

    # -- lazy collaborators -------------------------------------------------
    def _repo(self) -> Any:
        if self._repository is None:
            from backend.app.cli import build_financial_repository

            self._repository = build_financial_repository()
        return self._repository

    def _service(self) -> Any:
        if self._scorecards is None:
            self._scorecards = ScorecardService(self._repo())
        return self._scorecards

    def _prices(self) -> Any:
        if self._price_service is None:
            from backend.services.price_service import get_price_service

            self._price_service = get_price_service()
        return self._price_service

    def _order_by_market_cap(self, candidates: list[str]) -> list[str]:
        """Largest first by Yahoo market cap (USD); source order on failure.

        ``core_financials.total_assets`` is reported in the company's filing
        currency, so it cannot order a sector across US, Japanese and Korean
        filers. Market cap is the only comparable size measure; a failed
        snapshot leaves the repository order untouched.
        """
        if len(candidates) < 2:
            return candidates
        try:
            snapshots = self._prices().get_market_snapshots(candidates) or {}
        except Exception:  # noqa: BLE001 — no caps: keep the repository order
            return candidates
        if not snapshots:
            return candidates

        def cap(ticker: str) -> float:
            snapshot = snapshots.get(ticker) or {}
            value = snapshot.get("marketCap")
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        return sorted(candidates, key=lambda ticker: (-cap(ticker), ticker))

    # -- public API ---------------------------------------------------------
    def get_peer_dimensions(
        self, ticker: str, n_peers: int = 5
    ) -> dict[str, dict[str, int | None]]:
        """``{ticker: {dimension_key: score}}``, subject first, at most N peers.

        Only dimensions with a numeric score are meaningful; a ``None`` is a
        gap (never 0). Returns ``{}`` when the subject's scorecard cannot be
        built or the company has no sector/industry to group by.
        """
        symbol = str(ticker).upper().strip()
        wanted = max(int(n_peers), 0)
        card = self._service().build(symbol)
        if card is None:
            return {}
        subject_scores = {
            dimension.key: dimension.score for dimension in card.dimensions
        }
        payload: dict[str, dict[str, int | None]] = {
            symbol: {key: subject_scores.get(key) for key in DIMENSION_ORDER}
        }
        if wanted == 0:
            return payload

        sector = card.sector
        industry = card.industry
        lister = getattr(self._repo(), "list_peer_tickers", None)
        if lister is None:
            return payload
        candidates = self._order_by_market_cap(
            lister(
                sector=sector,
                industry=industry,
                exclude=symbol,
                limit=wanted * _CANDIDATE_MULTIPLIER,
            )
        )
        for peer in candidates:
            if len(payload) >= wanted + 1:
                break
            peer_card = self._service().build(peer)
            if peer_card is None:
                continue
            scores = {
                dimension.key: dimension.score for dimension in peer_card.dimensions
            }
            # Banks/REITs and empty cards carry no score: skip instead of
            # drawing an empty polygon and consuming a peer slot.
            if all(score is None for score in scores.values()):
                continue
            payload[peer] = {key: scores.get(key) for key in DIMENSION_ORDER}
        return payload
