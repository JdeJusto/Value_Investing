import fetchMock from "jest-fetch-mock";

import { ApiClient } from "../client";
import { fetchCompany, fetchMethodologies } from "../company";

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
