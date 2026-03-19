from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trader_incubator.exchange import ExchangeEngine
from trader_incubator.models import MarketTick, SeasonConfig, SkillSpec, TraderDefinition
from trader_incubator.skill_runtime import DeerFlowEmbeddedSkillRuntime


@dataclass
class WorldKernel:
    """
    World runtime orchestrator for trader incubation.

    Scope:
    - initialization phase orchestration
    - trading phase orchestration
    - non-trading phase orchestration
    """

    season: SeasonConfig
    shuaishu_skill: SkillSpec
    skill_runtime: DeerFlowEmbeddedSkillRuntime
    exchange: ExchangeEngine = field(init=False)
    traders: dict[str, TraderDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.exchange = ExchangeEngine(season=self.season)

    def bootstrap_traders(self, desired_count: int) -> str:
        """
        Ask 帅帅 skill to design trader roster.

        This function intentionally stores raw AI output for the next stage parser.
        """
        payload: dict[str, Any] = {
            "season": _season_payload(self.season),
            "desired_count": desired_count,
            "requirements": {
                "must_be_skill_driven": True,
                "style_similarity_max_pairwise": 0.5,
            },
        }
        result = self.skill_runtime.invoke_skill(self.shuaishu_skill, payload)
        return result.raw_response

    def register_traders(self, trader_defs: list[TraderDefinition]) -> None:
        for trader in trader_defs:
            self.traders[trader.trader_id] = trader
            self.exchange.register_trader(trader)

    def run_trading_minute(self, market_data: dict[str, Any], now: datetime) -> None:
        tick = MarketTick(timestamp=now, market_data=market_data)
        self.exchange.run_minute_tick(tick)

    def run_non_trading_cycle(self) -> None:
        self.exchange.run_non_trading_cycle()

    def request_trader_program_update(
        self,
        trader: TraderDefinition,
        market_research: dict[str, Any],
    ) -> str:
        """
        Ask trader skill to evolve its own Python program.
        """
        payload = {
            "season": _season_payload(self.season),
            "trader": {
                "id": trader.trader_id,
                "name": trader.name,
                "style": trader.style,
                "program_entry": trader.program_entry,
            },
            "market_research": market_research,
            "constraints": {
                "do_not_change_strategy_during_trading_hours": True,
            },
        }
        result = self.skill_runtime.invoke_skill(trader.trader_skill, payload)
        return result.raw_response


def _season_payload(season: SeasonConfig) -> dict[str, Any]:
    return {
        "season_id": season.season_id,
        "market": season.market.value,
        "starts_at": season.starts_at.isoformat(),
        "ends_at": season.ends_at.isoformat() if season.ends_at else None,
        "tradable_symbols": sorted(season.tradable_symbols) if season.tradable_symbols else None,
    }

