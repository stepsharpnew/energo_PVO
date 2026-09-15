# Selected-template v2

Status: confirmed product-flow rule. This topic controls the primary interactive
workflow. The PDF-only fact-source policy was approved on 2026-09-07; the
higher-coverage, visibly project-based draft policy was approved on 2026-09-08.
Neither policy approves a workbook candidate or treats a draft as execution
evidence. Factual profiles remain retired.

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
   and cannot create or change the mapping. Inspect all these targets, not only
   the first matches. The same evidenced fact may populate several targets when
   their registered meanings match; reuse its source pointer rather than
   inventing another fact or copying into a merely similar field.
5. A restricted generator applies admissible claims through the selected
   template contract and creates exactly one draft XLSX.
6. A `NEEDS_INPUT` result still produces that one draft when the registered
   contract is sufficient to generate safely. It must not create additional
   workbooks to cover other document families discovered in the PDF.

## Missing and unreliable values

- Write a value only when it is supported by the current uploaded PDF. Safe
  formatting normalization may remove differences in whitespace, quotation or
  separator formatting and recognized equivalent abbreviations without
  changing meaning or digits. It must not repair a guessed digit, complete an
  identifier, merge different entities, or turn a partial quote into an
  unsupported value. A human answer, profile, ETALON value or another project is
  not a fill source.
- Extract organization names, addresses and legal details when the PDF
  explicitly establishes their matching role and legal entity. Do not require
  an approved organization/customer/signatory profile. Preserve conflicts
  rather than choosing the most frequent organization name.
- Actual dates, quantities, measurements, material documents and signatory
  authority require explicit evidence of actual execution and the matching
  work/role. Design quantities, project-development signatures, issue dates and
  planned schedules do not establish execution facts.
- A project quantity, material, name or type may nevertheless prefill a draft
  target with explicit `allow_project_basis: true`. Set
  `value_basis="project"`, retain its PDF evidence, and visibly distinguish it
  as «по проекту». Do not label it verified execution or clear `NEEDS_INPUT`.
  Without that target permission, leave a design-only value blank. Actual
  dates, act numbers, passports/certificates, signatory authority and measured
  results never gain this permission merely because a related design fact is
  available.
- A missing, conflicting, ambiguous, rejected, or otherwise unreliable value
  stays blank in its semantic cell. The user-approved descriptive mapping
  extension below is about target wording, not uncertainty in the source fact.
- Apply the contract-defined visible fill to every unresolved writable target.
  Do not replace a missing fact with `НЕ ПОДТВЕРЖДЕНО`, a guessed value, a value
  copied from another workbook, or an empty-looking formula.
- The fill is a review marker, not evidence. Record the field key, target, reason,
  and source gap in the report and return `NEEDS_INPUT` for critical fields.
  Distinguish `not_returned` (the model omitted the target), `rejected` (a
  proposed value failed checks), and `missing_from_pdf` (explicitly reported
  absence of source evidence). Omission and rejection must not masquerade as
  proof of absence. Preserve available evidence and the specific rejection.
  Filled project-basis values remain a separate review group, not empty cells.
- If a controlled regeneration workflow is added, it must start from the clean
  registered workbook, reapply admissible facts, and remove the fill only from
  fields that have become resolved. The current MVP does not accept follow-up
  answers after `NEEDS_INPUT`.
- New policy and contract versions do not automatically rewrite saved runs or
  replace their pinned contracts. Preserve historical output and evidence.

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

## Coverage-first draft policy, 2026-09-14

Increase the number of useful values extracted from the current PDF. Inspect
title/requisites, explanatory notes, work statements and every relevant material
specification; missing actual dates or certificates do not prevent filling the
other fields. Do not optimize the count by duplicating items or mixing work
segments. PDF-supported coverage and raw filled-cell count are different metrics.

- For `allows_mapping_review=true` descriptive targets, exact caption wording
  is not required. A plausible target match for certain source text may be
  written with a concise Russian `mapping_review_reason`. Orange means
  «проверить привязку», not verified. Keep `value_basis` document/project, source
  page, quote and `NEEDS_INPUT`. All source-text and digit checks still apply.
- This permission never applies to organization/representative roles, legal
  identifiers, actual dates, quantities, measured results, act/passport/certificate
  numbers or authority. A conflict in the PDF, even for a descriptive field,
  stays unresolved. An organization role may follow its entity in the same PDF
  block; label order alone is not grounds to discard documentary evidence.
- When `material_tables` is offered, prefer one compact `material_rows` record
  per PDF position. Include its table ID, name, optional type and quantity with
  source unit, file ID, original physical page, full row quote and value basis.
  The server splits values into registered columns. Do not duplicate these
  records in assignments. Missing quality documents must not suppress a
  permitted project material name/quantity. Report table overflow, never
  overwrite occupied rows or combine different source positions.
- On visual packets use the visible `Original PDF page: N` label as `page:N`.
  A shortened packet's ordinal is not an original physical page locator.
- Use independent PDFs, including the operator-provided `example2/`, for
  offline coverage regression. Completed XLSX files are comparison only;
  neither they nor corpus findings may enter a filling request.

## User-approved PDF-only policy, 2026-09-07

The user explicitly approved abandoning organization/customer/signatory
profiles entirely: only facts found in the current uploaded document may be
filled. This is the approved product source policy, replacing the audit's
earlier unapproved proposal and all previous profile prerequisites. It is not
approval of the candidate templates or a license to invent missing data.

- Do not load profile files or create profile-derived claims, and do not ask
  for profile approval. Processing modes economy/balanced/quality remain budget
  settings and are unrelated to this retirement.
- Organization, address and legal-detail fields become eligible for extraction
  from the PDF when the contract meaning, organization role and legal entity
  are unambiguous. A present-but-blocked field must not be reported as absent.
- A customer branch is usable only when explicitly identified in that role by
  the current PDF. Conflicting designer identities remain unresolved: do not
  pick the more frequent name or combine different legal entities' details.
- A person named as a developer, design approver or director does not thereby
  acquire authority to sign AOSR. Actual-work dates, quantities, measurements,
  material documents and execution signatories require their own explicit
  documentary evidence in the PDF. The 2026-09-08 draft extension permits only
  explicitly allowed project-basis prefills, never their promotion to actuals.
- Preserve page-based evidence and distinguish missing, conflicting, ambiguous
  and rejected values. Leave unresolved targets visibly blank and return
  `NEEDS_INPUT`; the marked file remains a specialist-review draft.
- ETALON, another project's documents, saved profiles and typed follow-up
  answers cannot supply model-filled facts. Corpus comparison remains a
  separate post-generation check.

## ETALON boundary

The completed workbooks in `ETALON/` are a regression-only corpus paired with
their recorded project PDF. As explicitly requested by the operator, that PDF
may itself be uploaded as the one project source. The workbooks are never
project inputs, claim evidence, profile sources, template
approval evidence, or model context. Current tooling compares a cleaned
candidate with its ETALON counterpart during registration and records technical
findings. It does not yet execute a blind PDF-to-draft semantic parity run.
Future post-generation comparison may report discrepancies, formula errors,
external links, visibility differences, and stale values as findings, but must
never learn an apparent ETALON defect as a mapping or exception.

## Offline corpus findings

Corpus-specific observations are routed separately through
`selected_template_findings` and `project2_findings` in `references/index.yaml`.
Never load those topics into a paid analysis or document-filling model context,
even when the uploaded PDF belongs to the recorded corpus. The model must
rediscover facts from that run's actual PDF rather than from historical notes.

## Legacy corpora

The approved project1 semantic blind-test rules and the project2
regression/discovery rules remain valid in their recorded scopes. If a legacy
project contains several workbook families, exercise selected-template v2 as
separate runs—one selected template and one output workbook per run.
