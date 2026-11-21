"""Per-ticker expense-line overrides (verified against the filing).

Only add an entry when the generic map (:data:`EXPENSE_LINE_MAP`) cannot
represent the filing. Values are the canonical line keys:

- a tag string selects that exact XBRL concept;
- a number is a verified value in USD (rare; document the source);
- ``None`` means "not disclosed" (never zero).
"""

from __future__ import annotations

#: ticker -> {line_item: tag | float | None}
EXPENSE_OVERRIDES: dict[str, dict[str, str | float | None]] = {
    # No unverified overrides yet. Add entries only after checking the 10-K.
}
