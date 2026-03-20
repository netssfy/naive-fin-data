---
name: 0号
description: Execute trader 0号 with style event-driven/swing/high-conviction for season s1. Use when this trader needs to analyze market data, produce trading signals, and refine strategy during non-trading time.
trader: 0号
season: s1
style: event-driven/swing/high-conviction
program_entry: trader_incubator.skills.seasons.s1.traders.0号.strategy:TraderProgram
symbols: [01810, 00700]
---

# 0号

## Trading Time Rules
- Analyze market input and emit tradable signals.
- Do not modify strategy during active trading hours.

## Non-Trading Time Rules
- Review trade outcomes.
- Research market updates.
- Propose and implement strategy improvements in `strategy.py`.

## Exchange Interface Contract
The strategy class in `strategy.py` must subclass `TradingStrategy` from `trader_incubator.exchange`
and be loadable by the Exchange via `program_entry`:
```python
import importlib
module, cls_name = "trader_incubator.skills.seasons.s1.traders.0号.strategy:TraderProgram".split(":")
strategy_cls = getattr(importlib.import_module(module), cls_name)
instance = strategy_cls(name="0号", symbols=['01810', '00700'])
```
