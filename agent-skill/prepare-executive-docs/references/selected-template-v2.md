# Selected-template v2

Status: confirmed product-flow rule. This topic controls the primary interactive
workflow. It does not approve any workbook candidate, customer profile, signatory
profile, or document-family semantic rule.

## Run contract

1. Before analysis, the operator selects exactly one registered workbook
   template by its stable public template ID.
2. The operator uploads exactly one project PDF. The selected workbook is a
   server-side resource and is never uploaded with the project.
3. The selected template ID is immutable for the run and all of its revisions.
   Choosing another template starts another run.
4. The model extracts and reconciles claims from the uploaded PDF. It never
   selects, substitutes, or infers the workbook template, output filename, or
   workbook structure. The registered contract supplies the complete writable
   target whitelist; the model may assign values only to those declared targets
   and cannot create or change the mapping.
5. A restricted generator applies admissible claims through the selected
   template contract and creates exactly one draft XLSX.
6. A `NEEDS_INPUT` result still produces that one draft when the registered
   contract is sufficient to generate safely. It must not create additional
   workbooks to cover other document families discovered in the PDF.

## Missing and unreliable values

- Write a value only when it is observed in the uploaded PDF, derived by an
  approved rule with a rule ID, or confirmed by a named specialist.
- A missing, conflicting, ambiguous, rejected, or otherwise unreliable value
  stays blank in its semantic cell.
- Apply the contract-defined visible fill to every unresolved writable target.
  Do not replace a missing fact with `НЕ ПОДТВЕРЖДЕНО`, a guessed value, a value
  copied from another workbook, or an empty-looking formula.
- The fill is a review marker, not evidence. Record the field key, target, reason,
  and source gap in the report and return `NEEDS_INPUT` for critical fields.
- If a controlled regeneration workflow is added, it must start from the clean
  registered workbook, reapply admissible facts, and remove the fill only from
  fields that have become resolved. The current MVP does not accept follow-up
  answers after `NEEDS_INPUT`.

## Template status

- `DISCOVERY_REVIEW_REQUIRED` means the writable-cell whitelist and manual-field
  classification were conservatively discovered from the unfilled source and
  still require specialist review.
- `READY_FOR_VISUAL_APPROVAL` means a candidate has passed the recorded
  technical preparation needed for specialist inspection. It is still not an
  approved production template.
- A candidate may be shown with its status and may only produce a visibly marked
  review draft under an explicitly registered candidate contract. It cannot
  reach final approval.
- Only explicit specialist confirmation may change a template to `APPROVED`.
  Technical cleanliness, an ETALON counterpart, or a successful regression run
  does not grant approval.
- Final release additionally requires an approved contract, no unresolved
  critical fields, and all deterministic and independent checks to pass.
- The current MVP has no selected-template approval or revision route. It
  therefore cannot promote even a technically successful selected-template run
  to final output.

Confirmed discovery snapshot, 2026-07-30:

- all five registered candidates have `candidate_external_links: 0` and
  `package_forbidden_token_count: 0`; external-link cache parts, unreferenced
  shared strings, custom XML, and prior document-author metadata are removed
  during deterministic registration;
- `ojr` and `protocols` pass the current deterministic workbook checks but
  remain `DISCOVERY_REVIEW_REQUIRED`;
- `emr` remains blocked by 20 raw/formula `#REF!` findings;
- `avk` remains blocked by two formulas that still refer to other workbooks;
- `aosr_vl` remains blocked by six raw/formula `#REF!` findings and one formula
  that still refers to another workbook.

Additional visual regression finding, 2026-08-01:

- the `ojr` candidate has no formula-error token, but valid direct-reference
  formulas render false zero values while their unresolved source cells are
  blank. LibreOffice and artifact-tool both confirmed `№ 0` from
  `Обложка!F23` / `Титульный лист!Q4` referencing blank
  `Данные объект!B2`; LibreOffice also confirmed zero dates in
  `Раздел1!D5:E7` referencing blank `Данные объект!B7:B8`;
- treat this as a visual and semantic release blocker until the candidate uses
  blank-preserving formulas and its contract/version/hashes are regenerated.
  A formula-error scan alone cannot detect this class of defect.

Confirmed `aosr_vl` remediation snapshot, 2026-08-05:

- the old candidate exposed 126 targets but only two model-writable fields;
  66 cleared cells belonged to the visible organization lookup sheet rather
  than the project-facing fill contract, while hard-coded numeric quantities
  on the AOSR sheets were not discovered at all;
- `2026-08-05-discovery-3` separates cleanup-only cells from 65 true targets,
  exposes 28 explicitly described and semantically identified PDF-backed
  fields, and retains 37 profile/date/signatory fields for manual confirmation;
- the rebuilt candidate has zero formula-error tokens, zero raw `#REF!`, zero
  external formula references, and zero unguarded direct/concatenation formulas.
  Its 304 formula differences against the dirty ETALON are reviewed remediation
  changes, not values learned from ETALON;
- a paid quality regression against a synthetic, non-sensitive PDF filled all
  28 model-writable fields, kept all 37 server-controlled fields unresolved,
  and produced zero technical validation errors. This is regression evidence,
  not specialist approval of the template.

These counts are reproducible corpus observations, not approval decisions or
new semantic rules.

The current discovery contracts record coordinates, labels, value kinds,
required flags, and manual-confirmation reasons. They do not yet provide the
stable semantic target IDs, repeat-range rules, or declared render/visibility
expectations required by `semantic-fields.md` for an approved production
contract. This limitation is acceptable only while status remains
`DISCOVERY_REVIEW_REQUIRED`.

## ETALON boundary

`ETALON/` is a regression-only corpus paired with its recorded project PDF. Its
workbooks are never project inputs, claim evidence, profile sources, template
approval evidence, or model context. Current tooling compares a cleaned
candidate with its ETALON counterpart during registration and records technical
findings. It does not yet execute a blind PDF-to-draft semantic parity run.
Future post-generation comparison may report discrepancies, formula errors,
external links, visibility differences, and stale values as findings, but must
never learn an apparent ETALON defect as a mapping or exception.

## Legacy corpora

The approved project1 semantic blind-test rules and the project2
regression/discovery rules remain valid in their recorded scopes. If a legacy
project contains several workbook families, exercise selected-template v2 as
separate runs—one selected template and one output workbook per run.
