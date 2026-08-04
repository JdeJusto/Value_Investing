import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import type { Company } from '../types'

export default function CompaniesPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Company[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const navigate = useNavigate()

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const { data } = await api.get('/companies/search', { params: { q: query, limit: 30 } })
      setResults(data)
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white mb-6">Empresas</h1>

      <div className="flex gap-3 mb-8">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="flex-1 bg-[#161b22] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-[#00cc88]"
          placeholder="Buscar por nombre o ticker (ej: AAPL, Microsoft)"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-6 py-3 transition-colors disabled:opacity-50"
        >
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </div>

      {searched && !loading && results.length === 0 && (
        <div className="text-gray-500 text-center py-12">No se encontraron empresas</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.map((c) => (
          <div
            key={c.ticker}
            onClick={() => navigate(`/companies/${c.ticker}`)}
            className="bg-[#161b22] rounded-xl border border-[#2d3139] p-5 cursor-pointer hover:border-[#00cc88] transition-colors"
          >
            <div className="flex justify-between items-start mb-2">
              <div>
                <span className="text-white font-semibold">{c.ticker}</span>
                <span className="text-gray-400 text-sm ml-2">{c.exchange}</span>
              </div>
              {c.price && <span className="text-[#00cc88] font-mono">${c.price.toFixed(2)}</span>}
            </div>
            <div className="text-gray-400 text-sm truncate">{c.name || c.ticker}</div>
            {c.sector && <div className="text-gray-500 text-xs mt-1">{c.sector}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}
