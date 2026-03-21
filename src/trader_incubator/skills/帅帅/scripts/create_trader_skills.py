﻿#!/usr/bin/env python3
"""create_trader_skills.py — 帅帅用来创建交易员 skill 文件的工具脚本。

用法：
  python create_trader_skills.py \\
      --season "Season 1" \\
      --trader "Alpha Wolf" \\
      --style "trend-following/intraday/strict-stop-loss" \\
      --program-entry "trader_incubator.skills.seasons.season-1.traders.alpha-wolf.strategy:TraderProgram" \\
      [--symbols 000725 600519 ...] \\
      [--project-root .]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT_GUESS = _HERE.parents[5]
sys.path.insert(0, str(_PROJECT_ROOT_GUESS / "src"))

from trader_incubator.trader import Trader  # noqa: E402
from trader_incubator.season import Season, SeasonTraderRef, slugify  # noqa: E402


def create_trader(
    season: str,
    trader: str,
    style: str,
    program_entry: str | None,
    symbols: list[str],
    project_root: Path,
) -> Trader:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    season_obj = Season.load(season_slug=slugify(season), project_root=project_root)

    # Build a temporary Trader to derive slugs/module names
    t_tmp = Trader(trader=trader, season=season, style=style, program_entry="", symbols=symbols)
    if not program_entry:
        program_entry = (
            f"trader_incubator.skills.seasons.{t_tmp.season_module_name}"
            f".traders.{t_tmp.module_name}.strategy:TraderProgram"
        )

    t = Trader(
        trader=trader,
        season=season,
        style=style,
        program_entry=program_entry,
        initial_capital=season_obj.initial_capital,
        symbols=symbols,
        created_at=now,
    )

    # 1. Save trader.json
    trader_json_path = t.save(project_root)
    print(f"created: {trader_json_path}")

    # 2. Scaffold skill files
    skill_dir = (
        project_root / "src" / "trader_incubator" / "skills" / "seasons"
        / t.season_slug / "traders" / t.slug
    )
    _write_skill_md(skill_dir / "SKILL.md", t)
    _write_openai_yaml(skill_dir / "agents" / "openai.yaml", t)
    _write_strategy(skill_dir / "strategy.py", t)

    # 3. Update season.json roster
    s = season_obj
    s.add_trader(SeasonTraderRef(
        trader=t.trader,
        style=t.style,
        program_entry=t.program_entry,
    ))
    s.save(project_root)
    print(f"updated: season.json roster ({len(s.traders)} traders)")

    return t


def _write_skill_md(path: Path, t: Trader) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    symbols_inline = ", ".join(t.symbols)
    content = f"""---
name: {t.slug}
description: Execute trader {t.trader} with style {t.style} for season {t.season}. Use when this trader needs to analyze market data, produce trading signals, and refine strategy during non-trading time.
trader: {t.trader}
season: {t.season}
style: {t.style}
program_entry: {t.program_entry}
symbols: [{symbols_inline}]
---

# {t.trader}

## Trading Time Rules
- Analyze market input and emit tradable signals.
- Do not modify strategy during active trading hours.

## Non-Trading Time Rules
- Review trade outcomes.
- Research market updates.
- Propose and implement strategy improvements in `strategy.py`.

## Exchange Interface Contract
The strategy class in `strategy.py` must subclass `TradingStrategy` from `trader_incubator.exchange`
and be loadable by the Exchange via `program_entry`:
```python
import importlib
module, cls_name = "{t.program_entry}".split(":")
strategy_cls = getattr(importlib.import_module(module), cls_name)
instance = strategy_cls(name="{t.slug}", symbols={t.symbols!r})
```
"""
    path.write_text(content, encoding="utf-8")


def _write_openai_yaml(path: Path, t: Trader) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    short_desc = f"Trader {t.trader} ({t.style}) strategy executor."
    default_prompt = f"Use ${t.slug} to analyze market data and generate signals."
    content = (
        "interface:\n"
        f"  display_name: \"{_yaml_escape(t.trader)}\"\n"
        f"  short_description: \"{_yaml_escape(short_desc)}\"\n"
        f"  default_prompt: \"{_yaml_escape(default_prompt)}\"\n"
    )
    path.write_text(content, encoding="utf-8")




def _write_strategy(path: Path, t: Trader) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cls_name = t.program_entry.split(":")[-1] if ":" in t.program_entry else "TraderProgram"
    content = f'''from __future__ import annotations

from datetime import datetime
from typing import Mapping

import pandas as pd

from trader_incubator.exchange import TradingStrategy


class {cls_name}(TradingStrategy):
    """{t.trader} — {t.style} strategy for season {t.season}.

    slug: {t.slug}
    program_entry: {t.program_entry}
    """

    def on_pre_open(self, event_time: datetime) -> None:
        """Called before market opens. Prepare any intraday state here."""
        pass

    def on_minute(self, event_time: datetime, latest_bars: Mapping[str, pd.Series]) -> None:
        """Called every minute during trading hours.

        Implement {t.style} trading logic here.
        Use self.place_market_order(code, side, quantity) to submit orders.
        Use self.history(code, lookback) to access historical bars.
        """
        pass

    def on_post_close(self, event_time: datetime) -> None:
        """Called after market closes. Review and log daily results."""
        pass
'''
    path.write_text(content, encoding="utf-8")


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description="帅帅创建交易员 skill 文件")
    parser.add_argument("--season", required=True, help="赛季名称，如 'Season 1'")
    parser.add_argument("--trader", required=True, help="交易员名称，如 'Alpha Wolf'")
    parser.add_argument("--style", required=True, help="交易风格，如 trend-following/intraday/strict-stop-loss")
    parser.add_argument("--program-entry", default=None, help="策略类入口（可选，不填自动生成）")
    parser.add_argument("--symbols", nargs="*", default=[], help="可交易股票代码列表")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    create_trader(
        season=args.season,
        trader=args.trader,
        style=args.style,
        program_entry=args.program_entry,  # None means auto-generate
        symbols=args.symbols,
        project_root=project_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
