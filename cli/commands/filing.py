"""`filing` — open or print the SEC EDGAR URL of one filing.

The listing command (``vi filings``) is ticker-scoped; this one resolves a
single filing either by accession number or by ``<ticker> <N>`` (1-indexed,
same order as the listing table).
"""

from __future__ import annotations

import sys
import webbrowser
from argparse import Namespace

from backend.app.cli import add_demo_argument
from cli.formatters import red


def register(subparsers):
    p = subparsers.add_parser(
        "filing",
        help="Open or print a single SEC filing URL",
        description=(
            "Resolve one filing and open its EDGAR index in the system "
            "browser. In SSH/headless sessions the URL is printed instead."
        ),
    )
    sub = p.add_subparsers(dest="action", required=True)

    open_p = sub.add_parser("open", help="Open a filing in the browser")
    _add_target_args(open_p)
    open_p.add_argument(
        "--url-only",
        action="store_true",
        help="Print the URL instead of opening a browser",
    )
    add_demo_argument(open_p)
    open_p.set_defaults(func=_open)

    url_p = sub.add_parser("url", help="Print only the filing URL")
    _add_target_args(url_p)
    add_demo_argument(url_p)
    url_p.set_defaults(func=_url)


def _add_target_args(parser) -> None:
    parser.add_argument(
        "target",
        help="Accession number (0001397187-26-000127) or ticker (with N)",
    )
    parser.add_argument(
        "index",
        type=int,
        nargs="?",
        help="1-indexed filing position when target is a ticker",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="When using <ticker> <N>, include every form type",
    )


def _has_browser() -> bool:
    """Best-effort graphical-session detection (no new dependency)."""
    import os

    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        return False
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    return sys.platform == "darwin"


def _open_url(url: str, *, url_only: bool = False) -> int:
    if not url:
        print(red("Could not build the EDGAR URL for this filing."), file=sys.stderr)
        return 2
    if url_only:
        print(url)
        return 0
    if _has_browser():
        webbrowser.open(url)
        print(f"Opening: {url}")
        return 0
    print("No browser detected. Copy this URL:")
    print()
    print(f"  {url}")
    print()
    return 0


def _looks_like_accession(value: str) -> bool:
    cleaned = value.replace("-", "").strip()
    return len(cleaned) == 18 and cleaned.isdigit()


def _resolve(args: Namespace) -> tuple[str, str] | None:
    """Return ``(label, url)`` for the requested filing, or ``None``."""
    from backend.services.filing_service import (
        DEFAULT_FORM_TYPES,
        FilingService,
        filing_edgar_url,
    )

    target = (args.target or "").strip()
    service = FilingService()
    if args.index is not None:
        if not target:
            print("A ticker is required with <N>.", file=sys.stderr)
            return None
        if args.index < 1:
            print("N must be >= 1.", file=sys.stderr)
            return None
        form_types = None if args.all else list(DEFAULT_FORM_TYPES)
        records = service.list_filings(target, form_types=form_types, limit=args.index)
        if len(records) < args.index:
            print(
                f"{target.upper()}: only {len(records)} filing(s) match "
                f"(requested #{args.index}).",
                file=sys.stderr,
            )
            return None
        record = records[args.index - 1]
        label = (
            f"{target.upper()} #{args.index} ({record.form_type} {record.filing_date})"
        )
        return label, filing_edgar_url(record.accession_number, record.cik)

    if not _looks_like_accession(target):
        print(
            "Usage: vi filing open <accession> | <ticker> <N>",
            file=sys.stderr,
        )
        return None
    accession = target.replace("-", "")
    record = service.get_by_accession(accession)
    if record is None:
        print(f"Filing {target} not found.", file=sys.stderr)
        return None
    label = f"{record.ticker or record.cik} ({record.form_type} {record.filing_date})"
    return label, filing_edgar_url(record.accession_number, record.cik)


def _open(args: Namespace) -> int:
    resolved = _resolve(args)
    if resolved is None:
        return 2
    _label, url = resolved
    return _open_url(url, url_only=args.url_only)


def _url(args: Namespace) -> int:
    resolved = _resolve(args)
    if resolved is None:
        return 2
    _label, url = resolved
    if not url:
        print(red("Could not build the EDGAR URL for this filing."), file=sys.stderr)
        return 2
    print(url)
    return 0
