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
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    void fetchStats()
    void fetchHealth()
  }, [])

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

  return (
    <div className="min-h-screen bg-neutral-100 text-neutral-900">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-10">
        <header className="mb-6 border border-neutral-200 bg-white p-5 shadow-soft md:mb-8 md:p-7">
          <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
            <div className="max-w-3xl">
              <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-neutral-500">Property Data Search</p>
              <h1 className="text-2xl font-semibold tracking-tight text-black md:text-4xl">DarGlobal and Wasalt Property Q&A</h1>
              <p className="mt-3 text-sm leading-6 text-neutral-600 md:text-base">
                Search and ask questions over publicly collected pages from DarGlobal and Wasalt. Answers are based on retrieved dataset content and include source links when available.
              </p>
            </div>
            <div className="w-full border border-neutral-200 bg-neutral-50 p-4 text-sm md:w-[320px]">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-medium text-neutral-900">Dataset status</span>
                <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${health?.knowledge_base_ready ? 'border-neutral-900 bg-black text-white' : 'border-neutral-300 bg-white text-neutral-700'}`}>
                  {health?.knowledge_base_ready ? 'Ready' : health ? 'Starting' : 'Unknown'}
                </span>
              </div>
              <div className="text-neutral-700">{kbSummary}</div>
              <div className="mt-2 text-xs text-neutral-500">Filter: {filters.find(f => f.value === sourceFilter)?.label}</div>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="space-y-4">
            <section className="border border-neutral-200 bg-white p-4 shadow-soft md:p-5">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-700">Source filter</h2>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:grid-cols-1">
                {filters.map((f) => (
                  <button
                    key={f.value}
                    onClick={() => setSourceFilter(f.value)}
                    className={`w-full border px-3 py-2 text-left text-sm transition ${sourceFilter === f.value ? 'border-black bg-black text-white' : 'border-neutral-300 bg-white text-neutral-800 hover:border-neutral-500'}`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs leading-5 text-neutral-500">Limit retrieval to one source or search across all collected pages.</p>
            </section>

            <section className="border border-neutral-200 bg-white p-4 shadow-soft md:p-5">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-700">Example questions</h2>
              <div className="space-y-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void sendMessage(s)}
                    className="w-full border border-neutral-200 bg-neutral-50 px-3 py-2 text-left text-sm text-neutral-800 transition hover:border-neutral-400 hover:bg-white"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </section>

            <section className="border border-neutral-200 bg-white p-4 shadow-soft md:p-5">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-700">About this dataset</h2>
              <ul className="space-y-2 text-sm leading-6 text-neutral-600">
                <li>Built from publicly accessible pages collected from darglobal.co.uk and wasalt.sa.</li>
                <li>Responses cite retrieved source URLs from the collected snapshot.</li>
                <li>Coverage can be incomplete when pages are unavailable or protected.</li>
                <li>If a detail is not found in the dataset, the answer should state that clearly.</li>
              </ul>
            </section>
          </aside>

          <main className="flex min-h-[70vh] flex-col border border-neutral-200 bg-white shadow-soft">
            <div className="flex items-center justify-between gap-3 border-b border-neutral-200 px-4 py-4 md:px-6">
              <div>
                <h2 className="text-base font-semibold text-black md:text-lg">Conversation</h2>
                <p className="text-xs text-neutral-500 md:text-sm">Questions are answered from retrieved pages in the selected source scope.</p>
              </div>
              <button
                onClick={() => { setMessages([]); setError(null) }}
                className="border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 hover:border-black hover:text-black"
              >
                Clear
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
              {messages.length === 0 && (
                <div className="border border-dashed border-neutral-300 bg-neutral-50 p-5 text-sm leading-6 text-neutral-600">
                  Ask a question to search the collected DarGlobal and Wasalt pages. Retrieved source links will appear with the answer.
                </div>
              )}

              {messages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[95%] border px-4 py-3 md:max-w-[85%] ${m.role === 'user' ? 'border-neutral-900 bg-neutral-900 text-white' : 'border-neutral-200 bg-white text-neutral-900'}`}>
                    <div className={`mb-1 text-[11px] font-medium uppercase tracking-wide ${m.role === 'user' ? 'text-neutral-300' : 'text-neutral-500'}`}>
                      {m.role === 'user' ? 'Question' : 'Answer'}
                    </div>
                    <div className="whitespace-pre-wrap text-sm leading-6">{m.content}</div>

                    {m.role === 'assistant' && m.notice && (
                      <div className="mt-3 border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-600">{m.notice}</div>
                    )}

                    {m.role === 'assistant' && m.sources && m.sources.length > 0 && (
                      <div className="mt-4 border-t border-neutral-200 pt-3">
                        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">Sources</div>
                        <div className="space-y-2">
                          {m.sources.map((s, i) => (
                            <a
                              key={`${m.id}-${i}-${s.url}`}
                              href={s.url}
                              target="_blank"
                              rel="noreferrer"
                              className="block border border-neutral-200 bg-neutral-50 p-3 transition hover:border-neutral-500 hover:bg-white"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="text-sm font-medium text-neutral-900">{s.title || s.url}</div>
                                <span className="border border-neutral-300 bg-white px-2 py-0.5 text-[11px] text-neutral-700">{sourceLabel(s.source)}</span>
                              </div>
                              <div className="mt-1 break-all text-xs text-neutral-500">{s.url}</div>
                              {s.snippet && <div className="mt-2 text-xs leading-5 text-neutral-600">{s.snippet}</div>}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}

                    {m.role === 'assistant' && (m.model || typeof m.retrievedCount === 'number') && (
                      <div className="mt-3 text-[11px] text-neutral-500">
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
                  <div className="border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600">Searching collected pages and preparing an answer...</div>
                </div>
              )}

              {error && <div className="border border-neutral-300 bg-neutral-50 px-3 py-2 text-sm text-neutral-800">{error}</div>}
              <div ref={endRef} />
            </div>

            <form onSubmit={onSubmit} className="border-t border-neutral-200 bg-neutral-50 p-4 md:p-5">
              <label htmlFor="question" className="mb-2 block text-xs font-medium uppercase tracking-wide text-neutral-600">Your question</label>
              <div className="flex flex-col gap-3 md:flex-row">
                <textarea
                  id="question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about projects, locations, or details found in the collected data..."
                  rows={3}
                  className="flex-1 resize-none border border-neutral-300 bg-white px-4 py-3 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-black focus:outline-none"
                />
                <button
                  disabled={loading || !question.trim()}
                  className="border border-black bg-black px-5 py-3 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:border-neutral-300 disabled:bg-neutral-200 disabled:text-neutral-500 md:w-36"
                >
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </div>
              <p className="mt-2 text-xs leading-5 text-neutral-500">Answers use retrieved website content from the collected dataset and may be incomplete.</p>
            </form>
          </main>
        </div>
      </div>
    </div>
  )
}
