import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { ApiRequestError, type ApiEnvelope } from "../api/client";
import type { FinancialsResponse, InsightsResponse } from "../api/company";
import { FinancialsTab } from "../components/FinancialsTab";
import { ThemeProvider } from "../theme/ThemeProvider";

type FinancialsQuery = UseQueryResult<ApiEnvelope<FinancialsResponse>, Error>;
type InsightsQuery = UseQueryResult<ApiEnvelope<InsightsResponse>, Error>;

function queryResult<T>(
  partial: Partial<UseQueryResult<ApiEnvelope<T>, Error>>,
): UseQueryResult<ApiEnvelope<T>, Error> {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
    isSuccess: false,
    ...partial,
  } as unknown as UseQueryResult<ApiEnvelope<T>, Error>;
}

const FINANCIALS: FinancialsResponse = {
  ticker: "AAPL",
  name: "Apple Inc.",
  period: "FY",
  years: [2025, 2024],
  balance_sheet: [
    {
      concept: "AssetsCurrent",
      label: "Current Assets",
      unit: "USD",
      values: { "2025": "$152.99B", "2024": "$143.57B" },
    },
    {
      concept: "InventoryNet",
      label: "Inventory",
      unit: "USD",
      values: { "2025": "$5.72B", "2024": "—" },
    },
  ],
  income_statement: [
    {
      concept: "Revenues",
      label: "Revenue",
      unit: "USD",
      values: { "2025": "$416.16B", "2024": "$391.04B" },
    },
  ],
  cash_flow: [
    {
      concept: "NetCashProvidedByUsedInOperatingActivities",
      label: "Operating Cash Flow",
      unit: "USD",
      values: { "2025": "$118.25B", "2024": "$118.25B" },
    },
  ],
  other: [
    {
      concept: "EntityCommonStockSharesOutstanding",
      label: "Shares Outstanding",
      unit: "shares",
      values: { "2025": "14.78B sh", "2024": "15.12B sh" },
    },
  ],
  counts: {
    balance_sheet: 2,
    income_statement: 1,
    cash_flow: 1,
    other: 1,
    total: 5,
  },
};

const INSIGHTS: InsightsResponse = {
  ticker: "AAPL",
  metrics: [
    {
      metric: "revenue",
      label: "Revenue",
      latest_value: "$416,161,000,000",
      latest_year: 2025,
      yoy_change_pct: 6.4,
      cagr_5y: 8.7,
      cagr_10y: null,
      average_5y: "$381,234,000,000",
      trend: "growing",
      stability: "stable",
      direction_changed: false,
      notes: [],
    },
    {
      metric: "net_income",
      label: "Net Income",
      latest_value: "$112,010,000,000",
      latest_year: 2025,
      yoy_change_pct: 19.5,
      cagr_5y: 12.1,
      cagr_10y: null,
      average_5y: null,
      trend: "growing",
      stability: "volatile",
      direction_changed: false,
      notes: ["turnaround from loss to profit"],
    },
    {
      metric: "free_cash_flow",
      label: "Free Cash Flow",
      latest_value: "$105,539,000,000",
      latest_year: 2025,
      yoy_change_pct: -3.0,
      cagr_5y: 4.2,
      cagr_10y: null,
      average_5y: null,
      trend: "stable",
      stability: "stable",
      direction_changed: false,
      notes: [],
    },
  ],
  warnings: [],
};

const META = {
  source: "financial_database",
  as_of: "",
  cache_ttl: 0,
} as const;

function renderTab(
  financialsQuery: FinancialsQuery,
  insightsQuery: InsightsQuery,
) {
  return render(
    <ThemeProvider>
      <FinancialsTab
        financialsQuery={financialsQuery}
        insightsQuery={insightsQuery}
        ticker="AAPL"
      />
    </ThemeProvider>,
  );
}

function successQueries() {
  return [
    queryResult<FinancialsResponse>({
      data: { data: FINANCIALS, meta: META },
      isSuccess: true,
    }),
    queryResult<InsightsResponse>({
      data: { data: INSIGHTS, meta: META },
      isSuccess: true,
    }),
  ] as const;
}

test("renders the summary panel and the four sub-tabs", async () => {
  const [financials, insights] = successQueries();
  await renderTab(financials, insights);
  expect(screen.getByTestId("insights-summary")).toBeTruthy();
  expect(screen.getByText("Revenue")).toBeTruthy();
  expect(screen.getByText("Net Income")).toBeTruthy();
  expect(screen.getByText("YoY +6.4%")).toBeTruthy();
  expect(screen.getByText("YoY -3.0%")).toBeTruthy();
  expect(screen.getByText("Balance Sheet (2)")).toBeTruthy();
  expect(screen.getByText("Income Statement (1)")).toBeTruthy();
  expect(screen.getByText("Cash Flow (1)")).toBeTruthy();
  expect(screen.getByText("Other (1)")).toBeTruthy();
  expect(screen.getByText("Current Assets")).toBeTruthy();
  expect(screen.getByText("$152.99B")).toBeTruthy();
  expect(screen.getByText("FY2025")).toBeTruthy();
  expect(screen.getByText("FY2024")).toBeTruthy();
});

test("switching sub-tabs shows different rows", async () => {
  const [financials, insights] = successQueries();
  await renderTab(financials, insights);
  expect(screen.getByText("Current Assets")).toBeTruthy();
  await fireEvent.press(screen.getByText("Income Statement (1)"));
  expect(screen.queryByText("Current Assets")).toBeNull();
  expect(screen.getAllByText("Revenue")).toHaveLength(2); // summary + table
  expect(screen.getByText("$416.16B")).toBeTruthy();
});

test("the concept search filters the summary", async () => {
  const [financials, insights] = successQueries();
  await renderTab(financials, insights);
  await fireEvent.changeText(screen.getByTestId("insights-search"), "cash");
  expect(screen.getByText("Free Cash Flow")).toBeTruthy();
  expect(screen.queryByText("Net Income")).toBeNull();
});

test("tapping an insight expands its notes", async () => {
  const [financials, insights] = successQueries();
  await renderTab(financials, insights);
  expect(screen.queryByTestId("insight-notes-net_income")).toBeNull();
  await fireEvent.press(screen.getByTestId("insight-net_income"));
  expect(screen.getByTestId("insight-notes-net_income")).toBeTruthy();
  expect(screen.getByText("• turnaround from loss to profit")).toBeTruthy();
});

test("renders a skeleton while the facts load", async () => {
  await renderTab(
    queryResult<FinancialsResponse>({ isLoading: true, isPending: true }),
    queryResult<InsightsResponse>({ isLoading: true, isPending: true }),
  );
  expect(screen.getByTestId("skeleton-cards")).toBeTruthy();
});

test("maps a network error to the shared message", async () => {
  await renderTab(
    queryResult<FinancialsResponse>({
      error: new ApiRequestError("NETWORK_ERROR", "unreachable", 0),
      isError: true,
    }),
    queryResult<InsightsResponse>({ isLoading: true, isPending: true }),
  );
  expect(
    screen.getByText("Cannot reach the server. Check Settings."),
  ).toBeTruthy();
});
