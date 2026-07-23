# Document rules

- Scope: AOSR KL-0.4 kV, KL-6 kV, and VRS only.
- One work item produces one AOSR. Combining separate works is prohibited.
- Keep one consecutive AOSR number sequence for the project.
- Project data is the baseline. If field work changed the design, attach the approved execution scheme and use supported actual values.
- Do not create or alter execution schemes, CAD drawings, surveys, protocols, AVK, GNB, overhead-line, substation, or EMR documents in this pilot.
- Do not apply signature images, seals, or electronic signatures.
- Copy applicable schemes, passports, and certificates without modifying them.
- Materials used in an act must have a passport or certificate identifier. `б/н`, `б/д`, and blanks are blocking unless a later approved exception says otherwise.
- Select the customer branch from the operator input. Customer and signatory values must come from an approved profile valid on the work dates.
- Do not release a workbook whose contract is unapproved or whose structural diff exceeds the whitelist.
- A repeated work or route segment produces another AOSR instance. A template tab number is not a semantic work identifier; determine the work from its content and evidence.
- If the contract has only one instance of a required sheet type, do not combine repeated works and do not overwrite the first act. Block until an instance/clone rule is approved.

Project1 is a blind test. The user has approved the filled workbooks as the semantic golden set for expected document composition, field values, and sheet selection. Known isolated technical defects (`#REF!`, broken named ranges, external links, and template-contamination cells) are excluded from golden comparison and must not be reproduced. During a blind generation run, the filled workbooks remain hidden from the model and are used only for specialist comparison after generation.

Project2 is a regression/discovery corpus of completed documentation. It is not automatically golden. Use `project2-findings.md` for confirmed structural observations and unresolved branches. Do not inherit its numbering, cross-workbook links, profiles, or apparent copy errors.
