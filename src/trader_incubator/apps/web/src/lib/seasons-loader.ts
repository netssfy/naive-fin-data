type DesktopBridge = { apiBaseUrl?: string }
const desktopApiBase = (globalThis as { desktop?: DesktopBridge }).desktop?.apiBaseUrl?.trim()
const envApiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
const API_BASE = desktopApiBase || envApiBase || 'http://127.0.0.1:8000'

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore non-json error body
    }
    throw new Error(`API ${response.status}: ${detail}`)
  }

  return (await response.json()) as T
}

export type SeasonJson = {
  slug: string
  season: string
  market: string
  start_date: string
  end_date: string | null
  initial_capital: number
  fee_rate: number
  symbol_pool: string[]
  traders: Array<{ trader: string; style: string; program_entry: string }>
  created_at: string
}

export type Season = {
  slug: string
  name: string
  market: string
  start_date: string
  end_date: string | null
  initial_capital: number
  fee_rate: number
  traders: string[]
}

export type TraderSummary = {
  slug: string
  season_slug: string
  trader: string
  season: string
  style: string
  program_entry: string
  initial_capital: number | null
  symbols: string[]
  created_at: string
}

export type EquitySnapshot = {
  date: string
  cash: number
  holdings_value: number
  total_assets: number
  initial_capital: number
  return_pct: number
  holdings: Record<string, { quantity: number; close_price: number; value: number }>
}

export type Order = {
  order_id: number
  symbol_key: string
  side: 'buy' | 'sell'
  quantity: number
  submitted_at: string
  status: string
  fill_price: number | null
  commission: number
  message: string
}

export async function loadSeasons(): Promise<Season[]> {
  const payload = await fetchJson<SeasonJson[]>('/api/seasons')
  return payload.map((item) => ({
    slug: item.slug,
    name: item.season,
    market: item.market,
    start_date: item.start_date,
    end_date: item.end_date,
    initial_capital: item.initial_capital,
    fee_rate: item.fee_rate ?? 0.0004,
    traders: item.traders.map((t) => t.trader),
  }))
}

export async function loadSeasonTraders(seasonSlug: string): Promise<TraderSummary[]> {
  return await fetchJson<TraderSummary[]>(`/api/seasons/${encodeURIComponent(seasonSlug)}/traders`)
}

export async function loadEquity(seasonSlug: string): Promise<Record<string, EquitySnapshot[]>> {
  return await fetchJson<Record<string, EquitySnapshot[]>>(`/api/seasons/${encodeURIComponent(seasonSlug)}/equity`)
}

export async function loadOrders(seasonSlug: string): Promise<Record<string, Order[]>> {
  return await fetchJson<Record<string, Order[]>>(`/api/seasons/${encodeURIComponent(seasonSlug)}/orders`)
}
