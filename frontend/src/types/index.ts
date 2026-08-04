export interface User {
  id: number
  email: string
  display_name: string | null
  is_active: boolean
  is_superuser: boolean
}

export interface MetricInterpretation {
  value: number | null
  formatted: string
  interpretation: string
}

export interface AnalysisResponse {
  ticker: string
  name: string | null
  price: number | null
  market_cap: number | null
  enterprise_value: number | null
  score: number
  revenue: number | null
  net_income: number | null
  fcf: number | null
  metrics: Record<string, MetricInterpretation>
}

export interface ScreenerRow {
  ticker: string
  name: string | null
  price: number | null
  market_cap: number | null
  per: number | null
  pb: number | null
  roe: number | null
  roic: number | null
  fcf_yield: number | null
  ev_ebit: number | null
  debt_to_equity: number | null
  score: number | null
  extra: Record<string, number | null>
}

export interface ScreenerJob {
  job_id: string
  status: string
}

export interface ScreenerJobStatus {
  job_id: string
  status: string
  progress: number
  results: ScreenerRow[] | null
  error_message: string | null
}

export interface Portfolio {
  id: number
  name: string
  description: string | null
  is_public: boolean
  created_at: string
  updated_at: string
  ticker_count: number
  items: PortfolioItem[]
}

export interface PortfolioItem {
  id: number
  ticker: string
  shares: number
  avg_cost: number | null
  notes: string | null
}

export interface Alert {
  id: number
  ticker: string
  metric_name: string
  operator: string
  threshold: number
  is_active: boolean
  notify_email: boolean
  notify_push: boolean
  last_triggered: string | null
  created_at: string
}

export interface Watchlist {
  id: number
  name: string
  ticker_count: number
  items: { id: number; ticker: string }[]
}

export interface Company {
  ticker: string
  name: string | null
  sector: string | null
  industry: string | null
  exchange: string | null
  country: string | null
  market_cap: number | null
  enterprise_value: number | null
  beta: number | null
  price: number | null
}
