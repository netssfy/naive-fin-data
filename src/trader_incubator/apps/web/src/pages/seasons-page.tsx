import { useEffect, useMemo, useState } from 'react'
import {
  loadSeasons,
  loadSeasonTraders,
  loadEquity,
  loadOrders,
  type Season,
  type TraderSummary,
  type EquitySnapshot,
  type Order,
} from '@/lib/seasons-loader'
import { createSeasonFile, type CreateSeasonInput } from '@/lib/create-season'

const COLORS = ['#0891b2', '#059669', '#d97706', '#dc2626', '#7c3aed', '#db2777']
const PAGE_SIZE = 15

function SparkLine({ points, color, width = 400, height = 120 }: { points: EquitySnapshot[]; color: string; width?: number; height?: number }) {
  if (points.length < 1) return <p className="mt-2 text-xs text-slate-400">No data</p>

  const values = points.map((p) => p.total_assets)
  const minV = Math.min(...values)
  const maxV = Math.max(...values)
  const range = maxV - minV || 1
  const pad = 8
  const w = width - pad * 2
  const h = height - pad * 2

  const coords = points.map((p, i) => {
    const x = pad + (i / Math.max(points.length - 1, 1)) * w
    const y = pad + h - ((p.total_assets - minV) / range) * h
    return `${x},${y}`
  })

  const polyline = coords.join(' ')
  const last = points[points.length - 1]
  const isPos = last.return_pct >= 0

  return (
    <div>
      <div className="mb-1 flex items-baseline gap-2">
        <span className={`text-lg font-bold ${isPos ? 'text-emerald-700' : 'text-rose-600'}`}>
          {isPos ? '+' : ''}
          {last.return_pct.toFixed(2)}%
        </span>
        <span className="text-xs text-slate-500">Assets {last.total_assets.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
        <polyline points={polyline} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <polyline points={`${pad},${pad + h} ${polyline} ${pad + w},${pad + h}`} fill={color} fillOpacity="0.08" stroke="none" />
      </svg>
    </div>
  )
}

function OrdersTable({ orders }: { orders: Order[] }) {
  const [page, setPage] = useState(0)
  if (orders.length === 0) return <p className="text-xs text-slate-400">No orders</p>

  const sorted = [...orders].sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const slice = sorted.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-stone-200 text-slate-500">
              <th className="pb-1 pr-2 font-medium">Time</th>
              <th className="pb-1 pr-2 font-medium">Symbol</th>
              <th className="pb-1 pr-2 font-medium">Side</th>
              <th className="pb-1 pr-2 font-medium">Qty</th>
              <th className="pb-1 pr-2 font-medium">Price</th>
              <th className="pb-1 pr-2 font-medium">Fee</th>
              <th className="pb-1 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {slice.map((o) => {
              const code = o.symbol_key.split(':').pop() ?? o.symbol_key
              const time = o.submitted_at.slice(0, 16).replace('T', ' ')
              return (
                <tr key={o.order_id} className="border-b border-stone-100 last:border-0">
                  <td className="py-1 pr-2 tabular-nums text-slate-500">{time}</td>
                  <td className="py-1 pr-2 font-mono">{code}</td>
                  <td className={`py-1 pr-2 font-semibold ${o.side === 'buy' ? 'text-emerald-700' : 'text-rose-600'}`}>{o.side}</td>
                  <td className="py-1 pr-2 tabular-nums">{o.quantity}</td>
                  <td className="py-1 pr-2 tabular-nums">{o.fill_price?.toFixed(2) ?? '-'}</td>
                  <td className="py-1 pr-2 tabular-nums text-amber-600">{o.commission > 0 ? o.commission.toFixed(2) : '-'}</td>
                  <td className={`py-1 ${o.status === 'filled' ? 'text-slate-500' : 'text-rose-500'}`}>{o.status}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-1">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="rounded border border-stone-300 px-2 py-0.5 text-[11px] text-slate-500 hover:border-stone-400 disabled:opacity-30"
          >
            Newer
          </button>
          <span className="text-[11px] text-slate-400">
            {page + 1} / {totalPages} · {sorted.length} rows
          </span>
          <button
            type="button"
            disabled={page === totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            className="rounded border border-stone-300 px-2 py-0.5 text-[11px] text-slate-500 hover:border-stone-400 disabled:opacity-30"
          >
            Older
          </button>
        </div>
      )}
    </div>
  )
}

function TraderPanel({ trader, equity, orders, color }: { trader: TraderSummary; equity: EquitySnapshot[]; orders: Order[]; color: string }) {
  const [tab, setTab] = useState<'equity' | 'orders'>('equity')
  return (
    <article className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          <span className="text-sm font-semibold text-slate-800">{trader.trader}</span>
        </div>
        <div className="flex gap-1">
          {(['equity', 'orders'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded border px-2 py-0.5 text-[11px] transition-colors ${tab === t ? 'border-cyan-600/40 bg-cyan-600/10 text-cyan-700' : 'border-stone-300 text-slate-500 hover:border-stone-400'}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {tab === 'equity' ? <SparkLine points={equity} color={color} /> : <OrdersTable orders={orders} />}
    </article>
  )
}

function SeasonCard({ season, selected, onClick }: { season: Season; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg border p-3 text-left transition-colors ${selected ? 'border-cyan-600/40 bg-cyan-600/10' : 'border-stone-300 bg-stone-50/90 hover:border-stone-400'}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-900">{season.slug.toUpperCase()}</span>
        <span className="rounded border border-stone-300 px-1.5 py-0.5 text-[11px] text-slate-500">{season.market}</span>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">{season.start_date} → {season.end_date ?? 'ongoing'}</p>
      <p className="mt-1 text-[11px] text-slate-500">{season.traders.length} traders · capital {Math.round(season.initial_capital)}</p>
      <p className="mt-0.5 text-[11px] text-slate-400">fee {(season.fee_rate * 10000).toFixed(1)} bp</p>
    </button>
  )
}

const INITIAL_FORM: CreateSeasonInput = {
  season: '',
  market: 'A_SHARE',
  start_date: '',
  end_date: '',
  initial_capital: 1_000_000,
  fee_rate: 0.0004,
  symbol_pool: [],
}

function CreateSeasonModal({ onClose, onCreated }: { onClose: () => void; onCreated: (slug: string) => void }) {
  const [form, setForm] = useState<CreateSeasonInput>(INITIAL_FORM)
  const [symbolInput, setSymbolInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof CreateSeasonInput>(key: K, value: CreateSeasonInput[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function addSymbol() {
    const code = symbolInput.trim()
    if (code && !form.symbol_pool.includes(code)) set('symbol_pool', [...form.symbol_pool, code])
    setSymbolInput('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.season.trim() || !form.start_date) return
    setLoading(true)
    setError(null)
    try {
      const slug = await createSeasonFile(form)
      onCreated(slug)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Create season failed')
    } finally {
      setLoading(false)
    }
  }

  const inputCls = 'w-full rounded border border-stone-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 focus:border-cyan-500 focus:outline-none'
  const labelCls = 'mb-1 block text-xs font-medium text-slate-600'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-stone-300 bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">Create Season</h3>
          <button type="button" onClick={onClose} className="text-lg leading-none text-slate-400 hover:text-slate-600">×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>Season Name *</label>
            <input className={inputCls} placeholder="Season 1" value={form.season} onChange={(e) => set('season', e.target.value)} required />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Market *</label>
              <select className={inputCls} value={form.market} onChange={(e) => set('market', e.target.value as CreateSeasonInput['market'])}>
                <option value="A_SHARE">A_SHARE</option>
                <option value="HK">HK</option>
                <option value="US">US</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Start Date *</label>
              <input className={inputCls} type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} required />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>End Date</label>
              <input className={inputCls} type="date" value={form.end_date ?? ''} onChange={(e) => set('end_date', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>Initial Capital</label>
              <input className={inputCls} type="number" min={1} value={form.initial_capital} onChange={(e) => set('initial_capital', Number(e.target.value))} />
            </div>
          </div>

          <div>
            <label className={labelCls}>Fee (bp)</label>
            <input className={inputCls} type="number" step="0.1" min={0} value={(form.fee_rate * 10000).toFixed(1)} onChange={(e) => set('fee_rate', Number(e.target.value) / 10000)} />
          </div>

          <div>
            <label className={labelCls}>Symbol Pool (optional)</label>
            <div className="flex gap-2">
              <input
                className={inputCls}
                placeholder="Add symbol"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addSymbol()
                  }
                }}
              />
              <button type="button" onClick={addSymbol} className="shrink-0 rounded border border-stone-300 px-3 text-xs text-slate-600 hover:border-stone-400">Add</button>
            </div>
            {form.symbol_pool.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {form.symbol_pool.map((code) => (
                  <span key={code} className="flex items-center gap-1 rounded bg-stone-100 px-2 py-0.5 text-xs font-mono text-slate-700">
                    {code}
                    <button type="button" onClick={() => set('symbol_pool', form.symbol_pool.filter((c) => c !== code))} className="text-slate-400 hover:text-rose-500">×</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-xs text-rose-600">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="rounded border border-stone-300 px-4 py-1.5 text-xs text-slate-600 hover:border-stone-400">Cancel</button>
            <button type="submit" disabled={loading} className="rounded bg-cyan-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-cyan-800 disabled:opacity-50">
              {loading ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function SeasonsPage() {
  const [seasons, setSeasons] = useState<Season[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [traders, setTraders] = useState<TraderSummary[]>([])
  const [equity, setEquity] = useState<Record<string, EquitySnapshot[]>>({})
  const [orders, setOrders] = useState<Record<string, Order[]>>({})
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function refreshSeasons(preferredSlug?: string) {
    setLoading(true)
    setError(null)
    try {
      const list = await loadSeasons()
      setSeasons(list)
      const next = preferredSlug ?? selected ?? list[0]?.slug ?? null
      setSelected(next)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load seasons')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshSeasons()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) {
      setTraders([])
      setEquity({})
      setOrders({})
      return
    }

    void (async () => {
      try {
        const [t, e, o] = await Promise.all([loadSeasonTraders(selected), loadEquity(selected), loadOrders(selected)])
        setTraders(t)
        setEquity(e)
        setOrders(o)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load season data')
      }
    })()
  }, [selected])

  const selectedLabel = useMemo(() => (selected ? selected.toUpperCase() : ''), [selected])

  function handleCreated(slug: string) {
    setShowCreate(false)
    void refreshSeasons(slug)
  }

  return (
    <>
      {showCreate && <CreateSeasonModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />}
      <section className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">Seasons</h2>
            <button type="button" onClick={() => setShowCreate(true)} className="rounded border border-stone-300 px-2 py-0.5 text-[11px] text-slate-600 transition-colors hover:border-cyan-500 hover:text-cyan-700">
              + New
            </button>
          </div>
          <ul className="space-y-2">
            {seasons.map((s) => (
              <li key={s.slug}>
                <SeasonCard season={s} selected={selected === s.slug} onClick={() => setSelected(s.slug)} />
              </li>
            ))}
            {!loading && seasons.length === 0 && <p className="text-xs text-slate-400">No seasons</p>}
          </ul>
        </aside>

        <div className="panel p-4">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">
            Traders
            {selected && <span className="ml-2 font-normal normal-case text-slate-400">· {selectedLabel}</span>}
          </h2>

          {loading && <p className="text-sm text-slate-400">Loading...</p>}
          {error && <p className="mb-3 text-sm text-rose-600">{error}</p>}

          {!loading && traders.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {traders.map((trader, idx) => (
                <TraderPanel
                  key={trader.slug}
                  trader={trader}
                  equity={equity[trader.slug] ?? []}
                  orders={orders[trader.slug] ?? []}
                  color={COLORS[idx % COLORS.length]}
                />
              ))}
            </div>
          ) : (
            !loading && !error && <p className="text-sm text-slate-400">Select a season to view data.</p>
          )}
        </div>
      </section>
    </>
  )
}
