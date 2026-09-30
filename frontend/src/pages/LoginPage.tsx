import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/useAuth'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/')
    } catch {
      setError('Email o contraseña inválidos')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0e1117]">
      <div className="w-full max-w-md bg-[#161b22] rounded-2xl border border-[#2d3139] p-8">
        <h1 className="text-2xl font-bold text-white mb-2">
          <span className="text-[#00cc88]">ValueInvest</span> Pro
        </h1>
        <p className="text-gray-400 mb-8">Inicia sesión para acceder a tu cuenta</p>

        {error && (
          <div className="bg-red-400/10 border border-red-400/30 text-red-400 rounded-lg p-3 mb-4 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-[#00cc88]"
              placeholder="tu@email.com"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Contraseña</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-[#00cc88]"
              placeholder="••••••••"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-3 transition-colors disabled:opacity-50"
          >
            {loading ? 'Iniciando sesión...' : 'Iniciar sesión'}
          </button>
        </form>

        <p className="text-center text-gray-500 mt-6 text-sm">
          ¿No tienes cuenta?{' '}
          <Link to="/register" className="text-[#00cc88] hover:underline">
            Regístrate
          </Link>
        </p>
      </div>
    </div>
  )
}
