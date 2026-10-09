import type { ApiClient, ApiEnvelope } from "./client";

/**
 * Shape returned by `GET /api/v1/screener` (API Phase 4).
 *
 * `pe`/`roe`/`fcf_yield` arrive as ratios (0.1099 = 10.99%); `roe_min` and
 * `fcf_yield_min` filters are sent as percentages (the CLI/UI convention).
 */
export type ScreenerRow = {
  ticker: string;
  name: string | null;
  sector: string | null;
  price: number | null;
  market_cap: number | null;
  pe: number | null;
  roe: number | null;
  fcf_yield: number | null;
  verdict: string | null;
  score: number | null;
  category: string | null;
  key_reason: string | null;
};

export type ScreenerFilterParams = {
  universe?: string;
  sector?: string;
  verdict?: string;
  category?: string;
  pe_max?: number;
  roe_min?: number;
  fcf_yield_min?: number;
  market_cap_min?: number;
  market_cap_max?: number;
  page?: number;
  page_size?: number;
};

export type ScreenerData = {
  universe: string;
  methodology: string;
  filters: Record<string, unknown>;
  rows: ScreenerRow[];
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  warning?: string;
};

/** Query string for the screener call (skips empty values). */
export function buildScreenerQuery(params: ScreenerFilterParams): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  return query.toString();
}

export function fetchScreener(
  client: ApiClient,
  params: ScreenerFilterParams,
): Promise<ApiEnvelope<ScreenerData>> {
  return client.get<ScreenerData>(`/api/v1/screener?${buildScreenerQuery(params)}`);
}
