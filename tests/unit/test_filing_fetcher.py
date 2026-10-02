"""FilingFetcher: disk cache, no re-fetch, graceful failures."""

from __future__ import annotations

import json
import urllib.error
from typing import Self

from backend.services.filing_fetcher import FilingFetcher


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> bool:
        return False


def _patch_urlopen(monkeypatch, handler):
    monkeypatch.setattr(
        "backend.services.filing_fetcher.urllib.request.urlopen", handler
    )


def test_fetch_writes_cache_and_never_refetches(tmp_path, monkeypatch):
    calls: list[str] = []

    def handler(request, timeout=None):
        calls.append(request.full_url)
        return _Response("<html><body>doc</body></html>")

    _patch_urlopen(monkeypatch, handler)
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0 x@example.com")

    first = fetcher.fetch_html("0000320193", "0000320193-24-000123", "aapl.htm")
    assert first is not None and "doc" in first
    assert len(calls) == 1
    cached = tmp_path / "320193" / "000032019324000123" / "aapl.htm"
    assert cached.exists()

    # Same session: memory cache, no new request.
    assert fetcher.fetch_html("0000320193", "0000320193-24-000123", "aapl.htm") == first
    assert len(calls) == 1

    # New session: disk cache, still no request.
    fresh = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0 x@example.com")
    assert fresh.fetch_html("0000320193", "0000320193-24-000123", "aapl.htm") == first
    assert len(calls) == 1


def test_http_error_returns_none_without_raising(tmp_path, monkeypatch):
    def handler(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    _patch_urlopen(monkeypatch, handler)
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    assert fetcher.fetch_html("1", "acc", "doc.htm") is None


def test_transport_error_returns_none(tmp_path, monkeypatch):
    def handler(request, timeout=None):
        raise OSError("network down")

    _patch_urlopen(monkeypatch, handler)
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    assert fetcher.fetch_html("1", "acc", "doc.htm") is None


def test_primary_document_resolution_prefers_the_biggest_non_exhibit(
    tmp_path, monkeypatch
):
    payload = json.dumps(
        {
            "directory": {
                "item": [
                    {"name": "a10-kexhibit991.htm", "size": "50000"},
                    {"name": "aapl-20240928.htm", "size": "1500000"},
                    {"name": "0000320193-24-000123-index.html", "size": "20000"},
                ]
            }
        }
    )
    _patch_urlopen(monkeypatch, lambda request, timeout=None: _Response(payload))
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    assert (
        fetcher.resolve_primary_document("0000320193", "0000320193-24-000123")
        == "aapl-20240928.htm"
    )


def test_fetch_without_primary_document_resolves_then_fetches(tmp_path, monkeypatch):
    payload = json.dumps({"directory": {"item": [{"name": "doc.htm", "size": "100"}]}})
    seen: list[str] = []

    def handler(request, timeout=None):
        seen.append(request.full_url)
        if request.full_url.endswith("index.json"):
            return _Response(payload)
        return _Response("<html>doc</html>")

    _patch_urlopen(monkeypatch, handler)
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    html = fetcher.fetch_html("0000320193", "0000320193-24-000123")
    assert html == "<html>doc</html>"
    assert len(seen) == 2  # index.json + the document


def test_get_cached_reads_without_network(tmp_path, monkeypatch):
    def handler(request, timeout=None):  # pragma: no cover — must not be called
        raise AssertionError("network call for a cached document")

    _patch_urlopen(monkeypatch, handler)
    target = tmp_path / "320193" / "000032019324000123"
    target.mkdir(parents=True)
    (target / "aapl.htm").write_text("<html>cached</html>", encoding="utf-8")

    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    assert fetcher.get_cached("0000320193", "0000320193-24-000123") == (
        "<html>cached</html>"
    )
    assert fetcher.fetch_html("0000320193", "0000320193-24-000123", "aapl.htm") == (
        "<html>cached</html>"
    )


def test_cache_size_warning_and_clear(tmp_path):
    fetcher = FilingFetcher(cache_dir=tmp_path, user_agent="Test/1.0")
    assert fetcher.cache_size_bytes() == 0
    assert fetcher.cache_warning(limit=1) is None
    (tmp_path / "doc.htm").write_text("x" * 100, encoding="utf-8")
    assert fetcher.cache_size_bytes() == 100
    assert fetcher.cache_warning(limit=1) is not None
    assert fetcher.clear_cache() == 1
    assert fetcher.cache_size_bytes() == 0
