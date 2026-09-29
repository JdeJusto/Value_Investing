"""Shared helpers for the universe construction scripts.

Centralizes the SEC EDGAR company ticker/CIK map and the European index
registry used by ``fetch_russell2000.py``, ``fetch_european_indices.py`` and
``build_universe.py`` so each script stays thin and unit-testable.

SEC data source: ``https://www.sec.gov/files/company_tickers.json`` — the
official EDGAR ticker-to-CIK map. It only contains companies that file with
the SEC, which is exactly the property used to decide whether a European
company is analyzable by this project (fundamentals come from SEC EDGAR via
Financial-DataBase).
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Optional

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# User-Agent required by SEC's fair-access policy (contact info included).
SEC_USER_AGENT = "ValueInvesting universe-builder research@example.com"

# European indices sourced from Wikipedia constituent lists. Values are
# (URL, expected approximate count) — the count is advisory/logged, never
# enforced, because index membership drifts at every rebalance.
EUROPEAN_INDEXES: dict[str, tuple[str, int]] = {
    "FTSE100": ("https://en.wikipedia.org/wiki/FTSE_100_Index", 100),
    "DAX40": ("https://en.wikipedia.org/wiki/DAX", 40),
    "CAC40": ("https://en.wikipedia.org/wiki/CAC_40", 40),
    "IBEX35": ("https://en.wikipedia.org/wiki/IBEX_35", 35),
    "FTSE_MIB": ("https://en.wikipedia.org/wiki/FTSE_MIB", 40),
    "AEX": ("https://en.wikipedia.org/wiki/AEX_index", 25),
    "SMI": ("https://en.wikipedia.org/wiki/Swiss_Market_Index", 20),
    "OMXS30": ("https://en.wikipedia.org/wiki/OMX_Stockholm_30", 30),
    # The Copenhagen benchmark is the OMX Copenhagen 20; the "25" label in
    # the wiki table refers to the constituent count reported there.
    "OMXC25": ("https://en.wikipedia.org/wiki/OMX_Copenhagen_20", 25),
}

# Preferred US ticker for the few companies where SEC ``company_tickers.json``
# only exposes an OTC/USR ticker while Financial-DataBase (and the workflow)
# is keyed on a different ticker. ABB has no NYSE listing in the SEC map — its
# EDGAR tickers are OTC ADRs (ABLZF/ABBNY); Financial-DataBase resolves ABB
# under ABBNY, so the European fetcher uses that one.
SEC_TICKER_PREFERENCES = {"ABLZF": "ABBNY"}

# European constituents whose SEC name-match is a FALSE POSITIVE: a different
# US company happens to share the same name key after company-type token
# stripping, and the European company does not file with the SEC (no ADR /
# 20-F / 40-F). Keyed by ``(index_code, company_key(name))``; the value is the
# human reason. Name-only matching can never distinguish these two, so they
# need a curated exclusion (audited manually against the index constituents
# and SEC EDGAR in 2026-09).
SEC_NAME_COLLISIONS: dict[tuple[str, str], str] = {
    ("AEX", "nn"): "NN Group N.V. (AEX) does not file with the SEC — the "
    "match is NN, Inc. (US, NASDAQ: NNBR)",
    ("DAX40", "merck"): "Merck KGaA (Frankfurt) does not file with the SEC — "
    "the match is Merck & Co. (US, NYSE: MRK)",
    ("FTSE100", "compass"): "Compass Group plc (LSE: CPG) does not file with "
    "the SEC — the match is Compass, Inc. (US, NYSE: COMP)",
    ("OMXS30", "eqt"): "EQT AB (Stockholm) does not file with the SEC — the "
    "match is EQT Corp (US, NYSE: EQT)",
}


# Company-type tokens that commonly differ between the Wikipedia constituent
# table and the SEC company title (dropped from the matching key for both).
_COMPANY_TYPE_TOKENS = {
    "a",
    "ag",
    "as",
    "co",
    "corp",
    "corporation",
    "group",
    "groupe",
    "grup",
    "holding",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "n",
    "nv",
    "plc",
    "sa",
    "sarl",
    "se",
    "spa",
    "srl",
    "v",
    "the",
    "aktiengesellschaft",
}


def _http_get_bytes(
    url: str,
    timeout: int = 90,
    user_agent: str = SEC_USER_AGENT,
) -> bytes:
    """Fetch a URL as bytes with a browser/contact User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def normalize_ticker(ticker: str) -> str:
    """Upper-case a ticker and normalize share-class separators.

    iShares holdings use ``MOG A`` while SEC EDGAR uses ``MOG-A``; this
    maps the iShares form and plain dots (``BF.B``) onto the EDGAR dash
    form (``BF-B``).
    """
    if not ticker:
        return ""
    t = ticker.strip().upper()
    t = re.sub(r"\s+", "-", t.replace(".", "-"))
    return t.strip("-")


def stripped_ticker(ticker: str) -> str:
    """Ticker with all non-alphanumerics removed (for lookup fallback)."""
    return re.sub(r"[^A-Z0-9]", "", normalize_ticker(ticker))


def company_key(name: str) -> str:
    """Compact, suffix-stripped matching key for a company name.

    Letters only, company-type tokens removed on both sides so that e.g.
    ``NOVO NORDISK A/S`` (Wikipedia) and ``NOVO NORDISK A S`` (SEC) collapse
    to the same key ``novonordisk``.
    """
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    kept = [
        w for w in words if w not in _COMPANY_TYPE_TOKENS and len(w) > 1
    ]
    return "".join(kept)


def _token_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity of two compact keys."""
    ta = set(re.findall(r"[a-z0-9]+", a))
    tb = set(re.findall(r"[a-z0-9]+", b))
    if not ta or not tb:
        return 1.0 if a == b else 0.0
    return len(ta & tb) / len(ta | tb)


def sec_company_tickers(
    raw_json: Optional[str] = None,
    url: str = SEC_COMPANY_TICKERS_URL,
    fetch: Optional[callable] = None,
) -> dict[str, Any]:
    """Load the SEC EDGAR ticker→CIK map.

    Returns a dict with:

    - ``ticker``: exact EDGAR ticker -> ``{cik, title}`` (cik is the
      10-digit zero-padded string);
    - ``stripped``: alnum-stripped ticker -> exact ticker (fallback);
    - ``titles``: list of ``(compact_key, title, ticker, cik)`` for name
      matching.

    ``raw_json``/``fetch`` allow hermetic tests; otherwise the live SEC file
    is downloaded. The map is cached per process.
    """
    cache_key = "cached_sec_tickers"
    cached = getattr(sec_company_tickers, cache_key, None)
    if cached is not None:
        return cached

    if raw_json is None:
        if fetch is None:
            fetch = _http_get_bytes
        payload = fetch(url)
        raw_json = payload.decode("utf-8")
    else:
        # An explicit raw_json identifies the *exact* map (tests/verification);
        # never serve a process-cached map built from a different dataset.
        cache_key = None

    data = json.loads(raw_json)  # {"0": {"cik_str": 320193, "ticker": ..., "title": ...}}

    by_ticker: dict[str, dict[str, str]] = {}
    by_stripped: dict[str, str] = {}
    titles: list[tuple[str, str, str, str]] = []
    for entry in data.values():
        cik = str(entry["cik_str"]).zfill(10)
        ticker = normalize_ticker(entry["ticker"])
        title = str(entry["title"])
        by_ticker[ticker] = {"cik": cik, "title": title}
        by_stripped.setdefault(stripped_ticker(ticker), ticker)
        titles.append((company_key(title), title, ticker, cik))

    result = {
        "ticker": by_ticker,
        "stripped": by_stripped,
        "titles": titles,
    }
    if cache_key is not None:
        setattr(sec_company_tickers, cache_key, result)
    return result


def ticker_to_sec(
    ticker: str, sec: dict[str, Any]
) -> Optional[dict[str, str]]:
    """Resolve a US ticker to ``{cik, title, ticker}`` via the SEC map."""
    t = normalize_ticker(ticker)
    entry = sec["ticker"].get(t)
    if entry is None:
        alt = sec["stripped"].get(stripped_ticker(t))
        if alt is not None:
            entry = sec["ticker"].get(alt)
            t = alt
    if entry is None:
        return None
    return {"cik": entry["cik"], "title": entry["title"], "ticker": t}


_LAST_MATCHES: dict[str, Optional[dict[str, str]]] = {}


def match_sec_company(
    name: str, sec: dict[str, Any], threshold: float = 0.8
) -> Optional[dict[str, str]]:
    """Match a company name against SEC filers by normalized name key.

    Returns ``{cik, title, ticker, score}`` for the best match above
    ``threshold`` (token-set Jaccard), else ``None``. Ticker-based matches
    are intentionally NOT used for European constituents: domestic exchange
    tickers frequently collide with unrelated US symbols (e.g. DAX's
    ``DTE`` is Deutsche Telekom while SEC's ``DTE`` is DTE Energy).
    """
    if not name:
        return None
    key = company_key(name)
    if not key:
        return None
    cached = _LAST_MATCHES.get(f"{threshold}:{key}")
    if cached is not None:
        return cached or None

    best: Optional[tuple[float, str, str, str]] = None
    for cand_key, title, ticker, cik in sec["titles"]:
        if not cand_key:
            continue
        score = _token_jaccard(key, cand_key)
        if best is None or score > best[0]:
            best = (score, title, ticker, cik)
        if score == 1.0 and len(key) == len(cand_key):
            break  # exact compact match cannot be beaten
    if best is None or best[0] < threshold:
        _LAST_MATCHES[f"{threshold}:{key}"] = None
        return None
    result = {
        "cik": best[3],
        "title": best[1],
        "ticker": SEC_TICKER_PREFERENCES.get(best[2], best[2]),
        "score": round(best[0], 4),
    }
    _LAST_MATCHES[f"{threshold}:{key}"] = result
    return dict(result)