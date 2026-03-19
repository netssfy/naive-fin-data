#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


def _validate_entry(entry: dict) -> list[str]:
    errors: list[str] = []
    required = [
        "trader_id",
        "name",
        "style",
        "program_entry",
        "trader_skill_name",
        "trader_skill_path",
        "trader_default_prompt",
        "similarity",
    ]
    for key in required:
        if key not in entry:
            errors.append(f"missing trader field: {key}")

    program_entry = entry.get("program_entry", "")
    if isinstance(program_entry, str) and ":" not in program_entry:
        errors.append(f"invalid program_entry for {entry.get('trader_id', 'unknown')}")

    skill_name = entry.get("trader_skill_name", "")
    if isinstance(skill_name, str) and not _SKILL_NAME_PATTERN.match(skill_name):
        errors.append(f"invalid trader_skill_name for {entry.get('trader_id', 'unknown')}")

    skill_path = entry.get("trader_skill_path", "")
    if isinstance(skill_path, str) and not skill_path.endswith("/SKILL.md"):
        errors.append(f"invalid trader_skill_path for {entry.get('trader_id', 'unknown')}")

    default_prompt = entry.get("trader_default_prompt", "")
    if isinstance(default_prompt, str) and not default_prompt.strip():
        errors.append(f"empty trader_default_prompt for {entry.get('trader_id', 'unknown')}")

    similarity = entry.get("similarity", {})
    if not isinstance(similarity, dict):
        errors.append(f"similarity must be object for {entry.get('trader_id', 'unknown')}")
    else:
        for other_id, value in similarity.items():
            if not isinstance(value, (int, float)):
                errors.append(f"similarity[{other_id}] must be number for {entry.get('trader_id', 'unknown')}")
            elif value < 0 or value > 0.5:
                errors.append(
                    f"similarity[{other_id}]={value} exceeds allowed range [0, 0.5] for {entry.get('trader_id', 'unknown')}"
                )

    return errors


def validate_roster(payload: dict, expected_count: int | None) -> list[str]:
    errors: list[str] = []
    for key in ("status", "season_id", "market", "generated_at", "errors", "traders"):
        if key not in payload:
            errors.append(f"missing top-level field: {key}")

    traders = payload.get("traders", [])
    if not isinstance(traders, list):
        errors.append("traders must be an array")
        return errors

    if payload.get("status") == "ok" and expected_count is not None and len(traders) != expected_count:
        errors.append(f"traders count mismatch: expected {expected_count}, got {len(traders)}")

    for entry in traders:
        if not isinstance(entry, dict):
            errors.append("each trader must be an object")
            continue
        errors.extend(_validate_entry(entry))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate shuaishuai roster JSON")
    parser.add_argument("json_file", help="Path to roster json")
    parser.add_argument("--expected-count", type=int, default=None)
    args = parser.parse_args()

    path = Path(args.json_file)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    errors = validate_roster(payload, args.expected_count)
    if errors:
        print("INVALID")
        for err in errors:
            print(f"- {err}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
