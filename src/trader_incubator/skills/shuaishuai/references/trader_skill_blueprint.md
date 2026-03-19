# Trader Skill Blueprint

Create one skill per trader under `src/trader_incubator/skills/traders/<trader_id>/`.

## Required Files
- `SKILL.md`
- `agents/openai.yaml`
- `references/identity.md`

## SKILL.md Frontmatter
- `name`: use `trader-<trader_id>`
- `description`: explain this trader's style and when to invoke the skill

## SKILL.md Body
Include:
1. Trader identity (`trader_id`, `name`, `style`)
2. Program contract (`program_entry`)
3. Trading-time rule: do not change strategy during market hours
4. Non-trading-time duties: review, research, refine

## openai.yaml
Set:
- `interface.display_name`
- `interface.short_description`
- `interface.default_prompt`

## identity.md
Record the same trader metadata in machine-readable JSON and a short text summary.
