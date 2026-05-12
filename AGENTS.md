# Agent Instructions

This repo is a personal/local assistant system. Treat local credentials, indexed data, and logs as sensitive. Do not expose the bot publicly or broaden access controls without an explicit security review.

## Orientation

- Main user-facing docs are in `README.md`.
- Claude-specific project notes are in `CLAUDE.md`; keep this file aligned with those notes when changing agent behavior.
- Runtime configuration lives in `src/config.py` and `.env.example`.
- The Slack bot supports `intent`, `agent`, and `multi_agent` modes. `multi_agent` routes through specialist agents in `src/bot/agents/`.
- Calendar "next/upcoming" behavior is current-time-aware through `USER_TIMEZONE`; preserve that invariant when changing calendar tools or prompts.

## Development

- Use `rg` for repo search.
- Prefer narrow, behavior-focused changes over broad refactors.
- Confirmable write actions live under `src/bot/actions/` and should be routed through the pending-action confirmation flow.
- Do not bypass Slack confirmation for writes such as email drafts/sends, calendar events, GitHub issues, Todoist changes, Notion writes, or Zotero additions.
- Run focused tests for touched areas, and run full `pytest` when changing shared bot, agent, tool, or integration code.

## Common Commands

```bash
pytest
pytest tests/test_executor.py
ruff check src tests
python scripts/run_bot.py
```
