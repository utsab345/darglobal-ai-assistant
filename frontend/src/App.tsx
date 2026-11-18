import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

type SourceItem = {
  title: string
  url: string
  source: 'dar_global' | 'wasalt' | 'unknown'
  snippet?: string
  score?: number
  metadata?: Record<string, unknown>
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceItem[]
  model?: string | null
}

type ChatResponse = {
  answer: string
  sources: SourceItem[]
  model?: string | null
  retrieved_count: number
}

type Stats = {
  scrape?: { results?: Array<Record<string, unknown>> }
  knowledge_base?: Record<string, unknown>
}

const configuredApiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const API_BASE = configuredApiBase || (import.meta.env.DEV ? 'http://localhost:8000' : '')
const SUGGESTIONS = [
  'What properties does DarGlobal offer?',
  'Which projects are available in Saudi Arabia?',
  'Tell me about DarGlobal developments in Dubai.',
  'What amenities are offered in a particular project?',
  'What information is available about properties on Wasalt?',
  'Compare relevant projects from the collected data.'
]

function sourceLabel(s: SourceItem['source']) {
  if (s === 'dar_global') return 'DarGlobal'
  if (s === 'wasalt') return 'Wasalt'
  return 'Unknown'
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState<'all' | 'dar_global' | 'wasalt'>('all')
  const [stats, setStats] = useState<Stats | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => { void fetchStats() }, [])

  async function fetchStats() {
    try {
      const r = await fetch(`${API_BASE}/api/stats`)
      if (r.ok) setStats(await r.json())
    } catch {}
  }

  const kbSummary = useMemo(() => {
    const kb = stats?.knowledge_base as any
    if (!kb) return null
    return `${kb.unique_documents ?? 0} docs, ${kb.chunks ?? 0} chunks (DarGlobal ${kb.sources?.dar_global ?? 0}, Wasalt ${kb.sources?.wasalt ?? 0})`
  }, [stats])

  async function sendMessage(text: string) {
    const q = text.trim()
    if (!q || loading) return
    setError(null)
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: q }
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(prev => [...prev, userMsg])
    setQuestion('')
    setLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, conversation_history: history, source_filter: sourceFilter })
      })
      if (!resp.ok) throw new Error(await resp.text() || `Request failed (${resp.status})`)
      const data = (await resp.json()) as ChatResponse
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: data.answer, sources: data.sources || [], model: data.model }])
    } catch (e: any) {
      setError(e?.message || 'Failed to get response')
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: 'I could not complete that request right now. Please try again in a moment.' }])
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void sendMessage(question)
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_rgba(176,141,87,0.18),_transparent_45%),linear-gradient(180deg,#0f0d0b_0%,#15120f_40%,#0f0d0b_100%)] text-stone-100">
      <div className="max-w-7xl mx-auto px-4 py-6 md:py-10">
        <header className="mb-6 md:mb-8 rounded-2xl border border-stone-800/80 bg-stone-950/40 backdrop-blur p-5 md:p-7 shadow-glow">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
            <div>
              <p className="text-xs tracking-[0.25em] uppercase text-brand-500 mb-2">DarGlobal × Wasalt</p>
              <h1 className="text-2xl md:text-4xl font-semibold leading-tight">Applied AI Property Intelligence Assistant</h1>
              <p className="mt-2 text-stone-300 max-w-3xl">Premium real-estate chatbot grounded in publicly collected website information from DarGlobal and Wasalt, with source citations and retrieval-based responses.</p>
            </div>
            <div className="text-sm text-stone-300 bg-stone-900/70 border border-stone-800 rounded-xl p-3 min-w-[260px]">
              <div className="font-medium text-stone-100 mb-1">Knowledge Base</div>
              <div>{kbSummary || 'Loading stats...'}</div>
              <div className="mt-1 text-xs text-stone-400">Source filter: {sourceFilter === 'all' ? 'All sources' : sourceLabel(sourceFilter as any)}</div>
            </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-[340px_1fr] gap-6">
          <aside className="space-y-4">
            <section className="rounded-2xl border border-stone-800 bg-stone-950/50 p-4 md:p-5">
              <h2 className="font-semibold text-lg mb-3">Source Selection</h2>
              <div className="grid grid-cols-3 gap-2">
                {([
                  ['all', 'All'],
                  ['dar_global', 'DarGlobal'],
                  ['wasalt', 'Wasalt'],
                ] as const).map(([val, label]) => (
                  <button key={val} onClick={() => setSourceFilter(val)} className={`rounded-lg px-3 py-2 text-sm border transition ${sourceFilter===val ? 'bg-brand-500/20 border-brand-500 text-brand-100' : 'bg-stone-900 border-stone-700 text-stone-300 hover:border-stone-500'}`}>{label}</button>
                ))}
              </div>
              <p className="text-xs text-stone-400 mt-3">Use filters to focus retrieval on DarGlobal, Wasalt, or all collected sources.</p>
            </section>

            <section className="rounded-2xl border border-stone-800 bg-stone-950/50 p-4 md:p-5">
              <h2 className="font-semibold text-lg mb-3">Suggested Questions</h2>
              <div className="space-y-2">
                {SUGGESTIONS.map(s => (
                  <button key={s} onClick={() => void sendMessage(s)} className="w-full text-left text-sm rounded-lg border border-stone-700 bg-stone-900/70 hover:border-brand-500/60 hover:bg-stone-900 px-3 py-2 transition">{s}</button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-stone-800 bg-stone-950/50 p-4 md:p-5">
              <h2 className="font-semibold text-lg mb-2">About Data Sources</h2>
              <ul className="text-sm text-stone-300 space-y-2 list-disc pl-5">
                <li>Public pages collected from <span className="text-brand-100">darglobal.co.uk</span> and <span className="text-brand-100">wasalt.sa</span>.</li>
                <li>Responses are retrieval-augmented and cite source URLs from the collected dataset.</li>
                <li>If data is unavailable, the assistant states that verified information was not found.</li>
                <li>DarGlobal live access may be limited by anti-bot protections; coverage depends on accessible pages.</li>
              </ul>
            </section>
          </aside>

          <main className="rounded-2xl border border-stone-800 bg-stone-950/50 overflow-hidden flex flex-col min-h-[70vh]">
            <div className="px-4 md:px-6 py-4 border-b border-stone-800 flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold text-lg">Chat Assistant</h2>
                <p className="text-xs text-stone-400">Ask about projects, locations, available collected information, and source-specific details.</p>
              </div>
              <button onClick={() => { setMessages([]); setError(null) }} className="text-sm px-3 py-2 rounded-lg border border-stone-700 hover:border-stone-500 bg-stone-900">Clear chat</button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
              {messages.length === 0 && (
                <div className="rounded-xl border border-dashed border-stone-700 bg-stone-900/40 p-5 text-stone-300">
                  Start by asking a question about DarGlobal or Wasalt. Answers will include retrieved source citations when available.
                </div>
              )}
              {messages.map(m => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[95%] md:max-w-[85%] rounded-2xl px-4 py-3 border ${m.role === 'user' ? 'bg-brand-500/20 border-brand-500/40 text-brand-50' : 'bg-stone-900/80 border-stone-700 text-stone-100'}`}>
                    <div className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</div>
                    {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-stone-700/70">
                        <div className="text-xs uppercase tracking-wide text-stone-400 mb-2">Sources</div>
                        <div className="space-y-2">
                          {m.sources.map((s, i) => (
                            <a key={`${m.id}-${i}-${s.url}`} href={s.url} target="_blank" rel="noreferrer" className="block rounded-lg border border-stone-700 hover:border-brand-500/50 bg-stone-950/60 p-2.5">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-sm font-medium text-stone-100 line-clamp-1">{s.title || s.url}</div>
                                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${s.source==='dar_global'?'border-amber-500/40 text-amber-200':s.source==='wasalt'?'border-emerald-500/40 text-emerald-200':'border-stone-600 text-stone-300'}`}>{sourceLabel(s.source)}</span>
                              </div>
                              <div className="text-xs text-stone-400 mt-1 break-all">{s.url}</div>
                              {s.snippet && <div className="text-xs text-stone-300 mt-1 line-clamp-2">{s.snippet}</div>}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                    {m.role === 'assistant' && m.model && <div className="mt-2 text-[11px] text-stone-500">Model: {m.model}</div>}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start"><div className="rounded-2xl px-4 py-3 border border-stone-700 bg-stone-900/80 text-stone-300 text-sm">Retrieving sources and generating response...</div></div>
              )}
              {error && <div className="rounded-lg border border-red-900/50 bg-red-950/30 text-red-200 px-3 py-2 text-sm">{error}</div>}
              <div ref={endRef} />
            </div>

            <form onSubmit={onSubmit} className="border-t border-stone-800 p-4 md:p-5 bg-stone-950/70">
              <div className="flex flex-col md:flex-row gap-3">
                <textarea value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask a question about DarGlobal or Wasalt..." rows={2} className="flex-1 resize-none rounded-xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500/60" />
                <button disabled={loading || !question.trim()} className="md:w-40 rounded-xl px-4 py-3 font-medium bg-brand-500 text-stone-950 hover:bg-brand-100 disabled:opacity-50 disabled:cursor-not-allowed transition">Send</button>
              </div>
              <p className="mt-2 text-xs text-stone-500">Responses use only retrieved website information from the collected dataset and may be incomplete depending on scraping coverage.</p>
            </form>
          </main>
        </div>
      </div>
    </div>
  )
}
