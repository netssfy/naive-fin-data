from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
DOCS_ROOT = ROOT / "docs"
OUTPUT_FILE = DOCS_ROOT / "status-data.json"

UTC8 = timezone(timedelta(hours=8))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_code_name_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.exists():
        return mapping

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        if code:
            mapping[code] = name
    return mapping


def _parse_iso_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC8)
        return dt.astimezone(UTC8)
    except Exception:
        return None


def _time_score(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    try:
        return dt.timestamp()
    except Exception:
        return None


def _status_level(latest_fetch: datetime | None) -> str:
    latest_ts = _time_score(latest_fetch)
    if latest_ts is None:
        return "unknown"
    age_seconds = datetime.now(UTC8).timestamp() - latest_ts
    if age_seconds <= 36 * 3600:
        return "fresh"
    if age_seconds <= 4 * 24 * 3600:
        return "stale"
    return "old"


def _normalize_periods(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    periods = status.get("periods")
    if isinstance(periods, dict):
        out: dict[str, dict[str, Any]] = {}
        for period, value in periods.items():
            if isinstance(value, dict):
                out[str(period)] = {
                    "last_fetch_time": value.get("last_fetch_time"),
                    "last_data_time": value.get("last_data_time"),
                    "total_records": int(value.get("total_records", 0) or 0),
                }
        return out

    legacy_period = str(status.get("last_period", "")).strip().lower()
    if not legacy_period:
        return {}
    return {
        legacy_period: {
            "last_fetch_time": status.get("last_fetch_time"),
            "last_data_time": status.get("last_data_time"),
            "total_records": int(status.get("total_records", 0) or 0),
        }
    }


def build() -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    stock_root = DATA_ROOT / "stock"
    if not stock_root.exists():
        return {
            "generated_at": datetime.now(UTC8).isoformat(),
            "items": items,
        }

    for market_dir in sorted([p for p in stock_root.iterdir() if p.is_dir()]):
        market = market_dir.name
        name_map = _read_code_name_map(market_dir / "code.jsonl")

        for code_dir in sorted([p for p in market_dir.iterdir() if p.is_dir()]):
            code = code_dir.name
            status = _read_json(code_dir / "status.json")
            periods = _normalize_periods(status)

            latest_fetch: datetime | None = None
            latest_data: datetime | None = None
            latest_fetch_score: float | None = None
            latest_data_score: float | None = None
            total_records = 0
            for info in periods.values():
                total_records += int(info.get("total_records", 0) or 0)

                fetch_time = _parse_iso_time(info.get("last_fetch_time"))
                fetch_score = _time_score(fetch_time)
                if fetch_score is not None and (latest_fetch_score is None or fetch_score > latest_fetch_score):
                    latest_fetch = fetch_time
                    latest_fetch_score = fetch_score

                data_time = _parse_iso_time(info.get("last_data_time"))
                data_score = _time_score(data_time)
                if data_score is not None and (latest_data_score is None or data_score > latest_data_score):
                    latest_data = data_time
                    latest_data_score = data_score

            item = {
                "type": "stock",
                "market": market,
                "code": code,
                "name": name_map.get(code, ""),
                "periods": periods,
                "period_count": len(periods),
                "total_records": total_records,
                "latest_fetch_time": latest_fetch.isoformat() if latest_fetch else None,
                "latest_data_time": latest_data.isoformat() if latest_data else None,
                "status": _status_level(latest_fetch),
            }
            items.append(item)

    return {
        "generated_at": datetime.now(UTC8).isoformat(),
        "items": items,
    }


def main() -> int:
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
