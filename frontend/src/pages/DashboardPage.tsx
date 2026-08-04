import { useAuth } from '../store/AuthContext'

export default function DashboardPage() {
  const { user } = useAuth()

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
      <p className="text-gray-400 mb-8">Bienvenido, {user?.display_name || user?.email}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6">
          <div className="text-gray-400 text-sm mb-1">Empresas en Watchlist</div>
          <div className="text-2xl font-bold text-white">0</div>
        </div>
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6">
          <div className="text-gray-400 text-sm mb-1">Carteras Activas</div>
          <div className="text-2xl font-bold text-white">0</div>
        </div>
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6">
          <div className="text-gray-400 text-sm mb-1">Alertas Configuradas</div>
          <div className="text-2xl font-bold text-white">0</div>
        </div>
        <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-6">
          <div className="text-gray-400 text-sm mb-1">Screener Ejecutados</div>
          <div className="text-2xl font-bold text-white">0</div>
        </div>
      </div>

      <div className="bg-[#161b22] rounded-xl border border-[#2d3139] p-8">
        <h2 className="text-lg font-semibold text-white mb-4">Acceso Rápido</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="/screener"
            className="bg-[#0d1117] rounded-lg border border-[#2d3139] p-6 hover:border-[#00cc88] transition-colors group"
          >
            <div className="text-[#00cc88] group-hover:text-white text-lg font-semibold mb-2">Screener</div>
            <p className="text-gray-500 text-sm">Filtra empresas por métricas fundamentales</p>
          </a>
          <a
            href="/companies"
            className="bg-[#0d1117] rounded-lg border border-[#2d3139] p-6 hover:border-[#00cc88] transition-colors group"
          >
            <div className="text-[#00cc88] group-hover:text-white text-lg font-semibold mb-2">Empresas</div>
            <p className="text-gray-500 text-sm">Busca y analiza empresas en detalle</p>
          </a>
          <a
            href="/portfolios"
            className="bg-[#0d1117] rounded-lg border border-[#2d3139] p-6 hover:border-[#00cc88] transition-colors group"
          >
            <div className="text-[#00cc88] group-hover:text-white text-lg font-semibold mb-2">Carteras</div>
            <p className="text-gray-500 text-sm">Gestiona tus carteras virtuales</p>
          </a>
        </div>
      </div>
    </div>
  )
}
