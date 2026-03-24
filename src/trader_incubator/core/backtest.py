from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import importlib
import importlib.util
import logging
from pathlib import Path
import sys
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from exchange import (
    Order,
    SimulatedMatchingEngine,
    SymbolRef,
    TradingStrategy,
    _ensure_timezone,
    _floor_to_minute,
)
from persistence import persist_backtest_results
from season import Season
from trader import Trader


SUPPORTED_PERIODS: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "1d")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestResult:
    season_slug: str
    start_at: datetime
    end_at: datetime
    triggered_minutes: int
    orders: list[Order]


class MultiPeriodHistoricalDataStore:
    def __init__(
        self,
        project_root: Path | str,
        start_at: datetime,
        end_at: datetime,
        periods: Sequence[str] = SUPPORTED_PERIODS,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self.project_root = Path(project_root)
        self.data_root = self.project_root / "data"
        self.tz = ZoneInfo(timezone)
        self.start_at = _ensure_timezone(start_at, self.tz)
        self.end_at = _ensure_timezone(end_at, self.tz)
        self.periods = tuple(str(item).strip().lower() for item in periods)
        self._catalog: dict[tuple[str, str], list[Path]] = self._build_catalog()
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}

    def _build_catalog(self) -> dict[tuple[str, str], list[Path]]:
        catalog: dict[tuple[str, str], list[Path]] = {}
        for parquet_file in self.data_root.glob("*/*/*/*/*.parquet"):
            rel = parquet_file.relative_to(self.data_root)
            if len(rel.parts) != 5:
                continue
            type_name, market, code, period, _ = rel.parts
            normalized_period = str(period).strip().lower()
            if normalized_period not in self.periods:
                continue
            symbol_key = SymbolRef(code=code, market=market, type_name=type_name).key
            catalog.setdefault((normalized_period, symbol_key), []).append(parquet_file)
        return catalog

    def warmup(self, symbols: Sequence[SymbolRef]) -> None:
        for symbol in symbols:
            for period in self.periods:
                self._load_symbol_period(symbol=symbol, period=period)

    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        if "timestamp" not in out.columns:
            return out.iloc[0:0]
        out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
        out = out.dropna(subset=["timestamp"]).reset_index(drop=True)
        if out.empty:
            return out
        if out["timestamp"].dt.tz is None:
            out["timestamp"] = out["timestamp"].dt.tz_localize(self.tz)
        else:
            out["timestamp"] = out["timestamp"].dt.tz_convert(self.tz)
        out = out[(out["timestamp"] >= self.start_at) & (out["timestamp"] <= self.end_at)]
        return out.sort_values("timestamp").reset_index(drop=True)

    def _load_symbol_period(self, symbol: SymbolRef, period: str) -> pd.DataFrame:
        normalized_period = str(period).strip().lower()
        cache_key = (normalized_period, symbol.key)
        if cache_key in self._cache:
            return self._cache[cache_key]

        parquet_files = sorted(self._catalog.get(cache_key, []))
        if not parquet_files:
            empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"])
            self._cache[cache_key] = empty
            return empty

        frames: list[pd.DataFrame] = []
        for parquet_file in parquet_files:
            try:
                frames.append(pd.read_parquet(parquet_file))
            except Exception:
                continue
        if not frames:
            empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"])
            self._cache[cache_key] = empty
            return empty

        merged = pd.concat(frames, ignore_index=True)
        merged = self._normalize_df(merged)
        self._cache[cache_key] = merged
        return merged

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str = "1m",
    ) -> pd.DataFrame:
        normalized_period = str(period).strip().lower()
        if normalized_period not in self.periods:
            raise ValueError(f"unsupported period: {period}")
        df = self._load_symbol_period(symbol=symbol, period=normalized_period)
        if df.empty:
            return df.copy()

        out = df
        if end_time is not None:
            end_ts = _ensure_timezone(end_time, self.tz)
            out = out[out["timestamp"] <= end_ts]
        if lookback > 0:
            out = out.tail(lookback)
        return out.reset_index(drop=True).copy()

    def latest_bars(self, symbols: Sequence[SymbolRef], at: datetime, period: str = "1m") -> dict[str, pd.Series]:
        normalized_period = str(period).strip().lower()
        at_ts = _ensure_timezone(at, self.tz)
        result: dict[str, pd.Series] = {}
        for symbol in symbols:
            df = self._load_symbol_period(symbol=symbol, period=normalized_period)
            if df.empty:
                continue
            bar = df[df["timestamp"] <= at_ts].tail(1)
            if bar.empty:
                continue
            result[symbol.key] = bar.iloc[0]
        return result


class BacktestExchange:
    def __init__(
        self,
        strategies: Sequence[TradingStrategy],
        data_store: MultiPeriodHistoricalDataStore,
        debug: bool = False,
        fee_rate: float = 0.0,
    ) -> None:
        self.strategies = list(strategies)
        self.data_store = data_store
        self.matching_engine = SimulatedMatchingEngine(fee_rate=fee_rate)
        self.debug = bool(debug)
        self._current_time: datetime | None = None
        self._current_bars: dict[str, pd.Series] = {}
        # date -> {symbol_key -> close_price}, populated at end of each trading day
        self.daily_close_prices: dict[date, dict[str, float]] = {}
        for strategy in self.strategies:
            strategy._bind_exchange(self)  # type: ignore[arg-type]
            self.matching_engine.seed_cash(strategy_name=strategy.name, initial_cash=strategy.initial_capital)

    def run(self, start_at: datetime, end_at: datetime) -> int:
        start_ts = _floor_to_minute(_ensure_timezone(start_at, self.data_store.tz))
        end_ts = _floor_to_minute(_ensure_timezone(end_at, self.data_store.tz))
        if end_ts < start_ts:
            raise ValueError("end_at must be >= start_at")

        subscribed_symbols = self._collect_subscribed_symbols()
        self.data_store.warmup(subscribed_symbols)

        cursor = start_ts
        triggered_minutes = 0
        prev_date: date | None = None
        while cursor <= end_ts:
            self._current_time = cursor
            self._current_bars = self.data_store.latest_bars(subscribed_symbols, at=cursor, period="1m")
            if self.debug:
                print(
                    f"[BT][{cursor.isoformat()}] tick "
                    f"bars={len(self._current_bars)} strategies={len(self.strategies)}"
                )
            for strategy in self.strategies:
                strategy_bars = {
                    symbol.key: self._current_bars[symbol.key]
                    for symbol in strategy.symbols
                    if symbol.key in self._current_bars
                }
                before_orders = len(self.matching_engine.orders)
                strategy.on_minute(cursor, strategy_bars)
                if self.debug:
                    new_orders = len(self.matching_engine.orders) - before_orders
                    print(
                        f"[BT][{cursor.isoformat()}] strategy={strategy.name} "
                        f"bars={len(strategy_bars)} new_orders={new_orders}"
                    )

            current_date = cursor.date()
            next_cursor = cursor + timedelta(minutes=1)
            # record close prices when the day rolls over or at the very last tick
            is_last_tick = next_cursor > end_ts
            is_day_end = next_cursor.date() != current_date
            if (is_day_end or is_last_tick) and self._current_bars:
                self.daily_close_prices[current_date] = {
                    sym_key: float(bar.get("close", 0.0) or 0.0)
                    for sym_key, bar in self._current_bars.items()
                }

            triggered_minutes += 1
            cursor = next_cursor
        return triggered_minutes

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str = "1m",
    ) -> pd.DataFrame:
        capped_end_time = self._cap_end_time(end_time)
        return self.data_store.get_history(symbol=symbol, lookback=lookback, end_time=capped_end_time, period=period)

    def place_market_order(self, strategy_name: str, symbol: SymbolRef, side: str, quantity: int) -> Order:
        submitted_at = self._current_time or self.data_store.start_at
        bar = self._current_bars.get(symbol.key)
        return self.matching_engine.submit_market_order(
            strategy_name=strategy_name,
            symbol=symbol,
            side=side,
            quantity=quantity,
            submitted_at=submitted_at,
            bar=bar,
        )

    def get_position(self, strategy_name: str, code: str, market: str = "cn", type_name: str = "stock") -> int:
        symbol = SymbolRef(code=str(code).strip(), market=market, type_name=type_name)
        return self.matching_engine.get_position(strategy_name=strategy_name, symbol=symbol)

    def list_orders(self, strategy_name: str | None = None) -> list[Order]:
        if strategy_name is None:
            return list(self.matching_engine.orders)
        return [item for item in self.matching_engine.orders if item.strategy_name == strategy_name]

    def _get_positions_for_strategy(self, strategy_name: str) -> dict[str, int]:
        return self.matching_engine.get_positions(strategy_name=strategy_name)

    def _get_trade_history_for_strategy(self, strategy_name: str) -> list[Order]:
        return self.matching_engine.get_trade_history(strategy_name=strategy_name)

    def _cap_end_time(self, end_time: datetime | None) -> datetime | None:
        if self._current_time is None:
            return end_time
        if end_time is None:
            return self._current_time
        normalized = _ensure_timezone(end_time, self.data_store.tz)
        return min(normalized, self._current_time)

    def _collect_subscribed_symbols(self) -> list[SymbolRef]:
        seen = set()
        out: list[SymbolRef] = []
        for strategy in self.strategies:
            for symbol in strategy.symbols:
                if symbol.key in seen:
                    continue
                seen.add(symbol.key)
                out.append(symbol)
        return out


def run_season_backtest(
    start_date: str | date | datetime,
    end_date: str | date | datetime,
    season_slug: str,
    project_root: Path | str = ".",
    timezone: str = "Asia/Shanghai",
    debug: bool = False,
    persist: bool = True,
) -> BacktestResult:
    tz = ZoneInfo(timezone)
    start_at = _to_datetime(start_date, tz=tz, is_end=False)
    end_at = _to_datetime(end_date, tz=tz, is_end=True)
    if end_at < start_at:
        raise ValueError("end_date must be >= start_date")

    strategies = load_season_strategies(season_slug=season_slug, project_root=project_root)
    if debug:
        print(
            f"[BT] season={season_slug} strategies={len(strategies)} "
            f"start={start_at.isoformat()} end={end_at.isoformat()}"
        )
    season = Season.load(season_slug=season_slug, project_root=project_root)
    data_store = MultiPeriodHistoricalDataStore(
        project_root=project_root,
        start_at=start_at,
        end_at=end_at,
        periods=SUPPORTED_PERIODS,
        timezone=timezone,
    )
    exchange = BacktestExchange(
        strategies=strategies,
        data_store=data_store,
        debug=debug,
        fee_rate=season.fee_rate,
    )
    triggered_minutes = exchange.run(start_at=start_at, end_at=end_at)

    if persist and exchange.daily_close_prices:
        strategies_meta = [
            {
                "name": s.name,
                "slug": s.name,  # trader slug == strategy name in backtest
                "initial_capital": s.initial_capital,
            }
            for s in strategies
        ]
        persist_backtest_results(
            project_root=Path(project_root),
            season_slug=season_slug,
            engine=exchange.matching_engine,
            strategies_meta=strategies_meta,
            close_prices_by_date=exchange.daily_close_prices,
        )

    return BacktestResult(
        season_slug=season_slug,
        start_at=start_at,
        end_at=end_at,
        triggered_minutes=triggered_minutes,
        orders=exchange.list_orders(),
    )


def load_season_strategies(season_slug: str, project_root: Path | str = ".") -> list[TradingStrategy]:
    season = Season.load(season_slug=season_slug, project_root=project_root)
    traders = Trader.load_all(season_slug=season_slug, project_root=project_root)
    market = _normalize_market(season.market)
    traders_by_slug = {item.slug: item for item in traders}

    strategies: list[TradingStrategy] = []
    for ref in season.traders:
        trader_obj = traders_by_slug.get(ref.slug)
        symbols = list(trader_obj.symbols) if trader_obj and trader_obj.symbols else list(season.symbol_pool)
        initial_capital = (
            float(trader_obj.initial_capital)
            if trader_obj and trader_obj.initial_capital is not None
            else float(season.initial_capital)
        )
        if not symbols:
            continue
        try:
            strategy = _instantiate_strategy(
                program_entry=ref.program_entry,
                strategy_name=ref.trader,
                symbols=symbols,
                market=market,
                initial_capital=initial_capital,
                project_root=Path(project_root),
            )
            strategies.append(strategy)
        except Exception as exc:
            logger.warning(
                "[backtest] skip invalid trader strategy season=%s trader=%s program_entry=%s error=%s",
                season_slug,
                ref.trader,
                ref.program_entry,
                exc,
            )
    return strategies


def _instantiate_strategy(
    program_entry: str,
    strategy_name: str,
    symbols: Sequence[str],
    market: str,
    initial_capital: float,
    project_root: Path,
) -> TradingStrategy:
    module_name, class_name = _split_program_entry(program_entry)
    module = _import_program_module(module_name=module_name, project_root=project_root)
    strategy_cls = getattr(module, class_name)

    try:
        strategy = strategy_cls(
            name=strategy_name,
            symbols=list(symbols),
            default_market=market,
            default_type_name="stock",
            initial_capital=float(initial_capital),
        )
    except TypeError:
        try:
            strategy = strategy_cls(
                name=strategy_name,
                symbols=list(symbols),
                default_market=market,
                default_type_name="stock",
            )
            if hasattr(strategy, "initial_capital"):
                strategy.initial_capital = float(initial_capital)
        except TypeError:
            strategy = strategy_cls()
            if hasattr(strategy, "initial_capital"):
                strategy.initial_capital = float(initial_capital)
    if not isinstance(strategy, TradingStrategy):
        raise TypeError(f"strategy class is not TradingStrategy: {program_entry}")
    return strategy


def _import_program_module(module_name: str, project_root: Path):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        pass

    normalized_module_names = [module_name]
    if module_name.startswith("trader_incubator.core.skills."):
        normalized_module_names.append(module_name.replace("trader_incubator.core.", "", 1))

    for candidate in normalized_module_names[1:]:
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError:
            continue

    for candidate in normalized_module_names:
        module_path = project_root / "src" / Path(*candidate.split("."))
        module_file = module_path.with_suffix(".py")
        if not module_file.exists():
            # Compatibility fallback:
            # old server flow could place trader folder as slug-with-hyphen while
            # program_entry used module_name_with_underscore.
            parts = candidate.split(".")
            if len(parts) >= 3 and parts[-3] == "traders":
                alt_parts = list(parts)
                alt_parts[-2] = alt_parts[-2].replace("_", "-")
                alt_module_file = (project_root / "src" / Path(*alt_parts)).with_suffix(".py")
                if alt_module_file.exists():
                    module_file = alt_module_file
                    candidate = ".".join(alt_parts)
                else:
                    continue
            else:
                continue
        spec = importlib.util.spec_from_file_location(candidate, module_file)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[candidate] = module
        spec.loader.exec_module(module)
        return module
    raise ModuleNotFoundError(module_name)


def _split_program_entry(program_entry: str) -> tuple[str, str]:
    text = str(program_entry).strip()
    if ":" not in text:
        raise ValueError(f"invalid program_entry: {program_entry}")
    module_name, class_name = text.split(":", 1)
    return module_name.strip(), class_name.strip()


def _normalize_market(raw_market: str) -> str:
    text = str(raw_market).strip().lower()
    if text in {"a_share", "ashare", "cn", "china"}:
        return "cn"
    if text in {"hk", "hkex"}:
        return "hk"
    if text in {"us", "usa"}:
        return "us"
    return text


def _to_datetime(value: str | date | datetime, tz: ZoneInfo, is_end: bool) -> datetime:
    if isinstance(value, datetime):
        return _ensure_timezone(value, tz)
    if isinstance(value, date):
        target_time = time(23, 59) if is_end else time(0, 0)
        return datetime.combine(value, target_time, tzinfo=tz)
    text = str(value).strip()
    if "T" in text or " " in text:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _ensure_timezone(parsed, tz)
    parsed_date = date.fromisoformat(text)
    target_time = time(23, 59) if is_end else time(0, 0)
    return datetime.combine(parsed_date, target_time, tzinfo=tz)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run season backtest quickly (default season: s1)")
    parser.add_argument("--season", default="s1", help="season slug, default: s1")
    parser.add_argument("--project-root", default=".", help="project root path")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="runtime timezone")
    parser.add_argument("--start", default=None, help="start datetime/date, ISO-8601")
    parser.add_argument("--end", default=None, help="end datetime/date, ISO-8601")
    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="when --start is provided but --end is omitted, end=start+minutes (default 30)",
    )
    parser.add_argument("--debug", action="store_true", help="print per-minute debug logs")
    parser.add_argument("--print-orders", type=int, default=20, help="print first N orders, default 20")
    return parser


def _resolve_backtest_window(
    season_slug: str,
    project_root: Path | str,
    timezone: str,
    start: str | None,
    end: str | None,
    minutes: int,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone)
    if start is not None and end is not None:
        return _to_datetime(start, tz=tz, is_end=False), _to_datetime(end, tz=tz, is_end=True)

    if start is not None:
        start_at = _to_datetime(start, tz=tz, is_end=False)
        return start_at, start_at + timedelta(minutes=max(int(minutes), 1))

    season = Season.load(season_slug=season_slug, project_root=project_root)
    start_at = _to_datetime(season.start_date, tz=tz, is_end=False).replace(hour=9, minute=30)
    if end is not None:
        return start_at, _to_datetime(end, tz=tz, is_end=True)
    return start_at, start_at + timedelta(minutes=max(int(minutes), 1))


def main() -> int:
    args = _build_parser().parse_args()
    start_at, end_at = _resolve_backtest_window(
        season_slug=args.season,
        project_root=args.project_root,
        timezone=args.timezone,
        start=args.start,
        end=args.end,
        minutes=args.minutes,
    )
    result = run_season_backtest(
        start_date=start_at,
        end_date=end_at,
        season_slug=args.season,
        project_root=args.project_root,
        timezone=args.timezone,
        debug=args.debug,
    )
    print(f"season={result.season_slug}")
    print(f"start={result.start_at.isoformat()}")
    print(f"end={result.end_at.isoformat()}")
    print(f"triggered_minutes={result.triggered_minutes}")
    print(f"orders={len(result.orders)}")

    limit = max(int(args.print_orders), 0)
    for item in result.orders[:limit]:
        print(
            f"id={item.order_id} strategy={item.strategy_name} symbol={item.symbol_key} "
            f"side={item.side} qty={item.quantity} status={item.status} fill={item.fill_price} "
            f"at={item.submitted_at.isoformat()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
