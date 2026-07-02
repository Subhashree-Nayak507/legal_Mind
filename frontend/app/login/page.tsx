'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/app/context/AuthContext'

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { setAuthed } = useAuth()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        await api.login(email, password)
      } else {
        await api.register(email, password, name || undefined)
      }
      setAuthed(true)
      router.push('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Is the backend running?')
    }
    setLoading(false)
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', padding: '24px 16px',
      background: 'radial-gradient(circle at 20% 20%, #1e3a8a22, transparent 50%), radial-gradient(circle at 80% 80%, #1d4ed822, transparent 50%), #0b1120',
    }}>
      <div className="fade-in" style={{
        width: '100%', maxWidth: 380,
        background: 'linear-gradient(180deg, #16213a 0%, #131c30 100%)',
        border: '1px solid #243249', borderRadius: 18, padding: '32px 28px',
        boxShadow: '0 20px 60px -10px rgba(0,0,0,0.5)',
      }}>
        {/* Logo */}
        <div style={{
          width: 46, height: 46, borderRadius: 12, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 22, marginBottom: 14,
          background: 'linear-gradient(135deg, #1d4ed8, #2563eb)',
          boxShadow: '0 8px 20px -4px rgba(37,99,235,0.5)',
        }}>⚖️</div>

        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#f1f5f9', letterSpacing: '-0.02em' }}>LegalMind</h1>
        <p style={{ margin: '6px 0 24px', fontSize: 13.5, color: '#64748b' }}>
          {mode === 'login' ? 'Sign in to your account' : 'Create an account to get started'}
        </p>

        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {mode === 'register' && (
            <input
              placeholder="Name (optional)"
              value={name}
              onChange={e => setName(e.target.value)}
              style={inputStyle}
            />
          )}
          <input
            type="email"
            placeholder="Email address"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            style={inputStyle}
            autoComplete="email"
          />
          <input
            type="password"
            placeholder="Password (min 8 characters)"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={8}
            style={inputStyle}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          {error && (
            <div style={{
              fontSize: 13, color: '#f87171', background: '#2d1a1a',
              border: '1px solid #7f1d1d', borderRadius: 8, padding: '9px 12px', lineHeight: 1.4,
            }}>{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', background: 'linear-gradient(135deg, #1d4ed8, #2563eb)',
              border: 'none', borderRadius: 10, padding: '13px 0',
              color: 'white', fontSize: 14, fontWeight: 600,
              cursor: loading ? 'default' : 'pointer',
              opacity: loading ? 0.6 : 1, marginTop: 4,
              boxShadow: '0 6px 18px -6px rgba(37,99,235,0.5)',
              transition: 'opacity 0.15s',
            }}>
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <p style={{ textAlign: 'center', fontSize: 13, color: '#64748b', marginTop: 20, marginBottom: 0 }}>
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <span
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            style={{ color: '#60a5fa', cursor: 'pointer', fontWeight: 500 }}>
            {mode === 'login' ? 'Register' : 'Sign in'}
          </span>
        </p>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', background: '#0b1120', border: '1px solid #243249', borderRadius: 9,
  padding: '11px 13px', color: '#e2e8f0', fontSize: 14, outline: 'none',
  transition: 'border-color 0.15s',
}