"""The SEC facts client shared by the audit and the validation scripts."""

from __future__ import annotations

import json
from datetime import date
from typing import Self

import pytest

from backend.services.sec_facts_client import (
    Fact,
    SecFactsClient,
    SecFallbackFetcher,
    annual_facts,
    concept_has_facts,
    drop_zero_facts,
    parse_date,
    preferred_facts,
    split_tag,
)

FY_START = date(2023, 9, 30)
FY_END = date(2024, 9, 28)


# ---------------------------------------------------------------------------
# stubs
# ---------------------------------------------------------------------------
class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _Router:
    """A fake ``urlopen`` that answers by the kind of SEC endpoint asked."""

    def __init__(self, *, concept=None, facts=None) -> None:
        self.concept = concept
        self.facts = facts
        self.calls: list[str] = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        if "companyconcept" in url:
            body = self.concept
        else:
            body = self.facts
        if body is None:
            raise OSError("network down")
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        return _Response(body)


def _fact(
    value: float,
    *,
    end: date = FY_END,
    start: date | None = FY_START,
    form: str = "10-K",
    filed: str = "2024-11-01",
) -> dict:
    raw: dict = {"val": value, "end": end.isoformat(), "form": form, "filed": filed}
    if start is not None:
        raw["start"] = start.isoformat()
    return raw


def _envelope(*facts: dict, unit: str = "USD") -> dict:
    return {"units": {unit: list(facts)}}


def _client(router: _Router) -> SecFactsClient:
    return SecFactsClient("agent", min_interval=0.0, opener=router)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def test_split_tag_defaults_to_us_gaap_and_accepts_a_taxonomy():
    assert split_tag("Revenues") == ("us-gaap", "Revenues")
    assert split_tag("dei:EntityCommonStockSharesOutstanding") == (
        "dei",
        "EntityCommonStockSharesOutstanding",
    )


def test_parse_date_tolerates_a_trailing_timestamp():
    assert parse_date("2024-09-28T00:00:00") == FY_END
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_concept_has_facts_distinguishes_an_empty_envelope():
    assert concept_has_facts(_envelope(_fact(1.0)))
    assert not concept_has_facts({"units": {"USD": {}}})
    assert not concept_has_facts({"units": {}})
    assert not concept_has_facts({})
    assert not concept_has_facts(None)


def test_drop_zero_facts_keeps_only_non_zero_values():
    facts = [Fact(value=0.0), Fact(value=1.0), Fact(value=-2.0)]
    assert [fact.value for fact in drop_zero_facts(facts)] == [1.0, -2.0]


def test_annual_facts_sorts_the_closest_period_first():
    payload = _envelope(
        _fact(90.0, end=date(2023, 9, 30), start=date(2022, 10, 1)),
        _fact(100.0),
    )
    assert [fact.value for fact in annual_facts(payload, FY_END)] == [100.0, 90.0]


def test_preferred_facts_prefers_a_covering_tag_over_a_stale_later_filing():
    stale = _fact(
        1.0, end=date(2018, 9, 29), start=date(2017, 10, 1), filed="2025-01-01"
    )
    by_tag = {
        "Revenues": annual_facts(_envelope(stale), FY_END),
        "Current": annual_facts(_envelope(_fact(2.0)), FY_END),
    }
    tag, facts = preferred_facts(by_tag, FY_END)
    assert tag == "Current"
    assert facts[0].value == 2.0


# ---------------------------------------------------------------------------
# the client
# ---------------------------------------------------------------------------
def test_the_per_tag_endpoint_is_used_when_it_answers():
    router = _Router(concept=_envelope(_fact(100.0)), facts={"facts": {}})
    client = _client(router)
    payload = client.fetch("0000320193", "Revenues")
    assert concept_has_facts(payload)
    assert client.fallback_issuers == set()
    assert not any("companyfacts" in url for url in router.calls)


def test_an_empty_envelope_falls_back_to_companyfacts():
    facts = {"facts": {"us-gaap": {"Revenues": _envelope(_fact(100.0))}}}
    router = _Router(concept={"units": {"USD": {}}}, facts=facts)
    client = _client(router)
    assert client.fetch("0000320193", "Revenues") == _envelope(_fact(100.0))
    assert client.fallback_issuers == {"0000320193"}


def test_the_fallback_loads_the_taxonomy_named_by_the_tag():
    facts = {
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": _envelope(_fact(100.0))}
        }
    }
    router = _Router(concept={"units": {"shares": {}}}, facts=facts)
    client = _client(router)
    payload = client.fetch("0000320193", "dei:EntityCommonStockSharesOutstanding")
    assert concept_has_facts(payload)
    assert any("/dei/" in url for url in router.calls)


def test_a_transport_failure_degrades_to_none_without_a_fallback():
    router = _Router(concept=None, facts=None)
    client = SecFactsClient("agent", min_interval=0.0, attempts=2, opener=router)
    assert client.companyconcept("1", "Revenues") is None
    assert client.concepts("1") is None
    assert client.latest_annual("1", ["Revenues"], FY_END) is None
    assert client.fallback_issuers == set()


def test_responses_are_cached_for_the_process_lifetime():
    router = _Router(concept=_envelope(_fact(100.0)), facts={"facts": {}})
    client = _client(router)
    client.fetch("0000320193", "Revenues")
    client.fetch("0000320193", "Revenues")
    assert len(router.calls) == 1


def test_a_malformed_body_degrades_to_none():
    router = _Router(concept=b"not json", facts={"facts": {}})
    client = _client(router)
    assert client.companyconcept("1", "Revenues") is None


def test_latest_annual_applies_the_tag_preference():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": _envelope(
                    _fact(
                        265.0,
                        end=date(2018, 9, 29),
                        start=date(2017, 10, 1),
                        filed="2025-01-01",
                    )
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _envelope(
                    _fact(100.0, filed="2024-06-01")
                ),
            }
        }
    }
    router = _Router(concept={"units": {"USD": {}}}, facts=facts)
    client = _client(router)
    chosen = client.latest_annual(
        "0000320193",
        [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],
        FY_END,
    )
    assert chosen == {
        "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "value": 100.0,
        "period_end": FY_END,
        "filed": "2024-06-01",
    }


def test_latest_annual_drops_zero_placeholders_unless_asked_to_keep_them():
    facts = {"facts": {"us-gaap": {"Assets": _envelope(_fact(0.0, start=None))}}}
    router = _Router(concept={"units": {"USD": {}}}, facts=facts)
    client = _client(router)
    assert client.latest_annual("0000320193", ["Assets"], FY_END) is None
    kept = client.latest_annual("0000320193", ["Assets"], FY_END, keep_zero=True)
    assert kept is not None and kept["value"] == 0.0


def test_annual_facts_for_a_tag_is_sorted_and_filtered():
    router = _Router(concept=_envelope(_fact(0.0)), facts={"facts": {}})
    client = _client(router)
    assert client.annual_facts("1", "Revenues", FY_END) == []
    assert len(client.annual_facts("1", "Revenues", FY_END, keep_zero=True)) == 1


# ---------------------------------------------------------------------------
# one code path for both scripts
# ---------------------------------------------------------------------------
def test_the_audit_and_the_validation_read_the_same_number():
    # Two full years of facts, the current one filed later: both scripts must
    # pick FY2024, because they run the same parser and the same preference.
    payload = _envelope(
        _fact(90.0, end=date(2023, 9, 30), start=date(2022, 10, 1)),
        _fact(100.0),
    )
    router = _Router(concept=payload, facts={"facts": {}})
    client = _client(router)

    from scripts.audit_data_quality import AUDIT_METRICS, sec_metric_facts
    from scripts.validate_data_sample import annual_fact

    revenue = next(spec for spec in AUDIT_METRICS if spec.metric == "revenue")
    by_tag, dropped = sec_metric_facts("0000320193", revenue, client.fetch, FY_END)
    audit_value = by_tag[revenue.tags[0]][0].value
    validate_value = annual_fact(client.fetch("0000320193", revenue.tags[0]), FY_END)

    assert dropped is False
    assert audit_value == validate_value == 100.0

    # And the same parser is what the client itself returns.
    chosen = client.latest_annual("0000320193", list(revenue.tags), FY_END)
    assert chosen is not None and chosen["value"] == 100.0


def test_the_fallback_fetcher_serves_every_tag_from_one_document():
    asked: list[tuple[str, str]] = []

    def loader(cik: str, taxonomy: str):
        asked.append((cik, taxonomy))
        return {"Revenues": _envelope(_fact(100.0))}

    fetcher = SecFallbackFetcher(lambda cik, tag: {"units": {"USD": {}}}, loader)
    assert concept_has_facts(fetcher("0000021344", "Revenues"))
    assert fetcher.fallback_issuers == {"0000021344"}
    assert asked == [("0000021344", "us-gaap")]


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_facts_of_a_zero_year_are_reported_consistently(value):
    # A regression guard for the shared parser: both scripts must see the same
    # set of facts for a payload, zero-valued or not.
    payload = _envelope(_fact(value))
    assert [fact.value for fact in annual_facts(payload, FY_END)] == [value]


def test_a_manifestly_old_period_still_parses():
    # ``annual_facts`` is period-agnostic: a genuine one-year span from an old
    # period parses, and only the preference decides it does not cover the year.
    payload = _envelope(
        _fact(1.0, end=date(2018, 9, 29), start=date(2017, 10, 1)),
    )
    facts = annual_facts(payload, FY_END)
    assert [fact.value for fact in facts] == [1.0]
