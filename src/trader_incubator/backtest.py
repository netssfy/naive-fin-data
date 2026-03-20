from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import importlib
import importlib.util
from pathlib import Path
import sys
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from trader_incubator.exchange import (
    Order,
    SimulatedMatchingEngine,
    SymbolRef,
    TradingStrategy,
    _ensure_timezone,
    _floor_to_minute,
)
from trader_incubator.season import Season
from trader_incubator.trader import Trader


SUPPORTED_PERIODS: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "1d")


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
    ) -> None:
        self.strategies = list(strategies)
        self.data_store = data_store
        self.matching_engine = SimulatedMatchingEngine()
        self.debug = bool(debug)
        self._current_time: datetime | None = None
        self._current_bars: dict[str, pd.Series] = {}
        for strategy in self.strategies:
            strategy._bind_exchange(self)  # type: ignore[arg-type]

    def run(self, start_at: datetime, end_at: datetime) -> int:
        start_ts = _floor_to_minute(_ensure_timezone(start_at, self.data_store.tz))
        end_ts = _floor_to_minute(_ensure_timezone(end_at, self.data_store.tz))
        if end_ts < start_ts:
            raise ValueError("end_at must be >= start_at")

        subscribed_symbols = self._collect_subscribed_symbols()
        self.data_store.warmup(subscribed_symbols)

        cursor = start_ts
        triggered_minutes = 0
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
            triggered_minutes += 1
            cursor = cursor + timedelta(minutes=1)
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
    data_store = MultiPeriodHistoricalDataStore(
        project_root=project_root,
        start_at=start_at,
        end_at=end_at,
        periods=SUPPORTED_PERIODS,
        timezone=timezone,
    )
    exchange = BacktestExchange(strategies=strategies, data_store=data_store, debug=debug)
    triggered_minutes = exchange.run(start_at=start_at, end_at=end_at)
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
        if not symbols:
            continue
        strategy = _instantiate_strategy(
            program_entry=ref.program_entry,
            strategy_name=ref.trader,
            symbols=symbols,
            market=market,
            project_root=Path(project_root),
        )
        strategies.append(strategy)
    return strategies


def _instantiate_strategy(
    program_entry: str,
    strategy_name: str,
    symbols: Sequence[str],
    market: str,
    project_root: Path,
) -> TradingStrategy:
    module_name, class_name = _split_program_entry(program_entry)
    module = _import_program_module(module_name=module_name, project_root=project_root)
    strategy_cls = getattr(module, class_name)

    try:
        strategy = strategy_cls(name=strategy_name, symbols=list(symbols), default_market=market, default_type_name="stock")
    except TypeError:
        strategy = strategy_cls()
    if not isinstance(strategy, TradingStrategy):
        raise TypeError(f"strategy class is not TradingStrategy: {program_entry}")
    return strategy


def _import_program_module(module_name: str, project_root: Path):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        pass

    module_path = project_root / "src" / Path(*module_name.split("."))
    module_file = module_path.with_suffix(".py")
    if not module_file.exists():
        raise ModuleNotFoundError(module_name)
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(module_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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
