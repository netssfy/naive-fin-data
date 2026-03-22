export function SettingsPage() {
  return (
    <section className="panel p-5">
      <h2 className="text-lg font-semibold text-slate-900">Execution Guardrails</h2>
      <p className="mt-1 text-xs text-slate-600">All autonomous actions must pass these controls before live trading.</p>
      <ul className="mt-4 space-y-2 text-sm text-slate-700">
        <li className="rounded-md border border-stone-300 bg-stone-50/90 px-3 py-2">Code changes require diff audit and deterministic replay.</li>
        <li className="rounded-md border border-stone-300 bg-stone-50/90 px-3 py-2">Position sizing uses capped risk budget per agent and per symbol.</li>
        <li className="rounded-md border border-stone-300 bg-stone-50/90 px-3 py-2">A single panic button can pause all strategies and revoke order permissions.</li>
      </ul>
    </section>
  )
}