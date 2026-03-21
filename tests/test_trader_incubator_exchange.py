from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import shutil
import uuid

import pandas as pd

from trader_incubator.exchange import Exchange, TradingSessionConfig, TradingStrategy


class FakeClock:
    def __init__(self, start_at: datetime) -> None:
        self._now = start_at
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        seconds = max(seconds, 0.0)
        self.sleep_calls.append(seconds)
        self._now = self._now + timedelta(seconds=seconds)


class RecordingStrategy(TradingStrategy):
    def __init__(self) -> None:
        super().__init__(name="demo", symbols=["cn:000001"])
        self.pre_open_events: list[datetime] = []
        self.minute_events: list[datetime] = []
        self.post_close_events: list[datetime] = []
        self.last_seen_close: list[float] = []
        self.created_orders = []

    def on_pre_open(self, event_time: datetime) -> None:
        self.pre_open_events.append(event_time)

    def on_minute(self, event_time: datetime, latest_bars: dict[str, pd.Series]) -> None:
        self.minute_events.append(event_time)
        bar = latest_bars.get("stock:cn:000001")
        if bar is not None:
            self.last_seen_close.append(float(bar["close"]))
        if len(self.minute_events) == 1:
            _ = self.history(code="000001", lookback=2, end_time=event_time)
            self.created_orders.append(self.place_market_order(code="000001", side="buy", quantity=100))

    def on_post_close(self, event_time: datetime) -> None:
        self.post_close_events.append(event_time)


def _new_test_root() -> Path:
    root = Path(".tmp") / "tests" / f"exchange-{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _cleanup_test_root(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def _write_1m_data(root: Path) -> None:
    out_dir = root / "data" / "stock" / "cn" / "000001" / "1m"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-03-19 09:30:00+08:00", periods=5, freq="min"),
            "open": [10.0, 10.2, 10.1, 10.3, 10.4],
            "high": [10.1, 10.3, 10.2, 10.4, 10.5],
            "low": [9.9, 10.1, 10.0, 10.2, 10.3],
            "close": [10.0, 10.25, 10.15, 10.35, 10.45],
            "adj_close": [10.0, 10.25, 10.15, 10.35, 10.45],
            "volume": [1000, 1100, 1200, 1300, 1400],
            "code": ["000001"] * 5,
        }
    )
    df.to_parquet(out_dir / "20260319.parquet", index=False)


def test_exchange_waits_preopen_and_triggers_minute_callbacks() -> None:
    root = _new_test_root()
    try:
        _write_1m_data(root)
        tz = ZoneInfo("Asia/Shanghai")
        fake_clock = FakeClock(datetime(2026, 3, 19, 9, 0, tzinfo=tz))
        strategy = RecordingStrategy()

        exchange = Exchange(
            strategies=[strategy],
            project_root=root,
            session_config=TradingSessionConfig(
                open_time=datetime.strptime("09:30", "%H:%M").time(),
                close_time=datetime.strptime("09:33", "%H:%M").time(),
                pre_open_lead_minutes=5,
                timezone="Asia/Shanghai",
            ),
            clock=fake_clock,  # type: ignore[arg-type]
        )

        exchange.run(max_minutes=2)

        assert len(strategy.pre_open_events) == 1
        assert strategy.pre_open_events[0].hour == 9 and strategy.pre_open_events[0].minute == 25
        assert strategy.minute_events == [
            datetime(2026, 3, 19, 9, 30, tzinfo=tz),
            datetime(2026, 3, 19, 9, 31, tzinfo=tz),
        ]
        assert strategy.last_seen_close == [10.0, 10.25]
        assert len(strategy.post_close_events) == 1
        assert fake_clock.sleep_calls[0] == 25 * 60
    finally:
        _cleanup_test_root(root)


def test_exchange_strategy_helpers_history_and_market_order() -> None:
    root = _new_test_root()
    try:
        _write_1m_data(root)
        tz = ZoneInfo("Asia/Shanghai")
        fake_clock = FakeClock(datetime(2026, 3, 19, 9, 25, tzinfo=tz))
        strategy = RecordingStrategy()

        exchange = Exchange(
            strategies=[strategy],
            project_root=root,
            session_config=TradingSessionConfig(
                open_time=datetime.strptime("09:30", "%H:%M").time(),
                close_time=datetime.strptime("09:31", "%H:%M").time(),
                pre_open_lead_minutes=5,
                timezone="Asia/Shanghai",
            ),
            clock=fake_clock,  # type: ignore[arg-type]
        )
        exchange.run(max_minutes=1)

        orders = exchange.list_orders("demo")
        assert len(orders) == 1
        assert orders[0].status == "filled"
        assert orders[0].fill_price == 10.0
        assert exchange.get_position(strategy_name="demo", code="000001") == 100
    finally:
        _cleanup_test_root(root)
