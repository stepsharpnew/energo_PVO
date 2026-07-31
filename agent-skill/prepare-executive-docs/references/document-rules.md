# Document rules

## Selected-template v2

- The operator selects exactly one registered workbook template before analysis
  and uploads exactly one project PDF.
- One run creates exactly one draft XLSX from that server-side template. The
  model cannot select another template, create another workbook, invent an
  output name, or create or change the registered writable-target whitelist.
- The model may return an assignment only for a contract-declared target. Reject
  every arbitrary or unregistered sheet/cell coordinate.
- A value may be written only from an admissible claim. A missing, conflicting,
  ambiguous, or unreliable value stays blank and receives the
  contract-defined visible fill.
- A visible fill means `NEEDS_INPUT`; it is not a value, confirmation, or
  permission to release.
- Regeneration begins from the clean registered template, not from an earlier
  generated workbook.
- ETALON workbooks are regression-only. Never use their values, visibility,
  formulas, profiles, signatures, or apparent corrections as project evidence
  or model context.
- `DISCOVERY_REVIEW_REQUIRED` means the writable-cell whitelist still awaits
  specialist review. `READY_FOR_VISUAL_APPROVAL` is likewise a candidate state,
  not approval. Either candidate may produce only a visibly marked review draft
  under a registered candidate contract and cannot reach final release.
- Do not release a workbook whose contract is unapproved, whose critical fields
  remain unresolved, or whose structural diff exceeds its whitelist.
- Do not apply signature images, seals, or electronic signatures.

## Approved legacy AOSR scope

- The recorded production semantic scope remains AOSR KL-0.4 kV, KL-6 kV, and
  VRS. Other families need separately approved contracts and semantic rules.
- One work item produces one AOSR. Combining separate works is prohibited.
- Keep one consecutive AOSR number sequence for the project.
- Project data is the design baseline. If field work changed the design, attach
  the approved execution scheme and use supported actual values.
- In the legacy pilot, do not create or alter execution schemes, CAD drawings,
  surveys, protocols, AVK, GNB, overhead-line, substation, or EMR documents.
- Copy applicable schemes, passports, and certificates without modifying them.
- Materials used in an act must have a passport or certificate identifier.
  `б/н`, `б/д`, and blanks are blocking unless a later approved exception says
  otherwise.
- Select the customer branch from operator input. Customer and signatory values
  must come from an approved profile valid on the work dates.
- A repeated work or route segment produces another AOSR instance. A template
  tab number is not a semantic work identifier; determine the work from content
  and evidence.
- If a contract has only one instance of a required sheet type, do not combine
  repeated works and do not overwrite the first act. Block until an
  instance/clone rule is approved.

Project1 is a blind test. The user has approved the filled workbooks as the semantic golden set for expected document composition, field values, and sheet selection. Known isolated technical defects (`#REF!`, broken named ranges, external links, and template-contamination cells) are excluded from golden comparison and must not be reproduced. During a blind generation run, the filled workbooks remain hidden from the model and are used only for specialist comparison after generation.

Under selected-template v2, exercise each approved project1 workbook as a
separate run. Project1 approval does not approve the new candidates in
`NEW_TEMPLATES/`.

For recovery of a draft after a model or budget failure, the approved project1
document composition and work names may be reused only when the uploaded project
PDF has the exact recorded project1 SHA-256. This recovery must not copy dates,
quantities, signatories, profile values, passport/certificate details, or other
execution facts from the filled golden workbooks. Missing values stay
`NEEDS_INPUT` and must be visibly marked inside every generated XLSX.

Project2 is a regression/discovery corpus of completed documentation. It is not automatically golden. Use `project2-findings.md` for confirmed structural observations and unresolved branches. Do not inherit its numbering, cross-workbook links, profiles, or apparent copy errors.

`ETALON/` is a separate regression-only corpus paired with its project PDF. Its
name does not grant template approval or make completed values admissible
evidence. Record technical exclusions and specialist-confirmed semantic
expectations before using it for parity assertions.
