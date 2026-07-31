# Validation rules

All errors block finalization.

Run-contract checks: exactly one immutable selected template ID, exactly one
uploaded PDF, exactly one logical workbook plan, and exactly one generated
XLSX. In selected-template v2 that plan is the pinned contract plus validated
assignments and PDF evidence pointers, not a legacy
`ProjectState.document_plans` item. The plan template ID, source SHA-256, output
filename, and template version must match the registered contract. A
model-selected or substituted template is an error.

Input checks: the uploaded source is a valid, readable, unencrypted PDF and is
the only project evidence for selected-template v2. Uploaded XLSX files,
completed workbooks, and anything under `ETALON/` are invalid project evidence.

Technical workbook checks: valid OOXML ZIP, unchanged worksheet order and names,
no new external links, no forbidden formula errors, no structural changes
outside the contract, contract-correct sheet visibility, no stale project
tokens, and successful open without repair.

Unresolved-field checks:

- every missing, conflicting, ambiguous, rejected, or unapproved-rule field
  remains blank;
- every unresolved contract target has exactly the registered visible fill;
- a resolved target does not retain the unresolved fill after regeneration;
- style changes are limited to the fill component of declared unresolved
  targets; number format, font, border, alignment, protection, merged ranges,
  formulas, row/column dimensions, and print settings remain unchanged unless
  the contract explicitly allows them;
- every unresolved field is present in the unresolved field register with a
  reason and blocking status;
- any unresolved critical field produces `NEEDS_INPUT` and blocks final release.

Contract-specific semantic checks apply only to the selected document kind. For
approved AOSR contracts they include: one work per act; every planned work
covered once; consecutive numbering; actual dates with evidence and valid order;
actual quantities not masquerading as project values; approved schemes for
changes; known change state; acceptable material documents; approved
branch/profile; consistent object and organization identifiers; and no rejected
or conflicting critical claims.

Cross-run checks: when separate selected-template runs share a project identity,
detect incompatible object-card values, duplicate AOSR numbers where applicable,
route/installation text copied from another segment, and repeated work instances
that the selected contract cannot represent. Never solve a conflict by emitting
a second workbook in the same run.

Visual checks: render only contract-declared review sheets and print areas using
the contract's page size, orientation, and expected page-count bounds. Check for
clipped text, unexpected blank pages, broken fonts, unintended visible utility
sheets, unrelated content, and a visible but non-destructive unresolved-field
fill.

Template-status checks: `DISCOVERY_REVIEW_REQUIRED` means the whitelist itself
still awaits specialist review, while `READY_FOR_VISUAL_APPROVAL` remains a
candidate state. Technical cleanliness, ETALON parity, or a successful draft
does not promote either state. The current selected-template MVP exposes no
approval transition; a future release requires an explicit specialist approval
record.

The current ETALON comparison runs after candidate generation, during template
registration, and outside the evidence context. It records structural
differences and technical defects; it does not yet perform blind PDF-to-draft
semantic parity. Do not convert any ETALON difference into an exception or
claim.

Independent model review receives the selected public template identity, final
claims, the single workbook plan, unresolved field register, deterministic
findings, PDF source pointers for critical fields, and rendered previews in a
fresh context. It does not receive ETALON, prior private reasoning, or authority
to override deterministic errors.
