# Workflow

The primary input is one project PDF plus one stable server-side template ID
selected by the operator. The primary output is exactly one traceable draft
XLSX based on that template, never a redesigned project or a model-selected
document set.

Required phases:

1. Resolve the selected template ID to one registered contract. Record its ID,
   status, version, and SHA-256. The model cannot change this selection.
2. Validate that the run contains exactly one uploaded PDF. Inventory and index
   it by content and SHA-256.
3. Inspect every registered writable target and extract all supported values,
   not just the object card or first matching cell. Reuse the same PDF fact for
   every registered target whose meaning actually matches. The current PDF is
   the only fact source. Organization details are
   eligible when their role and legal entity are explicit; no organization,
   customer or signatory profile is loaded or required.
4. Store claims before deciding. Preserve every side of a conflict and its page
   locator. Do not settle conflicting organization identities by majority vote
   or copy a designer into a contractor field. Actual execution fields require
   actual execution evidence, not project intent or a design signature.
5. For an AOSR contract, extract its work items and determine change state as
   `YES`, `NO`, or `UNKNOWN`. For other contracts, apply only their approved
   family rules.
6. Build one logical workbook plan for the selected template: the immutable
   contract plus the validated assignment set and PDF evidence pointers. The
   legacy `ProjectState.document_plans` collection stays empty. Do not add
   another plan because the PDF contains another document family.
7. Generate one draft XLSX through the registered contract. Safe formatting
   normalization must preserve meaning and digits. Where a target explicitly
   sets `allow_project_basis`, a documented project quantity, material, name or
   type may be written with `value_basis="project"` and a visible «по проекту»
   marker. This is not actual-execution evidence. Keep other unresolved targets
   blank and visibly filled; unknown mappings remain closed. A declared
   `allows_mapping_review` descriptive target may retain certain PDF text with
   a plausible match and orange `mapping_review_reason`, not an invented or
   conflicting fact. Prefer compact `material_rows` for supported tables.
8. Return one grouped `NEEDS_INPUT` batch for all known critical blockers and
   project-basis values awaiting execution confirmation. Distinguish omitted
   (`not_returned`), rejected, and explicitly missing PDF evidence instead of
   labeling every blank as absent from the document. The marked draft remains
   available for specialist review.
9. In the current MVP, stop the automatic selected-template run after returning
   the one marked draft; follow-up answers and revision are not accepted.
10. Run deterministic validation and send the draft plus unresolved register to
    the specialist. Rendering and independent model review are mandatory before
    a future final-release workflow, but they are not represented as approval in
    the current discovery-only MVP.

For an approved AOSR contract, the selected sheets define individual acts. The
starting number belongs to the first selected act even if its original worksheet
name is `АОСР-3`; subsequent selected acts receive consecutive numbers. This
numbering rule does not apply automatically to non-AOSR workbooks.

An operational retry is limited to failed analysis and, for selected-template,
failed generation. Keep the template ID and both pinned template/contract hashes
immutable and create the workbook again from the clean registered source. The
current selected-template MVP rejects revisions. Selecting another template
always creates a separate run.

Policy or contract changes apply to new runs. Do not automatically rewrite a
saved run, replace its pinned contract, or relabel its historical evidence.

Legacy project1 composition may still be tested, but selected-template v2 runs
its three approved workbook families separately. Project2 remains a
regression/discovery corpus and never supplies facts for a selected-template run.
