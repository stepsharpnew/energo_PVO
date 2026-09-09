# Corrections and controlled learning

Record a specialist correction with artifact, location, current value, expected value, reason, and scope. Default scope is `project`.

Classify it as project data, extraction defect, general rule, Rosseti-specific rule, branch-specific rule, template defect, or object exception. The legacy controlled-revision route may preserve corrections in ProjectState and generate an immutable revision. The current selected-template MVP does not accept follow-up answers or revisions: record the issue and let the specialist edit the downloaded draft outside the automatic run.

Under the user-approved PDF-only policy, a specialist's proposed value is not
new PDF evidence. An extraction correction must point to the current uploaded
PDF, and a new selected-template run must not import legacy answers, profiles
or completed-workbook values. Approval of a structural rule or template does
not authorize reusing another project's facts.

For `customer` or `global`, create a knowledge proposal in `PROPOSED`. Do not edit approved references automatically. A specialist must approve the proposal, and all regression scenarios must pass before the knowledge version changes to `APPROVED`.

Fine-tuning is outside the MVP. Accumulate a stable, verified correction corpus first.
