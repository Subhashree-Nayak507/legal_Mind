'use client'
import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/app/context/AuthContext'

// Fixed session id — same user always resumes the same conversation,
// even after page refresh. Scoped by user_id on the backend so two
// different users sharing "main" never collide.
const SESSION_ID = 'main'

type Message = { role: 'user' | 'assistant'; content: string; sources?: any[]; latency?: number; fromCache?: boolean }
type UploadedDoc = { doc_id: string; filename: string; chunk_count: number; uploaded_at: string }

const MOBILE_BREAKPOINT = 768

export default function Home() {
  const { isAuthed, loading: authLoading, logout } = useAuth()
  const router = useRouter()

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')
  const [docs, setDocs] = useState<UploadedDoc[]>([])
  const [isMobile, setIsMobile] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  useEffect(() => {
    if (!authLoading && !isAuthed) router.push('/login')
  }, [authLoading, isAuthed, router])

  // Load documents + chat history from backend on mount
  useEffect(() => {
    if (!isAuthed) return
    // Load previously uploaded documents for this user
    api.listDocuments().then(data => {
      setDocs(data.documents || [])
    }).catch(() => {})

    // Restore chat history so conversation survives page refresh
    api.getHistory(SESSION_ID).then(data => {
      const history: Message[] = (data.history || []).map((m: any) => ({
        role: m.role,
        content: m.content,
      }))
      setMessages(history)
    }).catch(() => {})
  }, [isAuthed])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  async function uploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg('')
    try {
      const data = await api.ingest(file)
      if (data.duplicate) {
        setUploadMsg(`ℹ️ ${data.filename} — already uploaded, using existing copy`)
      } else {
        setUploadMsg(`✓ ${data.filename} — ${data.child_chunks} chunks stored`)
      }
      // Refresh doc list from backend so it stays in sync
      const updated = await api.listDocuments()
      setDocs(updated.documents || [])
      if (isMobile) setSidebarOpen(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { logout(); router.push('/login'); return }
      setUploadMsg(`✗ ${err instanceof ApiError ? err.message : 'Upload failed. Is the backend running?'}`)
    }
    setUploading(false)
    e.target.value = ''
  }

  async function deleteDoc(docId: string) {
    setDeletingId(docId)
    try {
      await api.deleteDocument(docId)
      setDocs(prev => prev.filter(d => d.doc_id !== docId))
    } catch (err) {
      alert('Delete failed. Try again.')
    }
    setDeletingId(null)
  }

  async function sendMessage() {
    if (!input.trim() || loading) return
    const question = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setLoading(true)
    try {
      const data = await api.query(question, SESSION_ID)
      setMessages(prev => [...prev, {
        role: 'assistant', content: data.answer,
        sources: data.sources, latency: data.latency_ms, fromCache: data.from_cache,
      }])
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) { logout(); router.push('/login'); return }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err instanceof ApiError ? err.message : 'Connection error. Is the backend running?'}`,
      }])
    }
    setLoading(false)
  }

  if (authLoading || !isAuthed) return null

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0b1120', position: 'relative', overflow: 'hidden' }}>

      {isMobile && sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 20 }} />
      )}

      {/* ── LEFT PANEL — documents ── */}
      <div style={{
        width: isMobile ? '82vw' : 320, maxWidth: 320,
        flexShrink: 0, display: 'flex', flexDirection: 'column',
        borderRight: '1px solid #1e293b', background: '#0e1626',
        ...(isMobile ? {
          position: 'fixed', top: 0, left: 0, height: '100vh', zIndex: 21,
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.22s ease-out',
          boxShadow: sidebarOpen ? '8px 0 30px -8px rgba(0,0,0,0.5)' : 'none',
        } : {}),
      }}>
        {/* Brand */}
        <div style={{ padding: '22px 20px 16px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid #1e293b' }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 19, background: 'linear-gradient(135deg, #1d4ed8, #2563eb)', boxShadow: '0 6px 16px -4px rgba(37,99,235,0.5)' }}>⚖️</div>
          <div>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#f1f5f9', letterSpacing: '-0.02em' }}>LegalMind</h1>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#64748b' }}>Document Q&A</p>
          </div>
        </div>

        {/* Upload button */}
        <div style={{ padding: '16px 20px 12px' }}>
          <label style={{
            cursor: uploading ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            width: '100%', background: uploading ? '#16213a' : 'linear-gradient(135deg, #1d4ed8, #2563eb)',
            border: uploading ? '1px solid #243249' : 'none', borderRadius: 10, padding: '11px 0',
            fontSize: 13.5, fontWeight: 600, color: uploading ? '#94a3b8' : 'white', boxSizing: 'border-box',
            boxShadow: uploading ? 'none' : '0 6px 16px -4px rgba(37,99,235,0.5)',
          }}>
            {uploading ? (
              <><span className="typing-dot" /> <span className="typing-dot" /> <span className="typing-dot" />
                <span style={{ marginLeft: 4 }}>Uploading...</span></>
            ) : '+  Upload Document'}
            <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt,.md,.html,.csv,.json"
              onChange={uploadFile} style={{ display: 'none' }} disabled={uploading} />
          </label>
          {uploadMsg && (
            <p className="fade-in" style={{ margin: '10px 0 0', fontSize: 12.5,
              color: uploadMsg.startsWith('✓') ? '#4ade80' : uploadMsg.startsWith('ℹ') ? '#60a5fa' : '#f87171', lineHeight: 1.4 }}>
              {uploadMsg}
            </p>
          )}
          <p style={{ margin: '10px 0 0', fontSize: 11, color: '#475569' }}>PDF, DOCX, TXT, MD, HTML, CSV, JSON</p>
        </div>

        {/* Document list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 14px 16px' }}>
          <p style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '8px 6px 8px', fontWeight: 600 }}>
            Your Documents ({docs.length})
          </p>
          {docs.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#3f4a5e', marginTop: 40, padding: '0 12px' }}>
              <div style={{ fontSize: 30 }}>🗂️</div>
              <p style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.5 }}>No documents yet. Upload one to start asking questions.</p>
            </div>
          ) : (
            docs.map((d) => (
              <div key={d.doc_id} className="fade-in" style={{
                background: '#16213a', border: '1px solid #243249', borderRadius: 10,
                padding: '10px 12px', marginBottom: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ fontSize: 15 }}>📄</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ margin: 0, fontSize: 13, color: '#e2e8f0', fontWeight: 500,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.filename}
                    </p>
                    <p style={{ margin: '3px 0 0', fontSize: 11, color: '#64748b' }}>
                      {d.chunk_count} chunks
                    </p>
                    <p style={{ margin: '2px 0 0', fontSize: 10.5, color: '#475569' }}>
                      {new Date(d.uploaded_at).toLocaleDateString()}
                    </p>
                  </div>
                  {/* Delete button */}
                  <button
                    onClick={() => deleteDoc(d.doc_id)}
                    disabled={deletingId === d.doc_id}
                    title="Delete document"
                    style={{
                      background: 'transparent', border: 'none', cursor: deletingId === d.doc_id ? 'default' : 'pointer',
                      color: '#475569', fontSize: 14, padding: '2px 4px', borderRadius: 4, flexShrink: 0,
                      opacity: deletingId === d.doc_id ? 0.4 : 1,
                    }}>
                    🗑️
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Logout */}
        <div style={{ padding: '14px 20px', borderTop: '1px solid #1e293b' }}>
          <button onClick={() => { logout(); router.push('/login') }}
            style={{ width: '100%', background: 'transparent', border: '1px solid #243249', borderRadius: 9,
              padding: '9px 0', color: '#94a3b8', fontSize: 13, cursor: 'pointer' }}>
            Logout
          </button>
        </div>
      </div>

      {/* ── RIGHT PANEL — chat ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
        background: 'radial-gradient(circle at 85% 0%, #1e3a8a14, transparent 40%)' }}>
        {/* Header */}
        <div style={{ padding: isMobile ? '16px 18px' : '20px 32px', borderBottom: '1px solid #1e293b',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            {isMobile && (
              <button onClick={() => setSidebarOpen(true)} aria-label="Open documents"
                style={{ background: '#16213a', border: '1px solid #243249', borderRadius: 9,
                  width: 36, height: 36, flexShrink: 0, color: '#e2e8f0', fontSize: 16, cursor: 'pointer' }}>☰</button>
            )}
            <div style={{ minWidth: 0 }}>
              <h2 style={{ margin: 0, fontSize: isMobile ? 15 : 16, fontWeight: 600, color: '#f1f5f9' }}>Ask a question</h2>
              <p style={{ margin: '2px 0 0', fontSize: 12, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {docs.length > 0 ? `Querying across ${docs.length} document${docs.length > 1 ? 's' : ''}` : 'Upload a document to begin'}
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '18px 18px' : '24px 32px' }}>
          {messages.length === 0 && (
            <div className="fade-in" style={{ textAlign: 'center', color: '#475569', marginTop: isMobile ? 50 : 90 }}>
              <div style={{ fontSize: 44, animation: 'pulseGlow 2.5s infinite' }}>💬</div>
              <p style={{ marginTop: 14, fontSize: 14.5 }}>Ask anything about the documents you've uploaded.</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className="fade-in" style={{ marginBottom: 18, display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, maxWidth: isMobile ? '92%' : '78%', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                <div style={{ width: 26, height: 26, borderRadius: 8, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 13, background: msg.role === 'user' ? '#334155' : 'linear-gradient(135deg, #1d4ed8, #2563eb)' }}>
                  {msg.role === 'user' ? '🧑' : '⚖️'}
                </div>
                <div style={{
                  background: msg.role === 'user' ? 'linear-gradient(135deg, #1d4ed8, #2563eb)' : '#16213a',
                  border: msg.role === 'user' ? 'none' : '1px solid #243249',
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                  padding: '11px 15px', fontSize: 14.5, lineHeight: 1.6,
                  boxShadow: msg.role === 'user' ? '0 4px 14px -4px rgba(37,99,235,0.4)' : 'none',
                }}>
                  {msg.content}
                </div>
              </div>
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div style={{ marginTop: 8, paddingLeft: 34, maxWidth: isMobile ? '92%' : '78%' }}>
                  {msg.sources.map((s, si) => (
                    <div key={si} style={{ fontSize: 11, color: '#7c8aa3', background: '#0e1626',
                      border: '1px solid #1e293b', borderRadius: 6, padding: '4px 9px', marginBottom: 4, display: 'inline-block', marginRight: 6 }}>
                      📎 {s.filename} · chunk {s.chunk_index} · score {s.score}
                    </div>
                  ))}
                  <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
                    {msg.latency}ms {msg.fromCache && '· cached'}
                  </div>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="fade-in" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 26, height: 26, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, background: 'linear-gradient(135deg, #1d4ed8, #2563eb)' }}>⚖️</div>
              <div style={{ background: '#16213a', border: '1px solid #243249', borderRadius: '16px 16px 16px 4px', padding: '13px 16px', display: 'flex', gap: 4 }}>
                <span className="typing-dot" /> <span className="typing-dot" /> <span className="typing-dot" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ padding: isMobile ? '14px 18px 18px' : '16px 32px 22px', borderTop: '1px solid #1e293b', display: 'flex', gap: 10 }}>
          <input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
            placeholder="Ask a question about your document..."
            style={{ flex: 1, background: '#16213a', border: '1px solid #243249', borderRadius: 11,
              padding: '12px 16px', color: '#e2e8f0', fontSize: 14.5, outline: 'none' }}
            disabled={loading} />
          <button onClick={sendMessage} disabled={loading || !input.trim()}
            style={{ background: 'linear-gradient(135deg, #1d4ed8, #2563eb)', border: 'none', borderRadius: 11, padding: '12px 22px',
              color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer',
              opacity: loading || !input.trim() ? 0.5 : 1,
              boxShadow: loading || !input.trim() ? 'none' : '0 6px 16px -4px rgba(37,99,235,0.5)' }}>
            Send
          </button>
        </div>
      </div>
    </div>
  )
}