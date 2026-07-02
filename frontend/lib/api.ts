
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

const TOKEN_KEY = 'legalmind_token'
const TOKEN_MAX_AGE_DAYS = 1 

export function getToken(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${TOKEN_KEY}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function setToken(token: string) {
  if (typeof document === 'undefined') return
  const maxAge = TOKEN_MAX_AGE_DAYS * 24 * 60 * 60
  document.cookie = `${TOKEN_KEY}=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; SameSite=Lax`
}

export function clearToken() {
  if (typeof document === 'undefined') return
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0; SameSite=Lax`
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle(res: Response) {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  async register(email: string, password: string, name?: string) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    })
    const data = await handle(res)
    setToken(data.access_token)
    return data
  },

  async login(email: string, password: string) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await handle(res)
    setToken(data.access_token)
    return data
  },

  logout() {
    clearToken()
  },

  async query(question: string, sessionId: string) {
    const res = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ question, session_id: sessionId }),
    })
    return handle(res)
  },

  async ingest(file: File) {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    })
    return handle(res)
  },
  
  async listDocuments() {
    const res = await fetch(`${API_BASE}/documents`, {
      headers: { ...authHeaders() },
    })
    return handle(res)
  },
 
  async deleteDocument(docId: string) {
    const res = await fetch(`${API_BASE}/documents/${docId}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    })
    return handle(res)
  },
 
  async getHistory(sessionId: string = 'main') {
    const res = await fetch(`${API_BASE}/history?session_id=${sessionId}`, {
      headers: { ...authHeaders() },
    })
    return handle(res)
  }

}
