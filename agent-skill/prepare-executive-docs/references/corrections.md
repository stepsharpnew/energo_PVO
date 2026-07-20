# Corrections and controlled learning

Record a specialist correction with artifact, location, current value, expected value, reason, and scope. Default scope is `project`.

Classify it as project data, extraction defect, general rule, Rosseti-specific rule, branch-specific rule, template defect, or object exception. Correct the current ProjectState and generate a new immutable revision.

For `customer` or `global`, create a knowledge proposal in `PROPOSED`. Do not edit approved references automatically. A specialist must approve the proposal, and all regression scenarios must pass before the knowledge version changes to `APPROVED`.

Fine-tuning is outside the MVP. Accumulate a stable, verified correction corpus first.
