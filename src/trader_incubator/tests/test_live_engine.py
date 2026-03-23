from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from trader_incubator.exchange import TradingStrategy
from trader_incubator.live import LiveExchange


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


def test_live_exchange_realtime_1m_and_no_future_data(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    ak_calls: list[object] = []

    def fake_akshare(*args, **kwargs) -> pd.DataFrame:
        ak_calls.append((args, kwargs))
        return pd.DataFrame()

    def fake_download(*args, **kwargs) -> pd.DataFrame:
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

    monkeypatch.setattr("trader_incubator.live._call_akshare_with_candidates", fake_akshare)
    monkeypatch.setattr("trader_incubator.live.yf.download", fake_download)

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
    start_values = [item.get("start") for item in calls if item.get("start") is not None]
    assert start_values, "live fetch should pass start time"
    earliest_start = min(start_values)
    # In UTC, 2026-03-20 09:30+08:00 == 2026-03-20 01:30.
    assert earliest_start.hour == 1 and earliest_start.minute == 30
