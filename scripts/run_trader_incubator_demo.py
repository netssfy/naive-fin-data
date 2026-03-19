from __future__ import annotations

from datetime import datetime
from pathlib import Path

from trader_incubator.exchange import ExchangeEngine
from trader_incubator.models import Market, MarketTick, SeasonConfig, SkillSpec, TraderDefinition


def main() -> int:
    season = SeasonConfig(
        season_id="demo-season-001",
        market=Market.CN_A,
        starts_at=datetime(2026, 3, 19, 9, 30),
        tradable_symbols={"600000.SH"},
    )
    engine = ExchangeEngine(season=season)
    trader = TraderDefinition(
        trader_id="trader-demo-01",
        name="演示交易员",
        style="framework-smoke-test",
        creator_skill=SkillSpec(name="帅帅", skill_md_path=Path("dummy/shuaishu/SKILL.md")),
        trader_skill=SkillSpec(name="交易员-演示", skill_md_path=Path("dummy/trader/SKILL.md")),
        program_entry="trader_incubator.examples.demo_program:DemoTraderProgram",
    )
    engine.register_trader(trader)
    tick = MarketTick(timestamp=datetime(2026, 3, 19, 9, 31), market_data={"600000.SH": {"price": 10.5}})
    records = engine.run_minute_tick(tick)

    print("=== 交易所引擎演示输出 ===")
    for record in records:
        print(f"trader_id={record.trader_id}, timestamp={record.timestamp.isoformat()}")
        for signal in record.signals:
            print(
                f"  signal action={signal.action.value}, symbol={signal.symbol}, "
                f"qty={signal.quantity}, reason={signal.reason}"
            )
    print(f"total_records={len(engine.records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
