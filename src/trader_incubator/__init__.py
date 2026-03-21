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
    "run_all_seasons_live",
    "list_valid_season_slugs",
    "Season",
    "SeasonTraderRef",
    "Trader",
]


def __getattr__(name: str):
    if name in {"LiveExchange", "run_season_live", "run_all_seasons_live", "list_valid_season_slugs"}:
        from trader_incubator.live import LiveExchange, list_valid_season_slugs, run_all_seasons_live, run_season_live

        return {
            "LiveExchange": LiveExchange,
            "run_season_live": run_season_live,
            "run_all_seasons_live": run_all_seasons_live,
            "list_valid_season_slugs": list_valid_season_slugs,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

