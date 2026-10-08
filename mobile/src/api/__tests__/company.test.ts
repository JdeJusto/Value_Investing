import fetchMock from "jest-fetch-mock";

import { ApiClient } from "../client";
import {
  fetchCompany,
  fetchDCF,
  fetchFilings,
  fetchFinancials,
  fetchInsights,
  fetchMethodologies,
  fetchSection,
  fetchStatement,
} from "../company";

fetchMock.enableMocks();

const CONFIG = { baseUrl: "http://10.0.2.2:8000", apiKey: "secret-key" };

const META = {
  source: "mixed",
  as_of: "2026-10-08T00:00:00Z",
  cache_ttl: 300,
};

beforeEach(() => {
  fetchMock.resetMocks();
});

test("fetchCompany calls the company endpoint", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({ data: { ticker: "AAPL" }, meta: META }),
  );
  const client = new ApiClient(CONFIG);
  await fetchCompany(client, "aapl");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL",
  );
});

test("fetchMethodologies calls the methodologies endpoint and parses it", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: {
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
        ],
        summary: {
          buy_count: 0,
          watch_count: 0,
          hold_count: 0,
          avoid_count: 1,
          na_count: 0,
          insufficient_count: 0,
          consensus_score: -1,
        },
      },
      meta: META,
    }),
  );
  const client = new ApiClient(CONFIG);
  const result = await fetchMethodologies(client, "aapl");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/methodologies",
  );
  expect(result.data.methodologies[0].score).toBe(28.57);
  expect(result.data.methodologies[0].verdict).toBe("AVOID");
  expect(result.data.summary.consensus_score).toBe(-1);
});

test("a null methodology score is preserved as null", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: {
        ticker: "JPM",
        name: "JPMorgan Chase & Co.",
        methodologies: [
          {
            name: "graham",
            family: "DEEP_VALUE",
            verdict: "N/A",
            score: null,
            confidence: "HIGH",
            reasons: ["financial company — rules do not apply"],
            red_flags: [],
            failed_rules: [],
            passed_rules: [],
          },
        ],
        summary: {
          buy_count: 0,
          watch_count: 0,
          hold_count: 0,
          avoid_count: 0,
          na_count: 1,
          insufficient_count: 0,
          consensus_score: 0,
        },
      },
      meta: META,
    }),
  );
  const client = new ApiClient(CONFIG);
  const result = await fetchMethodologies(client, "JPM");
  expect(result.data.methodologies[0].score).toBeNull();
  expect(result.data.summary.na_count).toBe(1);
});

test("fetchDCF calls the dcf endpoint and parses the response", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: {
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
        sensitivity: [{ wacc: 0.065, growth: 0.04, value: 160.5 }],
        reasons: ["FCF base: 3-year average."],
        missing_inputs: [],
        source: "not-from-canon",
      },
      meta: META,
    }),
  );
  const client = new ApiClient(CONFIG);
  const result = await fetchDCF(client, "aapl");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/dcf",
  );
  expect(result.data.source).toBe("not-from-canon");
  expect(result.data.margin_of_safety).toBe(-1.411);
  expect(result.data.sensitivity).toHaveLength(1);
});

test("fetchFinancials builds the years and abbreviate query", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({ data: { ticker: "AAPL" }, meta: META }),
  );
  const client = new ApiClient(CONFIG);
  await fetchFinancials(client, "aapl", { years: 10, abbreviate: true });
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/financials?years=10&abbreviate=true",
  );
});

test("fetchFinancials without options sends no query string", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({ data: { ticker: "AAPL" }, meta: META }),
  );
  const client = new ApiClient(CONFIG);
  await fetchFinancials(client, "AAPL");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/financials",
  );
});

test("fetchInsights calls the insights endpoint", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: { ticker: "AAPL", metrics: [], warnings: [] },
      meta: META,
    }),
  );
  const client = new ApiClient(CONFIG);
  await fetchInsights(client, "AAPL");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/insights",
  );
});

test("fetchFilings builds the filter query", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({ data: { ticker: "AAPL" }, meta: META }),
  );
  const client = new ApiClient(CONFIG);
  await fetchFilings(client, "aapl", { form: "10-K", year: 2024, limit: 5 });
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/company/AAPL/filings?form=10-K&year=2024&limit=5",
  );
});

test("fetchStatement and fetchSection build their paths", async () => {
  fetchMock.mockResponseOnce(JSON.stringify({ data: {}, meta: META }));
  const client = new ApiClient(CONFIG);
  await fetchStatement(client, "0000320193-24-000123", "balance_sheet");
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://10.0.2.2:8000/api/v1/filings/0000320193-24-000123/statement/balance_sheet",
  );

  fetchMock.mockResponseOnce(JSON.stringify({ data: {}, meta: META }));
  await fetchSection(client, "0000320193-24-000123", "risk_factors", {
    wordLimit: 100,
  });
  expect(fetchMock.mock.calls[1][0]).toBe(
    "http://10.0.2.2:8000/api/v1/filings/0000320193-24-000123/section/risk_factors?word_limit=100",
  );
});
