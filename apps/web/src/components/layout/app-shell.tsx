import { NavLink, Outlet } from 'react-router-dom'

const navItem = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? 'rounded-md border border-cyan-700/20 bg-cyan-700/10 px-3 py-1.5 text-xs font-semibold tracking-wide text-cyan-900'
    : 'rounded-md border border-transparent px-3 py-1.5 text-xs font-semibold tracking-wide text-slate-500 hover:border-stone-300 hover:text-slate-800'

export function AppShell() {
  return (
    <div className="min-h-screen bg-app text-slate-900">
      <div className="pointer-events-none fixed inset-0 opacity-40 [background:linear-gradient(rgba(15,23,42,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(15,23,42,0.06)_1px,transparent_1px)] [background-size:24px_24px]" />
      <div className="relative mx-auto flex w-full max-w-[1600px] flex-col gap-5 px-4 py-5 sm:px-6">
        <header className="panel flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-cyan-800">Autonomous Trader Control</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">Mission Control</h1>
            <p className="mt-1 text-xs text-slate-600">Code-generating agents with guarded execution and full audit trail.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-emerald-700/20 bg-emerald-600/10 px-2 py-1 text-[11px] font-semibold text-emerald-900">
              Live Market: OPEN
            </span>
            <nav className="flex gap-1.5 rounded-lg border border-stone-300 bg-stone-100/90 p-1">
              <NavLink to="/" end className={navItem}>
                Dashboard
              </NavLink>
              <NavLink to="/settings" className={navItem}>
                Controls
              </NavLink>
            </nav>
          </div>
        </header>

        <main>
          <Outlet />
        </main>
      </div>
    </div>
  )
}