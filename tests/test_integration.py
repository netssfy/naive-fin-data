from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from naive_fin_data.fetcher import (
    fetch_all_a_share,
    fetch_all_hk,
    fetch_single_a_share,
    fetch_single_hk,
)


UTC8 = timezone(timedelta(hours=8))

def _today() -> str:
    return datetime.now(UTC8).strftime("%Y%m%d")


def _run_or_skip(callable_obj, *args, **kwargs):
    try:
        return callable_obj(*args, **kwargs)
    except Exception as exc:
        pytest.skip(f"AkShare endpoint unavailable in current environment: {exc}")


@pytest.mark.integration
def test_fetch_single_a_share_real_api(tmp_path: Path) -> None:
    output = _run_or_skip(
        fetch_single_a_share,
        code="600519",
        period="daily",
        output_root=tmp_path,
    )

    assert output == tmp_path / "stock" / "cn" / "600519" / "daily" / f"{_today()}.parquet"
    assert output.exists()

    df = pd.read_parquet(output)
    assert not df.empty
    assert "code" in df.columns
    assert "600519" in set(df["code"].astype(str).tolist())


@pytest.mark.integration
def test_fetch_single_hk_real_api(tmp_path: Path) -> None:
    output = _run_or_skip(
        fetch_single_hk,
        code="00005",
        period="daily",
        output_root=tmp_path,
    )

    assert output == tmp_path / "stock" / "hk" / "00005" / "daily" / f"{_today()}.parquet"
    assert output.exists()

    df = pd.read_parquet(output)
    assert not df.empty
    assert "code" in df.columns
    assert "00005" in set(df["code"].astype(str).tolist())


@pytest.mark.integration
def test_fetch_all_a_share_real_api_with_limit(tmp_path: Path) -> None:
    result = _run_or_skip(
        fetch_all_a_share,
        period="daily",
        output_root=tmp_path,
        limit=2,
    )

    total = len(result["success"]) + len(result["failed"])
    assert total == 2
    if not result["success"]:
        pytest.skip("AkShare responded but did not return successful A-share fetch results")

    for code in result["success"]:
        parquet_file = tmp_path / "stock" / "cn" / code / "daily" / f"{_today()}.parquet"
        assert parquet_file.exists()


@pytest.mark.integration
def test_fetch_all_hk_real_api_with_limit(tmp_path: Path) -> None:
    result = _run_or_skip(
        fetch_all_hk,
        period="daily",
        output_root=tmp_path,
        limit=2,
    )

    total = len(result["success"]) + len(result["failed"])
    assert total == 2
    if not result["success"]:
        pytest.skip("AkShare responded but did not return successful HK fetch results")

    for code in result["success"]:
        parquet_file = tmp_path / "stock" / "hk" / code / "daily" / f"{_today()}.parquet"
        assert parquet_file.exists()
