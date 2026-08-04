import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../services/api'
import type { AnalysisResponse } from '../types'
import MetricCard from '../components/MetricCard'
import { ArrowLeft, TrendingUp, BarChart3, Shield, Activity } from 'lucide-react'

const METRICS_DISPLAY: Record<string, string> = {
  roe: 'ROE',
  pb: 'P/B',
  fcf_yield: 'FCF Yield',
  operating_margin: 'Op. Margin',
  net_margin: 'Net Margin',
  roic: 'ROIC',
  incremental_roic: 'Incr. ROIC',
  ev_ebit: 'EV/EBIT',
  owner_earnings: 'Owner Earnings',
  piotroski_fscore: 'Piotroski F-Score',
  altman_zscore: 'Altman Z-Score',
  net_debt_to_ebitda: 'Net Debt/EBITDA',
  interest_coverage: 'Int. Coverage',
  gross_margin_stability: 'GM Stability',
  fcf_conversion: 'FCF Conversion',
  croic: 'CROIC',
  acquirers_multiple: "Acquirer's Multiple",
  dcf_value: 'DCF Value',
  shareholder_yield: 'Shareholder Yield',
}

const CATEGORIES: Record<string, string[]> = {
  Rentabilidad: ['roe', 'roic', 'incremental_roic', 'croic'],
  Valoración: ['pb', 'ev_ebit', 'fcf_yield', 'dcf_value', 'acquirers_multiple'],
  Márgenes: ['operating_margin', 'net_margin', 'fcf_conversion', 'gross_margin_stability'],
  Endeudamiento: ['net_debt_to_ebitda', 'interest_coverage'],
  Calidad: ['piotroski_fscore', 'altman_zscore', 'shareholder_yield', 'owner_earnings'],
}

const HIGHLIGHTS: Record<string, Record<string, 'positive' | 'negative' | 'neutral'>> = {
  roe: { Bueno: 'positive', Aceptable: 'neutral', Malo: 'negative' },
  pb: { Bueno: 'positive', Normal: 'neutral', Caro: 'negative' },
  fcf_yield: { Bueno: 'positive', Aceptable: 'neutral', Bajo: 'negative' },
  piotroski_fscore: { 'Muy fuerte': 'positive', Normal: 'neutral', Debil: 'negative' },
  altman_zscore: { Segura: 'positive', Gris: 'neutral', Riesgo: 'negative' },
}

function getHighlight(metricKey: string, interpretation: string): 'positive' | 'negative' | 'neutral' {
  const rules = HIGHLIGHTS[metricKey]
  if (!rules) return 'neutral'
  for (const [keyword, hl] of Object.entries(rules)) {
    if (interpretation.includes(keyword)) return hl
  }
  return 'neutral'
}

export default function CompanyDetailPage() {
  const { ticker } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    api
      .get(`/companies/${ticker}/analysis`)
      .then((res) => {
        setAnalysis(res.data)
        setError('')
      })
      .catch((err) => setError(err.response?.data?.detail || 'Error al cargar datos'))
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-[#00cc88] mr-3" />
        <span className="text-gray-400">Cargando análisis...</span>
      </div>
    )
  }

  if (error || !analysis) {
    return (
      <div className="p-8">
        <div className="text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg p-4">
          {error || 'No se encontraron datos'}
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <button
        onClick={() => navigate('/companies')}
        className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-4"
      >
        <ArrowLeft size={18} /> Volver
      </button>

      <div className="flex items-baseline gap-4 mb-8">
        <h1 className="text-2xl font-bold text-white">
          {analysis.name || analysis.ticker}{' '}
          <span className="text-gray-400 text-lg">{analysis.ticker}</span>
        </h1>
        {analysis.price && <span className="text-[#00cc88] text-xl font-mono">${analysis.price.toFixed(2)}</span>}
        <span className="bg-[#00cc88]/10 text-[#00cc88] px-3 py-1 rounded-full text-sm font-semibold">
          Score: {analysis.score.toFixed(4)}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <MetricCard label="Market Cap" value={analysis.market_cap ? `$${(analysis.market_cap / 1e9).toFixed(2)}B` : 'N/A'} />
        <MetricCard label="Revenue" value={analysis.revenue ? `$${(analysis.revenue / 1e9).toFixed(2)}B` : 'N/A'} />
        <MetricCard label="Net Income" value={analysis.net_income ? `$${(analysis.net_income / 1e9).toFixed(2)}B` : 'N/A'} />
        <MetricCard label="Free Cash Flow" value={analysis.fcf ? `$${(analysis.fcf / 1e9).toFixed(2)}B` : 'N/A'} />
      </div>

      {Object.entries(CATEGORIES).map(([category, metricKeys]) => {
        const metrics = metricKeys
          .map((k) => ({ key: k, ...analysis.metrics[k] }))
          .filter((m) => m.formatted)

        if (metrics.length === 0) return null

        return (
          <div key={category} className="mb-8">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              {category === 'Rentabilidad' && <TrendingUp size={20} className="text-[#00cc88]" />}
              {category === 'Valoración' && <BarChart3 size={20} className="text-blue-400" />}
              {category === 'Márgenes' && <Activity size={20} className="text-yellow-400" />}
              {category === 'Endeudamiento' && <Shield size={20} className="text-red-400" />}
              {category === 'Calidad' && <Shield size={20} className="text-purple-400" />}
              {category}
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {metrics.map((m) => (
                <MetricCard
                  key={m.key}
                  label={METRICS_DISPLAY[m.key] || m.key}
                  value={m.formatted}
                  interpretation={m.interpretation}
                  highlight={getHighlight(m.key, m.interpretation)}
                />
              ))}
            </div>
          </div>
        )
      })}

      {Object.keys(CATEGORIES).length === 0 && Object.keys(analysis.metrics).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Todas las Métricas</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(analysis.metrics).map(([key, m]) => (
              <MetricCard
                key={key}
                label={METRICS_DISPLAY[key] || key}
                value={m.formatted}
                interpretation={m.interpretation}
                highlight={getHighlight(key, m.interpretation)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
