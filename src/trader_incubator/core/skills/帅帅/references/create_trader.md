# 创建交易员

## 必填输入
- `season`：目标赛季名称，如 `Season 1`
- `desired_count`：要创建的交易员数量
- `market`：交易市场（从 `season.json` 读取）

## 可选输入
- `symbol_pool`：若赛季有股票代码限制，交易员只能交易这些标的

## 执行步骤

### 1. 读取赛季信息
确认 `core/skills/seasons/<season-slug>/season.json` 存在。若不存在，先执行创建赛季流程。

### 2. 设计交易员
- 参考 `references/style_axes.md` 选取风格组合
- 每对交易员之间相似度必须 ≤ 0.5
- 若赛季有 `symbol_pool`，交易员的 `symbols` 必须在其中选取
- 为每个交易员确定：
  - `trader`：交易员名称，同时作为 slug/ID
    - 名字必须贴合交易员的风格特性，让人一眼联想到其交易风格
    - 可以是中文名或英文名，符合人类真实命名习惯（不要机械拼接风格词）
    - 示例：趋势追踪+激进风格 → `陈破浪` 或 `Chase Ryder`；均值回归+低换手 → `林静水` 或 `Miles Calm`
  - `style`：风格描述，如 `trend-following/intraday/strict-stop-loss`
  - `program_entry`：策略类入口，格式为 `trader_incubator.core.skills.seasons.<season-slug>.traders.<trader-slug>.strategy:TraderProgram`

### 3. 为每个交易员调用脚本
```bash
python scripts/create_trader_skills.py \
    --season "<season>" \
    --trader "<trader>" \
    --style "<style>" \
    --program-entry "<program_entry>" \
    [--symbols <code1> <code2> ...] \
    --project-root .
```

脚本自动完成：
1. 保存 `trader.json`
2. 生成 skill 文件（SKILL.md、agents/openai.yaml、references/identity.md、strategy.py）
3. 将交易员引用写入 `season.json` 的 `traders` 字段

## 生成的文件结构
```
src/trader_incubator/core/skills/seasons/<season-slug>/traders/<trader-slug>/
├── trader.json
├── SKILL.md
├── strategy.py          ← 继承 TradingStrategy，由 AI 实现交易逻辑
├── agents/openai.yaml
└── references/identity.md
```

## trader.json 结构
```json
{
  "trader": "Alpha Wolf",
  "season": "Season 1",
  "style": "trend-following/intraday/strict-stop-loss",
  "program_entry": "trader_incubator.core.skills.seasons.season-1.traders.alpha-wolf.strategy:TraderProgram",
  "symbols": ["000725", "600519"],
  "created_at": "2026-01-01T00:00:00Z"
}
```

## strategy.py 契约
每个交易员的 `strategy.py` 必须：
- 继承 `trader_incubator.exchange.TradingStrategy`
- 覆写 `on_minute(self, event_time, latest_bars)` 实现真实交易逻辑
- 可通过 `program_entry` 被 Exchange 动态加载

交易员本质是一个 AI skill，由 AI Agent 根据交易员的风格和市场数据制定策略，生成 `strategy.py` 中的交易代码。

## 错误处理
若必填字段缺失，向用户说明缺少哪些字段，不执行脚本。
