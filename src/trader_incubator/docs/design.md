# Trader Incubator 设计文档（当前实现）

## 1. 目标与范围
本文档描述 `src/trader_incubator` 当前已落地实现，覆盖以下模块：
- 核心交易引擎与数据层：`core/exchange.py`、`core/backtest.py`、`core/live.py`
- 赛季/交易员模型与结果持久化：`core/season.py`、`core/trader.py`、`core/persistence.py`
- 管理与编排 API：`core/server.py`
- 非交易时段研究触发：`core/trader_research.py`
- 前端与桌面壳：`apps/web`、`apps/desktop`

不包含尚未实现的长期规划能力（见 `docs/epic.md`）。

## 2. 架构总览
当前系统是一个三层架构：

1. 核心层（Python）
- 统一策略接口 `TradingStrategy`
- 回测运行时 `BacktestExchange`
- 实时运行时 `LiveExchange`
- 模拟撮合 `SimulatedMatchingEngine`

2. 服务层（FastAPI）
- Season/Trader 的 CRUD
- 读取 `orders.json` / `equity.json`
- 调用 Codex 自动创建交易员策略
- 应用启动时后台拉起 `run_all_seasons_live`

3. 展示层（Web + Electron）
- React 页面消费 FastAPI
- Electron 打包时内置 Web 资源并拉起 Python API

## 3. 目录与职责

### 3.1 core 模块
- `exchange.py`
  - `SymbolRef`：统一 symbol key（`type:market:code`）
  - `TradingStrategy`：策略生命周期与交易 API
  - `SimulatedMatchingEngine`：市价单撮合、持仓、现金、手续费
  - `HistoricalDataStore`：本地 parquet 历史数据读取（单周期）
  - `Exchange`：基于交易时段的实时调度框架
  - `MarketCloseEventDetector`：按市场/交易日触发一次收盘事件

- `backtest.py`
  - `MultiPeriodHistoricalDataStore`：多周期历史数据缓存与读取（1m/5m/15m/30m/60m/1d）
  - `BacktestExchange`：分钟推进、禁止未来函数（history 截断到当前回测时刻）
  - `run_season_backtest`：赛季回测入口，支持结果落盘
  - `load_season_strategies`：按 season/trader 配置动态加载策略类

- `live.py`
  - `MultiSourceDataFeed`：实时多源拉取（AkShare -> Baostock -> yfinance）
  - `LiveMarketDataStore`：多周期行情缓存；按 symbol+period+minute 控制刷新
  - `LiveExchange`：实盘分钟级驱动（当前下单仍为模拟撮合）
  - `run_season_live`：单赛季 live 入口
  - `run_all_seasons_live`：多赛季并行运行（共享时钟与数据源）
  - 收盘后可触发 `run_season_trader_research`

- `persistence.py`
  - `save_orders`：按 trader 追加/去重写入 `orders.json`
  - `compute_daily_equity` + `save_equity`：写入每日权益快照 `equity.json`
  - `persist_backtest_results`：批量持久化订单和权益

- `season.py` / `trader.py`
  - 定义 Season/Trader 数据模型
  - 提供 slug/module 名规范化
  - 负责 JSON 文件读写

- `server.py`
  - FastAPI 应用与 REST 路由
  - 支持 `POST /api/seasons/{season_slug}/traders/codex`
    - 手动模式：先建 trader，再让 codex 改进策略文件
    - 自动模式：让 codex 基于脚本自动创建 trader
  - 提供 NDJSON 流式日志返回（`stream=true`）

- `trader_research.py`
  - 发现 season 下所有 trader
  - 生成复盘 prompt
  - 调用 `codex exec` 执行非交易时段策略改进

### 3.2 技能与配置目录
- 赛季配置：`src/trader_incubator/core/skills/seasons/<season>/season.json`
- 交易员配置：`.../traders/<trader>/trader.json`
- 策略代码：`.../traders/<trader>/strategy.py`
- 交易结果：`.../traders/<trader>/orders.json`、`equity.json`

### 3.3 前端与桌面壳
- `apps/web`
  - React + TypeScript + Vite + React Router + Zustand + Tailwind
  - 通过 API 拉取季赛、交易员、权益、订单
  - 支持调用后端 codex 创建交易员（含流式日志）

- `apps/desktop`
  - Electron 壳，主进程 `main.js`
  - 开发/打包均可自动启动 Python `core/server.py`
  - 打包后加载 `web-dist` 并内置 core 资源

## 4. 核心运行流程

### 4.1 回测流程（`run_season_backtest`）
1. 解析时间窗口并加载 season/trader。
2. 构建策略实例（兼容多种构造函数签名）。
3. 预热多周期历史数据。
4. 从 `start_at` 到 `end_at` 按分钟推进：
- 拉取各 symbol 对应分钟最新 bar。
- 调用策略 `on_minute`。
- 策略调用 `place_market_order` 进入模拟撮合。
5. 记录每日收盘价并持久化订单/权益。

### 4.2 实盘流程（`run_season_live`）
1. 加载策略并初始化 `LiveExchange`。
2. 每分钟 tick 时按市场交易时段决定是否执行。
3. 多源获取实时数据并更新缓存。
4. 执行 `on_minute`，下单进入模拟撮合。
5. 结束后将结果持久化为 `orders.json`/`equity.json`。

### 4.3 多赛季实盘（`run_all_seasons_live`）
1. 自动筛选当前有效 season（基于 `start_date/end_date`）。
2. 为每个 season 创建独立 `LiveExchange`（订单与持仓隔离）。
3. 共享一个 `RealClock` + `MultiSourceDataFeed` + `LiveMarketDataStore` 降低拉取开销。
4. 每分钟统一驱动所有 season tick。
5. 通过 `MarketCloseEventDetector` 在收盘时触发一次 trader research。

## 5. 数据与文件约定
- 历史行情：`data/<type>/<market>/<code>/<period>/*.parquet`
- season 文件：`src/trader_incubator/core/skills/seasons/<season>/season.json`
- trader 文件：`.../traders/<trader>/trader.json`
- 策略入口：`program_entry = module.path:ClassName`

## 6. API 概要（`core/server.py`）
- `GET /health`
- `GET/POST /api/seasons`
- `GET/PUT/DELETE /api/seasons/{season_slug}`
- `GET/POST /api/seasons/{season_slug}/traders`
- `POST /api/seasons/{season_slug}/traders/codex`
- `GET/PUT/DELETE /api/seasons/{season_slug}/traders/{trader_slug}`
- `GET /api/seasons/{season_slug}/equity`
- `GET /api/seasons/{season_slug}/orders`

## 7. 测试覆盖（当前）
`core/tests` 已覆盖主要链路：
- 回测分钟推进、无未来数据泄露、资金继承逻辑
- live 在交易时段/非交易时段行为
- 多赛季收盘研究触发
- server 的 season/trader CRUD 与 codex 分支流程

## 8. 关键约束与已知限制
- “live” 当前仍是模拟成交，不接券商网关。
- 交易日历仅按周末过滤，未接入法定节假日日历。
- 撮合逻辑按 bar close 成交，未建模深度撮合。
- 费用模型为统一费率，未细分佣金/税费/滑点模型。
- 部分模块使用 `from exchange import ...` 这类导入方式，运行环境需保证 `core` 模块可被直接解析。

## 9. 与旧文档差异（本次修正）
- 核心路径统一为 `src/trader_incubator/core/*`（非旧版根目录扁平结构）。
- 当前已存在前端与桌面壳，不再是“仅核心引擎”。
- 当前仓库无 `orchestrator.py`，改为 `server.py + run_all_seasons_live` 组合运行。
