import type { ApiClient, ApiEnvelope } from "./client";

/** One company in the consensus ranking. */
export type ConsensusCompany = {
  ticker: string;
  name: string;
  category: string;
  consensus_score: number;
  buy_count: number;
  avoid_count: number;
  insufficient_count: number;
  na_count: number;
  price: number | null;
  verdicts: Record<string, string>;
  verdict_string: string;
};

/** Snapshot response from GET /api/v1/consensus. */
export type ConsensusSnapshot = {
  date: string;
  universe: string;
  version: number;
  count: number;
  prices_available: boolean;
  na_count: number;
  buy_distribution: Record<string, number>;
  categories: Record<string, number>;
};

/** Ranking response from GET /api/v1/consensus/ranking. */
export type ConsensusRanking = {
  date: string;
  universe: string;
  by: string;
  top: number;
  rows: ConsensusCompany[];
};

/** By-category response from GET /api/v1/consensus/by-category. */
export type ConsensusByCategory = {
  date: string;
  universe: string;
  per_category: number;
  categories: Record<string, ConsensusCompany[]>;
};

/** Disagreement response from GET /api/v1/consensus/disagreement. */
export type ConsensusDisagreement = {
  date: string;
  universe: string;
  min_buy: number;
  max_buy: number;
  count: number;
  rows: ConsensusCompany[];
};

export function fetchConsensus(
  client: ApiClient,
  date?: string,
): Promise<ApiEnvelope<ConsensusSnapshot>> {
  const query = date ? `?date=${date}` : "";
  return client.get<ConsensusSnapshot>(`/api/v1/consensus${query}`);
}

export function fetchRanking(
  client: ApiClient,
  params: { date?: string; top?: number; by?: string } = {},
): Promise<ApiEnvelope<ConsensusRanking>> {
  const q = new URLSearchParams();
  if (params.date) q.set("date", params.date);
  if (params.top) q.set("top", String(params.top));
  if (params.by) q.set("by", params.by);
  return client.get<ConsensusRanking>(`/api/v1/consensus/ranking?${q.toString()}`);
}

export function fetchByCategory(
  client: ApiClient,
  params: { date?: string; per_category?: number } = {},
): Promise<ApiEnvelope<ConsensusByCategory>> {
  const q = new URLSearchParams();
  if (params.date) q.set("date", params.date);
  if (params.per_category) q.set("per_category", String(params.per_category));
  return client.get<ConsensusByCategory>(`/api/v1/consensus/by-category?${q.toString()}`);
}

export function fetchDisagreement(
  client: ApiClient,
  params: { date?: string; min_buy?: number; max_buy?: number } = {},
): Promise<ApiEnvelope<ConsensusDisagreement>> {
  const q = new URLSearchParams();
  if (params.date) q.set("date", params.date);
  if (params.min_buy) q.set("min_buy", String(params.min_buy));
  if (params.max_buy) q.set("max_buy", String(params.max_buy));
  return client.get<ConsensusDisagreement>(`/api/v1/consensus/disagreement?${q.toString()}`);
}