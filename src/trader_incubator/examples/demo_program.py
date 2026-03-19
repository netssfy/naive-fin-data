from __future__ import annotations

from trader_incubator.models import SignalAction, TradeSignal
from trader_incubator.program_api import TraderProgram, TraderProgramContext


class DemoTraderProgram(TraderProgram):
    """
    Minimal demo program:
    emits HOLD so we can verify exchange loading/execution/recording pipeline.
    """

    def on_market_tick(self, tick, context: TraderProgramContext) -> list[TradeSignal]:
        return [
            TradeSignal(
                action=SignalAction.HOLD,
                symbol="600000.SH",
                quantity=0,
                reason="demo_tick_received",
            )
        ]
