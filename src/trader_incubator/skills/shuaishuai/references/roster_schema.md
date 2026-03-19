# Roster Schema

Use this schema for `shuaishuai` output.

```json
{
  "status": "ok",
  "season_id": "string",
  "market": "A_SHARE|HK|US",
  "generated_at": "ISO-8601 datetime",
  "errors": [],
  "traders": [
    {
      "trader_id": "alpha-trend",
      "name": "Alpha Trend",
      "style": "trend-following",
      "program_entry": "trader_programs.alpha_trend:TraderProgram",
      "trader_skill_name": "trader-alpha-trend",
      "trader_skill_path": "src/trader_incubator/skills/traders/alpha-trend/SKILL.md",
      "trader_default_prompt": "Use $trader-alpha-trend to update the strategy code for season S1.",
      "similarity": {
        "beta-value": 0.34,
        "gamma-macro": 0.41
      }
    }
  ]
}
```

## Constraints
- `status` must be `ok` or `error`.
- `traders` length must equal requested `desired_count` when `status=ok`.
- `similarity` values must be numbers in `[0, 0.5]`.
- For every pair of traders, similarity must be `<= 0.5`.
- `program_entry` must include one `:` separator.
- `trader_skill_name` must be lowercase letters, digits, and hyphens.
- `trader_skill_path` must end with `/SKILL.md`.

## Error Output

```json
{
  "status": "error",
  "season_id": "string-or-empty",
  "market": "A_SHARE|HK|US|unknown",
  "generated_at": "ISO-8601 datetime",
  "errors": ["missing season.market"],
  "traders": []
}
```
