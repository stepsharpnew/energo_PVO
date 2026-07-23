# Executive documentation agent

Use `agent-skill/prepare-executive-docs/SKILL.md` for every task that analyzes, creates, checks, or revises Russian executive documentation.

Treat `agent-skill/prepare-executive-docs/references/` as the project memory bank. Load it through `references/index.yaml`, and record newly confirmed corpus findings there instead of expanding the root instructions.

Preserve `project1/`, `project2/`, and `template/` as immutable source material. Write generated artifacts only under `data/runs/`, `templates/approved/`, or explicit test temporary directories.

`project1/` is the approved semantic blind-test example subject to its recorded technical exclusions. `project2/` is a regression and discovery corpus, not an automatically approved golden set or a source of organization/customer profiles. Treat discrepancies found in either completed example as findings to review, not rules to copy.

Use cleaned candidates from `templates/approved/`, but do not mark a template, customer profile, signatory profile, or new cross-project rule as approved without explicit specialist confirmation. A technically clean template may remain `READY_FOR_VISUAL_APPROVAL`.

Run `uv run pytest` after changing the application, document tools, template contracts, or skill. Validate the skill with the bundled `quick_validate.py` before release.

Never silently invent dates, measurements, act numbers, certificate/passport details, signatories, or evidence. Missing or conflicting critical facts must produce `NEEDS_INPUT`.
