const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || 'http://127.0.0.1:8000'

// codex is installed as a local npm package; pass the bin path so the Python backend can find it
const CODEX_BIN = (import.meta.env.VITE_CODEX_BIN as string | undefined)?.trim() || './src/trader_incubator/apps/web/node_modules/.bin/codex'

export type CodexResult = {
  ok: boolean
  stdout: string
  stderr: string
}

export type CreateTraderResult = {
  traders: unknown[]
  codex: CodexResult
}

export async function autoCreateTraderWithCodex(seasonSlug: string): Promise<CreateTraderResult> {
  const response = await fetch(`${API_BASE}/api/seasons/${encodeURIComponent(seasonSlug)}/traders/codex`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codex_bin: CODEX_BIN }),
  })

  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore non-json error body
    }
    throw new Error(`Create trader failed (${response.status}): ${JSON.stringify(detail)}`)
  }

  return response.json() as Promise<CreateTraderResult>
}
