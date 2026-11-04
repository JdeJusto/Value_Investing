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
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2

logger = logging.getLogger("reconcile_from_sec")

DSN = "postgresql://financial:test@localhost:5432/financial_database"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"})
AUDIT_TABLE = "reconciliation_log"


def derive_fiscal_year(fact: dict[str, Any], fye_month: int) -> int:
    """Return the fiscal year to bucket a fact under.

    SEC's ``fy`` is the filing's presentation year and is normally the right
    label, but it can be off by one for start-year conventions (CNM) or 20-F
    filers (KT, IMOS). Only override it when it is clearly wrong (more than
    one year away from the period end); otherwise respect the filing.

    ``fye_month`` is kept in the signature for callers/tests that pass it, but
    the conservative rule anchors on the period end's calendar year.
    """
    sec_fy = fact.get("fy", fact.get("sec_fy"))
    end_raw = fact.get("end", fact.get("period_end"))
    end = date.fromisoformat(end_raw) if isinstance(end_raw, str) else end_raw
    if sec_fy is None:
        return end.year
    expected = end.year
    if abs(int(sec_fy) - expected) <= 1:
        return int(sec_fy)
    return expected


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


@dataclass
class Plan:
    ticker: str
    company_id: str
    cik: str
    fye_month: int
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
    sec_facts: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> Plan:
    """Pure planner: what to update/insert, without touching the database."""
    plan = Plan(ticker=ticker, company_id=company_id, cik=cik, fye_month=fye_month)
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
        new_fy = derive_fiscal_year(fact, fye_month)
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
        )
        if match is None:
            plan.inserts.append(change)
        elif int(match["fiscal_year"]) != new_fy:
            plan.updates.append(change)
        else:
            plan.skipped += 1
    return plan


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
            created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )


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
                         old_fiscal_year,new_fiscal_year,action,source_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'update',%s)""",
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
                         old_fiscal_year,new_fiscal_year,action,source_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'insert',%s)""",
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
            logger.info("%s: CIK %s, fiscal-year-end month %s", ticker, cik, fye_month)
            facts = _fetch_sec_facts(cik, user_agent)
            sec_facts = _iter_sec_facts(facts, since)
            existing = _load_existing(cur, company_id)
            plan = plan_changes(ticker, company_id, cik, fye_month, sec_facts, existing)
            logger.info(plan.summary())
            if args.apply:
                backup = Path(args.backup)
                rollback = Path(args.rollback)
                if len(tickers) > 1:
                    backup = backup.with_name(f"{backup.stem}_{ticker}{backup.suffix}")
                    rollback = rollback.with_name(
                        f"{rollback.stem}_{ticker}{rollback.suffix}"
                    )
                result = apply_plan(
                    conn,
                    plan,
                    existing=existing,
                    backup=backup,
                    rollback=rollback,
                    audit_table=args.audit_table,
                    run_id=run_id,
                )
                logger.info("%s: applied %s", ticker, result)
            time.sleep(0.2)
    finally:
        conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
