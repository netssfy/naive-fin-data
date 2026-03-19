from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trader_incubator.models import MarketTick, SeasonConfig, TradeSignal, TraderDefinition


@dataclass
class TraderProgramContext:
    trader: TraderDefinition
    season: SeasonConfig
    state: dict[str, Any] = field(default_factory=dict)


class TraderProgram(ABC):
    """Interface for trader strategy code loaded by the exchange engine."""

    @abstractmethod
    def on_market_tick(
        self,
        tick: MarketTick,
        context: TraderProgramContext,
    ) -> list[TradeSignal]:
        """Produce signals from market tick input."""

    def on_non_trading_time(self, context: TraderProgramContext) -> None:
        """Optional hook used by the world during non-trading time."""
        return None

