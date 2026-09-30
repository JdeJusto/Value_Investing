import { createContext, useContext } from 'react'
import type { User } from '../types'

export interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | undefined>(undefined)

// eslint-disable-next-line react-refresh/only-export-components -- hooks and
// contexts are not components; this module intentionally has no components so
// fast refresh works for the provider in ./AuthContext.tsx.
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
