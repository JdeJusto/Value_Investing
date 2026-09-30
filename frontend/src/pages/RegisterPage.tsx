import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/useAuth'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { register } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres')
      return
    }
    setLoading(true)
    try {
      await register(email, password, displayName || undefined)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al registrarse')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0e1117]">
      <div className="w-full max-w-md bg-[#161b22] rounded-2xl border border-[#2d3139] p-8">
        <h1 className="text-2xl font-bold text-white mb-2">
          Crear cuenta en <span className="text-[#00cc88]">ValueInvest</span> Pro
        </h1>
        <p className="text-gray-400 mb-8">Regístrate para empezar a analizar empresas</p>

        {error && (
          <div className="bg-red-400/10 border border-red-400/30 text-red-400 rounded-lg p-3 mb-4 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Nombre (opcional)</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#2d3139] rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-[#00cc88]"
              placeholder="Tu nombre"
            />
          </div>
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
              placeholder="Mínimo 8 caracteres"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#00cc88] hover:bg-[#00aa66] text-black font-semibold rounded-lg px-4 py-3 transition-colors disabled:opacity-50"
          >
            {loading ? 'Creando cuenta...' : 'Crear cuenta'}
          </button>
        </form>

        <p className="text-center text-gray-500 mt-6 text-sm">
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="text-[#00cc88] hover:underline">
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  )
}
