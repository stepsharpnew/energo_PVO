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
completed workbooks, including those under `ETALON/`, are invalid project
evidence. The paired project PDF is allowed when explicitly uploaded by the operator.
Organization/customer/signatory profiles and human answers are not
selected-template fill evidence, regardless of approval flags. A profile's
absence or lack of approval is not itself a blocker: validate the PDF evidence
for the requested field instead.

Technical workbook checks: valid OOXML ZIP, unchanged worksheet order and names,
no new external links, no forbidden formula errors, no structural changes
outside the contract, contract-correct sheet visibility, no stale project
tokens, and successful open without repair.

Assignment checks:

- each value and its semantic role are supported by the uploaded PDF;
- formatting normalization preserves meaning and every digit; do not accept
  changed identifiers, a guessed missing digit, or an altered quantity;
- a `value_basis="project"` assignment requires explicit target
  `allow_project_basis: true`, matching design evidence, a visible «по проекту»
  marker, and continued `NEEDS_INPUT`; it is never verified execution;
- actual dates, act numbers, quality-document identifiers, execution signers
  and authority, and measured results still require their own actual evidence;
- reusing a fact in several registered cells is valid only when each target's
  meaning matches; unknown mappings and conflicting values remain closed;
- an `allows_mapping_review` descriptive field may retain exact PDF text with
  a plausible mapping and `mapping_review_reason`, visibly orange. This does
  not relax value/page proof or permit uncertain critical facts. The report
  must distinguish these filled candidates from blank unresolved cells;
- compact material rows expand only into current registered table slots before
  the same assignment checks. No raw material row may bypass validation or
  silently overwrite a cell. Preserve identity, unit, segment and shared quote.

Unresolved-field checks:

- every missing, conflicting, ambiguous, rejected, or unapproved-rule field
  remains blank except the explicitly allowed descriptive mapping candidate,
  whose source fact is certain and which is separately marked and reported;
- every unresolved contract target has exactly the registered visible fill;
- a resolved target does not retain the unresolved fill after regeneration;
- style changes are limited to the fill component of declared unresolved
  targets; number format, font, border, alignment, protection, merged ranges,
  formulas, row/column dimensions, and print settings remain unchanged unless
  the contract explicitly allows them;
- every unresolved field is present in the unresolved field register with a
  reason and blocking status;
- omitted model records are `not_returned`, failed proposed values are
  `rejected`, and explicitly reported absence is `missing_from_pdf`; retain
  specific reasons and available evidence instead of labeling every blank
  missing from the PDF;
- any unresolved critical field produces `NEEDS_INPUT` and blocks final release.

Project-basis draft checks: distinguish filled project-basis targets from blank
unresolved targets in workbook markers and reporting. Their presence continues
to block final release even when every writable cell has a value. Project
marking must not turn numeric values into text or overwrite formulas. Preserve
the source template structure and limit marker changes to the declared targets.

Contract-specific semantic checks apply only to the selected document kind. For
approved AOSR contracts they include: one work per act; every planned work
covered once; consecutive numbering; actual dates with evidence and valid order;
actual quantities not masquerading as project values; approved schemes for
changes; known change state; acceptable material documents; explicit matching
customer/contractor/designer roles and signatory authority in the PDF; consistent
object and organization identifiers; and no rejected or conflicting critical
claims. A designer or design signer must not be silently promoted to an
execution role, and facts belonging to conflicting legal entities must not be
combined into one organization block.

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
