import { useState } from 'react'
import { loadSeasons, loadEquity, loadOrders, type Season, type EquitySnapshot, type Order } from '@/lib/seasons-loader'
import { createSeasonFile, type CreateSeasonInput } from '@/lib/create-season'

const COLORS = ['#0891b2', '#059669', '#d97706', '#dc2626', '#7c3aed', '#db2777']

// ---- SparkLine ----

function SparkLine({ points, color, width = 400, height = 120 }: {
  points: EquitySnapshot[]
  color: string
  width?: number
  height?: number
}) {
  if (points.length < 1) return <p className="text-xs text-slate-400 mt-2">暂无数据</p>

  const values = points.map(p => p.total_assets)
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
      <div className="flex items-baseline gap-2 mb-1">
        <span className={`text-lg font-bold ${isPos ? 'text-emerald-700' : 'text-rose-600'}`}>
          {isPos ? '+' : ''}{last.return_pct.toFixed(2)}%
        </span>
        <span className="text-xs text-slate-500">
          ¥{last.total_assets.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
        <polyline points={polyline} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <polyline
          points={`${pad},${pad + h} ${polyline} ${pad + w},${pad + h}`}
          fill={color} fillOpacity="0.08" stroke="none"
        />
      </svg>
    </div>
  )
}

// ---- OrdersTable ----

const PAGE_SIZE = 15

function OrdersTable({ orders }: { orders: Order[] }) {
  const [page, setPage] = useState(0)
  if (orders.length === 0) return <p className="text-xs text-slate-400">暂无成交记录</p>

  const sorted = [...orders].sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const slice = sorted.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-stone-200 text-slate-500">
              <th className="pb-1 pr-2 font-medium">时间</th>
              <th className="pb-1 pr-2 font-medium">标的</th>
              <th className="pb-1 pr-2 font-medium">方向</th>
              <th className="pb-1 pr-2 font-medium">数量</th>
              <th className="pb-1 pr-2 font-medium">成交价</th>
              <th className="pb-1 pr-2 font-medium">手续费</th>
              <th className="pb-1 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {slice.map(o => {
              const code = o.symbol_key.split(':').pop() ?? o.symbol_key
              const time = o.submitted_at.slice(0, 16).replace('T', ' ')
              return (
                <tr key={o.order_id} className="border-b border-stone-100 last:border-0">
                  <td className="py-1 pr-2 text-slate-500 tabular-nums">{time}</td>
                  <td className="py-1 pr-2 font-mono">{code}</td>
                  <td className={`py-1 pr-2 font-semibold ${o.side === 'buy' ? 'text-emerald-700' : 'text-rose-600'}`}>
                    {o.side === 'buy' ? '买入' : '卖出'}
                  </td>
                  <td className="py-1 pr-2 tabular-nums">{o.quantity}</td>
                  <td className="py-1 pr-2 tabular-nums">{o.fill_price?.toFixed(2) ?? '—'}</td>
                  <td className="py-1 pr-2 tabular-nums text-amber-600">
                    {o.commission > 0 ? o.commission.toFixed(2) : '—'}
                  </td>
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
            onClick={() => setPage(p => p - 1)}
            className="text-[11px] px-2 py-0.5 rounded border border-stone-300 text-slate-500 disabled:opacity-30 hover:border-stone-400"
          >
            ← 较新
          </button>
          <span className="text-[11px] text-slate-400">{page + 1} / {totalPages} · 共 {sorted.length} 条</span>
          <button
            type="button"
            disabled={page === totalPages - 1}
            onClick={() => setPage(p => p + 1)}
            className="text-[11px] px-2 py-0.5 rounded border border-stone-300 text-slate-500 disabled:opacity-30 hover:border-stone-400"
          >
            较旧 →
          </button>
        </div>
      )}
    </div>
  )
}

// ---- TraderPanel ----

function TraderPanel({ trader, equity, orders, color }: {
  trader: string
  equity: EquitySnapshot[]
  orders: Order[]
  color: string
}) {
  const [tab, setTab] = useState<'equity' | 'orders'>('equity')
  return (
    <article className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: color }} />
          <span className="text-sm font-semibold text-slate-800">{trader}</span>
        </div>
        <div className="flex gap-1">
          {(['equity', 'orders'] as const).map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                tab === t
                  ? 'border-cyan-600/40 bg-cyan-600/10 text-cyan-700'
                  : 'border-stone-300 text-slate-500 hover:border-stone-400'
              }`}
            >
              {t === 'equity' ? '净值' : '成交'}
            </button>
          ))}
        </div>
      </div>
      {tab === 'equity'
        ? <SparkLine points={equity} color={color} />
        : <OrdersTable orders={orders} />
      }
    </article>
  )
}

// ---- SeasonCard ----

function SeasonCard({ season, selected, onClick }: {
  season: Season
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left rounded-lg border p-3 transition-colors ${
        selected
          ? 'border-cyan-600/40 bg-cyan-600/10'
          : 'border-stone-300 bg-stone-50/90 hover:border-stone-400'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-900">{season.slug.toUpperCase()}</span>
        <span className="text-[11px] rounded border border-stone-300 px-1.5 py-0.5 text-slate-500">
          {season.market}
        </span>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">
        {season.start_date} → {season.end_date ?? '进行中'}
      </p>
      <p className="mt-1 text-[11px] text-slate-500">
        {season.traders.length} 位交易员 · ¥{(season.initial_capital / 10000).toFixed(0)}万
      </p>
      <p className="mt-0.5 text-[11px] text-slate-400">
        综合费率 {(season.fee_rate * 10000).toFixed(1)}‱
      </p>
    </button>
  )
}

// ---- CreateSeasonModal ----

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
    setForm(f => ({ ...f, [key]: value }))
  }

  function addSymbol() {
    const code = symbolInput.trim()
    if (code && !form.symbol_pool.includes(code)) {
      set('symbol_pool', [...form.symbol_pool, code])
    }
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
    } catch (err: any) {
      if (err?.name !== 'AbortError') setError(err?.message ?? '创建失败')
    } finally {
      setLoading(false)
    }
  }

  const inputCls = 'w-full rounded border border-stone-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 focus:border-cyan-500 focus:outline-none'
  const labelCls = 'block text-xs font-medium text-slate-600 mb-1'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-stone-300 bg-white p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-slate-900">新建赛季</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>赛季名称 *</label>
            <input className={inputCls} placeholder="如 Season 1" value={form.season}
              onChange={e => set('season', e.target.value)} required />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>交易市场 *</label>
              <select className={inputCls} value={form.market} onChange={e => set('market', e.target.value as any)}>
                <option value="A_SHARE">A股</option>
                <option value="HK">港股</option>
                <option value="US">美股</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>开始日期 *</label>
              <input className={inputCls} type="date" value={form.start_date}
                onChange={e => set('start_date', e.target.value)} required />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>结束日期（留空为永恒赛季）</label>
              <input className={inputCls} type="date" value={form.end_date ?? ''}
                onChange={e => set('end_date', e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>初始资金（元）</label>
              <input className={inputCls} type="number" min={1} value={form.initial_capital}
                onChange={e => set('initial_capital', Number(e.target.value))} />
            </div>
          </div>

          <div>
            <label className={labelCls}>综合费率（万分之几）</label>
            <input className={inputCls} type="number" step="0.1" min={0} value={(form.fee_rate * 10000).toFixed(1)}
              onChange={e => set('fee_rate', Number(e.target.value) / 10000)} />
          </div>

          <div>
            <label className={labelCls}>股票代码池（留空表示全市场）</label>
            <div className="flex gap-2">
              <input className={inputCls} placeholder="输入代码后回车添加" value={symbolInput}
                onChange={e => setSymbolInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSymbol() } }} />
              <button type="button" onClick={addSymbol}
                className="shrink-0 rounded border border-stone-300 px-3 text-xs text-slate-600 hover:border-stone-400">
                添加
              </button>
            </div>
            {form.symbol_pool.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {form.symbol_pool.map(code => (
                  <span key={code} className="flex items-center gap-1 rounded bg-stone-100 px-2 py-0.5 text-xs font-mono text-slate-700">
                    {code}
                    <button type="button" onClick={() => set('symbol_pool', form.symbol_pool.filter(c => c !== code))}
                      className="text-slate-400 hover:text-rose-500">✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-xs text-rose-600">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="rounded border border-stone-300 px-4 py-1.5 text-xs text-slate-600 hover:border-stone-400">
              取消
            </button>
            <button type="submit" disabled={loading}
              className="rounded bg-cyan-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-cyan-800 disabled:opacity-50">
              {loading ? '创建中…' : '选择目录并创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---- SeasonsPage ----

export function SeasonsPage() {
  const [seasons] = useState<Season[]>(() => loadSeasons())
  const [selected, setSelected] = useState<string | null>(() => {
    const all = loadSeasons()
    return all.length > 0 ? all[0].slug : null
  })
  const [showCreate, setShowCreate] = useState(false)

  const equity = selected ? loadEquity(selected) : {}
  const orders = selected ? loadOrders(selected) : {}
  const traders = selected
    ? (seasons.find(s => s.slug === selected)?.traders ?? [])
    : []

  function handleCreated(slug: string) {
    setShowCreate(false)
    alert(`赛季已创建：${slug}\n\n请刷新页面以加载新赛季。`)
    window.location.reload()
  }

  return (
    <>
      {showCreate && <CreateSeasonModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />}
      <section className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="panel p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">赛季列表</h2>
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="rounded border border-stone-300 px-2 py-0.5 text-[11px] text-slate-600 hover:border-cyan-500 hover:text-cyan-700 transition-colors"
            >
              + 新建
            </button>
          </div>
          <ul className="space-y-2">
            {seasons.map(s => (
              <li key={s.slug}>
                <SeasonCard season={s} selected={selected === s.slug} onClick={() => setSelected(s.slug)} />
              </li>
            ))}
            {seasons.length === 0 && <p className="text-xs text-slate-400">暂无赛季</p>}
          </ul>
        </aside>

        <div className="panel p-4">
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700 mb-4">
            交易员表现
            {selected && <span className="ml-2 text-slate-400 normal-case font-normal">· {selected.toUpperCase()}</span>}
          </h2>

          {traders.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {traders.map((trader, idx) => (
                <TraderPanel
                  key={trader}
                  trader={trader}
                  equity={equity[trader] ?? []}
                  orders={orders[trader] ?? []}
                  color={COLORS[idx % COLORS.length]}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">选择赛季后查看数据</p>
          )}
        </div>
      </section>
    </>
  )
}
