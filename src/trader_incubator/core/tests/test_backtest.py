from __future__ import annotations

import importlib
import json
from pathlib import Path
import uuid

import pandas as pd

from backtest import run_season_backtest


def _write_parquet(root: Path, period: str, timestamps: list[str], closes: list[float]) -> None:
    out_dir = root / "data" / "stock" / "hk" / "01810" / period
    out_dir.mkdir(parents=True, exist_ok=True)
    size = len(timestamps)
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "adj_close": closes,
            "volume": [1000] * size,
            "code": ["01810"] * size,
        }
    )
    df.to_parquet(out_dir / "20260320.parquet", index=False)


def test_run_season_backtest_minute_step_and_no_future_data(tmp_path: Path) -> None:
    season_slug = f"bt{uuid.uuid4().hex[:6]}"
    trader_slug = "alice"
    module_name = f"trader_incubator.core.skills.seasons.{season_slug}.traders.{trader_slug}.strategy"
    program_entry = f"{module_name}:TraderProgram"

    season_dir = tmp_path / "src" / "trader_incubator" / "core" / "skills" / "seasons" / season_slug
    trader_dir = season_dir / "traders" / trader_slug
    trader_dir.mkdir(parents=True, exist_ok=True)

    season_payload = {
        "season": season_slug,
        "market": "HK",
        "start_date": "2026-03-20",
        "end_date": "2026-03-20",
        "symbol_pool": ["01810"],
        "traders": [
            {
                "trader": "Alice",
                "style": "test",
                "program_entry": program_entry,
            }
        ],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (season_dir / "season.json").write_text(json.dumps(season_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trader_payload = {
        "trader": "Alice",
        "season": season_slug,
        "style": "test",
        "program_entry": program_entry,
        "symbols": ["01810"],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (trader_dir / "trader.json").write_text(json.dumps(trader_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    strategy_code = """
from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    minute_events = []
    closes = []
    future_violation = False

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        cls = type(self)
        cls.minute_events.append(event_time)

        bar = latest_bars.get("stock:hk:01810")
        if bar is not None:
            cls.closes.append(float(bar["close"]))

        for period in ("1m", "5m", "15m", "30m", "60m", "1d"):
            hist = self.history("01810", lookback=100, period=period, market="hk")
            if not hist.empty and hist["timestamp"].max().to_pydatetime() > event_time:
                cls.future_violation = True

        if len(cls.minute_events) == 1:
            self.place_market_order("01810", "buy", 100, market="hk")
"""
    (trader_dir / "strategy.py").write_text(strategy_code.strip() + "\n", encoding="utf-8")

    _write_parquet(
        tmp_path,
        period="1m",
        timestamps=[
            "2026-03-20 09:30:00+08:00",
            "2026-03-20 09:31:00+08:00",
            "2026-03-20 09:32:00+08:00",
        ],
        closes=[10.0, 11.0, 12.0],
    )
    _write_parquet(
        tmp_path,
        period="5m",
        timestamps=["2026-03-20 09:30:00+08:00", "2026-03-20 09:35:00+08:00"],
        closes=[20.0, 21.0],
    )
    _write_parquet(tmp_path, period="15m", timestamps=["2026-03-20 09:30:00+08:00"], closes=[30.0])
    _write_parquet(tmp_path, period="30m", timestamps=["2026-03-20 09:30:00+08:00"], closes=[40.0])
    _write_parquet(tmp_path, period="60m", timestamps=["2026-03-20 09:30:00+08:00"], closes=[50.0])
    _write_parquet(tmp_path, period="1d", timestamps=["2026-03-20 15:00:00+08:00"], closes=[60.0])

    result = run_season_backtest(
        start_date="2026-03-20T09:30:00+08:00",
        end_date="2026-03-20T09:31:00+08:00",
        season_slug=season_slug,
        project_root=tmp_path,
        timezone="Asia/Shanghai",
    )

    strategy_module = importlib.import_module(module_name)
    strategy_cls = strategy_module.TraderProgram
    assert [dt.isoformat() for dt in strategy_cls.minute_events] == [
        "2026-03-20T09:30:00+08:00",
        "2026-03-20T09:31:00+08:00",
    ]
    assert strategy_cls.closes == [10.0, 11.0]
    assert strategy_cls.future_violation is False

    assert result.triggered_minutes == 2
    assert len(result.orders) == 1
    assert result.orders[0].status == "filled"
    assert result.orders[0].fill_price == 10.0


def test_run_season_backtest_uses_season_initial_capital_for_trader(tmp_path: Path) -> None:
    season_slug = f"cap{uuid.uuid4().hex[:6]}"
    trader_slug = "cap-trader"
    module_name = f"trader_incubator.core.skills.seasons.{season_slug}.traders.{trader_slug}.strategy"
    program_entry = f"{module_name}:TraderProgram"

    season_dir = tmp_path / "src" / "trader_incubator" / "core" / "skills" / "seasons" / season_slug
    trader_dir = season_dir / "traders" / trader_slug
    trader_dir.mkdir(parents=True, exist_ok=True)

    season_payload = {
        "season": season_slug,
        "market": "HK",
        "start_date": "2026-03-20",
        "end_date": "2026-03-20",
        "initial_capital": 888888.0,
        "symbol_pool": ["01810"],
        "traders": [
            {
                "trader": "Cap Trader",
                "style": "test",
                "program_entry": program_entry,
            }
        ],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (season_dir / "season.json").write_text(json.dumps(season_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trader_payload = {
        "trader": "Cap Trader",
        "season": season_slug,
        "style": "test",
        "program_entry": program_entry,
        "symbols": ["01810"],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (trader_dir / "trader.json").write_text(json.dumps(trader_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    strategy_code = """
from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    initial_capitals = []

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        cls = type(self)
        if not cls.initial_capitals:
            cls.initial_capitals.append(float(self.initial_capital))
"""
    (trader_dir / "strategy.py").write_text(strategy_code.strip() + "\n", encoding="utf-8")

    _write_parquet(
        tmp_path,
        period="1m",
        timestamps=["2026-03-20 09:30:00+08:00"],
        closes=[10.0],
    )

    _ = run_season_backtest(
        start_date="2026-03-20T09:30:00+08:00",
        end_date="2026-03-20T09:30:00+08:00",
        season_slug=season_slug,
        project_root=tmp_path,
        timezone="Asia/Shanghai",
    )

    strategy_module = importlib.import_module(module_name)
    strategy_cls = strategy_module.TraderProgram
    assert strategy_cls.initial_capitals == [888888.0]


def test_run_season_backtest_prefers_trader_initial_capital_override(tmp_path: Path) -> None:
    season_slug = f"ovr{uuid.uuid4().hex[:6]}"
    trader_slug = "ovr-trader"
    module_name = f"trader_incubator.core.skills.seasons.{season_slug}.traders.{trader_slug}.strategy"
    program_entry = f"{module_name}:TraderProgram"

    season_dir = tmp_path / "src" / "trader_incubator" / "core" / "skills" / "seasons" / season_slug
    trader_dir = season_dir / "traders" / trader_slug
    trader_dir.mkdir(parents=True, exist_ok=True)

    season_payload = {
        "season": season_slug,
        "market": "HK",
        "start_date": "2026-03-20",
        "end_date": "2026-03-20",
        "initial_capital": 1000000.0,
        "symbol_pool": ["01810"],
        "traders": [
            {
                "trader": "Override Trader",
                "style": "test",
                "program_entry": program_entry,
            }
        ],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (season_dir / "season.json").write_text(json.dumps(season_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trader_payload = {
        "trader": "Override Trader",
        "season": season_slug,
        "style": "test",
        "program_entry": program_entry,
        "initial_capital": 12345.0,
        "symbols": ["01810"],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (trader_dir / "trader.json").write_text(json.dumps(trader_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    strategy_code = """
from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    initial_capitals = []

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        cls = type(self)
        if not cls.initial_capitals:
            cls.initial_capitals.append(float(self.initial_capital))
"""
    (trader_dir / "strategy.py").write_text(strategy_code.strip() + "\n", encoding="utf-8")

    _write_parquet(
        tmp_path,
        period="1m",
        timestamps=["2026-03-20 09:30:00+08:00"],
        closes=[10.0],
    )

    _ = run_season_backtest(
        start_date="2026-03-20T09:30:00+08:00",
        end_date="2026-03-20T09:30:00+08:00",
        season_slug=season_slug,
        project_root=tmp_path,
        timezone="Asia/Shanghai",
    )

    strategy_module = importlib.import_module(module_name)
    strategy_cls = strategy_module.TraderProgram
    assert strategy_cls.initial_capitals == [12345.0]


def test_run_season_backtest_imports_strategy_from_hyphen_folder_fallback(tmp_path: Path) -> None:
    season_slug = f"hyf{uuid.uuid4().hex[:6]}"
    trader_slug = "tmp-bot"
    module_name = f"trader_incubator.core.skills.seasons.{season_slug}.traders.tmp_bot.strategy"
    program_entry = f"{module_name}:TraderProgram"

    season_dir = tmp_path / "src" / "trader_incubator" / "core" / "skills" / "seasons" / season_slug
    trader_dir = season_dir / "traders" / trader_slug
    trader_dir.mkdir(parents=True, exist_ok=True)

    season_payload = {
        "season": season_slug,
        "market": "HK",
        "start_date": "2026-03-20",
        "end_date": "2026-03-20",
        "initial_capital": 1000000.0,
        "symbol_pool": ["01810"],
        "traders": [
            {
                "trader": "Tmp Bot",
                "style": "test",
                "program_entry": program_entry,
            }
        ],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (season_dir / "season.json").write_text(json.dumps(season_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trader_payload = {
        "trader": "Tmp Bot",
        "season": season_slug,
        "style": "test",
        "program_entry": program_entry,
        "symbols": ["01810"],
        "created_at": "2026-03-20T00:00:00Z",
    }
    (trader_dir / "trader.json").write_text(json.dumps(trader_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    strategy_code = """
from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from exchange import TradingStrategy


class TraderProgram(TradingStrategy):
    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        pass
"""
    (trader_dir / "strategy.py").write_text(strategy_code.strip() + "\n", encoding="utf-8")

    _write_parquet(
        tmp_path,
        period="1m",
        timestamps=["2026-03-20 09:30:00+08:00"],
        closes=[10.0],
    )

    result = run_season_backtest(
        start_date="2026-03-20T09:30:00+08:00",
        end_date="2026-03-20T09:30:00+08:00",
        season_slug=season_slug,
        project_root=tmp_path,
        timezone="Asia/Shanghai",
    )
    assert result.triggered_minutes == 1


