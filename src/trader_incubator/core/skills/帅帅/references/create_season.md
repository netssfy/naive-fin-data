# 创建赛季

## 必填输入
- `season`：赛季名称，同时作为目录 slug，如 `Season 1` -> slug `season-1`
- `market`：交易市场，`A_SHARE` | `HK` | `US`
- `start_date`：开始日期，ISO-8601，如 `2026-01-01`

## 可选输入
- `end_date`：结束日期；不填表示永恒赛季
- `symbol_pool`：可交易股票代码列表；不填表示该市场全部股票可交易

## 执行步骤

```bash
python scripts/season_manager.py create \
    --season "<season>" \
    --market <market> \
    --start-date <start_date> \
    [--end-date <end_date>] \
    [--symbols <code1> <code2> ...] \
    --project-root .
```

## 输出
`season.json` 保存到 `src/trader_incubator/skills/seasons/<slug>/season.json`，结构：
```json
{
  "season": "Season 1",
  "market": "A_SHARE",
  "start_date": "2026-01-01",
  "end_date": null,
  "symbol_pool": ["000725", "600519"],
  "traders": [],
  "created_at": "2026-01-01T00:00:00Z"
}
```

## 错误处理
若必填字段缺失，向用户说明缺少哪些字段，不执行脚本。
