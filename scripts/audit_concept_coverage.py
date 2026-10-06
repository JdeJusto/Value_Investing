"""Read-only audit of FDB XBRL concept coverage against the VI mapping.

Usage::

    python -m scripts.audit_concept_coverage --top 300 --min-companies 50

The audit answers: which high-coverage concepts stored in Financial-DataBase
are not mapped to a ``NormalizedFinancials`` field yet, and which companies
would gain coverage if they were. It writes the full report to
``docs/concept_coverage_audit.md``.

Coverage is reported twice:

* **raw** — mapped share of every high-coverage concept in the sample. Most
  XBRL concepts above 50 companies are note/disclosure tags (EPS details, tax
  reconciliations, lease maturity schedules, segment counts...) with no VI
  field to map to, so this number is informational only.
* **actionable** — mapped share of the concepts that *have* a known target
  field (``PROPOSED_FIELD`` plus every already-mapped concept). This is the
  gate: it stays at 100% while the actionable batch is mapped and drops when a
  new high-coverage alias appears.

Exit status (periodic use): 0 when actionable coverage >= ``--min-coverage``
(default 95%) and the actionable unmapped count <= ``--fail-if-unmapped``
(when given); 1 otherwise. ``--no-gate`` always exits 0.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.repositories.fdb_concept_mapping import (
    _SPLIT_RATIO_CONCEPTS,
    BALANCE_SHEET_CONCEPTS,
    CASH_FLOW_CONCEPTS,
    DEBT_CURRENT_PRIORITY,
    DEBT_NONCURRENT_PRIORITY,
    INCOME_STATEMENT_CONCEPTS,
)

DEFAULT_DB_URL = "postgresql://financial:test@localhost:5432/financial_database"
DEFAULT_OUTPUT = Path("docs/concept_coverage_audit.md")

#: Concepts the normalization reads outside the statement maps (bank revenue
#: reconstruction + split ratios).
SPECIAL_CONCEPTS = frozenset({"InterestIncomeExpenseNet", "NoninterestIncome"})

#: High-coverage concepts with a clear target field that the mapping does not
#: cover yet. Every entry is a candidate for the next mapping batch; the gate
#: compares mapped concepts against this list, so adding an entry without
#: mapping it makes the audit fail on purpose.
PROPOSED_FIELD: dict[str, str] = {
    # Income statement.
    "RevenuesNetOfInterestExpense": "revenue (bank top line)",
    "GeneralAndAdministrativeExpense": "sga (fallback after SG&A)",
    "OtherNonoperatingIncomeExpense": "non_operating_income_expense (fallback)",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": "pretax_income (fallback)",
    "IncomeLossFromContinuingOperations": "net_income (last fallback)",
    "InterestIncomeOperating": "bank revenue (gross interest - interest expense)",
    "InterestAndDividendIncomeOperating": "bank revenue (gross interest - interest expense)",
    # Balance sheet.
    "LiabilitiesAndStockholdersEquity": "total_assets (accounting identity fallback)",
    "AccountsReceivableNet": "accounts_receivable (unclassified balance sheet)",
    "AccountsPayableAndAccruedLiabilitiesCurrent": "accounts_payable (fallback)",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_outstanding",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted": "shares_outstanding (fallback)",
    "LongTermDebtCurrent": "total_debt (current portion)",
    "PropertyPlantAndEquipmentGross": "net_ppe via gross - accumulated depreciation",
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": "net_ppe via gross - accumulated depreciation",
    # Cash flow.
    "PaymentsForRepurchaseOfCommonStock": "repurchase_of_stock (fallback)",
    "StockRepurchasedDuringPeriodValue": "repurchase_of_stock (fallback)",
}

#: Buckets used to summarize the informational (no target field) concepts.
_BUCKET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "industry",
        re.compile(
            r"(rental|operatinglease|premium|claim|interestincome|interestexpense"
            r"|noninterest|secureddebt|investmentincome)",
            re.IGNORECASE,
        ),
    ),
    (
        "equity",
        re.compile(
            r"(stockholdersequity|shareholdersequity|retainedearnings"
            r"|additionalpaidincapital|comprehensiveincome|treasurystock"
            r"|minorityinterest|preferredstock)",
            re.IGNORECASE,
        ),
    ),
    (
        "tax",
        re.compile(
            r"(incometax|deferredtax|taxexpense|effectiveincometaxrate"
            r"|unrecognizedtax|taxespayable|taxpaid)",
            re.IGNORECASE,
        ),
    ),
    (
        "cash_flow",
        re.compile(
            r"(netcash|^cash|payments|proceeds|repurchase|dividend|depreciation"
            r"|amortization|sharebasedcompensation|stockissued|stockrepurchased"
            r"|increaseDecrease)",
            re.IGNORECASE,
        ),
    ),
    (
        "balance_assets",
        re.compile(
            r"(assets|receivable|inventory|propertyplant|goodwill|intangible"
            r"|marketablesecurities|prepaid|restrictedcash)",
            re.IGNORECASE,
        ),
    ),
    (
        "balance_liabilities",
        re.compile(
            r"(liabilit|payable|accrued|debt|borrow|contractwithcustomer"
            r"|financinglease|notespayable)",
            re.IGNORECASE,
        ),
    ),
    ("income_revenue", re.compile(r"(revenue|sales)", re.IGNORECASE)),
    (
        "income_costs",
        re.compile(
            r"(cost|operatingexpenses|generalandadministrative|sellinggeneral)",
            re.IGNORECASE,
        ),
    ),
    (
        "income_profit",
        re.compile(
            r"(netincome|incomeloss|profit|operatingincome|ebit|earningspershare)",
            re.IGNORECASE,
        ),
    ),
)


def mapped_concepts() -> set[str]:
    """Every concept the repository currently maps to a field."""
    return (
        set(INCOME_STATEMENT_CONCEPTS)
        | set(BALANCE_SHEET_CONCEPTS)
        | set(CASH_FLOW_CONCEPTS)
        | set(DEBT_CURRENT_PRIORITY)
        | set(DEBT_NONCURRENT_PRIORITY)
        | set(_SPLIT_RATIO_CONCEPTS)
        | set(SPECIAL_CONCEPTS)
    )


def classify(concept: str) -> str:
    """Bucket a concept name for the report (display only)."""
    for bucket, pattern in _BUCKET_RULES:
        if pattern.search(concept):
            return bucket
    return "note_disclosure"


def actionable_coverage(mapped: int, actionable_unmapped: int) -> float:
    """Mapped share of the actionable concepts (0-100), 100 when none."""
    total = mapped + actionable_unmapped
    if total == 0:
        return 100.0
    return mapped / total * 100.0


def load_top_concepts(top: int, db_url: str) -> list[tuple[str, int, int]]:
    """Top concepts by distinct active-listing companies (read-only)."""
    import psycopg2

    with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ff.concept, count(DISTINCT ff.company_id) AS companies,
                   count(*) AS facts
            FROM financial_facts ff
            JOIN company_listings cl
              ON cl.company_id = ff.company_id AND cl.is_active
            GROUP BY ff.concept
            ORDER BY companies DESC, facts DESC
            LIMIT %s
            """,
            (top,),
        )
        return [
            (str(concept), int(companies), int(facts))
            for concept, companies, facts in cur.fetchall()
        ]


def count_active_companies(db_url: str) -> int:
    """Active listed companies with at least one stored fact."""
    import psycopg2

    with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(DISTINCT c.id)
            FROM companies c
            JOIN company_listings cl ON cl.company_id = c.id AND cl.is_active
            WHERE EXISTS (SELECT 1 FROM financial_facts ff WHERE ff.company_id = c.id)
            """
        )
        return int(cur.fetchone()[0])


def mapped_without_facts(concepts: set[str], db_url: str) -> list[str]:
    """Mapped concepts that have no fact in Financial-DataBase at all."""
    if not concepts:
        return []
    import psycopg2

    with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT concept FROM financial_facts WHERE concept = ANY(%s)",
            (sorted(concepts),),
        )
        present = {str(row[0]) for row in cur.fetchall()}
    return sorted(concepts - present)


def render_markdown(
    sample: list[tuple[str, int, int]],
    *,
    top: int,
    min_companies: int,
    active_companies: int,
    missing_mapped: list[str],
    generated: str,
) -> str:
    """Full report body (pure; used by the CLI and the tests)."""
    mapped_set = mapped_concepts()
    above = [(c, co, f) for c, co, f in sample if co >= min_companies]
    listed = [(c, co, f) for c, co, f in above if c in mapped_set]
    proposed = [
        (c, co, f) for c, co, f in above if c not in mapped_set and c in PROPOSED_FIELD
    ]
    informational = [
        (c, co, f)
        for c, co, f in above
        if c not in mapped_set and c not in PROPOSED_FIELD
    ]
    coverage = actionable_coverage(len(listed), len(proposed))
    raw = len(listed) / len(above) * 100 if above else 100.0

    buckets: dict[str, list[tuple[str, int, int]]] = {}
    for entry in informational:
        buckets.setdefault(classify(entry[0]), []).append(entry)

    lines = [
        "# Concept coverage audit",
        "",
        (
            f"Generated by `python -m scripts.audit_concept_coverage --top {top} "
            f"--min-companies {min_companies}` on {generated}."
        ),
        "Read-only: no Financial-DataBase or Value Investing data is written.",
        "",
        "## Summary",
        "",
        f"- Active listed companies with facts: **{active_companies:,}**",
        f"- Concepts in the top-{top} sample: **{len(sample):,}**",
        f"- High-coverage concepts (>= {min_companies} companies): **{len(above):,}**",
        f"- Mapped: **{len(listed):,}**",
        f"- Unmapped with a proposed field (actionable): **{len(proposed):,}**",
        f"- Unmapped informational (note/disclosure tags): **{len(informational):,}**",
        f"- Raw coverage: **{raw:.1f}%**",
        f"- Actionable coverage: **{coverage:.1f}%**",
        "",
        "## Actionable unmapped concepts",
        "",
        "| Concept | Companies | Facts | Proposed field |",
        "| --- | ---: | ---: | --- |",
    ]
    lines += [
        f"| `{concept}` | {companies:,} | {facts:,} | {PROPOSED_FIELD[concept]} |"
        for concept, companies, facts in proposed
    ]
    if not proposed:
        lines.append("| _(none)_ | | | |")

    lines += [
        "",
        "## Informational unmapped concepts by bucket",
        "",
        "| Bucket | Concepts | Top concepts |",
        "| --- | ---: | --- |",
    ]
    for bucket in sorted(buckets, key=lambda b: (-len(buckets[b]), b)):
        entries = sorted(buckets[bucket], key=lambda e: -e[1])
        top_names = ", ".join(f"`{c}` ({co:,})" for c, co, _ in entries[:8])
        lines.append(f"| {bucket} | {len(entries)} | {top_names} |")

    lines += [
        "",
        "## Mapped concepts with no facts in FDB",
        "",
    ]
    if missing_mapped:
        lines += [f"- `{concept}`" for concept in missing_mapped]
    else:
        lines.append("- _(none)_")

    lines += [
        "",
        "## Full sample",
        "",
        "| Concept | Companies | Facts | Mapped |",
        "| --- | ---: | ---: | :---: |",
    ]
    lines += [
        f"| `{concept}` | {companies:,} | {facts:,} | {'✓' if concept in mapped_set else '✗'} |"
        for concept, companies, facts in sample
    ]
    lines.append("")
    return "\n".join(lines)


def print_table(sample: list[tuple[str, int, int]], min_companies: int) -> None:
    """Aligned stdout table; missing concepts are marked with ``✗``."""
    mapped_set = mapped_concepts()
    width = max((len(c) for c, _, _ in sample), default=40)
    print(f"{'concept':<{width}}  companies  mapped?")
    print("-" * (width + 22))
    for concept, companies, _facts in sample:
        if companies < min_companies:
            continue
        mark = "✓" if concept in mapped_set else "✗"
        print(f"{concept:<{width}}  {companies:>9,}  {mark}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=200, help="concepts to sample")
    parser.add_argument(
        "--min-companies",
        type=int,
        default=100,
        help="ignore concepts below this active-company coverage",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="markdown report path"
    )
    parser.add_argument(
        "--db-url", default=None, help="FDB connection string (env by default)"
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=95.0,
        help="minimum actionable coverage %% for exit 0",
    )
    parser.add_argument(
        "--fail-if-unmapped",
        type=int,
        default=None,
        help="exit 1 when the actionable unmapped count exceeds N",
    )
    parser.add_argument(
        "--no-gate", action="store_true", help="always exit 0 (report only)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_url = args.db_url or os.environ.get("FINANCIAL_DATABASE_URL", DEFAULT_DB_URL)

    sample = load_top_concepts(args.top, db_url)
    active = count_active_companies(db_url)
    mapped_set = mapped_concepts()
    missing_mapped = mapped_without_facts(mapped_set, db_url)

    print_table(sample, args.min_companies)
    above = [c for c, co, _ in sample if co >= args.min_companies]
    listed = len([c for c in above if c in mapped_set])
    proposed = len([c for c in above if c not in mapped_set and c in PROPOSED_FIELD])
    coverage = actionable_coverage(listed, proposed)
    print(
        f"\nmapped={listed} actionable_unmapped={proposed} "
        f"informational={len(above) - listed - proposed} "
        f"actionable_coverage={coverage:.1f}%"
    )

    report = render_markdown(
        sample,
        top=args.top,
        min_companies=args.min_companies,
        active_companies=active,
        missing_mapped=missing_mapped,
        generated=datetime.now(UTC).date().isoformat(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"report written to {args.output}")

    if args.no_gate:
        return 0
    failed = coverage < args.min_coverage
    if args.fail_if_unmapped is not None and proposed > args.fail_if_unmapped:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
