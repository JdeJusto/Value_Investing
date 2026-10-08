import type { ApiClient, ApiEnvelope } from "./client";

/**
 * Shape returned by `GET /api/v1/company/{ticker}` (Phase 1).
 *
 * `name`, `sector`, `cik`, `price`, `market_cap` and `currency` can be null
 * when the corresponding lookup fails or Yahoo is unreachable — the API
 * degrades instead of failing the request.
 */
export type CompanyResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  cik: string | null;
  price: number | null;
  market_cap: number | null;
  currency: string | null;
  fiscal_year: number | null;
};

export function fetchCompany(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<CompanyResponse>> {
  const normalized = ticker.trim().toUpperCase();
  return client.get<CompanyResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}`,
  );
}
