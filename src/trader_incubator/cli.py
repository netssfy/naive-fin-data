from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from trader_incubator.models import Market, SeasonConfig, SkillSpec
from trader_incubator.skill_runtime import DeerFlowEmbeddedSkillRuntime
from trader_incubator.world import WorldKernel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trader incubator world kernel")
    parser.add_argument("--season-id", required=True)
    parser.add_argument("--market", choices=[m.value for m in Market], required=True)
    parser.add_argument("--starts-at", required=True, help="ISO datetime")
    parser.add_argument("--shuaishu-skill-md", required=True, help="Path to 帅帅 skill.md")
    parser.add_argument("--desired-traders", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    season = SeasonConfig(
        season_id=args.season_id,
        market=Market(args.market),
        starts_at=datetime.fromisoformat(args.starts_at),
    )
    shuaishu = SkillSpec(name="帅帅", skill_md_path=Path(args.shuaishu_skill_md))
    world = WorldKernel(
        season=season,
        shuaishu_skill=shuaishu,
        skill_runtime=DeerFlowEmbeddedSkillRuntime(),
    )
    raw_roster_plan = world.bootstrap_traders(desired_count=args.desired_traders)
    print("=== 帅帅输出（交易员创建计划）===")
    print(raw_roster_plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

