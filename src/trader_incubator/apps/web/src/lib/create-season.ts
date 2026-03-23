const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || 'http://127.0.0.1:8000'

export type CreateSeasonInput = {
  season: string
  market: 'A_SHARE' | 'HK' | 'US'
  start_date: string
  end_date?: string
  initial_capital: number
  fee_rate: number
  symbol_pool: string[]
}

export async function createSeasonFile(input: CreateSeasonInput): Promise<string> {
  const response = await fetch(`${API_BASE}/api/seasons`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      season: input.season,
      market: input.market,
      start_date: input.start_date,
      end_date: input.end_date || null,
      initial_capital: input.initial_capital,
      fee_rate: input.fee_rate,
      symbol_pool: input.symbol_pool,
    }),
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore non-json error body
    }
    throw new Error(`Create season failed (${response.status}): ${detail}`)
  }

  const payload = (await response.json()) as { slug: string }
  return payload.slug
}
