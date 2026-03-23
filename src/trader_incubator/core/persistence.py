"""Persistence helpers: save per-trader orders and daily equity snapshots to disk."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Sequence

from exchange import Order, SimulatedMatchingEngine, SymbolRef


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _trader_dir(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    primary = project_root / "src" / "trader_incubator" / "skills" / "seasons" / season_slug / "traders" / trader_slug
    if primary.exists():
        return primary
    fallback = project_root / "src" / "trader_incubator" / "core" / "skills" / "seasons" / season_slug / "traders" / trader_slug
    if fallback.exists():
        return fallback
    # default to core path for new writes
    return fallback


def orders_path(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return _trader_dir(project_root, season_slug, trader_slug) / "orders.json"


def equity_path(project_root: Path, season_slug: str, trader_slug: str) -> Path:
    return _trader_dir(project_root, season_slug, trader_slug) / "equity.json"


# ---------------------------------------------------------------------------
# orders.json
# ---------------------------------------------------------------------------

def _order_to_dict(order: Order) -> dict:
    return {
        "order_id": order.order_id,
        "symbol_key": order.symbol_key,
        "side": order.side,
        "quantity": order.quantity,
        "submitted_at": order.submitted_at.isoformat(),
        "status": order.status,
        "fill_price": order.fill_price,
        "commission": order.commission,
        "message": order.message,
    }


def save_orders(
    project_root: Path,
    season_slug: str,
    trader_slug: str,
    orders: Sequence[Order],
) -> Path:
    """Append new orders to orders.json (deduplicates by order_id)."""
    path = orders_path(project_root, season_slug, trader_slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_ids = {item["order_id"] for item in existing}
    new_entries = [_order_to_dict(o) for o in orders if o.order_id not in existing_ids]
    merged = existing + new_entries
    merged.sort(key=lambda x: (x["submitted_at"], x["order_id"]))

    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# equity.json
# ---------------------------------------------------------------------------

def compute_daily_equity(
    engine: SimulatedMatchingEngine,
    trader_name: str,
    initial_capital: float,
    close_prices: dict[str, float],  # symbol_key -> close price
    trading_date: date,
) -> dict:
    """
    Compute end-of-day equity snapshot for one trader.

    total_assets = cash + Σ(position_qty × close_price)
    return_pct   = (total_assets - initial_capital) / initial_capital × 100
    """
    cash = engine.get_cash(trader_name)
    positions = engine.get_positions(trader_name)

    holdings_value = 0.0
    holdings: dict[str, dict] = {}
    for symbol_key, qty in positions.items():
        price = close_prices.get(symbol_key, 0.0)
        value = qty * price
        holdings_value += value
        holdings[symbol_key] = {"quantity": qty, "close_price": price, "value": round(value, 4)}

    total_assets = cash + holdings_value
    return_pct = (total_assets - initial_capital) / initial_capital * 100 if initial_capital else 0.0

    return {
        "date": trading_date.isoformat(),
        "cash": round(cash, 4),
        "holdings_value": round(holdings_value, 4),
        "total_assets": round(total_assets, 4),
        "initial_capital": round(initial_capital, 4),
        "return_pct": round(return_pct, 6),
        "holdings": holdings,
    }


def save_equity(
    project_root: Path,
    season_slug: str,
    trader_slug: str,
    snapshot: dict,
) -> Path:
    """Append or update a daily equity snapshot in equity.json (keyed by date)."""
    path = equity_path(project_root, season_slug, trader_slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    # upsert by date
    by_date = {item["date"]: item for item in existing}
    by_date[snapshot["date"]] = snapshot
    sorted_entries = sorted(by_date.values(), key=lambda x: x["date"])

    path.write_text(json.dumps(sorted_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Convenience: persist a full backtest result
# ---------------------------------------------------------------------------

def persist_backtest_results(
    project_root: Path,
    season_slug: str,
    engine: SimulatedMatchingEngine,
    strategies_meta: list[dict],  # [{"name": str, "slug": str, "initial_capital": float}]
    close_prices_by_date: dict[date, dict[str, float]],  # date -> {symbol_key -> price}
) -> None:
    """
    Save orders.json and equity.json for every trader after a backtest run.

    close_prices_by_date should contain the last available close price per symbol
    for each trading date that was simulated.
    """
    for meta in strategies_meta:
        trader_name: str = meta["name"]
        trader_slug: str = meta["slug"]
        initial_capital: float = meta["initial_capital"]

        # --- orders ---
        trader_orders = engine.get_trade_history(trader_name)
        save_orders(
            project_root=project_root,
            season_slug=season_slug,
            trader_slug=trader_slug,
            orders=trader_orders,
        )

        # --- equity: one snapshot per trading date ---
        for trading_date in sorted(close_prices_by_date):
            close_prices = close_prices_by_date[trading_date]
            snapshot = compute_daily_equity(
                engine=engine,
                trader_name=trader_name,
                initial_capital=initial_capital,
                close_prices=close_prices,
                trading_date=trading_date,
            )
            save_equity(
                project_root=project_root,
                season_slug=season_slug,
                trader_slug=trader_slug,
                snapshot=snapshot,
            )
