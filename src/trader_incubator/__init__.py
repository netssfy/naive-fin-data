from trader_incubator.backtest import BacktestResult, run_season_backtest
from trader_incubator.exchange import Exchange, Order, SymbolRef, TradingSessionConfig, TradingStrategy
from trader_incubator.season import Season, SeasonTraderRef
from trader_incubator.trader import Trader

__all__ = [
    "BacktestResult",
    "Exchange",
    "Order",
    "SymbolRef",
    "TradingSessionConfig",
    "TradingStrategy",
    "LiveExchange",
    "run_season_backtest",
    "run_season_live",
    "Season",
    "SeasonTraderRef",
    "Trader",
]


def __getattr__(name: str):
    if name in {"LiveExchange", "run_season_live"}:
        from trader_incubator.live import LiveExchange, run_season_live

        return {"LiveExchange": LiveExchange, "run_season_live": run_season_live}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

