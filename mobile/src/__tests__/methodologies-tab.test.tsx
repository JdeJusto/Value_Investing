import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { ApiRequestError, type ApiEnvelope } from "../api/client";
import type { MethodologiesResponse } from "../api/company";
import { MethodologiesTab } from "../components/MethodologiesTab";
import { ThemeProvider } from "../theme/ThemeProvider";

type MethodologiesQuery = UseQueryResult<
  ApiEnvelope<MethodologiesResponse>,
  Error
>;

function queryResult(partial: Partial<MethodologiesQuery>): MethodologiesQuery {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
    isSuccess: false,
    ...partial,
  } as unknown as MethodologiesQuery;
}

const RESPONSE: MethodologiesResponse = {
  ticker: "AAPL",
  name: "Apple Inc.",
  methodologies: [
    {
      name: "graham",
      family: "DEEP_VALUE",
      verdict: "AVOID",
      score: 28.57,
      confidence: "MEDIUM",
      reasons: ["No margin of safety."],
      red_flags: ["High P/BV"],
      failed_rules: ["criterion_1_size"],
      passed_rules: [],
    },
    {
      name: "buffett_classic",
      family: "QUALITY_COMPOUNDER",
      verdict: "BUY",
      score: 80.46,
      confidence: "HIGH",
      reasons: ["Durable moat."],
      red_flags: [],
      failed_rules: [],
      passed_rules: ["pillar_profitability"],
    },
  ],
  summary: {
    buy_count: 1,
    watch_count: 0,
    hold_count: 0,
    avoid_count: 1,
    na_count: 0,
    insufficient_count: 0,
    consensus_score: 0,
  },
};

function renderTab(query: MethodologiesQuery) {
  return render(
    <ThemeProvider>
      <MethodologiesTab query={query} ticker="AAPL" />
    </ThemeProvider>,
  );
}

test("renders a skeleton while loading", async () => {
  await renderTab(queryResult({ isLoading: true, isPending: true }));
  expect(screen.getByTestId("skeleton-cards")).toBeTruthy();
});

test("renders the summary chips and one card per methodology", async () => {
  await renderTab(
    queryResult({
      data: { data: RESPONSE, meta: { source: "mixed", as_of: "", cache_ttl: 0 } },
      isSuccess: true,
    }),
  );
  expect(screen.getByTestId("summary-chip-BUY")).toBeTruthy();
  expect(screen.getByTestId("summary-chip-AVOID")).toBeTruthy();
  expect(screen.getByText("BUY 1")).toBeTruthy();
  expect(screen.getByText("AVOID 1")).toBeTruthy();
  expect(screen.getAllByTestId(/^methodology-card-/)).toHaveLength(2);
  expect(screen.getByText("Score: 28.57")).toBeTruthy();
});

test("tapping a card expands it with reasons and red flags", async () => {
  await renderTab(
    queryResult({
      data: { data: RESPONSE, meta: { source: "mixed", as_of: "", cache_ttl: 0 } },
      isSuccess: true,
    }),
  );
  expect(screen.queryByTestId("methodology-detail-graham")).toBeNull();
  await fireEvent.press(screen.getByTestId("methodology-card-graham"));
  expect(screen.getByTestId("methodology-detail-graham")).toBeTruthy();
  expect(screen.getByText("• No margin of safety.")).toBeTruthy();
  expect(screen.getByText("• High P/BV")).toBeTruthy();
});

test("renders the mapped error message when the query fails", async () => {
  await renderTab(
    queryResult({
      error: new ApiRequestError("NETWORK_ERROR", "unreachable", 0),
      isError: true,
    }),
  );
  expect(
    screen.getByText("Cannot reach the server. Check Settings."),
  ).toBeTruthy();
});
