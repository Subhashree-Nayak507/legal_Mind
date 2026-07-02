'use client'
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { getToken, clearToken } from '@/lib/api'

type AuthContextType = {
  isAuthed: boolean
  loading: boolean
  setAuthed: (v: boolean) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthed, setIsAuthed] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // On first load, check if a token already exists from a previous session
    setIsAuthed(!!getToken())
    setLoading(false)
  }, [])

  function logout() {
    clearToken()
    setIsAuthed(false)
  }

  return (
    <AuthContext.Provider value={{ isAuthed, loading, setAuthed: setIsAuthed, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
