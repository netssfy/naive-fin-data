#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def scaffold_trader_skills(roster: dict[str, Any], project_root: Path) -> list[Path]:
    created: list[Path] = []
    traders = roster.get("traders", [])
    if not isinstance(traders, list):
        raise ValueError("roster.traders must be a list")

    for trader in traders:
        if not isinstance(trader, dict):
            raise ValueError("each trader must be an object")

        skill_name = str(trader["trader_skill_name"])
        raw_path = Path(str(trader["trader_skill_path"]))
        skill_path = raw_path if raw_path.is_absolute() else (project_root / raw_path)
        skill_dir = skill_path.parent

        _write_skill_md(skill_path, trader)
        _write_openai_yaml(skill_dir / "agents" / "openai.yaml", trader, skill_name)
        _write_identity(skill_dir / "references" / "identity.md", trader)

        created.append(skill_path)
        print(f"created: {skill_path}")

    return created


def _write_skill_md(path: Path, trader: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
name: {trader['trader_skill_name']}
description: Execute trader {trader['name']} with style {trader['style']}. Use when this trader needs to analyze market data, produce trading signals, and refine strategy during non-trading time.
---

# {trader['name']}

## Identity
- trader_id: `{trader['trader_id']}`
- style: `{trader['style']}`
- program_entry: `{trader['program_entry']}`

## Trading Time Rules
- Analyze market input and emit tradable signals.
- Do not modify strategy during active trading hours.

## Non-Trading Time Rules
- Review trade outcomes.
- Research market updates.
- Propose and implement strategy improvements.
"""
    path.write_text(content, encoding="utf-8")


def _write_openai_yaml(path: Path, trader: dict[str, Any], skill_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    short_desc = f"Trader {trader['name']} ({trader['style']}) strategy executor."
    default_prompt = trader.get(
        "trader_default_prompt",
        f"Use ${skill_name} to analyze market data and generate signals.",
    )
    content = (
        "interface:\n"
        f"  display_name: \"{_yaml_escape(str(trader['name']))}\"\n"
        f"  short_description: \"{_yaml_escape(short_desc)}\"\n"
        f"  default_prompt: \"{_yaml_escape(str(default_prompt))}\"\n"
    )
    path.write_text(content, encoding="utf-8")


def _write_identity(path: Path, trader: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "trader_id": trader["trader_id"],
        "name": trader["name"],
        "style": trader["style"],
        "program_entry": trader["program_entry"],
        "trader_skill_name": trader["trader_skill_name"],
    }
    content = "# Trader Identity\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n"
    path.write_text(content, encoding="utf-8")


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create trader skills from shuaishuai roster JSON")
    parser.add_argument("roster_json", help="Path to roster JSON file")
    parser.add_argument("--project-root", default=".", help="Project root for relative trader_skill_path")
    args = parser.parse_args()

    roster_path = Path(args.roster_json)
    project_root = Path(args.project_root).resolve()
    roster = json.loads(roster_path.read_text(encoding="utf-8-sig"))

    created = scaffold_trader_skills(roster, project_root)
    print(f"total_created={len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
