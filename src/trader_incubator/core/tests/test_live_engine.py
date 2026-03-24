from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from exchange import TradingStrategy
from live import LiveExchange, run_all_seasons_live


class FakeClock:
    def __init__(self, start_at: datetime) -> None:
        self._now = start_at

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=max(seconds, 0.0))


class RecordingLiveStrategy(TradingStrategy):
    def __init__(self) -> None:
        super().__init__(name="live-demo", symbols=["hk:01810"])
        self.minute_events: list[datetime] = []
        self.closes: list[float] = []
        self.future_violation = False

    def on_minute(self, event_time: datetime, latest_bars: dict[str, pd.Series]) -> None:
        self.minute_events.append(event_time)
        bar = latest_bars.get("stock:hk:01810")
        if bar is not None:
            self.closes.append(float(bar["close"]))
        for period in ("1m", "5m", "15m", "30m", "60m", "1d"):
            hist = self.history("01810", lookback=100, period=period, market="hk")
            if not hist.empty and hist["timestamp"].max().to_pydatetime() > event_time:
                self.future_violation = True


class NoopMarketStore:
    def __init__(self) -> None:
        self.latest_calls = 0

    def warmup(self, symbols, at) -> None:
        _ = (symbols, at)

    def latest_1m(self, symbols, at):
        _ = (symbols, at)
        self.latest_calls += 1
        return {}

    def get_history(self, symbol, lookback, end_time=None, period="1m"):
        _ = (symbol, lookback, end_time, period)
        return pd.DataFrame()


class RecordingNoopStrategy(TradingStrategy):
    def __init__(self) -> None:
        super().__init__(name="noop-market", symbols=["cn:000001"])
        self.events: list[datetime] = []

    def on_minute(self, event_time: datetime, latest_bars: dict[str, pd.Series]) -> None:
        _ = latest_bars
        self.events.append(event_time)


def test_live_exchange_realtime_1m_and_no_future_data(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    ak_calls: list[object] = []

    def fake_akshare(*args, **kwargs) -> pd.DataFrame:
        ak_calls.append((args, kwargs))
        return pd.DataFrame()

    def fake_history(*args, **kwargs) -> pd.DataFrame:
        calls.append(dict(kwargs))
        idx = pd.DatetimeIndex(
            [
                pd.Timestamp("2026-03-20T09:30:00+08:00"),
                pd.Timestamp("2026-03-20T09:31:00+08:00"),
                pd.Timestamp("2026-03-20T09:32:00+08:00"),
            ],
            name="Datetime",
        )
        return pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.1, 11.1, 12.1],
                "Low": [9.9, 10.9, 11.9],
                "Close": [10.0, 11.0, 12.0],
                "Adj Close": [10.0, 11.0, 12.0],
                "Volume": [1000, 1000, 1000],
            },
            index=idx,
        )

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, *args, **kwargs) -> pd.DataFrame:
            _ = (args, self.symbol)
            return fake_history(**kwargs)

    monkeypatch.setattr("live._call_akshare_with_candidates", fake_akshare)
    monkeypatch.setattr("live.yf.Ticker", FakeTicker)

    tz = ZoneInfo("Asia/Shanghai")
    clock = FakeClock(datetime(2026, 3, 20, 9, 30, tzinfo=tz))
    strategy = RecordingLiveStrategy()
    exchange = LiveExchange(
        strategies=[strategy],
        timezone="Asia/Shanghai",
        clock=clock,  # type: ignore[arg-type]
        debug=False,
    )

    minutes = exchange.run(max_minutes=2)

    assert minutes == 2
    assert [d.isoformat() for d in strategy.minute_events] == [
        "2026-03-20T09:30:00+08:00",
        "2026-03-20T09:31:00+08:00",
    ]
    assert strategy.closes == [10.0, 11.0]
    assert strategy.future_violation is False

    requested_intervals = {str(item.get("interval")) for item in calls}
    assert {"1m", "5m", "15m", "30m", "60m"}.issubset(requested_intervals)
    assert len(ak_calls) >= 5
    assert calls, "yfinance history should be called as fallback"


def test_live_exchange_skips_fetch_when_market_closed() -> None:
    tz = ZoneInfo("Asia/Shanghai")
    clock = FakeClock(datetime(2026, 3, 20, 8, 0, tzinfo=tz))
    strategy = RecordingNoopStrategy()
    store = NoopMarketStore()
    exchange = LiveExchange(
        strategies=[strategy],
        market="cn",
        timezone="Asia/Shanghai",
        clock=clock,  # type: ignore[arg-type]
        data_store=store,  # type: ignore[arg-type]
        debug=False,
    )

    minutes = exchange.run(max_minutes=2)
    assert minutes == 2
    assert store.latest_calls == 0
    assert strategy.events == []


def test_run_all_seasons_live_triggers_research_on_market_close(monkeypatch) -> None:
    class NoopStrategy(TradingStrategy):
        def __init__(self) -> None:
            super().__init__(name="noop", symbols=[])

    tz = ZoneInfo("Asia/Shanghai")
    fake_clock = FakeClock(datetime(2026, 3, 20, 14, 59, tzinfo=tz))
    research_calls: list[tuple[str, bool]] = []

    monkeypatch.setattr("live.RealClock", lambda _tz: fake_clock)
    monkeypatch.setattr("live.list_valid_season_slugs", lambda project_root, timezone: ["s1"])
    monkeypatch.setattr("live.load_season_strategies", lambda season_slug, project_root: [NoopStrategy()])
    monkeypatch.setattr("live.Season.load", lambda season_slug, project_root: SimpleNamespace(market="cn"))
    monkeypatch.setattr("live.LiveMarketDataStore.warmup", lambda self, symbols, at: None)
    monkeypatch.setattr("live.LiveMarketDataStore.latest_1m", lambda self, symbols, at: {})
    monkeypatch.setattr(
        "live.run_season_trader_research",
        lambda season_slug, project_root, codex_bin, dry_run=False: research_calls.append((season_slug, dry_run)) or 1,
    )

    minutes, seasons, orders = run_all_seasons_live(
        project_root=".",
        timezone="Asia/Shanghai",
        max_minutes=4,
        research_dry_run=True,
    )

    assert minutes == 4
    assert seasons == ["s1"]
    assert orders == []
    assert research_calls == [("s1", True)]

