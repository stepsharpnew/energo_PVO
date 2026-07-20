# Executive documentation agent

Use `agent-skill/prepare-executive-docs/SKILL.md` for every task that analyzes, creates, checks, or revises Russian executive documentation.

Preserve `project1/` and `template/` as immutable source material. Write generated artifacts only under `data/runs/`, `templates/approved/`, or explicit test temporary directories.

Run `uv run pytest` after changing the application, document tools, template contracts, or skill. Validate the skill with the bundled `quick_validate.py` before release.

Never silently invent dates, measurements, act numbers, certificate/passport details, signatories, or evidence. Missing or conflicting critical facts must produce `NEEDS_INPUT`.

