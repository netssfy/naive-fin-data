from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from trader_incubator.models import MarketTick, SeasonConfig, TradeRecord, TraderDefinition
from trader_incubator.program_api import TraderProgram, TraderProgramContext


def _load_program(program_entry: str) -> type[TraderProgram]:
    module_name, class_name = program_entry.split(":")
    module = import_module(module_name)
    klass = getattr(module, class_name)
    if not isinstance(klass, type) or not issubclass(klass, TraderProgram):
        raise TypeError(f"{program_entry} must point to a TraderProgram subclass.")
    return klass


@dataclass
class _TraderRuntime:
    definition: TraderDefinition
    program: TraderProgram
    context: TraderProgramContext


@dataclass
class ExchangeEngine:
    """
    Python-based exchange execution engine.

    Responsibilities:
    - load trader programs
    - execute programs every minute tick
    - record trader behavior
    """

    season: SeasonConfig
    _traders: dict[str, _TraderRuntime] = field(default_factory=dict)
    _records: list[TradeRecord] = field(default_factory=list)

    def register_trader(self, trader: TraderDefinition) -> None:
        program_class = _load_program(trader.program_entry)
        program = program_class()
        runtime = _TraderRuntime(
            definition=trader,
            program=program,
            context=TraderProgramContext(trader=trader, season=self.season),
        )
        self._traders[trader.trader_id] = runtime

    def run_minute_tick(self, tick: MarketTick) -> list[TradeRecord]:
        cycle_records: list[TradeRecord] = []
        for runtime in self._traders.values():
            signals = runtime.program.on_market_tick(tick, runtime.context)
            filtered = self._apply_symbol_guardrails(signals)
            record = TradeRecord(
                timestamp=tick.timestamp,
                trader_id=runtime.definition.trader_id,
                signals=filtered,
            )
            self._records.append(record)
            cycle_records.append(record)
        return cycle_records

    def run_non_trading_cycle(self) -> None:
        for runtime in self._traders.values():
            runtime.program.on_non_trading_time(runtime.context)

    @property
    def records(self) -> list[TradeRecord]:
        return list(self._records)

    def _apply_symbol_guardrails(self, signals: list[Any]) -> list[Any]:
        if self.season.tradable_symbols is None:
            return list(signals)
        return [s for s in signals if getattr(s, "symbol", None) in self.season.tradable_symbols]

