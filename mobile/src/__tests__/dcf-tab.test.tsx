import type { UseQueryResult } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react-native";

import type { ApiEnvelope } from "../api/client";
import type { DCFResponse, DCFSensitivityRow } from "../api/company";
import { DCFTab } from "../components/DCFTab";
import { ThemeProvider } from "../theme/ThemeProvider";

type DCFQuery = UseQueryResult<ApiEnvelope<DCFResponse>, Error>;

function queryResult(partial: Partial<DCFQuery>): DCFQuery {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
    isSuccess: false,
    ...partial,
  } as unknown as DCFQuery;
}

const SENSITIVITY: DCFSensitivityRow[] = [];
for (const wacc of [0.065, 0.085, 0.105]) {
  for (const growth of [0.04, 0.06, 0.08]) {
    SENSITIVITY.push({
      wacc,
      growth,
      value: 100 + Math.round(wacc * 1000) + Math.round(growth * 1000),
    });
  }
}

const RESPONSE: DCFResponse = {
  ticker: "AAPL",
  variant: "standard",
  intrinsic_value: 139.6,
  current_price: 340.0,
  margin_of_safety: -1.411,
  verdict: "OVERVALUED",
  wacc: 0.085,
  assumptions: {
    fcf_base: 106.6e9,
    growth_1_5: 0.06,
    growth_6_10: 0.05,
    terminal_growth: 0.025,
  },
  sensitivity: SENSITIVITY,
  reasons: ["FCF base: 3-year average."],
  missing_inputs: [],
  source: "not-from-canon",
};

const INSUFFICIENT: DCFResponse = {
  ticker: "ZZZZ",
  variant: "standard",
  intrinsic_value: null,
  current_price: null,
  margin_of_safety: null,
  verdict: "INSUFFICIENT_DATA",
  wacc: null,
  assumptions: {
    fcf_base: null,
    growth_1_5: null,
    growth_6_10: null,
    terminal_growth: 0.025,
  },
  sensitivity: [],
  reasons: ["FCF base: no usable free-cash-flow year."],
  missing_inputs: ["fcf_base"],
  source: "not-from-canon",
};

function renderTab(response: DCFResponse) {
  return render(
    <ThemeProvider>
      <DCFTab
        query={queryResult({
          data: {
            data: response,
            meta: { source: "mixed", as_of: "2026-10-08T00:00:00Z", cache_ttl: 300 },
          },
          isSuccess: true,
        })}
        ticker={response.ticker}
      />
    </ThemeProvider>,
  );
}

test("renders the metrics, verdict, assumptions and sensitivity table", async () => {
  await renderTab(RESPONSE);
  expect(screen.getByTestId("dcf-metrics")).toBeTruthy();
  expect(screen.getByText("$139.60")).toBeTruthy();
  expect(screen.getByText("$340.00")).toBeTruthy();
  expect(screen.getByText("-141%")).toBeTruthy();
  expect(screen.getByText("OVER")).toBeTruthy();
  expect(screen.getByTestId("dcf-assumptions")).toBeTruthy();
  expect(screen.getByText("8.50%")).toBeTruthy();
  expect(screen.getByTestId("sensitivity-table")).toBeTruthy();
  expect(screen.getByText("not-from-canon")).toBeTruthy();
});

test("insufficient data shows the fallback without numbers", async () => {
  await renderTab(INSUFFICIENT);
  expect(screen.getByTestId("dcf-insufficient")).toBeTruthy();
  expect(
    screen.getByText("Not enough data to value this company."),
  ).toBeTruthy();
  expect(
    screen.getByText("• FCF base: no usable free-cash-flow year."),
  ).toBeTruthy();
  expect(screen.queryByTestId("dcf-metrics")).toBeNull();
  expect(screen.queryByTestId("sensitivity-table")).toBeNull();
});
