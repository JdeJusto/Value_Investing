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

export type MethodologyVerdict =
  | "BUY"
  | "WATCH"
  | "HOLD"
  | "AVOID"
  | "N/A"
  | "INSUFFICIENT_DATA";

/** One methodology verdict from GET /company/{ticker}/methodologies. */
export type MethodologyResult = {
  name: string;
  family: string;
  verdict: MethodologyVerdict;
  score: number | null;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasons: string[];
  red_flags: string[];
  failed_rules: string[];
  passed_rules: string[];
};

export type MethodologiesSummary = {
  buy_count: number;
  watch_count: number;
  hold_count: number;
  avoid_count: number;
  na_count: number;
  insufficient_count: number;
  consensus_score: number;
};

export type MethodologiesResponse = {
  ticker: string;
  name: string | null;
  methodologies: MethodologyResult[];
  summary: MethodologiesSummary;
};

export function fetchMethodologies(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<MethodologiesResponse>> {
  const normalized = ticker.trim().toUpperCase();
  return client.get<MethodologiesResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}/methodologies`,
  );
}
