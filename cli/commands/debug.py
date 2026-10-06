import time

from cli.formatters import (
    bold,
    dim,
    fmt_pct,
    fmt_ratio,
    green,
    print_header,
    print_separator,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "debug",
        help="System diagnostics and quick tests",
        description="Verifies that all parts of the system work correctly.",
    )
    p.set_defaults(func=_run)


def _run(args):
    print_header("System Diagnostics", "═")

    print(f"  {bold('1. Basic imports')}")
    _test_imports()
    print(f"  {green('✓ OK')}")

    print(f"\n  {bold('2. Filters (FilterCriteria)')}")
    _test_filters()
    print(f"  {green('✓ OK')}")

    print(f"\n  {bold('3. Services')}")
    _test_services()
    print(f"  {green('✓ OK')}")

    print(f"\n  {bold('4. Screener (3 tickers)')}")
    _test_screener()

    print(f"\n  {bold('5. Available tickers')}")
    _test_tickers()

    print_separator("═")
    print(f"\n  {green('✓ Diagnostics completed')}")
    print()


def _test_imports():
    import backend.analytics.ratios.debt_to_equity
    import backend.analytics.ratios.per
    import backend.analytics.ratios.revenue_growth
    import backend.analytics.service
    import backend.app.cli
    import backend.domain.interfaces.provider
    import backend.domain.value_objects.filter_criteria
    import backend.domain.value_objects.screener_result
    import backend.providers.tickers
    import backend.providers.yahoo.provider
    import backend.services.screener_service  # noqa: F401


def _test_filters():
    from backend.domain.value_objects.filter_criteria import FilterCriteria

    tests = [
        (FilterCriteria.lt("per", 15), 10, True, "per < 15 with 10"),
        (FilterCriteria.lt("per", 15), 20, False, "per < 15 with 20"),
        (FilterCriteria.gt("roe", 0.15), 0.20, True, "roe > 0.15 with 0.20"),
        (FilterCriteria.gt("roe", 0.15), 0.10, False, "roe > 0.15 with 0.10"),
        (FilterCriteria.between("pb", 1, 3), 2, True, "pb between 1-3 with 2"),
        (FilterCriteria.between("pb", 1, 3), 5, False, "pb between 1-3 with 5"),
        (FilterCriteria.lt("per", 15), None, False, "per < 15 with None"),
    ]
    passed = 0
    for criteria, value, expected, desc in tests:
        result = criteria.matches(value)
        status = green("✓") if result == expected else red("✗")
        print(f"    {status} {desc}: {result}")
        if result == expected:
            passed += 1
    print(f"    Filters: {green(f'{passed}/{len(tests)} correct')}")


def _test_services():
    from backend.app.cli import build_analysis_service, build_screener_service

    a = build_analysis_service()
    assert a is not None
    s = build_screener_service()
    assert s is not None
    print(f"    CompanyAnalysisService: {green('created')}")
    print(f"    StockScreenerService:   {green('created')}")


def _test_screener():
    from backend.app.cli import build_screener_service
    from backend.domain.value_objects.filter_criteria import FilterCriteria

    service = build_screener_service()
    test_tickers = ["AAPL", "MSFT", "GOOGL"]
    filters = [FilterCriteria.lt("per", 40)]

    start = time.time()
    results = service.screen(tickers=test_tickers, filters=filters, top_n=5)
    elapsed = time.time() - start

    if results:
        print(
            f"    {green(f'{len(results)}/3')} tickers pass filters in {elapsed:.1f}s"
        )
        for r in results:
            per_str = fmt_ratio(r.per, 1) if r.per else dim("N/A")
            roe_str = fmt_pct(r.roe) if r.roe else dim("N/A")
            score_str = f"{r.score:.4f}" if r.score else dim("N/A")
            print(
                f"      {r.ticker:>6}  PER: {per_str:>6}  ROE: {roe_str:>6}  Score: {score_str}"
            )
    else:
        print(f"    {yellow('No results for the test tickers')}")


def _test_tickers():
    from backend.providers.tickers import TICKERS

    print(f"    {len(TICKERS)} tickers in static list")
    sample = ", ".join(TICKERS[:5])
    print(f"    First: {sample}")

    from backend.providers.tickers import search_tickers

    results = search_tickers("AAPL")
    print(f"    Search 'AAPL': {len(results)} results")
