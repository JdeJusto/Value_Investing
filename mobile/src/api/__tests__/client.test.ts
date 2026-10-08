import fetchMock from "jest-fetch-mock";

import { ApiClient, ApiRequestError } from "../client";

fetchMock.enableMocks();

const CONFIG = { baseUrl: "http://192.168.0.10:8000", apiKey: "secret-key" };

const ENVELOPE = {
  data: { ok: true },
  meta: { source: "internal", as_of: "2026-10-08T00:00:00Z", cache_ttl: 0 },
};

beforeEach(() => {
  fetchMock.resetMocks();
});

test("get sends the X-API-Key header and Accept: application/json", async () => {
  fetchMock.mockResponseOnce(JSON.stringify(ENVELOPE));

  const client = new ApiClient(CONFIG);
  await client.get("/api/v1/health");

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://192.168.0.10:8000/api/v1/health");
  const headers = init?.headers as Record<string, string>;
  expect(headers["X-API-Key"]).toBe("secret-key");
  expect(headers["Accept"]).toBe("application/json");
});

test("get parses a successful envelope", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: { ticker: "AAPL" },
      meta: { source: "mixed", as_of: "2026-10-08T00:00:00Z", cache_ttl: 300 },
    }),
  );

  const client = new ApiClient(CONFIG);
  const result = await client.get<{ ticker: string }>("/api/v1/company/AAPL");

  expect(result.data.ticker).toBe("AAPL");
  expect(result.meta.source).toBe("mixed");
  expect(result.meta.cache_ttl).toBe(300);
});

test("get throws ApiRequestError with the parsed code on 404", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      error: { code: "TICKER_NOT_FOUND", message: "Unknown ticker: ZZZZ" },
    }),
    { status: 404 },
  );

  const client = new ApiClient(CONFIG);
  const request = client.get("/api/v1/company/ZZZZ");

  await expect(request).rejects.toBeInstanceOf(ApiRequestError);
  await expect(request).rejects.toMatchObject({
    code: "TICKER_NOT_FOUND",
    status: 404,
  });
});

test("get throws NETWORK_ERROR when fetch rejects", async () => {
  fetchMock.mockRejectOnce(new TypeError("Network request failed"));

  const client = new ApiClient(CONFIG);
  const request = client.get("/api/v1/health");

  await expect(request).rejects.toBeInstanceOf(ApiRequestError);
  await expect(request).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
});

test("post serializes the body as JSON", async () => {
  fetchMock.mockResponseOnce(
    JSON.stringify({
      data: { added: true },
      meta: { source: "mixed", as_of: "2026-10-08T00:00:00Z", cache_ttl: 0 },
    }),
  );

  const client = new ApiClient(CONFIG);
  await client.post("/api/v1/portfolio/positions", { ticker: "AAPL", shares: 3 });

  const [, init] = fetchMock.mock.calls[0];
  expect(init?.body).toBe(JSON.stringify({ ticker: "AAPL", shares: 3 }));
  const headers = init?.headers as Record<string, string>;
  expect(headers["Content-Type"]).toBe("application/json");
});

test("non-JSON error bodies fall back to HTTP_<status>", async () => {
  fetchMock.mockResponseOnce("<html>gateway error</html>", { status: 502 });

  const client = new ApiClient(CONFIG);
  const request = client.get("/api/v1/health");

  await expect(request).rejects.toMatchObject({
    code: "HTTP_502",
    status: 502,
  });
});
