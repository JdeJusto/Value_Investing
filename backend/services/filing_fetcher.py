"""Fetch SEC filing documents with a local cache (never re-fetch per session).

Reuses the project's stdlib HTTP pattern (``urllib.request`` + a descriptive
``SEC_USER_AGENT``, same as ``sec_health``) — no second HTTP client library.
Documents are cached under ``data/raw/filings/<cik>/<accession>/<name>``
(gitignored) and also memoised in memory so one session never downloads the
same URL twice.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

#: SEC asks for at most 10 requests/second; one document per call is far
#: below that, but consecutive fetches are paced anyway.
_PACE_SECONDS = 0.15
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
#: Warn (never delete) when the cache grows past this size.
CACHE_WARN_BYTES = 500 * 1024 * 1024


class FilingFetcher:
    """Raw HTML for one filing, cached on disk and in memory."""

    def __init__(
        self,
        cache_dir: str | Path = "data/raw/filings",
        user_agent: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._ua = user_agent or os.environ.get("SEC_USER_AGENT") or ""
        self._timeout = timeout
        self._memory: dict[str, str] = {}
        self._last_fetch = 0.0

    # ------------------------------------------------------------------
    def _get(self, url: str) -> str | None:
        """One paced GET; None on any transport/HTTP error (never raises)."""
        pause = _PACE_SECONDS - (time.monotonic() - self._last_fetch)
        if pause > 0:
            time.sleep(pause)
        request = urllib.request.Request(
            url, headers={"User-Agent": self._ua, "Accept": "text/html,*/*"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — network/404 must degrade, not raise
            return None
        finally:
            self._last_fetch = time.monotonic()
        return payload

    def _cache_path(self, cik: str, accession: str, name: str) -> Path:
        cik_no_zeros = str(int(cik)) if str(cik).isdigit() else str(cik)
        return self._cache_dir / cik_no_zeros / accession.replace("-", "") / name

    # ------------------------------------------------------------------
    def resolve_primary_document(self, cik: str, accession: str) -> str | None:
        """The filing's main document, from ``index.json``.

        Picks the largest ``.htm`` that is not an exhibit (the primary
        document is normally the biggest and named ``<ticker>-<date>.htm``);
        falls back to any non-index ``.htm``.
        """
        cik_no_zeros = str(int(cik)) if str(cik).isdigit() else str(cik)
        url = f"{_ARCHIVES}/{cik_no_zeros}/{accession.replace('-', '')}/index.json"
        payload = self._get(url)
        if payload is None:
            return None
        try:
            items = json.loads(payload)["directory"]["item"]
        except (ValueError, KeyError, TypeError):
            return None
        candidates = [
            item
            for item in items
            if str(item.get("name", "")).endswith(".htm")
            and "exhibit" not in str(item.get("name", "")).lower()
            and "index" not in str(item.get("name", "")).lower()
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: int(item.get("size") or 0), reverse=True)
        return str(candidates[0]["name"])

    def get_cached(
        self, cik: str, accession: str, name: str | None = None
    ) -> str | None:
        """Read from disk/memory without any network access."""
        if name is None:
            directory = self._cache_path(cik, accession, "x").parent
            if not directory.exists():
                return None
            files = sorted(directory.glob("*.htm"))
            if not files:
                return None
            name = files[0].name
        path = self._cache_path(cik, accession, name)
        key = str(path)
        if key in self._memory:
            return self._memory[key]
        if path.exists():
            try:
                html = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
            self._memory[key] = html
            return html
        return None

    def fetch_html(
        self,
        cik: str,
        accession: str,
        primary_document: str | None = None,
    ) -> str | None:
        """Raw HTML for a filing, or None (cached, never re-fetched)."""
        if not cik or not accession:
            return None
        if primary_document is None:
            primary_document = self.resolve_primary_document(cik, accession)
            if primary_document is None:
                return None

        cached = self.get_cached(cik, accession, primary_document)
        if cached is not None:
            return cached

        cik_no_zeros = str(int(cik)) if str(cik).isdigit() else str(cik)
        url = (
            f"{_ARCHIVES}/{cik_no_zeros}/{accession.replace('-', '')}/"
            f"{primary_document}"
        )
        html = self._get(url)
        if html is None:
            return None

        path = self._cache_path(cik, accession, primary_document)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
        except OSError:
            pass  # a read-only cache dir must not break the fetch
        self._memory[str(path)] = html
        return html

    # ------------------------------------------------------------------
    def cache_size_bytes(self) -> int:
        if not self._cache_dir.exists():
            return 0
        return sum(
            path.stat().st_size for path in self._cache_dir.rglob("*") if path.is_file()
        )

    def cache_warning(self, limit: int = CACHE_WARN_BYTES) -> str | None:
        """A human warning when the cache is large (never deletes anything)."""
        size = self.cache_size_bytes()
        if size <= limit:
            return None
        return (
            f"filing cache is {size / 1024 / 1024:.0f} MB "
            f"(> {limit / 1024 / 1024:.0f} MB); consider clearing "
            f"{self._cache_dir} manually"
        )

    def clear_cache(self) -> int:
        """Delete every cached document; returns the number of files removed."""
        if not self._cache_dir.exists():
            return 0
        removed = 0
        for path in self._cache_dir.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        self._memory.clear()
        return removed
