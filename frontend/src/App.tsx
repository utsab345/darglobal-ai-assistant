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
  retrievedCount?: number
  notice?: string | null
}

type ChatResponse = {
  answer: string
  sources: SourceItem[]
  model?: string | null
  retrieved_count: number
  degraded?: boolean
  notice?: string | null
}

type Stats = {
  knowledge_base?: Record<string, unknown>
  scrape?: { results?: Array<Record<string, unknown>> }
}

const configuredApiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const API_BASE = configuredApiBase || (import.meta.env.DEV ? 'http://localhost:8000' : '')

const SUGGESTIONS = [
  'What properties does DarGlobal offer?',
  'Which DarGlobal projects are in the collected data?',
  'What information is available about Wasalt properties?',
  'Show project details and locations found in the dataset.',
  'Compare DarGlobal and Wasalt information from collected pages.',
]

function sourceLabel(s: SourceItem['source']) {
  if (s === 'dar_global') return 'DarGlobal'
  if (s === 'wasalt') return 'Wasalt'
  return 'Source'
}

function formatKbSummary(stats: Stats | null) {
  const kb = stats?.knowledge_base as any
  if (!kb) return 'Loading dataset information...'
  const docs = kb.unique_documents ?? kb.documents ?? 0
  const chunks = kb.chunks ?? 0
  const dg = kb.sources?.dar_global ?? 0
  const wa = kb.sources?.wasalt ?? 0
  return `${docs} documents, ${chunks} chunks (DarGlobal ${dg}, Wasalt ${wa})`
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState<'all' | 'dar_global' | 'wasalt'>('all')
  const [stats, setStats] = useState<Stats | null>(null)
  const [health, setHealth] = useState<{ status?: string; knowledge_base_ready?: boolean } | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    void fetchStats()
    void fetchHealth()
  }, [])

  useEffect(() => {
    const saved = localStorage.getItem('theme')
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
    const isDark = saved ? saved === 'dark' : prefersDark
    setDarkMode(isDark)
    document.documentElement.classList.toggle('dark', isDark)
  }, [])

  function toggleTheme() {
    setDarkMode((prev) => {
      const next = !prev
      document.documentElement.classList.toggle('dark', next)
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return next
    })
  }

  async function fetchStats() {
    try {
      const r = await fetch(`${API_BASE}/api/stats`)
      if (r.ok) setStats(await r.json())
    } catch {}
  }

  async function fetchHealth() {
    try {
      const r = await fetch(`${API_BASE}/health`)
      if (r.ok) setHealth(await r.json())
    } catch {}
  }

  const kbSummary = useMemo(() => formatKbSummary(stats), [stats])

  async function sendMessage(text: string) {
    const q = text.trim()
    if (!q || loading) return
    setError(null)

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: q }
    const history = messages.map((m) => ({ role: m.role, content: m.content }))
    setMessages((prev) => [...prev, userMsg])
    setQuestion('')
    setLoading(true)

    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          conversation_history: history,
          source_filter: sourceFilter,
        }),
      })

      if (!resp.ok) {
        const msg = await resp.text()
        throw new Error(msg || `Request failed (${resp.status})`)
      }

      const data = (await resp.json()) as ChatResponse
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.answer || 'No answer returned.',
        sources: data.sources || [],
        model: data.model ?? null,
        retrievedCount: data.retrieved_count ?? 0,
        notice: data.notice ?? null,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (e: any) {
      setError(e?.message || 'Failed to get a response. Please try again.')
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'The request could not be completed. Please try again.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void sendMessage(question)
  }

  const filters: Array<{ value: 'all' | 'dar_global' | 'wasalt'; label: string }> = [
    { value: 'all', label: 'All sources' },
    { value: 'dar_global', label: 'DarGlobal' },
    { value: 'wasalt', label: 'Wasalt' },
  ]

  const glassPanel = 'border border-white/50 bg-white/65 backdrop-blur-xl shadow-glass dark:border-white/10 dark:bg-slate-900/55'
  const softPanel = 'border border-slate-200/70 bg-white/70 backdrop-blur-md dark:border-white/10 dark:bg-slate-900/50'

  return (
    <div className="min-h-screen text-slate-900 dark:text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-10">
        <header className={`mb-6 rounded-2xl p-5 md:mb-8 md:p-7 ${glassPanel}`}>
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-accent-700 dark:text-accent-100">Property Data Search</p>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-950 dark:text-white md:text-4xl">DarGlobal and Wasalt Property Search</h1>
              <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300 md:text-base">
                Search publicly collected pages from DarGlobal and Wasalt. Results are based on retrieved dataset content and include source links when available.
              </p>
            </div>

            <div className="w-full space-y-3 lg:w-[340px]">
              <div className={`rounded-xl p-4 text-sm ${softPanel}`}>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Appearance</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={darkMode}
                    onClick={toggleTheme}
                    className={`relative inline-flex h-7 w-14 items-center rounded-full border transition ${darkMode ? 'border-accent-500 bg-accent-600' : 'border-slate-300 bg-slate-200/80 dark:border-white/20 dark:bg-slate-700'}`}
                    title="Toggle light and dark mode"
                  >
                    <span className="sr-only">Toggle dark mode</span>
                    <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${darkMode ? 'translate-x-8' : 'translate-x-1'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                  <span>{darkMode ? 'Dark mode on' : 'Light mode on'}</span>
                  <span className="rounded-full bg-mint-50 px-2 py-0.5 font-medium text-mint-600 dark:bg-emerald-500/15 dark:text-emerald-300">Glass view</span>
                </div>
              </div>

              <div className={`rounded-xl p-4 text-sm ${softPanel}`}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-medium text-slate-900 dark:text-slate-100">Dataset status</span>
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${health?.knowledge_base_ready ? 'bg-mint-50 text-mint-600 dark:bg-emerald-500/15 dark:text-emerald-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'}`}>
                    {health?.knowledge_base_ready ? 'Ready' : health ? 'Starting' : 'Unknown'}
                  </span>
                </div>
                <div className="text-slate-700 dark:text-slate-300">{kbSummary}</div>
                <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">Filter: {filters.find(f => f.value === sourceFilter)?.label}</div>
              </div>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="space-y-4">
            <section className={`rounded-2xl p-4 md:p-5 ${glassPanel}`}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">Source filter</h2>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:grid-cols-1">
                {filters.map((f) => (
                  <button
                    key={f.value}
                    onClick={() => setSourceFilter(f.value)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${sourceFilter === f.value ? 'border-accent-600 bg-accent-600 text-white shadow-sm' : 'border-slate-200/80 bg-white/60 text-slate-800 hover:border-accent-500 hover:bg-white/80 dark:border-white/10 dark:bg-slate-800/50 dark:text-slate-200 dark:hover:border-accent-500/60'}`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">Limit retrieval to one source or search across all collected pages.</p>
            </section>

            <section className={`rounded-2xl p-4 md:p-5 ${glassPanel}`}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">Example questions</h2>
              <div className="space-y-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void sendMessage(s)}
                    className="w-full rounded-lg border border-slate-200/80 bg-white/60 px-3 py-2 text-left text-sm text-slate-800 transition hover:border-accent-500/60 hover:bg-white/80 dark:border-white/10 dark:bg-slate-800/50 dark:text-slate-200 dark:hover:bg-slate-800/70"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </section>

            <section className={`rounded-2xl p-4 md:p-5 ${glassPanel}`}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">About this dataset</h2>
              <ul className="space-y-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                <li>Built from publicly accessible pages collected from darglobal.co.uk and wasalt.sa.</li>
                <li>Responses cite retrieved source URLs from the collected snapshot.</li>
                <li>Coverage can be incomplete when pages are unavailable or protected.</li>
                <li>If a detail is not found in the dataset, the answer states that clearly.</li>
              </ul>
            </section>
          </aside>

          <main className={`flex min-h-[70vh] flex-col overflow-hidden rounded-2xl ${glassPanel}`}>
            <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-4 py-4 dark:border-white/10 md:px-6">
              <div>
                <h2 className="text-base font-semibold text-slate-950 dark:text-white md:text-lg">Search results</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 md:text-sm">Questions are answered from retrieved pages in the selected source scope.</p>
              </div>
              <button
                onClick={() => { setMessages([]); setError(null) }}
                className="rounded-lg border border-slate-200/80 bg-white/60 px-3 py-2 text-sm text-slate-800 transition hover:border-slate-400 hover:bg-white/80 dark:border-white/10 dark:bg-slate-800/50 dark:text-slate-200 dark:hover:bg-slate-800/70"
              >
                Clear
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
              {messages.length === 0 && (
                <div className={`rounded-xl border border-dashed p-5 text-sm leading-6 text-slate-600 dark:text-slate-300 ${softPanel}`}>
                  Ask a question to search the collected DarGlobal and Wasalt pages. Retrieved source links will appear with each answer.
                </div>
              )}

              {messages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[95%] rounded-xl border px-4 py-3 md:max-w-[85%] ${m.role === 'user' ? 'border-accent-600 bg-accent-600 text-white shadow-sm' : 'border-slate-200/70 bg-white/75 text-slate-900 backdrop-blur-md dark:border-white/10 dark:bg-slate-900/60 dark:text-slate-100'}`}>
                    <div className={`mb-1 text-[11px] font-medium uppercase tracking-wide ${m.role === 'user' ? 'text-blue-100' : 'text-slate-500 dark:text-slate-400'}`}>
                      {m.role === 'user' ? 'Question' : 'Result'}
                    </div>
                    <div className="whitespace-pre-wrap text-sm leading-6">{m.content}</div>

                    {m.role === 'assistant' && m.notice && (
                      <div className="mt-3 rounded-lg border border-slate-200/70 bg-slate-50/80 px-3 py-2 text-xs text-slate-600 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-300">{m.notice}</div>
                    )}

                    {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                      <div className="mt-4 border-t border-slate-200/70 pt-3 dark:border-white/10">
                        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Sources</div>
                        <div className="space-y-2">
                          {m.sources.map((s, i) => (
                            <a
                              key={`${m.id}-${i}-${s.url}`}
                              href={s.url}
                              target="_blank"
                              rel="noreferrer"
                              className="block rounded-lg border border-slate-200/70 bg-slate-50/70 p-3 transition hover:border-accent-500/50 hover:bg-white/80 dark:border-white/10 dark:bg-slate-800/50 dark:hover:bg-slate-800/70"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{s.title || s.url}</div>
                                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${s.source === 'dar_global' ? 'bg-accent-100 text-accent-700 dark:bg-accent-500/20 dark:text-accent-100' : s.source === 'wasalt' ? 'bg-mint-50 text-mint-600 dark:bg-emerald-500/20 dark:text-emerald-300' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'}`}>{sourceLabel(s.source)}</span>
                              </div>
                              <div className="mt-1 break-all text-xs text-slate-500 dark:text-slate-400">{s.url}</div>
                              {s.snippet && <div className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-300">{s.snippet}</div>}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}

                    {m.role === 'assistant' && (m.model || typeof m.retrievedCount === 'number') && (
                      <div className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
                        {typeof m.retrievedCount === 'number' ? `Retrieved: ${m.retrievedCount}` : ''}
                        {typeof m.retrievedCount === 'number' && m.model ? ' · ' : ''}
                        {m.model ? `Model: ${m.model}` : ''}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className={`rounded-xl px-4 py-3 text-sm text-slate-600 dark:text-slate-300 ${softPanel}`}>Searching collected pages and preparing an answer...</div>
                </div>
              )}

              {error && <div className="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-sm text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">{error}</div>}
              <div ref={endRef} />
            </div>

            <form onSubmit={onSubmit} className="border-t border-slate-200/70 bg-white/40 p-4 backdrop-blur-md dark:border-white/10 dark:bg-slate-900/40 md:p-5">
              <label htmlFor="question" className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-600 dark:text-slate-300">Your question</label>
              <div className="flex flex-col gap-3 md:flex-row">
                <textarea
                  id="question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about projects, locations, or details found in the collected data..."
                  rows={3}
                  className="flex-1 resize-none rounded-xl border border-slate-200/80 bg-white/70 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20 dark:border-white/10 dark:bg-slate-800/60 dark:text-slate-100 dark:placeholder:text-slate-500"
                />
                <button
                  disabled={loading || !question.trim()}
                  className="rounded-xl border border-accent-600 bg-accent-600 px-5 py-3 text-sm font-medium text-white transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-500 dark:disabled:border-slate-700 dark:disabled:bg-slate-800 dark:disabled:text-slate-500 md:w-36"
                >
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Answers use retrieved website content from the collected dataset and may be incomplete.</p>
            </form>
          </main>
        </div>
      </div>
    </div>
  )
}
