from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
import time

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

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]

    out = out.reset_index().copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]

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
    out.columns = [str(col) for col in out.columns]
    return out


def _save_parquet(df: pd.DataFrame, target: FetchTarget, output_root: Path | str) -> Path:
    output_root = Path(output_root)
    output_dir = output_root / target.type / target.market / target.code / target.period
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{_today_str()}.parquet"
    df.to_parquet(output_file, index=False)
    return output_file



def _extract_last_data_time(df: pd.DataFrame) -> str | None:
    if "timestamp" not in df.columns or df.empty:
        return None
    ts = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
    if ts.empty:
        return None
    return ts.max().isoformat()


def _update_status(df: pd.DataFrame, target: FetchTarget, output_root: Path | str) -> Path:
    output_root = Path(output_root)
    status_dir = output_root / target.type / target.market / target.code
    status_dir.mkdir(parents=True, exist_ok=True)
    status_file = status_dir / "status.json"

    current_period = target.period
    period_records = int(len(df))
    status: dict[str, object] = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            status = {}

    status["code"] = target.code
    status["market"] = target.market
    status["type"] = target.type

    periods = status.get("periods", {})
    if not isinstance(periods, dict):
        periods = {}

    # Backward compatibility: migrate legacy flat fields into the period bucket.
    legacy_period = str(status.get("last_period", "")).strip().lower()
    if legacy_period and legacy_period not in periods:
        legacy_total = int(status.get("total_records", 0) or 0)
        periods[legacy_period] = {
            "last_fetch_time": status.get("last_fetch_time"),
            "last_data_time": status.get("last_data_time"),
            "total_records": legacy_total,
        }

    period_status = periods.get(current_period, {})
    if not isinstance(period_status, dict):
        period_status = {}

    prev_period_total = int(period_status.get("total_records", 0) or 0)
    period_status["last_fetch_time"] = datetime.now().isoformat()
    period_status["last_data_time"] = _extract_last_data_time(df)
    period_status["total_records"] = prev_period_total + period_records

    periods[current_period] = period_status
    status["periods"] = periods

    status_file.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status_file

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

    out = pd.DataFrame()
    out["code"] = df[code_col].dropna().astype(str).str.strip()
    if zfill is not None:
        out["code"] = out["code"].str.zfill(zfill)

    name_series = None
    for col in name_candidates:
        if col not in df.columns:
            continue
        s = df[col].fillna("").astype(str).str.strip()
        non_empty = s[(s != "") & (s.str.lower() != "nan")]
        if not non_empty.empty:
            name_series = s
            break
    if name_series is None:
        out["name"] = ""
    else:
        out["name"] = name_series

    out = out.drop_duplicates(subset=["code"]).reset_index(drop=True)
    return out


def _merge_code_name_df(base: pd.DataFrame, patch: pd.DataFrame) -> pd.DataFrame:
    merged = base.copy()
    patch_map = dict(zip(patch["code"].astype(str), patch["name"].astype(str)))
    merged["name"] = merged.apply(
        lambda r: patch_map.get(str(r["code"]), str(r["name"])) if str(r["name"]).strip() == "" else str(r["name"]),
        axis=1,
    )
    return merged

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
    raw = str(code).strip()
    numeric = raw.lstrip("0") or "0"
    # Yahoo HK equities are usually 4-digit codes (e.g. 0001.HK, 0700.HK).
    # Keep wider codes if present (e.g. 10000 -> 10000.HK).
    return f"{numeric.zfill(4)}.HK"


def _download_with_yfinance(symbol: str, period: str) -> pd.DataFrame:
    cfg = _get_interval_config(period)
    retries = 4
    for attempt in range(retries):
        df = yf.download(
            tickers=symbol,
            period=cfg["period"],
            interval=cfg["interval"],
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if not df.empty:
            return df

        if attempt < retries - 1:
            # Backoff for Yahoo transient throttling.
            time.sleep(3 * (attempt + 1))

    return pd.DataFrame()


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

    output_file = _save_parquet(df=df, target=target, output_root=output_root)
    _update_status(df=df, target=target, output_root=output_root)
    return output_file


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

    output_file = _save_parquet(df=df, target=target, output_root=output_root)
    _update_status(df=df, target=target, output_root=output_root)
    return output_file


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
    out = _get_code_name_df(df, ["code", "代码"], ["中文名称", "name", "名称", "英文名称"], zfill=6)
    out["market"] = market
    return _save_code_jsonl(out, output_root=output_root, type_name=type_name, market=market)


def export_hk_code_list(
    output_root: Path | str = "data",
    type_name: str = "stock",
    market: str = "hk",
) -> Path:
    try:
        df = ak.stock_hk_spot_em()
        out = _get_code_name_df(df, ["代码", "code", "symbol"], ["名称", "中文名称", "name", "英文名称"], zfill=5)
    except Exception:
        df = ak.stock_hk_spot()
        out = _get_code_name_df(df, ["symbol", "代码", "code"], ["中文名称", "name", "名称", "英文名称"], zfill=5)

    if (out["name"].astype(str).str.strip() == "").any():
        try:
            patch_df = ak.stock_hk_main_board_spot_em()
            patch = _get_code_name_df(
                patch_df,
                ["代码", "code", "symbol"],
                ["名称", "中文名称", "name", "英文名称"],
                zfill=5,
            )
            out = _merge_code_name_df(out, patch)
        except Exception:
            pass

    if (out["name"].astype(str).str.strip() == "").any():
        try:
            patch_df = ak.stock_hk_spot()
            patch = _get_code_name_df(
                patch_df,
                ["symbol", "代码", "code"],
                ["中文名称", "name", "名称", "英文名称"],
                zfill=5,
            )
            out = _merge_code_name_df(out, patch)
        except Exception:
            pass

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














