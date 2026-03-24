const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || 'http://127.0.0.1:8000'

// codex is installed as a local npm package; pass the bin path so the Python backend can find it
const CODEX_BIN = (import.meta.env.VITE_CODEX_BIN as string | undefined)?.trim() || './src/trader_incubator/apps/web/node_modules/.bin/codex'

export type CodexResult = {
  ok: boolean
  code?: number
  stdout: string
  stderr: string
}

export type CreateTraderResult = {
  traders?: unknown[]
  trader?: unknown
  codex: CodexResult
  error?: string
}

export type CreateTraderStreamEvent = {
  type: 'status' | 'log' | 'final'
  message?: string
  payload?: CreateTraderResult
}

export async function autoCreateTraderWithCodex(
  seasonSlug: string,
  onEvent?: (event: CreateTraderStreamEvent) => void,
): Promise<CreateTraderResult> {
  const useStream = typeof onEvent === 'function'
  const response = await fetch(`${API_BASE}/api/seasons/${encodeURIComponent(seasonSlug)}/traders/codex`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codex_bin: CODEX_BIN, stream: useStream }),
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

  if (!useStream || !response.body) {
    return response.json() as Promise<CreateTraderResult>
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalPayload: CreateTraderResult | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const raw of lines) {
      const line = raw.trim()
      if (!line) continue
      try {
        const event = JSON.parse(line) as CreateTraderStreamEvent
        onEvent(event)
        if (event.type === 'final' && event.payload) {
          finalPayload = event.payload
        }
      } catch {
        onEvent({ type: 'log', message: line })
      }
    }
  }

  if (!finalPayload) {
    throw new Error('Create trader failed: missing final stream payload')
  }
  if (finalPayload.error) {
    throw new Error(`Create trader failed (500): ${JSON.stringify(finalPayload.error)}`)
  }
  return finalPayload
}
