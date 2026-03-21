from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo
import itertools
import time as time_module

import pandas as pd


@dataclass(frozen=True)
class SymbolRef:
    code: str
    market: str = "cn"
    type_name: str = "stock"

    @property
    def key(self) -> str:
        return f"{self.type_name}:{self.market}:{self.code}"

    @classmethod
    def parse(
        cls,
        raw: str,
        default_market: str = "cn",
        default_type_name: str = "stock",
    ) -> SymbolRef:
        text = str(raw).strip()
        parts = [part.strip() for part in text.split(":") if part.strip()]
        if len(parts) == 1:
            return cls(code=parts[0], market=default_market, type_name=default_type_name)
        if len(parts) == 2:
            return cls(code=parts[1], market=parts[0], type_name=default_type_name)
        if len(parts) == 3:
            return cls(code=parts[2], market=parts[1], type_name=parts[0])
        raise ValueError(f"unsupported symbol format: {raw}")


@dataclass(frozen=True)
class TradingSessionConfig:
    open_time: time = time(9, 30)
    close_time: time = time(15, 0)
    pre_open_lead_minutes: int = 5
    timezone: str = "Asia/Shanghai"


@dataclass(frozen=True)
class SessionWindow:
    trading_day: date
    pre_open_at: datetime
    open_at: datetime
    close_at: datetime


@dataclass(frozen=True)
class Order:
    order_id: int
    strategy_name: str
    symbol_key: str
    side: str
    quantity: int
    submitted_at: datetime
    status: str
    fill_price: float | None
    message: str = ""


class RealClock:
    def __init__(self, tz: ZoneInfo) -> None:
        self._tz = tz

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        time_module.sleep(seconds)


class HistoricalDataStore:
    def __init__(self, project_root: Path | str, period: str = "1m", timezone: str = "Asia/Shanghai") -> None:
        self.project_root = Path(project_root)
        self.data_root = self.project_root / "data"
        self.period = str(period).strip().lower()
        self.tz = ZoneInfo(timezone)
        self._catalog: dict[str, list[Path]] = self._build_catalog()
        self._cache: dict[str, pd.DataFrame] = {}

    def _build_catalog(self) -> dict[str, list[Path]]:
        catalog: dict[str, list[Path]] = {}
        pattern = f"*/*/*/{self.period}/*.parquet"
        for parquet_file in self.data_root.glob(pattern):
            rel = parquet_file.relative_to(self.data_root)
            type_name, market, code, _, _ = rel.parts
            key = SymbolRef(code=code, market=market, type_name=type_name).key
            catalog.setdefault(key, []).append(parquet_file)
        return catalog

    def warmup(self, symbols: Sequence[SymbolRef]) -> None:
        for symbol in symbols:
            self._load_symbol(symbol)

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
        return out.sort_values("timestamp").reset_index(drop=True)

    def _load_symbol(self, symbol: SymbolRef) -> pd.DataFrame:
        if symbol.key in self._cache:
            return self._cache[symbol.key]

        parquet_files = sorted(self._catalog.get(symbol.key, []))
        if not parquet_files:
            empty_df = pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"]
            )
            self._cache[symbol.key] = empty_df
            return empty_df

        frames = []
        for parquet_file in parquet_files:
            try:
                frames.append(pd.read_parquet(parquet_file))
            except Exception:
                continue

        if not frames:
            out = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"])
            self._cache[symbol.key] = out
            return out

        merged = pd.concat(frames, ignore_index=True)
        merged = self._normalize_df(merged)
        self._cache[symbol.key] = merged
        return merged

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        df = self._load_symbol(symbol)
        if df.empty:
            return df.copy()
        requested_period = str(period or self.period).strip().lower()
        if requested_period != self.period:
            raise ValueError(f"historical store only loaded period={self.period}, got period={requested_period}")

        out = df
        if end_time is not None:
            end_ts = _ensure_timezone(end_time, self.tz)
            out = out[out["timestamp"] <= end_ts]
        if lookback > 0:
            out = out.tail(lookback)
        return out.reset_index(drop=True).copy()

    def latest_1m(self, symbols: Sequence[SymbolRef], at: datetime) -> dict[str, pd.Series]:
        at_ts = _ensure_timezone(at, self.tz)
        result: dict[str, pd.Series] = {}
        for symbol in symbols:
            df = self._load_symbol(symbol)
            if df.empty:
                continue
            bar = df[df["timestamp"] <= at_ts].tail(1)
            if bar.empty:
                continue
            result[symbol.key] = bar.iloc[0]
        return result


class SimulatedMatchingEngine:
    def __init__(self) -> None:
        self._next_order_id = itertools.count(start=1)
        self.orders: list[Order] = []
        self.positions: dict[str, dict[str, int]] = {}
        self.cash_ledger: dict[str, float] = {}

    def seed_cash(self, strategy_name: str, initial_cash: float) -> None:
        self.cash_ledger[strategy_name] = float(initial_cash)

    def submit_market_order(
        self,
        strategy_name: str,
        symbol: SymbolRef,
        side: str,
        quantity: int,
        submitted_at: datetime,
        bar: pd.Series | None,
    ) -> Order:
        normalized_side = str(side).strip().lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        order_id = next(self._next_order_id)
        if bar is None:
            order = Order(
                order_id=order_id,
                strategy_name=strategy_name,
                symbol_key=symbol.key,
                side=normalized_side,
                quantity=quantity,
                submitted_at=submitted_at,
                status="rejected",
                fill_price=None,
                message="no market data for this symbol on current minute",
            )
            self.orders.append(order)
            return order

        price = float(bar.get("close", 0.0) or 0.0)
        if price <= 0:
            order = Order(
                order_id=order_id,
                strategy_name=strategy_name,
                symbol_key=symbol.key,
                side=normalized_side,
                quantity=quantity,
                submitted_at=submitted_at,
                status="rejected",
                fill_price=None,
                message="invalid close price in current bar",
            )
            self.orders.append(order)
            return order

        signed_qty = quantity if normalized_side == "buy" else -quantity
        strategy_positions = self.positions.setdefault(strategy_name, {})
        strategy_positions[symbol.key] = strategy_positions.get(symbol.key, 0) + signed_qty
        self.cash_ledger[strategy_name] = self.cash_ledger.get(strategy_name, 0.0) - (signed_qty * price)

        order = Order(
            order_id=order_id,
            strategy_name=strategy_name,
            symbol_key=symbol.key,
            side=normalized_side,
            quantity=quantity,
            submitted_at=submitted_at,
            status="filled",
            fill_price=price,
            message="filled by latest 1m close price",
        )
        self.orders.append(order)
        return order

    def get_position(self, strategy_name: str, symbol: SymbolRef) -> int:
        return self.positions.get(strategy_name, {}).get(symbol.key, 0)

    def get_positions(self, strategy_name: str) -> dict[str, int]:
        all_positions = self.positions.get(strategy_name, {})
        return {symbol_key: quantity for symbol_key, quantity in all_positions.items() if quantity != 0}

    def get_trade_history(self, strategy_name: str) -> list[Order]:
        return [order for order in self.orders if order.strategy_name == strategy_name]

    def get_cash(self, strategy_name: str) -> float:
        return self.cash_ledger.get(strategy_name, 0.0)


class TradingStrategy:
    def __init__(
        self,
        name: str,
        symbols: Sequence[str],
        default_market: str = "cn",
        default_type_name: str = "stock",
        initial_capital: float = 0.0,
    ) -> None:
        self.name = str(name).strip()
        self._symbols = [
            SymbolRef.parse(raw=symbol, default_market=default_market, default_type_name=default_type_name)
            for symbol in symbols
        ]
        self.initial_capital = float(initial_capital)
        self._exchange: Exchange | None = None

    @property
    def symbols(self) -> tuple[SymbolRef, ...]:
        return tuple(self._symbols)

    def _bind_exchange(self, exchange: Exchange) -> None:
        self._exchange = exchange

    def on_pre_open(self, event_time: datetime) -> None:
        pass

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        pass

    def on_post_close(self, event_time: datetime) -> None:
        pass

    def history(
        self,
        code: str,
        lookback: int = 120,
        end_time: datetime | None = None,
        period: str = "1m",
        market: str = "cn",
        type_name: str = "stock",
    ) -> pd.DataFrame:
        exchange = self._require_exchange()
        symbol = SymbolRef(code=str(code).strip(), market=market, type_name=type_name)
        return exchange.get_history(symbol=symbol, lookback=lookback, end_time=end_time, period=period)

    def place_market_order(
        self,
        code: str,
        side: str,
        quantity: int,
        market: str = "cn",
        type_name: str = "stock",
    ) -> Order:
        exchange = self._require_exchange()
        symbol = SymbolRef(code=str(code).strip(), market=market, type_name=type_name)
        return exchange.place_market_order(strategy_name=self.name, symbol=symbol, side=side, quantity=quantity)

    def get_position(
        self,
        code: str,
        market: str = "cn",
        type_name: str = "stock",
    ) -> int:
        exchange = self._require_exchange()
        return exchange.get_position(strategy_name=self.name, code=str(code).strip(), market=market, type_name=type_name)

    def get_positions(self) -> dict[str, int]:
        exchange = self._require_exchange()
        return exchange._get_positions_for_strategy(strategy_name=self.name)

    def get_trade_history(self) -> list[Order]:
        exchange = self._require_exchange()
        return exchange._get_trade_history_for_strategy(strategy_name=self.name)

    def _require_exchange(self) -> Exchange:
        if self._exchange is None:
            raise RuntimeError("strategy is not bound to an exchange runtime")
        return self._exchange


class Exchange:
    def __init__(
        self,
        strategies: Sequence[TradingStrategy],
        project_root: Path | str = ".",
        session_config: TradingSessionConfig | None = None,
        clock: RealClock | None = None,
    ) -> None:
        self.strategies = list(strategies)
        self.session_config = session_config or TradingSessionConfig()
        self.tz = ZoneInfo(self.session_config.timezone)
        self.clock = clock or RealClock(self.tz)
        self.data_store = HistoricalDataStore(
            project_root=project_root,
            period="1m",
            timezone=self.session_config.timezone,
        )
        self.matching_engine = SimulatedMatchingEngine()
        self._current_bars: dict[str, pd.Series] = {}

        for strategy in self.strategies:
            strategy._bind_exchange(self)
            self.matching_engine.seed_cash(strategy_name=strategy.name, initial_cash=strategy.initial_capital)

    def run(self, max_minutes: int | None = None) -> None:
        subscribed_symbols = self._collect_subscribed_symbols()
        self.data_store.warmup(subscribed_symbols)

        session = self._resolve_session(self.clock.now())
        self._sleep_until(session.pre_open_at)

        pre_open_time = self.clock.now()
        for strategy in self.strategies:
            strategy.on_pre_open(pre_open_time)

        self._sleep_until(session.open_at)

        triggered_minutes = 0
        while self.clock.now() < session.close_at:
            tick_time = _floor_to_minute(self.clock.now())
            self._current_bars = self.data_store.latest_1m(subscribed_symbols, at=tick_time)

            for strategy in self.strategies:
                strategy_bars = {symbol.key: self._current_bars[symbol.key] for symbol in strategy.symbols if symbol.key in self._current_bars}
                strategy.on_minute(tick_time, strategy_bars)

            triggered_minutes += 1
            if max_minutes is not None and triggered_minutes >= max_minutes:
                break
            self._sleep_until(_next_minute(tick_time))

        post_close_time = self.clock.now()
        for strategy in self.strategies:
            strategy.on_post_close(post_close_time)

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str = "1m",
    ) -> pd.DataFrame:
        return self.data_store.get_history(symbol=symbol, lookback=lookback, end_time=end_time, period=period)

    def place_market_order(self, strategy_name: str, symbol: SymbolRef, side: str, quantity: int) -> Order:
        bar = self._current_bars.get(symbol.key)
        return self.matching_engine.submit_market_order(
            strategy_name=strategy_name,
            symbol=symbol,
            side=side,
            quantity=quantity,
            submitted_at=self.clock.now(),
            bar=bar,
        )

    def get_position(self, strategy_name: str, code: str, market: str = "cn", type_name: str = "stock") -> int:
        symbol = SymbolRef(code=str(code).strip(), market=market, type_name=type_name)
        return self.matching_engine.get_position(strategy_name=strategy_name, symbol=symbol)

    def list_orders(self, strategy_name: str | None = None) -> list[Order]:
        if strategy_name is None:
            return list(self.matching_engine.orders)
        return [order for order in self.matching_engine.orders if order.strategy_name == strategy_name]

    def _get_positions_for_strategy(self, strategy_name: str) -> dict[str, int]:
        return self.matching_engine.get_positions(strategy_name=strategy_name)

    def _get_trade_history_for_strategy(self, strategy_name: str) -> list[Order]:
        return self.matching_engine.get_trade_history(strategy_name=strategy_name)

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

    def _resolve_session(self, now: datetime) -> SessionWindow:
        current = _ensure_timezone(now, self.tz)
        trading_day = current.date()
        if _is_weekend(trading_day):
            trading_day = _next_trading_day(trading_day)

        window = _build_session_window(trading_day, self.session_config, self.tz)
        if current >= window.close_at:
            next_day = _next_trading_day(trading_day + timedelta(days=1))
            window = _build_session_window(next_day, self.session_config, self.tz)
        return window

    def _sleep_until(self, target: datetime) -> None:
        target_ts = _ensure_timezone(target, self.tz)
        now = self.clock.now()
        seconds = (target_ts - now).total_seconds()
        self.clock.sleep(max(seconds, 0.0))


def _build_session_window(trading_day: date, config: TradingSessionConfig, tz: ZoneInfo) -> SessionWindow:
    open_at = datetime.combine(trading_day, config.open_time, tzinfo=tz)
    close_at = datetime.combine(trading_day, config.close_time, tzinfo=tz)
    pre_open_at = open_at - timedelta(minutes=config.pre_open_lead_minutes)
    return SessionWindow(
        trading_day=trading_day,
        pre_open_at=pre_open_at,
        open_at=open_at,
        close_at=close_at,
    )


def _is_weekend(value: date) -> bool:
    return value.weekday() >= 5


def _next_trading_day(value: date) -> date:
    day = value
    while _is_weekend(day):
        day += timedelta(days=1)
    return day


def _floor_to_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _next_minute(value: datetime) -> datetime:
    return _floor_to_minute(value) + timedelta(minutes=1)


def _ensure_timezone(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)

