from __future__ import annotations

from datetime import datetime
from pathlib import Path
import uuid

import pandas as pd

from naive_fin_data import fetcher


STANDARD_COLUMNS = ["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"]
TEST_ROOT = Path(".tmp") / "tests" / "fetcher"


def _case_root(name: str) -> Path:
    root = TEST_ROOT / f"{name}-{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _yf_like_df() -> pd.DataFrame:
    idx = pd.DatetimeIndex([datetime(2026, 3, 19, 9, 31), datetime(2026, 3, 19, 9, 32)], name="Datetime")
    return pd.DataFrame(
        {
            "Open": [10.1, 10.2],
            "High": [10.3, 10.4],
            "Low": [10.0, 10.1],
            "Close": [10.2, 10.3],
            "Adj Close": [10.2, 10.3],
            "Volume": [1000, 1100],
        },
        index=idx,
    )


def test_fetch_single_a_share_prefers_akshare(monkeypatch) -> None:
    output_root = _case_root("a-ak")

    def fake_ak(symbol: str, period: str, adjust: str, start_date: str, end_date: str) -> pd.DataFrame:
        assert symbol == "600519"
        assert period == "daily"
        return pd.DataFrame(
            {
                "日期": ["2026-03-19", "2026-03-20"],
                "开盘": [1700.0, 1710.0],
                "最高": [1720.0, 1730.0],
                "最低": [1690.0, 1705.0],
                "收盘": [1715.0, 1725.0],
                "成交量": [100000, 120000],
            }
        )

    monkeypatch.setattr(fetcher.ak, "stock_zh_a_hist", fake_ak)

    def fail_yf(*args, **kwargs):
        raise AssertionError("yfinance should not be called when akshare succeeds")

    monkeypatch.setattr(fetcher, "_download_with_yfinance_incremental", fail_yf)

    output = fetcher.fetch_single_a_share(code="600519", period="1d", output_root=output_root)
    assert output is not None and output.exists()

    df = pd.read_parquet(output)
    assert list(df.columns) == STANDARD_COLUMNS
    assert set(df["code"].astype(str)) == {"600519"}
    # Keep source timestamp labeling as-is (no forced left alignment shift).
    assert pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d").tolist() == ["2026-03-19", "2026-03-20"]


def test_fetch_single_a_share_falls_back_to_yfinance(monkeypatch) -> None:
    output_root = _case_root("a-fallback")

    def fail_ak(*args, **kwargs):
        raise RuntimeError("akshare network error")

    monkeypatch.setattr(fetcher.ak, "stock_zh_a_hist", fail_ak)

    called = {"value": False}

    def fake_yf(symbol: str, period: str, last_data_time):
        called["value"] = True
        assert symbol.endswith((".SS", ".SZ", ".BJ"))
        return _yf_like_df()

    monkeypatch.setattr(fetcher, "_download_with_yfinance_incremental", fake_yf)

    output = fetcher.fetch_single_a_share(code="000725", period="1d", output_root=output_root)
    assert output is not None and output.exists()
    assert called["value"] is True

    df = pd.read_parquet(output)
    assert list(df.columns) == STANDARD_COLUMNS
    assert set(df["code"].astype(str)) == {"000725"}
    # yfinance timestamps should remain unchanged (no -period shift).
    assert pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S").tolist() == [
        "2026-03-19 09:31:00",
        "2026-03-19 09:32:00",
    ]


def test_fetch_single_hk_prefers_akshare(monkeypatch) -> None:
    output_root = _case_root("hk-ak")

    def fake_ak(symbol: str, period: str, adjust: str, start_date: str, end_date: str) -> pd.DataFrame:
        assert symbol == "00700"
        assert period == "daily"
        return pd.DataFrame(
            {
                "日期": ["2026-03-19", "2026-03-20"],
                "开盘": [310.0, 312.0],
                "最高": [315.0, 316.0],
                "最低": [308.0, 311.0],
                "收盘": [314.0, 315.0],
                "成交量": [230000, 250000],
            }
        )

    monkeypatch.setattr(fetcher.ak, "stock_hk_hist", fake_ak)

    def fail_yf(*args, **kwargs):
        raise AssertionError("yfinance should not be called when akshare succeeds")

    monkeypatch.setattr(fetcher, "_download_with_yfinance_incremental", fail_yf)

    output = fetcher.fetch_single_hk(code="700", period="1d", output_root=output_root)
    assert output is not None and output.exists()

    df = pd.read_parquet(output)
    assert list(df.columns) == STANDARD_COLUMNS
    assert set(df["code"].astype(str)) == {"00700"}
    # Keep source timestamp labeling as-is (no forced left alignment shift).
    assert pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d").tolist() == ["2026-03-19", "2026-03-20"]
