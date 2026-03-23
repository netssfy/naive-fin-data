/**
 * 通过 import.meta.glob 遍历文件系统加载所有 season/trader 数据
 */

// ---- season.json ----

export type SeasonJson = {
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
  market: string
  start_date: string
  end_date: string | null
  initial_capital: number
  fee_rate: number
  traders: string[]
}

const seasonModules = import.meta.glob<SeasonJson>(
  '../../../../core/skills/seasons/*/season.json',
  { eager: true }
)

export function loadSeasons(): Season[] {
  return Object.values(seasonModules).map((json) => ({
    slug: json.season,
    market: json.market,
    start_date: json.start_date,
    end_date: json.end_date,
    initial_capital: json.initial_capital,
    fee_rate: json.fee_rate ?? 0.0004,
    traders: json.traders.map((t) => t.trader),
  }))
}

// ---- equity.json ----

export type EquitySnapshot = {
  date: string
  cash: number
  holdings_value: number
  total_assets: number
  initial_capital: number
  return_pct: number
  holdings: Record<string, { quantity: number; close_price: number; value: number }>
}

const equityModules = import.meta.glob(
  '../../../../core/skills/seasons/*/traders/*/equity.json',
  { eager: true, import: 'default' }
)

/** Returns { [traderSlug]: EquitySnapshot[] } for a given season slug */
export function loadEquity(seasonSlug: string): Record<string, EquitySnapshot[]> {
  const result: Record<string, EquitySnapshot[]> = {}
  for (const [path, snapshots] of Object.entries(equityModules)) {
    const parts = path.split('/')
    const traderIdx = parts.indexOf('traders')
    const seasonIdx = parts.indexOf('seasons')
    if (seasonIdx === -1 || traderIdx === -1) continue
    const season = parts[seasonIdx + 1]
    const trader = parts[traderIdx + 1]
    if (season !== seasonSlug) continue
    result[trader] = Array.isArray(snapshots) ? (snapshots as EquitySnapshot[]) : []
  }
  return result
}

// ---- orders.json ----

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

const orderModules = import.meta.glob(
  '../../../../core/skills/seasons/*/traders/*/orders.json',
  { eager: true, import: 'default' }
)

/** Returns { [traderSlug]: Order[] } for a given season slug */
export function loadOrders(seasonSlug: string): Record<string, Order[]> {
  const result: Record<string, Order[]> = {}
  for (const [path, orders] of Object.entries(orderModules)) {
    const parts = path.split('/')
    const traderIdx = parts.indexOf('traders')
    const seasonIdx = parts.indexOf('seasons')
    if (seasonIdx === -1 || traderIdx === -1) continue
    const season = parts[seasonIdx + 1]
    const trader = parts[traderIdx + 1]
    if (season !== seasonSlug) continue
    result[trader] = Array.isArray(orders) ? (orders as Order[]) : []
  }
  return result
}
