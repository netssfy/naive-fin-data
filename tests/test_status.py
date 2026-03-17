from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from naive_fin_data.fetcher import FetchTarget, _update_status


def _make_df(size: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=size, freq="D"),
            "open": [1.0] * size,
            "high": [1.0] * size,
            "low": [1.0] * size,
            "close": [1.0] * size,
            "adj_close": [1.0] * size,
            "volume": [1] * size,
            "code": ["000725"] * size,
        }
    )


def test_update_status_grouped_by_period(tmp_path: Path) -> None:
    target = FetchTarget(type="stock", market="cn", code="000725", period="1d")

    _update_status(df=_make_df(2), target=target, output_root=tmp_path)
    _update_status(df=_make_df(3), target=target, output_root=tmp_path)

    status_file = tmp_path / "stock" / "cn" / "000725" / "status.json"
    status = json.loads(status_file.read_text(encoding="utf-8"))

    assert status["code"] == "000725"
    assert status["market"] == "cn"
    assert status["type"] == "stock"
    assert "periods" in status
    assert status["periods"]["1d"]["total_records"] == 5
    assert status["periods"]["1d"]["last_data_time"] is not None


def test_update_status_migrates_legacy_flat_schema(tmp_path: Path) -> None:
    status_dir = tmp_path / "stock" / "cn" / "000725"
    status_dir.mkdir(parents=True)
    status_file = status_dir / "status.json"
    status_file.write_text(
        json.dumps(
            {
                "last_fetch_time": "2026-03-17T10:00:00",
                "last_data_time": "2026-03-17T00:00:00",
                "total_records": 10,
                "code": "000725",
                "market": "cn",
                "type": "stock",
                "last_period": "1m",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target = FetchTarget(type="stock", market="cn", code="000725", period="1d")
    _update_status(df=_make_df(1), target=target, output_root=tmp_path)

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["periods"]["1m"]["total_records"] == 10
    assert status["periods"]["1d"]["total_records"] == 1
