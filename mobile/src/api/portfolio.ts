import type { ApiClient, ApiEnvelope } from "./client";

export type PortfolioPosition = {
  ticker: string;
  shares: number;
  avg_price: number | null;
  current_price: number | null;
  value: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  thesis: string | null;
  signal: string | null;
  signal_at_entry: string | null;
  price_source: string | null;
  opened_at: string | null;
};

export type PortfolioSummary = {
  cost: number;
  value: number;
  pnl: number;
  return_pct: number | null;
};

export type PortfolioData = {
  positions: PortfolioPosition[];
  summary: PortfolioSummary;
};

export type PortfolioPerformanceData = {
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  total_return: number | null;
  position_weights: Record<string, number>;
  positions: Array<{
    ticker: string;
    quantity: number;
    avg_price: number;
    current_price: number;
    market_value: number;
    unrealized_pnl: number;
    unrealized_return: number | null;
  }>;
  allocation: {
    overconcentrated: Array<{ ticker: string; weight: number }>;
    sector_exposure: Array<{ sector: string; weight: number }>;
    risk: {
      largest_position_weight: number;
      top_n_share: number;
      hhi: number;
      single_name_risk: boolean;
      top_n_risk: boolean;
    };
  };
};

export type PositionCreate = {
  ticker: string;
  shares: number;
  price: number;
  thesis?: string;
  signal?: string;
  date?: string;
};

export type ExitResponse = {
  ticker: string;
  exit_price: number;
  realized_pnl: number;
  realized_pnl_pct: number | null;
};

export function fetchPortfolio(
  client: ApiClient,
): Promise<ApiEnvelope<PortfolioData>> {
  return client.get<PortfolioData>("/api/v1/portfolio");
}

export function fetchPortfolioPerformance(
  client: ApiClient,
): Promise<ApiEnvelope<PortfolioPerformanceData>> {
  return client.get<PortfolioPerformanceData>("/api/v1/portfolio/performance");
}

export function addPosition(
  client: ApiClient,
  payload: PositionCreate,
): Promise<ApiEnvelope<PortfolioPosition>> {
  return client.post<PortfolioPosition>("/api/v1/portfolio/positions", payload);
}

export function removePosition(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<{ removed: boolean }>> {
  return client.delete<{ removed: boolean }>(
    `/api/v1/portfolio/positions/${encodeURIComponent(ticker)}`,
  );
}

export function exitPosition(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<ExitResponse>> {
  return client.post<ExitResponse>(
    `/api/v1/portfolio/positions/${encodeURIComponent(ticker)}/exit`,
    {},
  );
}