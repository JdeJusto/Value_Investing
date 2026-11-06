"""Historical P/E chart outlier filter (display only)."""

from __future__ import annotations

from ui.charts import split_pe_outliers


def test_split_pe_outliers_keeps_normal_years_and_counts_hidden() -> None:
    rows = [
        {"Fiscal year": 2025, "P/E": 10.0},
        {"Fiscal year": 2024, "P/E": 5_659.7},
        {"Fiscal year": 2023, "P/E": -4_532.1},
        {"Fiscal year": 2022, "P/E": 20.0},
    ]

    kept, hidden = split_pe_outliers(rows)

    assert [row["Fiscal year"] for row in kept] == [2025, 2022]
    assert hidden == 2


def test_split_pe_outliers_handles_all_outliers() -> None:
    kept, hidden = split_pe_outliers([{"Fiscal year": 2025, "P/E": 5_659.7}])

    assert kept == []
    assert hidden == 1
