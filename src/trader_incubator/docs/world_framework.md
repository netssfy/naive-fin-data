# 交易员孵化世界框架（仅框架/引擎）

## 目标
当前实现仅搭建世界框架，不实现任何具体交易策略或交易员风格细节。

## 组件映射
- 世界系统：`trader_incubator.world.WorldKernel`
- 交易所：`trader_incubator.exchange.ExchangeEngine`
- 帅帅（Skill 驱动）：`SkillSpec(name="帅帅", skill_md_path=...)` + `DeerFlowEmbeddedSkillRuntime`
- 交易员（Skill 驱动）：`TraderDefinition.trader_skill`
- 交易员交易程序（Python）：`program_entry="module.path:ClassName"`，由交易所动态加载

## 关键约束如何落地
- AI 驱动：`DeerFlowEmbeddedSkillRuntime` 使用 deer-flow Embedded Python Client。
- 帅帅创建交易员：`WorldKernel.bootstrap_traders(...)`。
- 交易员在非交易时段调整程序：`WorldKernel.request_trader_program_update(...)`。
- 交易所按分钟执行：`ExchangeEngine.run_minute_tick(...)`。
- 交易标的约束：`ExchangeEngine` 内置代码池过滤。

## 后续扩展点（已预留）
- 将 `bootstrap_traders` 输出从“原始文本”升级为结构化解析器。
- 将交易记录写入存储（数据库/事件流）。
- 引入交易时间判定器，由世界系统调度 `run_trading_minute` 与 `run_non_trading_cycle`。
- 在可视化面板读取 `season/traders/records` 进行展示。

