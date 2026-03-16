from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import akshare as ak
import pandas as pd
import yfinance as yf
import json

INTERVAL_CONFIG = {
    "1m": {"interval": "1m", "period": "7d"},
    "5m": {"interval": "5m", "period": "60d"},
    "15m": {"interval": "15m", "period": "60d"},
    "30m": {"interval": "30m", "period": "60d"},
    "60m": {"interval": "60m", "period": "730d"},
    "1d": {"interval": "1d", "period": "max"},
    "daily": {"interval": "1d", "period": "max"},
    "1w": {"interval": "1wk", "period": "max"},
    "weekly": {"interval": "1wk", "period": "max"},
    "1mo": {"interval": "1mo", "period": "max"},
    "monthly": {"interval": "1mo", "period": "max"},
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


def _get_interval_config(period: str) -> dict[str, str]:
    key = _normalize_period(period)
    if key not in INTERVAL_CONFIG:
        raise ValueError(f"unsupported period: {period}")
    return INTERVAL_CONFIG[key]


def _normalize_price_df(df: pd.DataFrame, code: str) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.reset_index().copy()
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

    out["code"] = code
    out = out[["timestamp", "open", "high", "low", "close", "adj_close", "volume", "code"]]
    return out


def _save_parquet(df: pd.DataFrame, target: FetchTarget, output_root: Path | str) -> Path:
    output_root = Path(output_root)
    output_dir = output_root / target.type / target.market / target.code / target.period
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{_today_str()}.parquet"
    df.to_parquet(output_file, index=False)
    return output_file


def _save_code_jsonl(
    df: pd.DataFrame,
    output_root: Path | str,
    type_name: str,
    market: str,
) -> Path:
    output_root = Path(output_root)
    output_dir = output_root / type_name / market
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "code.jsonl"

    merged: dict[str, str] = {}
    if output_file.exists():
        with output_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                code = str(item.get("code", "")).strip()
                name = str(item.get("name", "")).strip()
                if code:
                    merged[code] = name

    for row in df[["code", "name"]].itertuples(index=False):
        code = str(row.code).strip()
        name = str(row.name).strip()
        if code:
            merged[code] = name

    with output_file.open("w", encoding="utf-8") as f:
        for code in sorted(merged.keys()):
            f.write(json.dumps({"code": code, "name": merged[code]}, ensure_ascii=False) + "\n")
    return output_file


def _load_latest_codes_from_data(
    output_root: Path | str,
    type_name: str,
    market: str,
) -> list[str]:
    file = Path(output_root) / type_name / market / "code.jsonl"
    if not file.exists():
        return []

    codes: list[str] = []
    with file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            code = str(item.get("code", "")).strip()
            if code:
                codes.append(code)
    return codes


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


def _get_code_name_df(
    df: pd.DataFrame,
    code_candidates: list[str],
    name_candidates: list[str],
    zfill: int | None = None,
) -> pd.DataFrame:
    code_col = next((c for c in code_candidates if c in df.columns), None)
    if code_col is None:
        raise RuntimeError(f"code column not found in {list(df.columns)}")

    name_col = next((c for c in name_candidates if c in df.columns), None)
    out = pd.DataFrame()
    out["code"] = df[code_col].dropna().astype(str).str.strip()
    if zfill is not None:
        out["code"] = out["code"].str.zfill(zfill)

    if name_col is None:
        out["name"] = ""
    else:
        out["name"] = df[name_col].astype(str).fillna("").str.strip()

    out = out.drop_duplicates(subset=["code"]).reset_index(drop=True)
    return out


def _to_yf_a_symbol(code: str) -> str:
    raw = str(code).strip().zfill(6)
    if raw.startswith(("6", "9", "5")):
        suffix = ".SS"
    elif raw.startswith(("0", "2", "3")):
        suffix = ".SZ"
    else:
        suffix = ".BJ"
    return f"{raw}{suffix}"


def _to_yf_hk_symbol(code: str) -> str:
    return f"{str(code).strip().zfill(5)}.HK"


def _download_with_yfinance(symbol: str, period: str) -> pd.DataFrame:
    cfg = _get_interval_config(period)
    return yf.download(
        tickers=symbol,
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def fetch_single_a_share(
    code: str,
    period: str,
    output_root: Path | str = "data",
    adjust: str = "qfq",
    type_name: str = "stock",
    market: str = "cn",
) -> Path:
    del adjust
    norm_code = str(code).strip().zfill(6)
    norm_period = _normalize_period(period)
    target = FetchTarget(type=type_name, market=market, code=norm_code, period=norm_period)

    df = _download_with_yfinance(symbol=_to_yf_a_symbol(norm_code), period=norm_period)
    df = _normalize_price_df(df, norm_code)
    if df.empty:
        raise ValueError(f"no data returned for {norm_code}")
    return _save_parquet(df=df, target=target, output_root=output_root)


def list_all_a_share_codes() -> list[str]:
    df = ak.stock_info_a_code_name()
    return _get_codes_from_df(df, ["code", "代码"], zfill=6)


def fetch_all_a_share(
    period: str,
    output_root: Path | str = "data",
    adjust: str = "qfq",
    type_name: str = "stock",
    market: str = "cn",
    symbols: Iterable[str] | None = None,
    limit: int | None = None,
) -> dict[str, list[str]]:
    if symbols is not None:
        codes = list(symbols)
    else:
        codes = _load_latest_codes_from_data(output_root, type_name, market)
        if not codes:
            codes = list_all_a_share_codes()

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
    del adjust
    norm_code = str(code).strip().zfill(5)
    norm_period = _normalize_period(period)
    target = FetchTarget(type=type_name, market=market, code=norm_code, period=norm_period)

    df = _download_with_yfinance(symbol=_to_yf_hk_symbol(norm_code), period=norm_period)
    df = _normalize_price_df(df, norm_code)
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
    if symbols is not None:
        codes = list(symbols)
    else:
        codes = _load_latest_codes_from_data(output_root, type_name, market)
        if not codes:
            codes = list_all_hk_codes()

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


def export_a_share_code_list(
    output_root: Path | str = "data",
    type_name: str = "stock",
    market: str = "cn",
) -> Path:
    df = ak.stock_info_a_code_name()
    out = _get_code_name_df(df, ["code", "代码"], ["name", "名称"], zfill=6)
    out["market"] = market
    return _save_code_jsonl(out, output_root=output_root, type_name=type_name, market=market)


def export_hk_code_list(
    output_root: Path | str = "data",
    type_name: str = "stock",
    market: str = "hk",
) -> Path:
    try:
        df = ak.stock_hk_spot_em()
        out = _get_code_name_df(df, ["代码", "code", "symbol"], ["名称", "name"], zfill=5)
    except Exception:
        df = ak.stock_hk_spot()
        out = _get_code_name_df(df, ["symbol", "代码", "code"], ["name", "名称"], zfill=5)

    out["market"] = market
    return _save_code_jsonl(out, output_root=output_root, type_name=type_name, market=market)


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



