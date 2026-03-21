#!/usr/bin/env python3
"""season_manager.py — 创建和查看 season 配置。"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT_GUESS = _HERE.parents[5]
sys.path.insert(0, str(_PROJECT_ROOT_GUESS / "src"))

from trader_incubator.season import Season, slugify  # noqa: E402


def cmd_create(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    season = Season(
        season=args.season,
        market=args.market,
        start_date=args.start_date,
        end_date=args.end_date or None,
        initial_capital=float(args.initial_capital),
        symbol_pool=args.symbols or [],
        created_at=now,
    )

    path = season.save(project_root)
    print(f"created: {path}")
    print(season.to_json())
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    season_slug = slugify(args.season)
    try:
        season = Season.load(season_slug, project_root)
    except FileNotFoundError:
        print(f"error: season '{args.season}' (slug: {season_slug}) not found", file=sys.stderr)
        return 1
    print(season.to_json())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="season 管理工具")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="创建新 season")
    p_create.add_argument("--season", required=True, help="season 名称，如 'Season 1'")
    p_create.add_argument("--market", required=True, choices=["A_SHARE", "HK", "US"], help="交易市场")
    p_create.add_argument("--start-date", required=True, help="开始日期，ISO-8601，例如 2026-01-01")
    p_create.add_argument("--end-date", default=None, help="结束日期，可选")
    p_create.add_argument("--initial-capital", type=float, default=1000000.0, help="初始资金，默认 1000000")
    p_create.add_argument("--symbols", nargs="*", default=[], help="可交易股票代码列表；不填表示全市场")
    p_create.add_argument("--project-root", default=".", help="项目根目录")

    p_show = sub.add_parser("show", help="查看 season 配置")
    p_show.add_argument("--season", required=True, help="season 名称或 slug")
    p_show.add_argument("--project-root", default=".", help="项目根目录")

    args = parser.parse_args()

    if args.command == "create":
        return cmd_create(args)
    if args.command == "show":
        return cmd_show(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
