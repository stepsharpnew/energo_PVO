# Selected-template corpus findings

Status: offline audit and regression memory only. This topic contains
project-specific values and historical candidate snapshots. Never load it into
paid analysis, extraction, reconciliation or document-filling model context.
It is not evidence for a run, including a run on the same corpus PDF: the model
must read the actual uploaded PDF. Load the active `selected_template_v2` topic
for current policy and workflow.

The historical outcomes below are preserved for regression review. References
to current versions/counts describe their dated snapshot, not today's contract.
The user-approved PDF-only policy of 2026-09-07 supersedes all profile-based
permissions mentioned in those snapshots; it does not approve templates.

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

Historical counts and field permissions in this snapshot predate the
2026-09-07 PDF-only policy and are not current extraction instructions.

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

Confirmed PDF/contract regression findings, 2026-09-07:

The snapshots below were captured before the later same-day PDF-only policy
change. Preserve their observed outcomes, but do not reuse their profile-based
field exclusions as active rules.

- the paired `I-354783.Бережной.5557.pdf` has 23 pages. Pages 1–2,
  13–15, and 17–22 have broken embedded-font text; pages 3–5 have no text
  layer; pages 6–11 expose only an electronic-signature overlay. Only pages
  12, 16, and 23 have usable body text. `pdftotext` also loses letters and
  digits, so switching text extractors does not solve this source defect;
- index v3 records text reliability separately from text length. All 20
  unreliable pages are mandatory visual inputs. Visual evidence is accepted
  only for a page recorded in the server's source-hash-pinned upload manifest;
- selected-template routing does not apply the legacy VL/AOSR exclusions to
  the operator's one PDF. Legacy routing remains unchanged;
- nearby-caption discovery incorrectly classified object name, district, and
  address as profile/date fields in four templates. Explicit source-caption
  mappings now expose 19 model fields for `emr` (previously 16), 11 for
  `protocols` (7), 10 for `ojr` (6), and 7 for `avk` (2). OJR has 162 total
  targets after adding previously missed blank B5/B54. The candidate XLSX
  bytes are unchanged; the four contracts are `2026-09-07-discovery-3`;
- a real balanced run on the paired PDF completed with one paid response
  (72,560 input tokens, 1,351 output tokens; local pricing estimate $0.205497)
  and no technical XLSX errors. The saved response contains five assignments
  and a VL designation conflict (0.38 kV on page 1 versus 0.4 kV on page 14);
- post-generation comparison exposed a semantic mapping ambiguity: AOSR VL
  B42 is only labelled `Город` within the `Проект` organization block and has
  no formula consumers. `Москва 2026г.` on the attached design assignment
  (page 6) is not proof of this field's intended meaning. Do not copy the
  ETALON city or infer it from an organization address. AOSR VL B42 and the
  corresponding AVK B39 / OJR B53 / protocols B53 stay manual pending semantic
  clarification. AOSR VL is now `2026-09-07-discovery-4`, with 27 model fields
  and 38 manual fields. Four other assignments from that paid response remain
  admissible: object name, district, object address, and design-document code;
- selected-template submission validation preserves independently verified
  cells and marks invalid or omitted targets unresolved. It saves the paid
  submission and concise rejection reasons for deterministic replay. Field
  corrections do not trigger another paid turn; at most one batched source
  read is followed by final submission;
- these were technical fixes for marked drafts. Actual dates, quantities,
  certificates and signatories still require admissible evidence.
  Of the 27 AOSR VL model fields, 21 require actual executive-document facts;
  their absence from a design PDF must not be disguised as extraction failure.

The current discovery contracts record coordinates, labels, value kinds,
required flags, and manual-confirmation reasons. They do not yet provide the
stable semantic target IDs, repeat-range rules, or declared render/visibility
expectations required by `semantic-fields.md` for an approved production
contract. This limitation is acceptable only while status remains
`DISCOVERY_REVIEW_REQUIRED`.

Confirmed visual field-policy audit, 2026-09-07 (physical PDF pages; preceding
the later policy change):

- a yellow target did not establish absence from the PDF. At the time of this
  audit all AOSR VL organization blocks were excluded from `model_fields()` by
  `manual_reason`, before source analysis. The runtime prompt and source-priority
  topic also required an approved organization profile. Those restrictions were
  policy blockers, not proof that the source lacked organization details, and
  are superseded by the user-approved policy in `selected-template-v2.md`;
- pages 1–2 of the paired PDF name ООО «ГЕФЕСТ» and print its legal address,
  INN, OGRN, KPP and bank details. Page 7 section 1.3 explicitly names
  ООО «Гефест» as the general designer, consistent with the drawing stamps;
- page 7 section 1.2 explicitly names the customer as the branch of
  ПАО «Россети Московский регион» — Северные электрические сети. This is
  direct role evidence, not an inference from the object's territory;
- page 6 nevertheless labels ООО «Энергосистемы» as the project organization,
  while its electronic-signature overlay names ООО «ГЕФЕСТ». Preserve this
  source conflict. Repeated occurrences do not themselves establish approval
  priority, nor does the shared director name prove identical legal entities;
- page 7 sections 1.10–1.11 give construction/design timing only as
  «В соответствии с договором подряда». Dates of design issue, electronic
  signatures and technical conditions are not actual construction dates;
- persons on pages 2, 5–6, 11 and the drawing stamps have project-development,
  technical-condition or approval roles. Their presence does not establish
  authority to sign the AOSR as construction or customer representatives;
- pages 12–23 contain many design characteristics and quantities. Page 16
  states that final conductor length is clarified after setting out the route;
  page 19 states that grounding resistance is measured after installation and
  backfilling. Neither design quantities nor calculated resistance are actuals;
- page 15's plan labels the conductor 3×95+1×70, while the specifications on
  pages 12 and 22–23 give 3×70+1×95. Record this as a discrepancy for review,
  not a new exception or a reason to silently prefer a value.

## Policy-audit disposition, 2026-09-07

The user approved the PDF-only source policy after this audit; the active rule
is recorded in `selected-template-v2.md`. The following corpus-specific
consequence is retained here for offline review only:

- The paired PDF's explicit customer branch is usable role evidence. Its
  conflicting ООО «ГЕФЕСТ» / ООО «Энергосистемы» designer identities remain a
  conflict: do not pick the more frequent name or combine their details.

This finding is not a source of organization values for a model request. It
must never replace inspecting the uploaded document and its actual evidence.

## Budgeted multi-template regression, 2026-09-08/09

Source PDF SHA-256
`9c5678e1f1964ef0aaf670bfc2418c31af075dc61ab70876b725efae32b3a5be`,
25 physical pages, project 5593. These are offline QA observations, never
filling-model context or permission to import values into another run.

- Three single-response runs consumed an estimated $0.653745 from the
  user-authorized $1 budget: AOSR VL `c71398ea-af02-4c1c-882f-ad7b909deebe`
  (Terra, $0.244161, 10 accepted cells / 6 project-basis), EMR
  `bc1ef582-cefe-4ec1-a4d5-e931274b7357` (Terra, $0.317659, 45 accepted /
  44 project-basis), and AVK `ea27e34d-e3d1-409f-a064-12f763bf6370`
  (Luna, $0.091925, 5 accepted / 0 project-basis). Each run disabled retries
  and required exact preflight. Costs use the application's pricing snapshot,
  not an independently retrieved billing invoice. Historical jobs remain intact.
- In EMR, the model returned 22 material quantities, but every quantity was
  rejected because the value used number-then-unit (`143 м`) while the cited
  table row used unit-then-number (`м 143`). This is a narrow table matching
  defect, not missing PDF evidence. Preserve exact number, unit and material
  row association when testing a correction; do not permute arbitrary text.
- A separate, zero-paid-call replay after narrow address-spacing and material
  quantity-order corrections produced AOSR 11, EMR 66 and AVK six accepted
  cells from the same raw responses, with no changed values or locators.
  EMR gained 21 quantity cells. Compound-unit suffixes (including mathematical
  dot variants), spaced signs and partial decimal values are explicitly
  rejected. The replay is technical validation only: source conflicts, invalid
  visual quotations and hidden template rows remain review blockers. It did
  not overwrite the historical database records or workbooks.
- AOSR B3/B4 rejections included harmless spacing after address abbreviations
  (`уч.3/18` / `уч. 3/18`, `д.Бережки` / `д. Бережки`). Its B40 rejection was
  justified: the model again transcribed a 19-digit settlement account. Other
  legible requisites do not license guessing the missing account digit.
  B41 had address evidence but omitted the legal-entity name from its primary
  quote; this is distinct from an absent address. B23 was model-reported
  ambiguity between a customer-labelled entity and a letter recipient, not
  independently established conflicting customer roles.
- Visual review of physical pages 22–23 found 28 specification positions,
  exceeding the 23 EMR and 10 AVK material-row capacities. Repeated marks in
  different sections have different meanings and sometimes different units:
  F207 appears as 26 metres for line construction and 25 pieces for grounding.
  A dash in the NC20 quantity on page 22 is not zero. Route length and supplied
  wire length are distinct; do not substitute or recalculate one for the other.
- AOSR V63's accepted value had an invalid source association: the model's
  page-10 quote attached 12 to СВ95-3АТ, although that page attaches 12 to
  СВ110-5АТ and has a dash for СВ95-3АТ. Page 22 separately prints СВ95-3АТ,
  12 pieces. This does not validate the false page-10 quotation or resolve
  the material conflict. The source also differs for support 7 between the
  page-13 general plan (А23, two stands) and page-15 detailed plan (П23, one
  stand), without an observed unambiguous revision priority. Hash-pinned visual
  upload plus a model-transcribed quote is not independent cell/row verification.
- Real XLSX inspection confirmed AOSR's 10 assignments, 6 blue and 55 yellow
  targets, and 296 unchanged formulas. Rendering nevertheless exposed clipped
  line designation text in АОСР-2!I63:K63 and АОСР-4!I62:K62, a heavily reduced
  printed object card, and a draft header too close to the paper edge. A zero
  formula-error count is not visual or semantic approval.
- EMR retains 20 source-template `#REF!` formulas and AVK retains two external
  formulas. Their marked XLSX files remain available despite
  `FAILED_VALIDATION`; these are template defects, not failed model responses.
- The economy AVK run uploaded a 24-page visual subset omitting original page
  12. All 20 proposed material cells C77:D86 cited `page:21`, which is the
  specification's position inside that subset; its original physical page is
  22. Card citations before the omitted page retained the correct numbering.
  Validation against the original page 21 correctly rejected those quotes.
  Preserve an explicit input-page/original-page mapping in any future routing
  fix; do not weaken evidence validation or silently guess corrected locators.
- Rendering confirmed that EMR `Ведомость общ` rows 27–41 remain hidden in
  both the candidate and generated workbook: only eight of 22 populated
  positions are visible. AVK object-card rows 35–41 are also hidden, concealing
  three of its five accepted cells (B36/B40/B41). Hidden populated cells must
  not be presented as visible coverage. EMR table headers are blank in the
  candidate; AR1 links a district to a field captioned city at AR3. AR11 links
  blank object-card B8 and prints 30 December 1899. AVK B24/B25 link blank
  organization-detail cells and display false zeroes; C23's concatenation is
  visible outside the card. These inherited defects require separately
  validated candidate/contract changes, not fabricated PDF facts.

Audit artifacts and the spending ledger are under
`data/runs/budget-check-20260908/`; the source-page material audit is under
`data/runs/b2cf69f1-c3da-4663-9f03-37d540a956d7/qa/material-source-audit/`.
No observation in this section approves a candidate, a new mapping or an
execution fact. Any local replay must remain distinguishable from the paid
historical result and must not silently rewrite that result.

## Higher-coverage draft mapping audit, 2026-09-08

The operator requested a less restrictive, higher-coverage draft. The new
`2026-09-08-discovery-6` contracts preserve the candidate XLSX bytes and remain
`DISCOVERY_REVIEW_REQUIRED`, not approved templates. The following mappings are
derived only from `NEW_TEMPLATES` captions, anchors and formula topology:

- AOSR VL has eleven explicitly typed work/material quantity targets eligible
  for marked project-basis values. Actual dates, act numbers and quality-document
  fields do not gain this permission. The factual value must still be stated
  in the uploaded PDF for the same work and material; no missing volume may be
  calculated or invented merely to fill a cell.
- EMR `Ведомость общ` headers E17 (name), AI17 (type/mark) and BE17 (quantity)
  establish 23 repeated material rows, 19–41. Each row's three targets must
  describe the same PDF item, preserving stated units. The 69 targets include
  45 already-empty spare cells; adding their contract entries changes no XLSX
  bytes. Serial numbers, quality records, signatures and result columns remain
  withheld. Header and row-number drift is rejected during registration.
- AVK ` Журнал АВК` C34/D34 establish names and quantities. Rows 77–86 are ten
  genuinely blank spare rows with no pre-existing product/result links. Their
  20 targets accept explicitly marked project-basis items. Rows 36–76 instead
  link to individual acts containing old product labels. For example,
  `стойки!A37` and `Провод СИП 2!A39` are unregistered static example names,
  whereas their quantities are cleared. Opening those quantities could attach
  a new value to the wrong old mark, so these act targets stay withheld.
- Protocols require a separate candidate-cleaning revision before broad row
  filling. In `прот.№6`, D13:F21 contain synthetic result formulas derived from
  nominal current C13:C21 (multipliers and offsets), while adjacent duration
  and conformity text can remain static. In `прот.№7`, measured-value strings
  G23:H26 remain populated even though B23:B26 identifiers are cleared. In
  `прот.№8`, F15:O17 retain example resistance strings/dashes next to cleared
  B15:E17 design identification fields, and P15:P17 retain conformity text.
  These are source/candidate defects, never execution evidence or rules to
  imitate. No new protocol targets are opened in this revision.
- The existing discovery cleanup also clears some table captions as though
  they were row data (e.g. EMR E17/AI17/BE17 and AVK C34/D34). The new mappings
  are proven against immutable source captions and reject layout drift, but
  restoring those captions requires a separately verified candidate revision.

Project-basis filling is a labelled, review-required draft convenience, not
actual-work confirmation. Default document-basis assignments to these new
material targets still require explicit execution evidence. Neither this
audit nor the new mappings enables factual profiles, ETALON values or prior
project facts. This corpus-specific topic stays outside filling-model context.
