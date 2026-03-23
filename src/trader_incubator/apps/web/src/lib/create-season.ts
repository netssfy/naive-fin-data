/**
 * 通过 File System Access API 直接写 season.json 到本地文件系统
 */

export type CreateSeasonInput = {
  season: string
  market: 'A_SHARE' | 'HK' | 'US'
  start_date: string
  end_date?: string
  initial_capital: number
  fee_rate: number
  symbol_pool: string[]
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9\u4e00-\u9fff-]/g, '')
}

export async function createSeasonFile(input: CreateSeasonInput): Promise<string> {
  const slug = slugify(input.season)
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')

  const seasonJson = {
    season: input.season,
    market: input.market,
    start_date: input.start_date,
    end_date: input.end_date || null,
    initial_capital: input.initial_capital,
    fee_rate: input.fee_rate,
    symbol_pool: input.symbol_pool,
    traders: [],
    created_at: now,
  }

  const content = JSON.stringify(seasonJson, null, 2)

  // File System Access API
  const dirHandle = await (window as any).showDirectoryPicker({
    id: 'seasons-root',
    mode: 'readwrite',
    startIn: 'documents',
  })

  // 创建 <slug>/season.json
  const seasonDirHandle = await dirHandle.getDirectoryHandle(slug, { create: true })
  const fileHandle = await seasonDirHandle.getFileHandle('season.json', { create: true })
  const writable = await fileHandle.createWritable()
  await writable.write(content)
  await writable.close()

  return slug
}
