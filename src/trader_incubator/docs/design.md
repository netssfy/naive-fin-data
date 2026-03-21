# Trader Incubator 设计文档（当前实现）

## 1. 目标与范围
本文档描述 `src/trader_incubator` 当前代码实现的设计与职责划分，覆盖：
- 回测引擎（`backtest.py`）
- 实盘引擎（`live.py`）
- 交易执行与基础抽象（`exchange.py`）
- 赛季/交易员模型（`season.py`、`trader.py`）
- 包导出层（`__init__.py`）
- 当前示例策略与辅助脚本（`skills/seasons/...`、`skills/帅帅/scripts/...`）

不包含前端与可视化实现（当前目录无相关源码）。

## 2. 系统总览
系统围绕“策略按分钟触发”的统一运行模型实现，核心分为两条运行路径：
- 回测路径：从本地 parquet 历史数据读取，按分钟推进时间。
- 实盘路径：从 AkShare / yfinance 拉取当日分钟数据，按真实时钟推进。

统一抽象：
- `TradingStrategy`：策略基类，定义策略生命周期与下单/查仓接口。
- `SimulatedMatchingEngine`：模拟撮合和资金/持仓记账。
- `Order`：订单与成交结果的统一结构。

## 3. 目录与组件

### 3.1 核心模块
- `exchange.py`：交易基础设施（符号、时钟、会话、撮合、策略基类、实时交易所框架）
- `backtest.py`：回测数据存储、回测交易所、赛季策略加载、CLI
- `live.py`：多源实时数据拉取、实盘缓存存储、实盘交易所、CLI
- `season.py`：赛季数据模型与 JSON 文件持久化
- `trader.py`：交易员数据模型与 JSON 文件持久化
- `__init__.py`：包级 API 导出与 `LiveExchange` 惰性导入

### 3.2 赛季资产与脚本
- `skills/seasons/<season>/season.json`：赛季配置
- `skills/seasons/<season>/traders/<trader>/trader.json`：交易员配置
- `skills/seasons/<season>/traders/<trader>/strategy.py`：策略代码入口
- `skills/帅帅/scripts/season_manager.py`：创建/查看赛季配置
- `skills/帅帅/scripts/create_trader_skills.py`：创建交易员目录、策略模板并回写赛季 roster

## 4. 运行时流程

### 4.1 回测流程（`run_season_backtest`）
1. 解析时间窗口（支持 `str/date/datetime`）。
2. 加载赛季与交易员配置，生成策略实例（`load_season_strategies`）。
3. 初始化 `MultiPeriodHistoricalDataStore`（多周期历史数据）。
4. 初始化 `BacktestExchange` 并绑定策略。
5. 从 `start_at` 到 `end_at` 逐分钟循环：
- 取各 symbol 最新 1m bar。
- 调用各策略 `on_minute`。
- 策略内部可调用 `place_market_order`，进入模拟撮合。
6. 返回 `BacktestResult`（触发分钟数、订单列表）。

### 4.2 实盘流程（`run_season_live`）
1. 加载赛季策略。
2. 初始化 `LiveExchange` 与 `LiveMarketDataStore`。
3. 预热数据缓存。
4. 每分钟 tick：
- 拉取/刷新最新分钟数据（AkShare 优先，失败 fallback yfinance）。
- 调用策略 `on_minute`。
- 订单走 `SimulatedMatchingEngine`（当前仍是模拟撮合，不对接真实券商）。
5. 达到 `max_minutes` 或 `end_time` 后结束，返回分钟数与订单列表。

### 4.3 多赛季实盘流程（`run_all_seasons_live`）
1. 扫描 `skills/seasons/*/season.json` 并筛选“有效 season”：
- `start_date <= today`
- `end_date` 为空或 `end_date >= today`
2. 每个 season 创建一个独立 `LiveExchange`（独立撮合引擎、独立持仓与订单账本）。
3. 所有 season 的 exchange 共享同一个 `MultiSourceDataFeed`（带缓存）。
4. 每个 exchange 使用自己的 `LiveMarketDataStore`，但通过共享 feed 复用网络请求结果。
5. 外层调度器按分钟统一驱动各 exchange 的 `run_tick`，保证节奏一致同时保持交易隔离。

## 5. 类与职责

### 5.1 `exchange.py`
- `SymbolRef`
  - 职责：统一 symbol 表示（`type:market:code`），提供解析与 key 规范。
- `TradingSessionConfig`
  - 职责：描述交易时段配置（开收盘、预开盘、时区）。
- `SessionWindow`
  - 职责：承载某交易日的 pre-open/open/close 时间窗口。
- `Order`
  - 职责：承载订单结果（状态、成交价、原因信息）。
- `RealClock`
  - 职责：封装当前时间与 sleep，便于 runtime 控制与测试替换。
- `HistoricalDataStore`
  - 职责：读取本地单周期 parquet 数据（默认 1m），提供历史窗口和 latest bar 查询。
- `SimulatedMatchingEngine`
  - 职责：执行市价单模拟成交、维护订单列表、持仓和现金账本。
  - 成交规则：以当前 bar 的 `close` 作为成交价；无行情/无效价格则拒单。
- `TradingStrategy`
  - 职责：策略基类与统一接口。
  - 生命周期钩子：`on_pre_open` / `on_minute` / `on_post_close`。
  - 交易接口：`history`、`place_market_order`、`get_position(s)`、`get_trade_history`。
- `Exchange`
  - 职责：实时运行框架（会话时间控制 + 分钟触发 + 策略调度 + 下单路由）。

### 5.2 `backtest.py`
- `BacktestResult`
  - 职责：封装回测输出摘要。
- `MultiPeriodHistoricalDataStore`
  - 职责：加载多周期历史数据（`1m/5m/15m/30m/60m/1d`），提供历史与 latest 查询。
  - 特点：按 symbol+period 缓存，读取后统一时区与时间过滤。
- `BacktestExchange`
  - 职责：回测专用调度器（虚拟时钟推进），接口与 `TradingStrategy` 对齐。
  - 特点：`get_history` 会把 `end_time` 截断到当前回测时刻，防止未来函数。
- `load_season_strategies`
  - 职责：将 season/trader 配置解析为可运行策略对象。
  - 规则：trader 层 `symbols/initial_capital` 优先，否则回退 season 默认值。
- `_instantiate_strategy`
  - 职责：兼容不同策略构造签名，最终确保对象是 `TradingStrategy` 子类。
- CLI (`main`)
  - 职责：提供命令行快速回测入口。

### 5.3 `live.py`
- `MultiSourceDataFeed`
  - 职责：封装实时数据源优先级（AkShare -> yfinance）。
  - 特点：带请求级缓存（按 symbol/period/time-window），供多 session 共享。
- `LiveMarketDataStore`
  - 职责：维护实盘多周期缓存；提供 latest 1m 和历史切片。
  - 特点：网络侧只拉取 `1m`，`5m/15m/30m/60m/1d` 由本地重采样构建；同分钟同 symbol+period 只刷新一次。
- `LiveExchange`
  - 职责：实盘分钟调度与策略执行（当前订单撮合同样走模拟引擎）；支持注入 `data_store` 与共享 `clock`。
  - 关键接口：`prepare`（预热）与 `run_tick`（单分钟执行），便于外层多 session 协调调度。
- `list_valid_season_slugs`
  - 职责：发现当前有效赛季列表。
- `run_all_seasons_live`
  - 职责：以“一个 season 一个 exchange session”的隔离模型执行多赛季 live，并共享行情源降低请求成本。
- CLI (`main`)
  - 职责：提供命令行实盘运行入口（单赛季/多赛季）。

### 5.4 `season.py`
- `SeasonTraderRef`
  - 职责：赛季 roster 中的轻量交易员引用（名称、风格、程序入口）。
- `Season`
  - 职责：赛季聚合根，管理市场、赛期、初始资金、可交易标的池、交易员 roster。
  - 能力：JSON 序列化、保存/加载、`add_trader` 去重更新（按 slug）。
- `slugify` / `to_module_name`
  - 职责：统一文件路径和模块命名约定。

### 5.5 `trader.py`
- `Trader`
  - 职责：交易员配置模型，承载策略入口、风格、可交易标的、可选初始资金。
  - 能力：JSON 序列化、保存/加载、按赛季批量加载 `load_all`。

### 5.6 `__init__.py`
- 包导出职责：统一暴露常用 API（`TradingStrategy`, `Exchange`, `run_season_backtest` 等）。
- 惰性导入职责：通过 `__getattr__` 延迟导入 `LiveExchange/run_season_live`，避免不必要依赖加载。

## 6. 数据与文件约定
- 历史行情目录：`<project>/data/<type>/<market>/<code>/<period>/*.parquet`
- 赛季配置：`src/trader_incubator/skills/seasons/<season_slug>/season.json`
- 交易员配置：`src/trader_incubator/skills/seasons/<season_slug>/traders/<trader_slug>/trader.json`
- 策略入口：`program_entry` 采用 `module.path:ClassName`

## 7. 关键设计决策（当前实现）
- 回测与实盘共享策略接口和撮合引擎，降低策略迁移成本。
- 数据层按 symbol 缓存并惰性加载，减少重复 IO。
- 策略加载支持“宽松构造签名”，提高历史策略兼容性。
- 实盘数据采用多源兜底，优先国内数据接口，失败时退化到 yfinance。

## 8. 已知限制与 Review 关注点
- 当前“实盘”仍为模拟下单，不含真实券商网关。
- 会话日历仅处理周末，不含法定节假日与夜盘。
- 模拟撮合使用 bar close 成交，未建模滑点、手续费、撮合深度。
- 风控能力较基础：下单合法性检查有限，未做统一风险限额。
- `HistoricalDataStore` 仅支持初始化周期（默认 1m）；多周期能力主要在回测与实盘数据存储中。
- 文档 `epic.md` 体现了远期目标，和当前落地实现之间仍有功能差距（例如非交易时段策略演化流程仍未在核心引擎实现）。

## 9. 示例策略现状
`skills/seasons/s1/traders/trader0/strategy.py` 中的 `TraderProgram` 是测试策略：
- 每 5 分钟随机挑选一个可用 symbol
- 随机买卖与手数
- 卖出时会检查持仓，避免负持仓

它主要用于验证引擎调度与下单链路，不代表生产级策略实现。

## 10. CLI 启动示例
- 单赛季 live：
```bash
python -m trader_incubator.live --season s1 --max-minutes 5
```
- 多赛季 live（标准参数）：
```bash
python -m trader_incubator.live --all-seasons --max-minutes 5
```
- 多赛季 live（兼容别名，按当前实现支持）：
```bash
python -m trader_incubator.live --all-seaons --max-minutes 5
```

## 11. 主控循环（Orchestrator）
- 文件：`trader_incubator/orchestrator.py`
- 目标：在一个长期运行进程中自动切换两种模式：
  - 交易时段：拉起并守护 `live --all-seasons`
  - 非交易时段：按交易员触发 `codex cli` 复盘和策略改进
- 关键设计：
  - 每天只触发一次非交易时段研究任务（状态文件去重）
  - 子进程方式管理 live，切到非交易时段会安全停止 live 进程
  - 主控进程自动注入 `PYTHONPATH=src` 供子进程导入项目模块

示例：
```bash
python -m trader_incubator.orchestrator --poll-seconds 30
```

仅演练一次循环（不真的执行子进程）：
```bash
python -m trader_incubator.orchestrator --once --dry-run
```
