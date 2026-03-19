---
name: shuaishuai
description: Orchestrate trader season bootstrap in an agent-native world run by coding agents (Codex, Claude Code). Use when creating or refreshing trader participants, generating style-diverse rosters, and scaffolding each trader as an executable skill under season and symbol constraints.
---

# Shuaishuai

## Goal
Create a machine-readable trader roster and create trader skill folders from that roster.

## Required Workflow
1. Read input payload and extract `season`, `desired_count`, and constraints.
2. Read `references/roster_schema.md` and `references/trader_skill_blueprint.md`.
3. Design traders with clearly different styles; enforce max pairwise similarity `0.5`.
4. Produce strict roster JSON.
5. Create trader skill folders using `scripts/create_trader_skills.py`.
6. Return final JSON only.

## Roster Output Requirements
For each trader, output:
- `trader_id`
- `name`
- `style`
- `program_entry`
- `trader_skill_name`
- `trader_skill_path`
- `trader_default_prompt`
- `similarity` map keyed by other `trader_id`

## Skill-Creator Capability (Mandatory)
After roster generation, materialize trader skills under:
- `src/trader_incubator/skills/traders/<trader_id>/`

At minimum create for each trader:
- `SKILL.md`
- `agents/openai.yaml`
- `references/identity.md`

Use `scripts/create_trader_skills.py` for deterministic scaffolding, then allow coding agents to iterate trader skills later.

## Output Rules
- Return exactly one JSON object matching `references/roster_schema.md`.
- Return JSON only (no prose, no markdown fence).
- Keep all identifiers filesystem-safe (`[a-z0-9-]`).
- Keep `program_entry` in `module.path:ClassName` format.

## Failure Handling
If required input fields are missing, return:
- `status: "error"`
- concrete error strings in `errors`
- empty `traders` array

## Resource Usage
- Use `scripts/validate_roster_json.py` to validate roster JSON.
- Use `scripts/create_trader_skills.py` to scaffold trader skills.
- Use `references/style_axes.md` to avoid style overlap.
