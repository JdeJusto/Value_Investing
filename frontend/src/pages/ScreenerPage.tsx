import { useState } from 'react'
import api from '../services/api'
import type { ScreenerRow } from '../types'

const FILTER_OPTIONS = [
  { key: 'per', label: 'PER' },
  { key: 'pb', label: 'P/B' },
  { key: 'roe', label: 'ROE' },
  { key: 'roic', label: 'ROIC' },
  { key: 'fcf_yield', label: 'FCF Yield' },
  { key: 'ev_ebit', label: 'EV/EBIT' },
  { key: 'debt_to_equity', label: 'D/E' },
  { key: 'net_margin', label: 'Net Margin' },
  { key: 'operating_margin', label: 'Op. Margin' },
]

export default function ScreenerPage() {
  const [filters, setFilters] = useState<{ field: string; operator: string; value: any }[]>([])
  const [field, setField] = useState('per')
  const [operator, setOperator] = useState('lt')
  const [value, setValue] = useState('')
  const [topN, setTopN] = useState(25)
  const [results, setResults] = useState<ScreenerRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const addFilter = () => {
    if (!value) return
    setFilters([...filters, { field, operator, value: parseFloat(value) }])
    setValue('')
  }

  const removeFilter = (idx: number) => {
    setFilters(filters.filter((_, i) => i !== idx))
  }

  const runScreener = async () => {
    setLoading(true)
    setError('')
    try {
      const filterPayload = filters.map((f) => ({
        field: f.field,
        operator: f.operator,
        value: f.operator === 'between' ? f.value : f.operator === 'gt' || f.operator === 'lt' ? f.value : parseFloat(f.value as string) || f.value,
      }))
      const { data: job } = await api.post('/screener', {
        filters: filterPayload,
        top_n: topN,
      })
      const poll = setInterval(async () => {
        const { data: status } = await api.get(`/screener/${job.job_id}`)
        if (status.status === 'completed' && status.results) {
          clearInterval(poll)
          setResults(status.results)
          setLoading(false)
        } else if (status.status === 'failed') {
          clearInterval(poll)
          setError(status.error_message || 'Error en el screener')
          setLoading(false)
        }
      }, 2000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al ejecutar screener')
      setLoading(false)
    }
  }

  const formatVal = (val: number | null, isPct: boolean) => {
    if (val === null || val === undefined) return '—'
    return isPct ? `${(val * 100).toFixed(1)}%` : val.toFixed(2)
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white mb-6">Stock Screener</h1>

      <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6 mb-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <select
            value={field}
            onChange={(e) => setField(e.target.value)}
            className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-2 text-white"
          >
            {FILTER_OPTIONS.map((f) => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </select>
          <select
            value={operator}
            onChange={(e) => setOperator(e.target.value)}
            className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-2 text-white"
          >
            <option value="lt">Menor que</option>
            <option value="gt">Mayor que</option>
            <option value="between">Entre</option>
            <option value="lte">Menor o igual</option>
            <option value="gte">Mayor o igual</option>
          </select>
          <input
            type="number"
            step="0.01"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={operator === 'between' ? 'Valor mínimo' : 'Valor'}
            className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
          <button
            onClick={addFilter}
            className="bg-[#2d3139] hover:bg-[#3d4149] text-white rounded-lg px-4 py-2 transition-colors"
          >
            Añadir filtro
          </button>
        </div>

        {filters.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {filters.map((f, i) => (
              <span
                key={i}
                className="bg-[#00cc88]/10 text-[#00cc88] border border-[#00cc88]/30 rounded-full px-3 py-1 text-sm flex items-center gap-2"
              >
                {f.field} {f.operator} {f.value}
                <button onClick={() => removeFilter(i)} className="hover:text-red-400 ml-1">×</button>
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-4">
          <div>
            <label className="text-sm text-gray-400 mr-2">Top N:</label>
            <input
              type="number"
              value={topN}
              onChange={(e) => setTopN(parseInt(e.target.value) || 25)}
              min={1}
              max={100}
              className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-3 py-2 text-white w-20"
            />
          </div>
          <button
            onClick={runScreener}
            disabled={loading || filters.length === 0}
            className="bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-6 py-2 transition-colors disabled:opacity-50"
          >
            {loading ? 'Ejecutando...' : 'Ejecutar Screener'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-400/10 border border-red-400/30 text-red-400 rounded-lg p-4 mb-6">
          {error}
        </div>
      )}

      {results.length > 0 && (
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2d3139] text-gray-400 text-left">
                  <th className="px-4 py-3">#</th>
                  <th className="px-4 py-3">Ticker</th>
                  <th className="px-4 py-3">Nombre</th>
                  <th className="px-4 py-3">Price</th>
                  <th className="px-4 py-3">PER</th>
                  <th className="px-4 py-3">P/B</th>
                  <th className="px-4 py-3">ROE</th>
                  <th className="px-4 py-3">FCF Yield</th>
                  <th className="px-4 py-3">D/E</th>
                  <th className="px-4 py-3">Score</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={r.ticker} className="border-b border-[#2d3139] hover:bg-[#1a1c23] text-white">
                    <td className="px-4 py-3 text-gray-500">{i + 1}</td>
                    <td className="px-4 py-3 font-semibold text-[#00cc88]">{r.ticker}</td>
                    <td className="px-4 py-3 text-gray-400 max-w-[200px] truncate">{r.name || '—'}</td>
                    <td className="px-4 py-3 font-mono">${r.price?.toFixed(2) || '—'}</td>
                    <td className="px-4 py-3">{formatVal(r.per, false)}</td>
                    <td className="px-4 py-3">{formatVal(r.pb, false)}</td>
                    <td className="px-4 py-3">{formatVal(r.roe, true)}</td>
                    <td className="px-4 py-3">{formatVal(r.fcf_yield, true)}</td>
                    <td className="px-4 py-3">{formatVal(r.debt_to_equity, false)}</td>
                    <td className="px-4 py-3 font-semibold">{r.score?.toFixed(4) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
