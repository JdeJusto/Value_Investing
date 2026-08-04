import { useEffect, useState } from 'react'
import api from '../services/api'
import type { Alert } from '../types'
import { Plus, Trash2, BellOff, Bell } from 'lucide-react'

const METRIC_OPTIONS = ['roe', 'pb', 'fcf_yield', 'roic', 'ev_ebit', 'debt_to_equity', 'piotroski_fscore', 'price', 'score']

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [ticker, setTicker] = useState('')
  const [metric, setMetric] = useState('roe')
  const [operator, setOperator] = useState('gt')
  const [threshold, setThreshold] = useState('')

  useEffect(() => {
    loadAlerts()
  }, [])

  const loadAlerts = async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/alerts')
      setAlerts(data)
    } catch { /* ignore */ }
    setLoading(false)
  }

  const createAlert = async () => {
    if (!ticker.trim() || !threshold) return
    try {
      await api.post('/alerts', {
        ticker: ticker.toUpperCase(),
        metric_name: metric,
        operator,
        threshold: parseFloat(threshold),
      })
      setTicker('')
      setThreshold('')
      setShowCreate(false)
      loadAlerts()
    } catch { /* ignore */ }
  }

  const toggleAlert = async (a: Alert) => {
    try {
      await api.put(`/alerts/${a.id}/toggle`)
      loadAlerts()
    } catch { /* ignore */ }
  }

  const deleteAlert = async (id: number) => {
    try {
      await api.delete(`/alerts/${id}`)
      loadAlerts()
    } catch { /* ignore */ }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Alertas</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-2 transition-colors"
        >
          <Plus size={18} /> Nueva Alerta
        </button>
      </div>

      {showCreate && (
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">Crear Alerta</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500"
              placeholder="Ticker (ej: AAPL)"
            />
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-2 text-white"
            >
              {METRIC_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <select
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-2 text-white"
            >
              <option value="gt">Mayor que</option>
              <option value="lt">Menor que</option>
              <option value="gte">Mayor o igual</option>
              <option value="lte">Menor o igual</option>
            </select>
            <input
              type="number"
              step="0.01"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className="bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500"
              placeholder="Valor umbral"
            />
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={createAlert} className="bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-2 transition-colors">Crear</button>
            <button onClick={() => setShowCreate(false)} className="bg-[#2d3139] hover:bg-[#3d4149] text-white rounded-lg px-4 py-2 transition-colors">Cancelar</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-center py-12">Cargando...</div>
      ) : alerts.length === 0 ? (
        <div className="text-gray-500 text-center py-12">No tienes alertas configuradas</div>
      ) : (
        <div className="space-y-3">
          {alerts.map((a) => (
            <div key={a.id} className="bg-[#161b22] rounded-xl border border-[#2d3139] p-5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-white font-semibold">{a.ticker}</span>
                <span className="text-gray-400 text-sm">
                  {a.metric_name} {a.operator} {a.threshold}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => toggleAlert(a)} className="text-gray-500 hover:text-white transition-colors">
                  {a.is_active ? <Bell size={18} className="text-[#00cc88]" /> : <BellOff size={18} />}
                </button>
                <button onClick={() => deleteAlert(a.id)} className="text-gray-500 hover:text-red-400 transition-colors">
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
