from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd
import yfinance as yf

from trader_incubator.backtest import load_season_strategies
from trader_incubator.exchange import (
    Order,
    RealClock,
    SimulatedMatchingEngine,
    SymbolRef,
    TradingStrategy,
    _ensure_timezone,
    _floor_to_minute,
)


_SUPPORTED_PERIODS = {"1m", "5m", "15m", "30m", "60m", "1d"}
_LIVE_FETCH_PERIODS = ("1m", "5m", "15m", "30m", "60m")
_LIVE_BAR_COLUMNS = ["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"]
_AK_MINUTE_PERIOD_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}


def _to_yf_symbol(symbol: SymbolRef) -> str:
    if symbol.market == "hk":
        numeric = str(symbol.code).strip().lstrip("0") or "0"
        return f"{numeric.zfill(4)}.HK"
    if symbol.market == "us":
        return str(symbol.code).strip().upper()
    raw = str(symbol.code).strip().zfill(6)
    if raw.startswith(("6", "9", "5")):
        return f"{raw}.SS"
    if raw.startswith(("0", "2", "3")):
        return f"{raw}.SZ"
    return f"{raw}.BJ"


def _empty_live_bar_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_LIVE_BAR_COLUMNS)


def _call_akshare_with_candidates(candidates: list[tuple[str, dict[str, object]]]) -> pd.DataFrame:
    for fn_name, kwargs in candidates:
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        try:
            df = fn(**kwargs)
        except Exception:
            continue
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return pd.DataFrame()


def _normalize_timestamp_to_tz(series: pd.Series, tz: ZoneInfo) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.empty:
        return ts
    if ts.dt.tz is None:
        # Incoming source time is treated as UTC, then converted to UTC+8 target timezone.
        return ts.dt.tz_localize("UTC").dt.tz_convert(tz)
    return ts.dt.tz_convert(tz)


def _normalize_realtime_df(df: pd.DataFrame, code: str, tz: ZoneInfo) -> pd.DataFrame:
    if df.empty:
        return _empty_live_bar_df()
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]
    out = out.reset_index().copy()
    rename_map = {
        "Date": "timestamp",
        "Datetime": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    out = out.rename(columns=rename_map)
    for col in ["timestamp", "open", "high", "low", "close", "adj_close", "volume"]:
        if col not in out.columns:
            out[col] = pd.NA
    out["timestamp"] = _normalize_timestamp_to_tz(out["timestamp"], tz)
    out = out.dropna(subset=["timestamp"]).reset_index(drop=True)
    if out.empty:
        return _empty_live_bar_df()
    out["code"] = str(code)
    out = out[_LIVE_BAR_COLUMNS]
    return out.sort_values("timestamp").reset_index(drop=True)


def _normalize_akshare_realtime_df(df: pd.DataFrame, code: str, tz: ZoneInfo) -> pd.DataFrame:
    if df.empty:
        return _empty_live_bar_df()

    out = df.copy().reset_index(drop=True)
    rename_map = {
        "Date": "timestamp",
        "Datetime": "timestamp",
        "date": "timestamp",
        "datetime": "timestamp",
        "日期": "timestamp",
        "时间": "timestamp",
        "time": "timestamp",
        "Open": "open",
        "open": "open",
        "开盘": "open",
        "High": "high",
        "high": "high",
        "最高": "high",
        "Low": "low",
        "low": "low",
        "最低": "low",
        "Close": "close",
        "close": "close",
        "收盘": "close",
        "Adj Close": "adj_close",
        "adj_close": "adj_close",
        "Volume": "volume",
        "volume": "volume",
        "成交量": "volume",
    }
    out = out.rename(columns=rename_map)

    for col in ["timestamp", "open", "high", "low", "close", "volume"]:
        if col not in out.columns:
            out[col] = pd.NA
    if "adj_close" not in out.columns:
        out["adj_close"] = out["close"]

    out["timestamp"] = _normalize_timestamp_to_tz(out["timestamp"], tz)
    out = out.dropna(subset=["timestamp"]).reset_index(drop=True)
    if out.empty:
        return _empty_live_bar_df()

    out["code"] = str(code)
    out = out[_LIVE_BAR_COLUMNS]
    return out.sort_values("timestamp").reset_index(drop=True)


def _to_ak_a_symbol(code: str) -> str:
    return str(code).strip().zfill(6)


def _to_ak_hk_symbol(code: str) -> str:
    return str(code).strip().zfill(5)


def _to_ak_date_time_str(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")


class MultiSourceDataFeed:
    def __init__(self, timezone: str = "Asia/Shanghai") -> None:
        self.tz = ZoneInfo(timezone)

    def fetch(self, symbol: SymbolRef, period: str, start: datetime, end: datetime) -> pd.DataFrame:
        normalized_period = str(period).strip().lower()
        if normalized_period not in _LIVE_FETCH_PERIODS:
            raise ValueError(f"unsupported live fetch period: {period}")

        primary = self._fetch_akshare(symbol=symbol, period=normalized_period, start=start, end=end)
        if not primary.empty:
            return primary
        return self._fetch_yfinance(symbol=symbol, period=normalized_period, start=start, end=end)

    def _fetch_akshare(self, symbol: SymbolRef, period: str, start: datetime, end: datetime) -> pd.DataFrame:
        if symbol.market not in {"cn", "hk"}:
            return pd.DataFrame()
        ak_period = _AK_MINUTE_PERIOD_MAP.get(period)
        if not ak_period:
            return pd.DataFrame()

        start_str = _to_ak_date_time_str(start, self.tz)
        end_str = _to_ak_date_time_str(end, self.tz)
        candidates: list[tuple[str, dict[str, object]]]
        if symbol.market == "hk":
            candidates = [
                (
                    "stock_hk_hist_min_em",
                    {
                        "symbol": _to_ak_hk_symbol(symbol.code),
                        "period": ak_period,
                        "start_date": start_str,
                        "end_date": end_str,
                    },
                ),
                (
                    "stock_hk_hist_min",
                    {
                        "symbol": _to_ak_hk_symbol(symbol.code),
                        "period": ak_period,
                        "start_date": start_str,
                        "end_date": end_str,
                    },
                ),
            ]
        else:
            candidates = [
                (
                    "stock_zh_a_hist_min_em",
                    {
                        "symbol": _to_ak_a_symbol(symbol.code),
                        "period": ak_period,
                        "start_date": start_str,
                        "end_date": end_str,
                    },
                ),
            ]

        ak_df = _call_akshare_with_candidates(candidates)
        return _normalize_akshare_realtime_df(ak_df, symbol.code, self.tz)

    def _fetch_yfinance(self, symbol: SymbolRef, period: str, start: datetime, end: datetime) -> pd.DataFrame:
        yf_symbol = _to_yf_symbol(symbol)
        try:
            downloaded = yf.download(
                tickers=yf_symbol,
                start=start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                end=end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
                interval=period,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception:
            return _empty_live_bar_df()
        return _normalize_realtime_df(downloaded, symbol.code, self.tz)


def _aggregate_period(df_1m: pd.DataFrame, period: str) -> pd.DataFrame:
    normalized_period = str(period).strip().lower()
    if normalized_period == "1m":
        return df_1m.copy()
    if normalized_period not in _SUPPORTED_PERIODS:
        raise ValueError(f"unsupported period: {period}")
    if df_1m.empty:
        return df_1m.copy()

    freq_map = {"5m": "5min", "15m": "15min", "30m": "30min", "60m": "60min", "1d": "1D"}
    freq = freq_map[normalized_period]
    base = df_1m.set_index("timestamp")
    aggregated = (
        base.resample(freq, label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "adj_close": "last",
                "volume": "sum",
                "code": "last",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return aggregated


class LiveMarketDataStore:
    def __init__(
        self,
        timezone: str = "Asia/Shanghai",
        session_open_time: time = time(9, 30),
        data_feed: MultiSourceDataFeed | None = None,
    ) -> None:
        self.tz = ZoneInfo(timezone)
        self.session_open_time = session_open_time
        self.data_feed = data_feed or MultiSourceDataFeed(timezone=timezone)
        self._cache: dict[str, dict[str, pd.DataFrame]] = {period: {} for period in _SUPPORTED_PERIODS}

    def warmup(self, symbols: Sequence[SymbolRef], at: datetime) -> None:
        for symbol in symbols:
            self._refresh_symbol_all_periods(symbol=symbol, at=at)

    def latest_1m(self, symbols: Sequence[SymbolRef], at: datetime) -> dict[str, pd.Series]:
        at_ts = _ensure_timezone(at, self.tz)
        out: dict[str, pd.Series] = {}
        for symbol in symbols:
            self._refresh_symbol_all_periods(symbol=symbol, at=at_ts)
            df = self._cache["1m"].get(symbol.key)
            if df is None or df.empty:
                continue
            bar = df[df["timestamp"] <= at_ts].tail(1)
            if bar.empty:
                continue
            out[symbol.key] = bar.iloc[0]
        return out

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str = "1m",
    ) -> pd.DataFrame:
        normalized_period = str(period).strip().lower()
        if normalized_period not in _SUPPORTED_PERIODS:
            raise ValueError(f"unsupported period: {period}")
        period_df = self._cache.get(normalized_period, {}).get(symbol.key)
        if period_df is None:
            period_df = pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"]
            )
        out = period_df
        capped_end: datetime | None = None
        if end_time is not None:
            capped_end = _ensure_timezone(end_time, self.tz)
            out = out[out["timestamp"] <= capped_end]
        if lookback > 0:
            out = out.tail(lookback)
        return out.reset_index(drop=True).copy()

    def _refresh_symbol_all_periods(self, symbol: SymbolRef, at: datetime) -> None:
        for period in _LIVE_FETCH_PERIODS:
            self._refresh_symbol_period(symbol=symbol, period=period, at=at)
        self._rebuild_daily_from_60m(symbol=symbol)

    def _refresh_symbol_period(self, symbol: SymbolRef, period: str, at: datetime) -> None:
        start_ts = self._session_start(at)
        end_ts = at + timedelta(minutes=1)
        try:
            normalized = self.data_feed.fetch(symbol=symbol, period=period, start=start_ts, end=end_ts)
        except Exception:
            return
        if normalized.empty:
            return
        normalized = normalized[normalized["timestamp"] <= at].reset_index(drop=True)
        if normalized.empty:
            return
        existing = self._cache[period].get(symbol.key)
        if existing is None or existing.empty:
            self._cache[period][symbol.key] = normalized
            return
        merged = pd.concat([existing, normalized], ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
        self._cache[period][symbol.key] = merged

    def _rebuild_daily_from_60m(self, symbol: SymbolRef) -> None:
        source = self._cache["60m"].get(symbol.key)
        if source is None or source.empty:
            return
        self._cache["1d"][symbol.key] = _aggregate_period(source, "1d")

    def _session_start(self, at: datetime) -> datetime:
        at_ts = _ensure_timezone(at, self.tz)
        open_ts = datetime.combine(at_ts.date(), self.session_open_time, tzinfo=self.tz)
        if at_ts >= open_ts:
            return open_ts
        return open_ts - timedelta(days=1)


class LiveExchange:
    def __init__(
        self,
        strategies: Sequence[TradingStrategy],
        timezone: str = "Asia/Shanghai",
        clock: RealClock | None = None,
        debug: bool = False,
    ) -> None:
        self.strategies = list(strategies)
        self.tz = ZoneInfo(timezone)
        self.clock = clock or RealClock(self.tz)
        self.data_store = LiveMarketDataStore(timezone=timezone)
        self.matching_engine = SimulatedMatchingEngine()
        self.debug = bool(debug)
        self._current_time: datetime | None = None
        self._current_bars: dict[str, pd.Series] = {}
        for strategy in self.strategies:
            strategy._bind_exchange(self)  # type: ignore[arg-type]

    def run(self, max_minutes: int | None = None, end_time: datetime | None = None) -> int:
        subscribed_symbols = self._collect_subscribed_symbols()
        now = _floor_to_minute(self.clock.now())
        self.data_store.warmup(subscribed_symbols, at=now)

        triggered_minutes = 0
        while True:
            tick_time = _floor_to_minute(self.clock.now())
            if end_time is not None and tick_time > _floor_to_minute(_ensure_timezone(end_time, self.tz)):
                break

            self._current_time = tick_time
            self._current_bars = self.data_store.latest_1m(subscribed_symbols, at=tick_time)
            if self.debug:
                print(
                    f"[LIVE][{tick_time.isoformat()}] tick "
                    f"bars={len(self._current_bars)} strategies={len(self.strategies)}"
                )
            for strategy in self.strategies:
                strategy_bars = {
                    symbol.key: self._current_bars[symbol.key]
                    for symbol in strategy.symbols
                    if symbol.key in self._current_bars
                }
                before_orders = len(self.matching_engine.orders)
                strategy.on_minute(tick_time, strategy_bars)
                if self.debug:
                    print(
                        f"[LIVE][{tick_time.isoformat()}] strategy={strategy.name} "
                        f"bars={len(strategy_bars)} new_orders={len(self.matching_engine.orders) - before_orders}"
                    )

            triggered_minutes += 1
            if max_minutes is not None and triggered_minutes >= max_minutes:
                break
            self._sleep_until(tick_time + timedelta(minutes=1))
        return triggered_minutes

    def get_history(
        self,
        symbol: SymbolRef,
        lookback: int,
        end_time: datetime | None = None,
        period: str = "1m",
    ) -> pd.DataFrame:
        capped = self._cap_end_time(end_time)
        return self.data_store.get_history(symbol=symbol, lookback=lookback, end_time=capped, period=period)

    def place_market_order(self, strategy_name: str, symbol: SymbolRef, side: str, quantity: int) -> Order:
        submitted_at = self._current_time or _floor_to_minute(self.clock.now())
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

    def _sleep_until(self, target: datetime) -> None:
        target_ts = _ensure_timezone(target, self.tz)
        seconds = (target_ts - self.clock.now()).total_seconds()
        self.clock.sleep(max(seconds, 0.0))

    def _cap_end_time(self, end_time: datetime | None) -> datetime | None:
        if self._current_time is None:
            return end_time
        if end_time is None:
            return self._current_time
        return min(_ensure_timezone(end_time, self.tz), self._current_time)

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


def run_season_live(
    season_slug: str,
    project_root: Path | str = ".",
    timezone: str = "Asia/Shanghai",
    max_minutes: int | None = None,
    end_time: str | datetime | None = None,
    debug: bool = False,
) -> tuple[int, list[Order]]:
    strategies = load_season_strategies(season_slug=season_slug, project_root=project_root)
    if debug:
        print(f"[LIVE] season={season_slug} strategies={len(strategies)}")
    exchange = LiveExchange(strategies=strategies, timezone=timezone, debug=debug)
    end_ts: datetime | None = None
    if end_time is not None:
        if isinstance(end_time, datetime):
            end_ts = _ensure_timezone(end_time, ZoneInfo(timezone))
        else:
            end_ts = _ensure_timezone(datetime.fromisoformat(str(end_time).replace("Z", "+00:00")), ZoneInfo(timezone))
    minutes = exchange.run(max_minutes=max_minutes, end_time=end_ts)
    return minutes, exchange.list_orders()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run season live engine with realtime 1m bars")
    parser.add_argument("--season", required=True, help="season slug, e.g. s1")
    parser.add_argument("--project-root", default=".", help="project root path")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="runtime timezone")
    parser.add_argument("--max-minutes", type=int, default=None, help="stop after N minutes")
    parser.add_argument("--end-time", default=None, help="optional stop time, ISO-8601")
    parser.add_argument("--debug", action="store_true", help="print per-minute logs")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    minutes, orders = run_season_live(
        season_slug=args.season,
        project_root=args.project_root,
        timezone=args.timezone,
        max_minutes=args.max_minutes,
        end_time=args.end_time,
        debug=args.debug,
    )
    print(f"minutes={minutes}")
    print(f"orders={len(orders)}")
    for item in orders[:20]:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
