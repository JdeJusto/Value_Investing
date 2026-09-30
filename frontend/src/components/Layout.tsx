import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/useAuth'
import { LayoutDashboard, Search, Building2, Briefcase, Bell, LogOut } from 'lucide-react'

export default function Layout() {
  const { user, logout } = useAuth()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
      isActive
        ? 'bg-[#00cc88]/10 text-[#00cc88]'
        : 'text-gray-400 hover:text-white hover:bg-[#1a1c23]'
    }`

  return (
    <div className="flex h-screen">
      <aside className="w-64 bg-[#0d1117] border-r border-[#2d3139] flex flex-col">
        <div className="p-6 border-b border-[#2d3139]">
          <h1 className="text-xl font-bold text-white">
            <span className="text-[#00cc88]">ValueInvest</span> Pro
          </h1>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          <NavLink to="/" end className={linkClass}>
            <LayoutDashboard size={20} /> Dashboard
          </NavLink>
          <NavLink to="/screener" className={linkClass}>
            <Search size={20} /> Screener
          </NavLink>
          <NavLink to="/companies" className={linkClass}>
            <Building2 size={20} /> Companies
          </NavLink>
          <NavLink to="/portfolios" className={linkClass}>
            <Briefcase size={20} /> Portfolios
          </NavLink>
          <NavLink to="/alerts" className={linkClass}>
            <Bell size={20} /> Alerts
          </NavLink>
        </nav>
        <div className="p-4 border-t border-[#2d3139]">
          <div className="text-sm text-gray-400 mb-3">{user?.email}</div>
          <button
            onClick={logout}
            className="flex items-center gap-2 text-gray-400 hover:text-red-400 transition-colors text-sm"
          >
            <LogOut size={16} /> Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-[#0e1117]">
        <Outlet />
      </main>
    </div>
  )
}
