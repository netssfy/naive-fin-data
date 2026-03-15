from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import akshare as ak
import pandas as pd

MINUTE_PERIOD_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}

DAY_PERIOD_MAP = {
    "1d": "daily",
    "1w": "weekly",
    "1mo": "monthly",
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
}


@dataclass(frozen=True)
class FetchTarget:
    type: str
    market: str
    code: str
    period: str


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _normalize_period(period: str) -> str:
    return str(period).strip().lower()


def _resolve_minute_period(period: str) -> str | None:
    return MINUTE_PERIOD_MAP.get(_normalize_period(period))


def _resolve_day_period(period: str) -> str | None:
    return DAY_PERIOD_MAP.get(_normalize_period(period))


def _normalize_hist_df(df: pd.DataFrame, code: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["code"] = code
    return out


def _save_parquet(df: pd.DataFrame, target: FetchTarget, output_root: Path | str) -> Path:
    output_root = Path(output_root)
    output_dir = output_root / target.type / target.market / target.code / target.period
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{_today_str()}.parquet"
    df.to_parquet(output_file, index=False)
    return output_file


def _run_batch(
    codes: list[str],
    fetch_one: Callable[[str], None],
) -> dict[str, list[str]]:
    result = {"success": [], "failed": []}
    for code in codes:
        try:
            fetch_one(code)
            result["success"].append(code)
        except Exception:
            result["failed"].append(code)
    return result


def _get_codes_from_df(df: pd.DataFrame, candidates: list[str], zfill: int | None = None) -> list[str]:
    for col in candidates:
        if col in df.columns:
            series = df[col].dropna().astype(str).str.strip()
            if zfill is not None:
                series = series.str.zfill(zfill)
            return series.tolist()
    raise RuntimeError(f"unexpected schema for symbol list, available columns: {list(df.columns)}")


def fetch_single_a_share(
    code: str,
    period: str,
    output_root: Path | str = "data",
    adjust: str = "qfq",
    type_name: str = "stock",
    market: str = "cn",
) -> Path:
    norm_period = _normalize_period(period)
    target = FetchTarget(type=type_name, market=market, code=code, period=norm_period)

    minute_period = _resolve_minute_period(norm_period)
    if minute_period is not None:
        df = ak.stock_zh_a_hist_min_em(symbol=code, period=minute_period, adjust=adjust)
    else:
        day_period = _resolve_day_period(norm_period)
        if day_period is None:
            raise ValueError(f"unsupported A-share period: {period}")
        df = ak.stock_zh_a_hist(symbol=code, period=day_period, adjust=adjust)

    df = _normalize_hist_df(df, code)
    if df.empty:
        raise ValueError(f"no data returned for {code}")
    return _save_parquet(df=df, target=target, output_root=output_root)


def list_all_a_share_codes() -> list[str]:
    try:
        spot_df = ak.stock_zh_a_spot_em()
        return _get_codes_from_df(spot_df, ["代码", "code"])
    except Exception:
        basic_df = ak.stock_info_a_code_name()
        return _get_codes_from_df(basic_df, ["code", "代码"])


def fetch_all_a_share(
    period: str,
    output_root: Path | str = "data",
    adjust: str = "qfq",
    type_name: str = "stock",
    market: str = "cn",
    symbols: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict[str, list[str]]:
    codes = list(symbols) if symbols is not None else list_all_a_share_codes()
    if limit is not None:
        codes = codes[:limit]

    return _run_batch(
        codes=codes,
        fetch_one=lambda code: fetch_single_a_share(
            code=code,
            period=period,
            output_root=output_root,
            adjust=adjust,
            type_name=type_name,
            market=market,
        ),
    )


def fetch_single_hk(
    code: str,
    period: str,
    output_root: Path | str = "data",
    adjust: str = "",
    type_name: str = "stock",
    market: str = "hk",
) -> Path:
    norm_code = str(code).zfill(5)
    norm_period = _normalize_period(period)
    target = FetchTarget(type=type_name, market=market, code=norm_code, period=norm_period)

    minute_period = _resolve_minute_period(norm_period)
    if minute_period is not None:
        df = ak.stock_hk_hist_min_em(symbol=norm_code, period=minute_period, adjust=adjust)
    else:
        day_period = _resolve_day_period(norm_period)
        if day_period is None:
            raise ValueError(f"unsupported HK period: {period}")
        df = ak.stock_hk_hist(symbol=norm_code, period=day_period, adjust=adjust)

    df = _normalize_hist_df(df, norm_code)
    if df.empty:
        raise ValueError(f"no data returned for {norm_code}")
    return _save_parquet(df=df, target=target, output_root=output_root)


def list_all_hk_codes() -> list[str]:
    try:
        spot_df = ak.stock_hk_spot_em()
        return _get_codes_from_df(spot_df, ["代码", "code", "symbol"], zfill=5)
    except Exception:
        basic_df = ak.stock_hk_spot()
        return _get_codes_from_df(basic_df, ["symbol", "代码", "code"], zfill=5)


def fetch_all_hk(
    period: str,
    output_root: Path | str = "data",
    adjust: str = "",
    type_name: str = "stock",
    market: str = "hk",
    symbols: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict[str, list[str]]:
    codes = list(symbols) if symbols is not None else list_all_hk_codes()
    if limit is not None:
        codes = codes[:limit]

    return _run_batch(
        codes=codes,
        fetch_one=lambda code: fetch_single_hk(
            code=code,
            period=period,
            output_root=output_root,
            adjust=adjust,
            type_name=type_name,
            market=market,
        ),
    )


# Backward compatible wrappers

def fetch_single(
    target: FetchTarget,
    output_root: Path | str = "data",
    adjust: str = "qfq",
) -> Path:
    if target.market.lower() == "hk":
        return fetch_single_hk(
            code=target.code,
            period=target.period,
            output_root=output_root,
            adjust=adjust,
            type_name=target.type,
            market=target.market,
        )
    return fetch_single_a_share(
        code=target.code,
        period=target.period,
        output_root=output_root,
        adjust=adjust,
        type_name=target.type,
        market=target.market,
    )


def fetch_all(
    period: str,
    output_root: Path | str = "data",
    market: str = "cn",
    type_name: str = "stock",
    adjust: str = "qfq",
    symbols: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict[str, list[str]]:
    if market.lower() == "hk":
        return fetch_all_hk(
            period=period,
            output_root=output_root,
            adjust=adjust,
            type_name=type_name,
            market=market,
            symbols=symbols,
            limit=limit,
        )
    return fetch_all_a_share(
        period=period,
        output_root=output_root,
        adjust=adjust,
        type_name=type_name,
        market=market,
        symbols=symbols,
        limit=limit,
    )
