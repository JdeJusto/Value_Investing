"""Reconcile annual SEC facts that Financial-DataBase bucketed into the wrong
fiscal year.

SEC's ``fy`` field is the filing's presentation year, not the balance-sheet
year: BJRI's FY2025 10-K carries ``fy=2023`` and FDB stored its 193 annual
facts under FY2023. This script derives the year from ``end`` and the
company's fiscal-year-end month, then updates the existing rows (or inserts
missing facts) with a backup, a rollback script and an audit table.

Usage:
    python scripts/reconcile_from_sec.py --tickers BJRI --dry-run
    python scripts/reconcile_from_sec.py --tickers BJRI --apply \
        --backup /tmp/reconcile_bjri_backup.json \
        --rollback /tmp/reconcile_bjri_rollback.sql
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2

logger = logging.getLogger("reconcile_from_sec")

DSN = "postgresql://financial:test@localhost:5432/financial_database"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"})
AUDIT_TABLE = "reconciliation_log"


def derive_fiscal_year(
    fact: dict[str, Any], offset: int | None, sec_fy: int | None
) -> tuple[int, str]:
    """Return ``(fiscal_year, offset_source)`` for a fact.

    The company's own convention (``offset = fiscal_year - end.year``) is the
    source of truth. ``offset=None`` means there is not enough history, so
    SEC's ``fy`` is respected. A derived year more than two years away from
    SEC's ``fy`` is suspicious and also falls back to ``fy``.
    """
    end_raw = fact.get("end", fact.get("period_end"))
    end = date.fromisoformat(end_raw) if isinstance(end_raw, str) else end_raw
    if offset is None or sec_fy is None:
        return (int(sec_fy) if sec_fy is not None else end.year), "fallback_fy"
    derived = end.year + offset
    if abs(derived - int(sec_fy)) > 2:
        return int(sec_fy), "fallback_sanity"
    return derived, "mode_history"


def infer_offset_from_history(
    pairs: list[tuple[int, int]],
    *,
    lookback_years: int = 5,
    min_years: int = 3,
    current_year: int | None = None,
) -> int | None:
    """Infer a company's fiscal-year labelling offset from its own history.

    ``pairs`` are ``(fiscal_year, period_end_year)``. Only the last
    ``lookback_years`` are considered, and fewer than ``min_years`` distinct
    end years means no reliable convention. The mode wins; ties prefer the
    smallest absolute offset (0 over -1/+1).
    """
    current = current_year if current_year is not None else datetime.now(UTC).year
    recent = [(fy, ey) for fy, ey in pairs if ey >= current - lookback_years]
    if len({ey for _, ey in recent}) < min_years:
        return None
    offsets = [fy - ey for fy, ey in recent if abs(fy - ey) <= 1]
    if not offsets:
        return None
    counts: dict[int, int] = {}
    for value in offsets:
        counts[value] = counts.get(value, 0) + 1
    best = max(counts.values())
    candidates = [value for value, count in counts.items() if count == best]
    return min(candidates, key=lambda value: (abs(value), value))


def make_source_id(
    accn: str, namespace: str, concept: str, start: date | None, end: date
) -> str:
    """Match FDB's ``accession|namespace:concept|start|end`` audit key."""
    prefix = f"{accn}|{namespace}:{concept}"
    return (
        f"{prefix}|{start.isoformat()}|{end.isoformat()}"
        if start
        else f"{prefix}|{end.isoformat()}"
    )


@dataclass
class FactChange:
    concept: str
    namespace: str
    value: Decimal
    unit: str
    period_start: date | None
    period_end: date
    new_fiscal_year: int
    old_fiscal_year: int | None
    form: str
    filed: date | None
    source_id: str
    row_id: str | None = None
    offset_applied: int | None = None
    offset_source: str = ""


@dataclass
class Plan:
    ticker: str
    company_id: str
    cik: str
    fye_month: int
    offset: int | None = None
    updates: list[FactChange] = field(default_factory=list)
    inserts: list[FactChange] = field(default_factory=list)
    skipped: int = 0

    def summary(self) -> str:
        return (
            f"{self.ticker}: updates={len(self.updates)} "
            f"inserts={len(self.inserts)} skipped={self.skipped}"
        )


def _iter_sec_facts(facts: dict[str, Any], since: date) -> list[dict[str, Any]]:
    """Annual SEC facts normalised to plain dicts (annual forms only)."""
    out: list[dict[str, Any]] = []
    for namespace in ("us-gaap", "ifrs-full"):
        for concept, block in facts.get(namespace, {}).items():
            for unit, values in block.get("units", {}).items():
                for item in values:
                    if item.get("form") not in ANNUAL_FORMS:
                        continue
                    if item.get("fp") != "FY":
                        continue
                    end_raw = item.get("end")
                    if not end_raw:
                        continue
                    try:
                        end = date.fromisoformat(end_raw)
                    except ValueError:
                        continue
                    if end < since:
                        continue
                    value = item.get("val")
                    if value is None:
                        continue
                    start_raw = item.get("start")
                    start = date.fromisoformat(start_raw) if start_raw else None
                    filed_raw = item.get("filed")
                    filed = date.fromisoformat(filed_raw) if filed_raw else None
                    out.append(
                        {
                            "concept": concept,
                            "namespace": namespace,
                            "value": Decimal(str(value)),
                            "unit": unit,
                            "period_start": start,
                            "period_end": end,
                            "form": item.get("form"),
                            "filed": filed,
                            "accn": item.get("accn") or "",
                            "sec_fy": item.get("fy"),
                            "source_id": make_source_id(
                                item.get("accn") or "", namespace, concept, start, end
                            ),
                        }
                    )
    return out


def plan_changes(
    ticker: str,
    company_id: str,
    cik: str,
    fye_month: int,
    offset: int | None,
    sec_facts: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> Plan:
    """Pure planner: what to update/insert, without touching the database."""
    plan = Plan(
        ticker=ticker,
        company_id=company_id,
        cik=cik,
        fye_month=fye_month,
        offset=offset,
    )
    by_source = {row["source_id"]: row for row in existing if row.get("source_id")}
    by_period: dict[tuple[str, date | None, date], dict[str, Any]] = {}
    for row in existing:
        key = (row["concept"], row.get("period_start"), row["period_end"])
        by_period.setdefault(key, row)

    seen: set[str] = set()
    for fact in sec_facts:
        source_id = fact["source_id"]
        if source_id in seen:
            continue
        seen.add(source_id)
        new_fy, offset_source = derive_fiscal_year(fact, offset, fact.get("sec_fy"))
        match = by_source.get(source_id)
        if match is None:
            match = by_period.get(
                (fact["concept"], fact["period_start"], fact["period_end"])
            )
        change = FactChange(
            concept=fact["concept"],
            namespace=fact["namespace"],
            value=fact["value"],
            unit=fact["unit"],
            period_start=fact["period_start"],
            period_end=fact["period_end"],
            new_fiscal_year=new_fy,
            old_fiscal_year=match.get("fiscal_year") if match else None,
            form=fact["form"],
            filed=fact["filed"],
            source_id=source_id,
            row_id=str(match["id"]) if match else None,
            offset_applied=offset,
            offset_source=offset_source,
        )
        if match is None:
            plan.inserts.append(change)
        elif int(match["fiscal_year"]) != new_fy:
            plan.updates.append(change)
        else:
            plan.skipped += 1
    return plan


BALANCE_ASSET_CONCEPTS = frozenset(
    {"Assets", "AssetsTotal", "LiabilitiesAndStockholdersEquity"}
)
BALANCE_LIABILITY_CONCEPTS = frozenset({"Liabilities", "LiabilitiesTotal"})
BALANCE_EQUITY_CONCEPTS = frozenset(
    {
        "StockholdersEquity",
        "TotalEquityGrossMinorityInterest",
        "ShareholdersEquity",
        "Equity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    }
)


@dataclass
class MoveResult:
    moved: bool
    fiscal_year: int | None
    reason: str
    n_facts: int = 0
    old_fiscal_years: tuple[int, ...] = ()


@dataclass
class TickerReport:
    ticker: str
    company_id: str
    offset: int | None
    moved_groups: list[MoveResult] = field(default_factory=list)
    skipped_groups: list[MoveResult] = field(default_factory=list)
    reason: str = "ok"

    def summary(self) -> str:
        return (
            f"{self.ticker}: moved={len(self.moved_groups)} "
            f"skipped={len(self.skipped_groups)} reason={self.reason}"
        )


def _group_value(facts: list[dict], concepts: frozenset[str]) -> float | None:
    values = [
        float(fact["value"])
        for fact in facts
        if fact["concept"] in concepts and fact.get("value") is not None
    ]
    return max(values) if values else None


def plan_group(
    period_end: date,
    facts: list[dict],
    sec_index: dict[tuple[str, date | None, date], dict],
    offset: int | None,
) -> MoveResult:
    """Plan one balance group; never moves a subset of its facts."""
    if not facts:
        return MoveResult(False, None, "missing_components")
    targets: set[int] = set()
    for fact in facts:
        sec = sec_index.get(
            (fact["concept"], fact.get("period_start"), fact["period_end"])
        )
        if sec is not None:
            target, source = derive_fiscal_year(sec, offset, sec.get("sec_fy"))
            if source != "mode_history":
                return MoveResult(
                    False,
                    None,
                    "intra_group_discrepancy",
                    n_facts=len(facts),
                )
        elif offset is not None:
            target = fact["period_end"].year + offset
        else:
            target = int(fact["fiscal_year"])
        targets.add(target)
    if len(targets) != 1:
        return MoveResult(False, None, "intra_group_discrepancy", n_facts=len(facts))
    target = targets.pop()
    assets = _group_value(facts, BALANCE_ASSET_CONCEPTS)
    liabilities = _group_value(facts, BALANCE_LIABILITY_CONCEPTS)
    equity = _group_value(facts, BALANCE_EQUITY_CONCEPTS)
    if assets is None or liabilities is None or equity is None:
        return MoveResult(False, target, "missing_components", n_facts=len(facts))
    if assets and abs(assets - (liabilities + equity)) / abs(assets) > 0.01:
        return MoveResult(False, target, "balance_would_break", n_facts=len(facts))
    return MoveResult(
        True,
        target,
        "ok",
        n_facts=len(facts),
        old_fiscal_years=tuple(sorted({int(fact["fiscal_year"]) for fact in facts})),
    )


def _simulate_balance(
    facts_by_period: list[list[dict]],
    moves: dict[date, int],
    affected_years: set[int],
) -> bool:
    year_facts: dict[int, list[dict]] = {}
    for group in facts_by_period:
        for fact in group:
            year = moves.get(fact["period_end"], int(fact["fiscal_year"]))
            year_facts.setdefault(year, []).append(fact)
    for year, facts in year_facts.items():
        if year not in affected_years:
            continue
        assets = _group_value(facts, BALANCE_ASSET_CONCEPTS)
        liabilities = _group_value(facts, BALANCE_LIABILITY_CONCEPTS)
        equity = _group_value(facts, BALANCE_EQUITY_CONCEPTS)
        if assets is None or liabilities is None or equity is None:
            continue
        if assets and abs(assets - (liabilities + equity)) / abs(assets) > 0.01:
            logger.warning(
                "simulated balance would break in FY%s: assets=%s liabilities=%s equity=%s",
                year,
                assets,
                liabilities,
                equity,
            )
            return False
    return True


def plan_ticker(
    ticker: str,
    company_id: str,
    facts: list[dict],
    sec_facts: list[dict],
    offset: int | None,
) -> tuple[TickerReport, dict[date, int]]:
    """Plan every balance group and validate the final balance once."""
    report = TickerReport(ticker=ticker, company_id=company_id, offset=offset)
    sec_index = {
        (fact["concept"], fact.get("period_start"), fact["period_end"]): fact
        for fact in sec_facts
    }
    groups: dict[date, list[dict]] = {}
    for fact in facts:
        groups.setdefault(fact["period_end"], []).append(fact)
    moves: dict[date, int] = {}
    for period_end, group in sorted(groups.items()):
        result = plan_group(period_end, group, sec_index, offset)
        if result.moved and result.fiscal_year is not None:
            old_years = {int(fact["fiscal_year"]) for fact in group}
            if any(year != result.fiscal_year for year in old_years):
                moves[period_end] = result.fiscal_year
                report.moved_groups.append(result)
            else:
                report.skipped_groups.append(
                    MoveResult(False, result.fiscal_year, "already_correct")
                )
        else:
            report.skipped_groups.append(result)
    # Each moved group is validated on its own balance sheet in plan_group;
    # a year-wide max() across several period_end groups mixes comparatives
    # from different filings and is not a valid pre-flight metric.
    return report, moves


def reconcile_ticker(
    cur,
    company_id: str,
    ticker: str,
    sec_facts: list[dict],
    offset: int | None,
    *,
    apply: bool,
    run_id: str,
    audit_table: str = AUDIT_TABLE,
    backup: Path | None = None,
    rollback: Path | None = None,
    since: date | None = None,
) -> TickerReport:
    """Load a ticker's FY facts, plan atomically, and optionally move groups."""
    sql = """SELECT id, concept, value, fiscal_year, period_start, period_end
             FROM financial_facts
             WHERE company_id=%s AND fiscal_period='FY'"""
    params: list[Any] = [company_id]
    if since is not None:
        sql += " AND period_end >= %s"
        params.append(since)
    cur.execute(sql, params)
    facts = [
        {
            "id": str(row[0]),
            "concept": row[1],
            "value": row[2],
            "fiscal_year": row[3],
            "period_start": row[4],
            "period_end": row[5],
        }
        for row in cur.fetchall()
    ]
    report, moves = plan_ticker(ticker, company_id, facts, sec_facts, offset)
    if not apply or not moves:
        return report
    if backup is not None and rollback is not None:
        _write_group_artifacts(facts, moves, backup, rollback)
    _ensure_audit_table(cur)
    for period_end, target in moves.items():
        cur.execute(
            """UPDATE financial_facts SET fiscal_year=%s, updated_at=now()
               WHERE company_id=%s AND period_end=%s AND fiscal_period='FY'""",
            (target, company_id, period_end),
        )
        group = [f for f in facts if f["period_end"] == period_end]
        old_years = sorted({int(f["fiscal_year"]) for f in group})
        cur.execute(
            f"""INSERT INTO {audit_table}
                (run_id,ticker,company_id,concept,period_start,period_end,
                 old_fiscal_year,new_fiscal_year,action,source_id,
                 offset_applied,offset_source,reason)
                VALUES (%s,%s,%s,'*',NULL,%s,%s,%s,'group_move','reconcile',
                        %s,'mode_history','ok')""",
            (
                run_id,
                ticker,
                company_id,
                period_end,
                old_years[0] if len(old_years) == 1 else None,
                target,
                offset,
            ),
        )
    for result in report.skipped_groups:
        cur.execute(
            f"""INSERT INTO {audit_table}
                (run_id,ticker,company_id,concept,period_start,period_end,
                 old_fiscal_year,new_fiscal_year,action,source_id,
                 offset_applied,offset_source,reason)
                VALUES (%s,%s,%s,'*',NULL,NULL,NULL,NULL,'skip','reconcile',
                        %s,%s,%s)""",
            (
                run_id,
                ticker,
                company_id,
                offset,
                "mode_history" if offset is not None else "fallback_fy",
                result.reason,
            ),
        )
    cur.connection.commit()
    return report


def _load_existing(cur, company_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """SELECT id, concept, period_start, period_end, source_id, fiscal_year
           FROM financial_facts
           WHERE company_id=%s AND fiscal_period='FY'""",
        (company_id,),
    )
    return [
        {
            "id": row[0],
            "concept": row[1],
            "period_start": row[2],
            "period_end": row[3],
            "source_id": row[4],
            "fiscal_year": row[5],
        }
        for row in cur.fetchall()
    ]


def _company(cur, ticker: str) -> tuple[str, str] | None:
    cur.execute(
        """SELECT c.id, ci.identifier_value
           FROM company_listings cl
           JOIN companies c ON c.id=cl.company_id
           JOIN company_identifiers ci
             ON ci.company_id=c.id AND ci.identifier_type='CIK'
           WHERE cl.ticker=%s AND cl.is_active
           LIMIT 1""",
        (ticker.upper(),),
    )
    row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def read_tickers_file(path: str | Path) -> list[str]:
    """One ticker per line; blank lines and ``#`` comments are ignored."""
    tickers: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip().upper()
        if value:
            tickers.append(value)
    return tickers


def find_bucketing_candidates(cur) -> list[str]:
    """Tickers whose latest FY is sparse while an older FY is rich.

    The BJRI pattern: the latest 10-K was bucketed into an old year, leaving
    the latest fiscal year with a handful of stray facts.
    """
    cur.execute(
        """
        WITH per AS (
          SELECT company_id, fiscal_year, count(*) AS facts
          FROM financial_facts
          WHERE fiscal_period='FY' AND fiscal_year BETWEEN 2020 AND 2025
          GROUP BY 1,2
        ), ranked AS (
          SELECT company_id, facts,
                 row_number() OVER (PARTITION BY company_id
                                    ORDER BY fiscal_year DESC) AS rn,
                 max(facts) OVER (PARTITION BY company_id) AS max_facts
          FROM per
        )
        SELECT DISTINCT cl.ticker
        FROM ranked r
        JOIN company_listings cl ON cl.company_id=r.company_id AND cl.is_active
        JOIN company_identifiers ci
          ON ci.company_id=r.company_id AND ci.identifier_type='CIK'
        WHERE r.rn=1 AND r.facts < 50 AND r.max_facts > 500
        ORDER BY cl.ticker
        """
    )
    return [row[0].upper() for row in cur.fetchall() if row[0]]


def _fye_month(cur, company_id: str) -> int:
    cur.execute(
        """SELECT extract(month FROM period_end)::int AS m, count(*) AS n
           FROM financial_facts
           WHERE company_id=%s AND fiscal_period='FY' AND period_end IS NOT NULL
           GROUP BY m ORDER BY n DESC, m LIMIT 1""",
        (company_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 12


def infer_company_offset(
    cur, company_id: str, *, lookback_years: int = 5, min_years: int = 3
) -> int | None:
    """Infer the company's fiscal-year offset from its own fact history."""
    cur.execute(
        """SELECT fiscal_year, extract(year FROM period_end)::int
           FROM financial_facts
           WHERE company_id=%s AND fiscal_year IS NOT NULL
             AND period_end IS NOT NULL
             AND fiscal_period='FY'
             AND period_end >= CURRENT_DATE - (%s * INTERVAL '1 year')""",
        (company_id, lookback_years),
    )
    pairs = [(int(fy), int(ey)) for fy, ey in cur.fetchall()]
    return infer_offset_from_history(
        pairs, lookback_years=lookback_years, min_years=min_years
    )


def _sec_user_agent() -> str:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEC_USER_AGENT="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise SystemExit("SEC_USER_AGENT is required (set it in .env)")


def _fetch_sec_facts(cik: str, user_agent: str) -> dict[str, Any]:
    url = SEC_FACTS_URL.format(cik=int(cik))
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["facts"]


def _ensure_audit_table(cur) -> None:
    cur.execute(
        f"""CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            id bigserial PRIMARY KEY,
            run_id uuid NOT NULL,
            ticker text NOT NULL,
            company_id uuid NOT NULL,
            concept text NOT NULL,
            period_start date,
            period_end date,
            old_fiscal_year integer,
            new_fiscal_year integer,
            action text NOT NULL,
            source_id text,
            offset_applied smallint,
            offset_source text,
            reason text,
            created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    cur.execute(
        f"ALTER TABLE {AUDIT_TABLE} ADD COLUMN IF NOT EXISTS offset_applied smallint"
    )
    cur.execute(
        f"ALTER TABLE {AUDIT_TABLE} ADD COLUMN IF NOT EXISTS offset_source text"
    )
    cur.execute(f"ALTER TABLE {AUDIT_TABLE} ADD COLUMN IF NOT EXISTS reason text")


def _write_group_artifacts(
    facts: list[dict],
    moves: dict[date, int],
    backup: Path,
    rollback: Path,
) -> None:
    """Persist the pre-move rows and a per-row rollback SQL for a ticker."""
    backup.parent.mkdir(parents=True, exist_ok=True)
    serialised = [
        {
            key: (
                value.isoformat() if isinstance(value, (date, datetime)) else str(value)
            )
            for key, value in fact.items()
        }
        for fact in facts
    ]
    backup.write_text(
        json.dumps(
            {
                "facts": serialised,
                "moves": {key.isoformat(): value for key, value in moves.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    rollback.parent.mkdir(parents=True, exist_ok=True)
    lines = ["BEGIN;"]
    for fact in facts:
        if fact["period_end"] in moves:
            lines.append(
                f"UPDATE financial_facts SET fiscal_year = {int(fact['fiscal_year'])} "
                f"WHERE id = '{fact['id']}';"
            )
    lines.append("COMMIT;")
    rollback.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_backup(path: Path, plan: Plan, existing: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {k: (v.isoformat() if isinstance(v, date) else str(v)) for k, v in row.items()}
        for row in existing
    ]
    path.write_text(
        json.dumps(
            {
                "ticker": plan.ticker,
                "company_id": plan.company_id,
                "cik": plan.cik,
                "existing": rows,
                "updates": [c.__dict__ for c in plan.updates],
                "inserts": [c.__dict__ for c in plan.inserts],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


def _write_rollback(path: Path, plan: Plan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["BEGIN;"]
    for change in plan.updates:
        if change.row_id and change.old_fiscal_year is not None:
            lines.append(
                f"UPDATE financial_facts SET fiscal_year = {change.old_fiscal_year} "
                f"WHERE id = '{change.row_id}';"
            )
    for change in plan.inserts:
        if change.row_id:
            lines.append(f"DELETE FROM financial_facts WHERE id = '{change.row_id}';")
    lines.append("COMMIT;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_plan(
    conn,
    plan: Plan,
    *,
    existing: list[dict[str, Any]],
    backup: Path,
    rollback: Path,
    audit_table: str = AUDIT_TABLE,
    run_id: str | None = None,
) -> dict[str, int]:
    _write_backup(backup, plan, existing)
    # Assign stable ids to inserts before writing the rollback so the script
    # can delete exactly those rows.
    for change in plan.inserts:
        change.row_id = str(uuid.uuid4())
    _write_rollback(rollback, plan)

    cur = conn.cursor()
    cur.execute("SELECT id FROM data_providers WHERE name='SEC EDGAR' LIMIT 1")
    provider = cur.fetchone()
    if not provider:
        raise RuntimeError("SEC EDGAR provider missing from data_providers")
    provider_id = provider[0]
    run_id = run_id or str(uuid.uuid4())
    _ensure_audit_table(cur)
    updated = inserted = 0
    try:
        for change in plan.updates:
            cur.execute(
                """UPDATE financial_facts
                   SET fiscal_year=%s, updated_at=now()
                   WHERE id=%s AND fiscal_year=%s""",
                (change.new_fiscal_year, change.row_id, change.old_fiscal_year),
            )
            if cur.rowcount:
                updated += 1
                cur.execute(
                    f"""INSERT INTO {audit_table}
                        (run_id,ticker,company_id,concept,period_start,period_end,
                         old_fiscal_year,new_fiscal_year,action,source_id,
                         offset_applied,offset_source)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'update',%s,%s,%s)""",
                    (
                        run_id,
                        plan.ticker,
                        plan.company_id,
                        change.concept,
                        change.period_start,
                        change.period_end,
                        change.old_fiscal_year,
                        change.new_fiscal_year,
                        change.source_id,
                        change.offset_applied,
                        change.offset_source,
                    ),
                )
        for change in plan.inserts:
            cur.execute(
                """INSERT INTO financial_facts
                   (id,company_id,provider_id,concept,value,unit,period_start,
                    period_end,fiscal_year,fiscal_period,form,source_id,filing_date,namespace)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'FY',%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (
                    change.row_id,
                    plan.company_id,
                    provider_id,
                    change.concept,
                    change.value,
                    change.unit,
                    change.period_start,
                    change.period_end,
                    change.new_fiscal_year,
                    change.form,
                    change.source_id,
                    change.filed,
                    change.namespace,
                ),
            )
            if cur.rowcount:
                inserted += 1
                cur.execute(
                    f"""INSERT INTO {audit_table}
                        (run_id,ticker,company_id,concept,period_start,period_end,
                         old_fiscal_year,new_fiscal_year,action,source_id,
                         offset_applied,offset_source)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'insert',%s,%s,%s)""",
                    (
                        run_id,
                        plan.ticker,
                        plan.company_id,
                        change.concept,
                        change.period_start,
                        change.period_end,
                        None,
                        change.new_fiscal_year,
                        change.source_id,
                        change.offset_applied,
                        change.offset_source,
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"updated": updated, "inserted": inserted}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="BJRI", help="Comma-separated tickers")
    p.add_argument("--tickers-file", default=None, help="One ticker per line")
    p.add_argument(
        "--identify-bucketing-candidates",
        action="store_true",
        help="Print tickers matching the sparse-latest/rich-older pattern",
    )
    p.add_argument("--run-id", default=None, help="Audit run id (one per batch)")
    p.add_argument("--apply", action="store_true", help="Write (default: dry-run)")
    p.add_argument("--backup", default="/tmp/reconcile_backup.json")
    p.add_argument("--rollback", default="/tmp/reconcile_rollback.sql")
    p.add_argument("--audit-table", default=AUDIT_TABLE)
    p.add_argument("--since", default="2023-01-01")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    since = date.fromisoformat(args.since)
    user_agent = _sec_user_agent()
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    failures = 0
    if args.identify_bucketing_candidates:
        for ticker in find_bucketing_candidates(cur):
            print(ticker)
        conn.close()
        return 0
    if args.tickers_file:
        tickers = read_tickers_file(args.tickers_file)
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    run_id = args.run_id or str(uuid.uuid4())
    try:
        for ticker in tickers:
            found = _company(cur, ticker)
            if not found:
                logger.error("%s: no active listing/CIK", ticker)
                failures += 1
                continue
            company_id, cik = found
            fye_month = _fye_month(cur, company_id)
            offset = infer_company_offset(cur, company_id)
            logger.info(
                "%s: CIK %s, fiscal-year-end month %s, offset %s",
                ticker,
                cik,
                fye_month,
                offset,
            )
            facts = _fetch_sec_facts(cik, user_agent)
            sec_facts = _iter_sec_facts(facts, since)
            backup = Path(args.backup)
            rollback = Path(args.rollback)
            if len(tickers) > 1:
                backup = backup.with_name(f"{backup.stem}_{ticker}{backup.suffix}")
                rollback = rollback.with_name(
                    f"{rollback.stem}_{ticker}{rollback.suffix}"
                )
            report = reconcile_ticker(
                cur,
                company_id,
                ticker,
                sec_facts,
                offset,
                apply=args.apply,
                run_id=run_id,
                audit_table=args.audit_table,
                backup=backup if args.apply else None,
                rollback=rollback if args.apply else None,
                since=since,
            )
            logger.info(report.summary())
            for skipped in report.skipped_groups:
                if skipped.reason not in ("ok", "already_correct"):
                    logger.info(
                        "%s: skip group end=%s reason=%s",
                        ticker,
                        skipped.fiscal_year,
                        skipped.reason,
                    )
            if report.reason != "ok":
                logger.warning("%s: %s", ticker, report.reason)
            time.sleep(0.2)
    finally:
        conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
