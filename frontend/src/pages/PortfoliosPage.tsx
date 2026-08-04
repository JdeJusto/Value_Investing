import { useEffect, useState } from 'react'
import api from '../services/api'
import type { Portfolio } from '../types'
import { Plus, Trash2 } from 'lucide-react'

export default function PortfoliosPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  useEffect(() => {
    loadPortfolios()
  }, [])

  const loadPortfolios = async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/portfolios')
      setPortfolios(data)
    } catch { /* ignore */ }
    setLoading(false)
  }

  const createPortfolio = async () => {
    if (!newName.trim()) return
    try {
      await api.post('/portfolios', { name: newName, description: newDesc || undefined })
      setNewName('')
      setNewDesc('')
      setShowCreate(false)
      loadPortfolios()
    } catch { /* ignore */ }
  }

  const deletePortfolio = async (id: number) => {
    if (!confirm('¿Eliminar esta cartera?')) return
    try {
      await api.delete(`/portfolios/${id}`)
      loadPortfolios()
    } catch { /* ignore */ }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Carteras</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-2 transition-colors"
        >
          <Plus size={18} /> Nueva Cartera
        </button>
      </div>

      {showCreate && (
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">Crear Cartera</h2>
          <div className="space-y-3">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500"
              placeholder="Nombre de la cartera"
            />
            <input
              type="text"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500"
              placeholder="Descripción (opcional)"
            />
            <div className="flex gap-3">
              <button
                onClick={createPortfolio}
                className="bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-2 transition-colors"
              >
                Crear
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="bg-[#2d3139] hover:bg-[#3d4149] text-white rounded-lg px-4 py-2 transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-center py-12">Cargando...</div>
      ) : portfolios.length === 0 ? (
        <div className="text-gray-500 text-center py-12">
          No tienes carteras. ¡Crea una!
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {portfolios.map((p) => (
            <div key={p.id} className="bg-[#161b22] rounded-xl border border-[#2d3139] p-5">
              <div className="flex justify-between items-start mb-3">
                <h3 className="text-white font-semibold">{p.name}</h3>
                <button
                  onClick={() => deletePortfolio(p.id)}
                  className="text-gray-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {p.description && <p className="text-gray-400 text-sm mb-3">{p.description}</p>}
              <div className="text-[#00cc88] text-sm">{p.ticker_count} posiciones</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
