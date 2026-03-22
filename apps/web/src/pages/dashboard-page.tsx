import { useMemo } from 'react'
import { useUiStore } from '@/store/ui-store'

type Agent = {
  id: string
  name: string
  status: 'running' | 'review' | 'paused'
  pnl: string
  risk: 'low' | 'mid' | 'high'
}

type AuditLog = {
  time: string
  type: string
  detail: string
}

const agents: Agent[] = [
  { id: 'ag-001', name: 'Momentum Scout', status: 'running', pnl: '+4.2%', risk: 'mid' },
  { id: 'ag-002', name: 'Mean Reversion X', status: 'review', pnl: '+1.3%', risk: 'low' },
  { id: 'ag-003', name: 'News Arbitrage', status: 'paused', pnl: '-0.8%', risk: 'high' },
]

const auditLogs: AuditLog[] = [
  { time: '09:31:11', type: 'Prompt', detail: 'Agent requested breakout logic with 2h volatility gate.' },
  { time: '09:31:26', type: 'Code Diff', detail: 'Added trailing stop and max-position sizing in strategy executor.' },
  { time: '09:31:42', type: 'Risk Check', detail: 'Exposure 18.2%, slippage stress passed, leverage remains under 2.0x.' },
  { time: '09:32:05', type: 'Order', detail: 'Submitted BUY 0.35 BTC, limit 68124.5, broker accepted.' },
]

function statusClass(status: Agent['status']) {
  if (status === 'running') return 'text-emerald-900 border-emerald-700/25 bg-emerald-600/10'
  if (status === 'review') return 'text-amber-900 border-amber-700/25 bg-amber-500/10'
  return 'text-rose-900 border-rose-700/25 bg-rose-500/10'
}

function riskColor(risk: Agent['risk']) {
  if (risk === 'low') return 'text-emerald-700'
  if (risk === 'mid') return 'text-amber-700'
  return 'text-rose-700'
}

export function DashboardPage() {
  const { launchCount, incrementLaunchCount, transport, setTransport } = useUiStore()

  const riskScore = useMemo(() => {
    const base = transport === 'ipc' ? 71 : 64
    return Math.min(99, base + launchCount)
  }, [launchCount, transport])

  return (
    <section className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
      <aside className="panel p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">Agents</h2>
          <span className="text-xs text-slate-500">{agents.length} online</span>
        </div>
        <ul className="mt-4 space-y-2">
          {agents.map((agent) => (
            <li key={agent.id} className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">{agent.name}</p>
                  <p className="mt-1 text-[11px] text-slate-500">{agent.id}</p>
                </div>
                <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${statusClass(agent.status)}`}>
                  {agent.status.toUpperCase()}
                </span>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs">
                <span className="text-slate-600">PnL {agent.pnl}</span>
                <span className={riskColor(agent.risk)}>Risk {agent.risk.toUpperCase()}</span>
              </div>
            </li>
          ))}
        </ul>
      </aside>

      <div className="space-y-4">
        <article className="panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Strategy Composer</h2>
              <p className="text-xs text-slate-600">Agent writes strategy code, then waits for risk gate before execution.</p>
            </div>
            <button
              type="button"
              onClick={incrementLaunchCount}
              className="rounded-md border border-cyan-700/25 bg-cyan-700/10 px-3 py-2 text-xs font-semibold text-cyan-900 hover:bg-cyan-700/20"
            >
              Generate Next Revision
            </button>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">Prompt Intent</p>
              <p className="mt-2 text-sm text-slate-800">Build BTC intraday strategy with trend filter, drawdown cap, and adaptive exit.</p>
            </div>
            <div className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">Code Snapshot</p>
              <pre className="mt-2 overflow-x-auto text-xs text-cyan-900">
{`if (trend > 0 && drawdown < 0.03) {
  size = capital * 0.12;
  placeLong(size, stopATR * 1.8);
}`}
              </pre>
            </div>
          </div>
        </article>

        <article className="panel p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">Audit Timeline</h3>
          <ol className="mt-3 space-y-2">
            {auditLogs.map((log) => (
              <li key={`${log.time}-${log.type}`} className="rounded-lg border border-stone-300 bg-stone-50/90 p-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-800">{log.type}</span>
                  <span className="text-slate-500">{log.time}</span>
                </div>
                <p className="mt-1 text-xs text-slate-600">{log.detail}</p>
              </li>
            ))}
          </ol>
        </article>
      </div>

      <aside className="space-y-4">
        <article className="panel p-4">
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">Risk And Execution</h2>
          <p className="mt-2 text-4xl font-bold text-emerald-700">{riskScore}</p>
          <p className="text-xs text-slate-600">Composite safety score. Trading is blocked below 60.</p>
          <div className="mt-4 h-2 rounded bg-stone-200">
            <div className="h-2 rounded bg-emerald-600" style={{ width: `${riskScore}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <button
              type="button"
              onClick={() => setTransport('http')}
              className="rounded-md border border-stone-300 bg-white px-2 py-2 font-semibold text-slate-700 hover:border-stone-400"
            >
              Broker API
            </button>
            <button
              type="button"
              onClick={() => setTransport('ipc')}
              className="rounded-md border border-stone-300 bg-white px-2 py-2 font-semibold text-slate-700 hover:border-stone-400"
            >
              Desktop IPC
            </button>
          </div>
          <div className="mt-4 flex gap-2 text-xs">
            <button type="button" className="flex-1 rounded-md bg-rose-600 px-3 py-2 font-semibold text-white hover:bg-rose-500">
              Pause All
            </button>
            <button type="button" className="flex-1 rounded-md border border-emerald-700/30 bg-emerald-600/10 px-3 py-2 font-semibold text-emerald-900 hover:bg-emerald-600/20">
              Approve Batch
            </button>
          </div>
        </article>

        <article className="panel p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-700">Control Summary</h3>
          <dl className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">Deploy Iterations</dt>
              <dd className="font-semibold text-slate-900">{launchCount}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">Execution Channel</dt>
              <dd className="font-semibold text-slate-900">{transport.toUpperCase()}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-slate-500">Audit Integrity</dt>
              <dd className="font-semibold text-emerald-700">OK</dd>
            </div>
          </dl>
        </article>
      </aside>
    </section>
  )
}