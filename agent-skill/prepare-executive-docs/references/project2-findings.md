# Project2 corpus findings

Status: confirmed structural audit dated 2026-07-22. This file records observations, not automatically approved production rules.

## Corpus role

`project2/` contains 16 completed Excel workbooks, not the primary project/TU/scheme/passport input package expected by the MVP. It is a regression and discovery corpus. Do not expose its completed values to a blind generation call and do not use it as a source of facts for another object.

| Family | Books | Current MVP |
|---|---:|---|
| KL | 2 | Yes, for regression and rule discovery |
| GNB | 10 | No |
| EMR | 1 | No |
| OJR | 1 | No |
| AVK | 1 | No |
| BRTP | 1 | No |

The audit found 279 sheets, including 64 sheets whose names begin with `АОСР`. The exact machine-readable inventory, hashes, formulas, external links, print settings, and object-card comparison are in `data/runs/_project2_analysis/audit/project-corpus-audit.json`.

## Confirmed KL observations

- `9. АОСР КЛ-1.xlsx` and `9. АОСР КЛ-2.xlsx` have the same SAP/object/project code but different installation/route values. Treat them as two segments of one larger object until a specialist says otherwise.
- Each KL workbook contains 10 AOSR tabs. Both contain `АОСР-2` plus `АОСР-2 (2)` and `АОСР-4` plus `АОСР-4 (2)`. The repeated labels contain different work descriptions. Therefore the sheet label is not a stable semantic work type, and a work instance needs its own ID.
- Each KL workbook numbers its acts from 1 through 10 with suffix `/КЛ`. Across the shared project code this produces duplicate act identities. This conflicts with the current MVP rule of one sequence per project. Keep the current rule until the specialist explicitly defines whether numbering is per project, route, installation, or workbook.
- In `9. АОСР КЛ-2.xlsx`, sheet `АОСР-3`, the work description references the installation from `9. АОСР КЛ-1.xlsx`. Treat this as a possible cross-segment copy error and request confirmation; never learn it as a mapping rule.
- The two KL books contain technical defects and external links. A defect in a filled example is excluded from expected output.

## Broader product observations

- Ten separate GNB books and many repeated BRTP tabs show that one document family can require multiple independent instances. Future contracts need `work_type` plus `instance_index`/segment identity rather than a unique hard-coded sheet name.
- All 16 books retain at least one OOXML external-link part. Many links connect books in the completed package. The MVP may inspect these as historical dependencies, but generated final books must be self-contained and contain no external links.
- Organization, customer, and signatory values in these workbooks are not approved profiles. They require explicit specialist confirmation and validity dates before production use.
- Several object-card fields differ across the corpus because it includes disciplines/segments and possibly separate subprojects. Do not merge them by folder membership alone.

## Required regression checks

1. Classify all 16 files by content and preserve SHA-256 without modifying them.
2. Detect the two KL segment books as related by project identity but distinct by installation.
3. Extract ten separate work instances from each KL book without combining repeated base labels.
4. Flag duplicate cross-book act numbers under the current project-wide numbering rule.
5. Flag the foreign-route text in KL-2/`АОСР-3`.
6. Report formula errors and external links without reproducing them.
7. Keep GNB, EMR, OJR, AVK, and BRTP out of generation until their contracts and rules are approved.

## Unresolved specialist decision

Define the scope of AOSR numbering for a multi-route object: one sequence for the complete project, a separate sequence per route/installation, or another documented convention. Until confirmed, a new similar input must enter `NEEDS_INPUT` before numbering.
