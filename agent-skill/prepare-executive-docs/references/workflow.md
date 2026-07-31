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
3. Extract the object card and only the semantic fields required by the selected
   contract.
4. Store claims before deciding. Preserve every side of a conflict and its page
   locator.
5. For an AOSR contract, extract its work items and determine change state as
   `YES`, `NO`, or `UNKNOWN`. For other contracts, apply only their approved
   family rules.
6. Build one logical workbook plan for the selected template: the immutable
   contract plus the validated assignment set and PDF evidence pointers. The
   legacy `ProjectState.document_plans` collection stays empty. Do not add
   another plan because the PDF contains another document family.
7. Generate one draft XLSX through the registered contract. Write admissible
   values; keep unresolved semantic targets blank and visibly filled.
8. Return one grouped `NEEDS_INPUT` batch for all known critical blockers. The
   marked draft remains available for specialist review.
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

Legacy project1 composition may still be tested, but selected-template v2 runs
its three approved workbook families separately. Project2 remains a
regression/discovery corpus and never supplies facts for a selected-template run.
