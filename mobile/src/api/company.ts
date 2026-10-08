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

export type DCFVariant =
  | "standard"
  | "reit"
  | "ddm_financial"
  | "ddm_financial_two_stage"
  | "hyper_growth";

export type DCFAssumptions = {
  fcf_base: number | null;
  growth_1_5: number | null;
  growth_6_10: number | null;
  terminal_growth: number;
};

export type DCFSensitivityRow = {
  wacc: number;
  growth: number;
  value: number | null;
};

/** Shape of GET /company/{ticker}/dcf (source is always not-from-canon). */
export type DCFResponse = {
  ticker: string;
  variant: DCFVariant;
  intrinsic_value: number | null;
  current_price: number | null;
  margin_of_safety: number | null;
  verdict: "UNDERVALUED" | "FAIR" | "OVERVALUED" | "INSUFFICIENT_DATA";
  wacc: number | null;
  assumptions: DCFAssumptions;
  sensitivity: DCFSensitivityRow[];
  reasons: string[];
  missing_inputs: string[];
  source: "not-from-canon";
};

export function fetchDCF(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<DCFResponse>> {
  const normalized = ticker.trim().toUpperCase();
  return client.get<DCFResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}/dcf`,
  );
}

export type FinancialsRow = {
  concept: string;
  label: string;
  unit: string;
  values: Record<string, string>; // fiscal year -> formatted value
};

export type FinancialsCounts = {
  balance_sheet: number;
  income_statement: number;
  cash_flow: number;
  other: number;
  total: number;
};

/** Shape of GET /company/{ticker}/financials. */
export type FinancialsResponse = {
  ticker: string;
  name: string | null;
  period: string;
  years: number[];
  balance_sheet: FinancialsRow[];
  income_statement: FinancialsRow[];
  cash_flow: FinancialsRow[];
  other: FinancialsRow[];
  counts: FinancialsCounts;
};

export type InsightsMetric = {
  metric: string;
  label: string;
  latest_value: string | null;
  latest_year: number | null;
  yoy_change_pct: number | null;
  cagr_5y: number | null;
  cagr_10y: number | null;
  average_5y: string | null;
  trend: "growing" | "stable" | "declining";
  stability: "stable" | "volatile";
  direction_changed: boolean;
  notes: string[];
};

/** Shape of GET /company/{ticker}/insights. */
export type InsightsResponse = {
  ticker: string;
  metrics: InsightsMetric[];
  warnings: string[];
};

export function fetchFinancials(
  client: ApiClient,
  ticker: string,
  opts?: { years?: number; abbreviate?: boolean },
): Promise<ApiEnvelope<FinancialsResponse>> {
  const params = new URLSearchParams();
  if (opts?.years) {
    params.set("years", String(opts.years));
  }
  if (opts?.abbreviate) {
    params.set("abbreviate", "true");
  }
  const query = params.toString();
  const normalized = ticker.trim().toUpperCase();
  return client.get<FinancialsResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}/financials${
      query ? `?${query}` : ""
    }`,
  );
}

export function fetchInsights(
  client: ApiClient,
  ticker: string,
): Promise<ApiEnvelope<InsightsResponse>> {
  const normalized = ticker.trim().toUpperCase();
  return client.get<InsightsResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}/insights`,
  );
}

export type Filing = {
  accession_number: string;
  form_type: string;
  filing_date: string;
  period_of_report: string | null;
  fiscal_year: number | null;
  is_amended: boolean;
  sec_url: string | null;
};

/** Shape of GET /company/{ticker}/filings. */
export type FilingsResponse = {
  ticker: string;
  filings: Filing[];
  count: number;
  available_forms: string[];
  available_years: number[];
};

export type StatementLine = {
  label: string;
  current: string | null;
  prior: string | null;
  indent_level: number;
};

/** Shape of GET /filings/{accession}/statement/{type}. */
export type StatementResponse = {
  accession_number: string;
  form_type: string;
  filing_date: string;
  period_end: string | null;
  statement_type: string;
  source: string;
  warnings: string[];
  lines: StatementLine[];
};

/** Shape of GET /filings/{accession}/section/{type}. */
export type SectionResponse = {
  accession_number: string;
  form_type: string;
  section_type: string;
  title: string;
  word_count: number;
  source: string;
  warnings: string[];
  text: string;
  truncated: boolean;
};

export function fetchFilings(
  client: ApiClient,
  ticker: string,
  filters?: {
    form?: string;
    year?: number;
    limit?: number;
    includeAmendments?: boolean;
  },
): Promise<ApiEnvelope<FilingsResponse>> {
  const params = new URLSearchParams();
  if (filters?.form) {
    params.set("form", filters.form);
  }
  if (filters?.year) {
    params.set("year", String(filters.year));
  }
  if (filters?.limit) {
    params.set("limit", String(filters.limit));
  }
  if (filters?.includeAmendments === false) {
    params.set("include_amendments", "false");
  }
  const query = params.toString();
  const normalized = ticker.trim().toUpperCase();
  return client.get<FilingsResponse>(
    `/api/v1/company/${encodeURIComponent(normalized)}/filings${
      query ? `?${query}` : ""
    }`,
  );
}

export function fetchStatement(
  client: ApiClient,
  accession: string,
  statementType: string,
): Promise<ApiEnvelope<StatementResponse>> {
  return client.get<StatementResponse>(
    `/api/v1/filings/${encodeURIComponent(accession)}/statement/${encodeURIComponent(
      statementType,
    )}`,
  );
}

export function fetchSection(
  client: ApiClient,
  accession: string,
  sectionType: string,
  opts?: { wordLimit?: number },
): Promise<ApiEnvelope<SectionResponse>> {
  const params = new URLSearchParams();
  if (opts?.wordLimit) {
    params.set("word_limit", String(opts.wordLimit));
  }
  const query = params.toString();
  return client.get<SectionResponse>(
    `/api/v1/filings/${encodeURIComponent(accession)}/section/${encodeURIComponent(
      sectionType,
    )}${query ? `?${query}` : ""}`,
  );
}
