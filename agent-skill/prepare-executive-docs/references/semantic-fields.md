# Semantic fields

Selected-template v2 separates evidence from workbook mapping. The registered
template contract—not the model—declares the complete writable-target
whitelist. The model may return a value and PDF provenance only for an exact
target exposed by that contract. It cannot create a target, change the mapping,
or write outside the whitelist.

Every contract must declare:

- stable public `template_id`, document kind, version, status, and source
  SHA-256;
- each allowed target's sheet, cell, human-readable label, value kind, and
  stable target identifier when one is available;
- which targets are critical, optional, or manual-only;
- a visible unresolved-fill rule and the exact cells/ranges it may affect;
- any bounded repeated-row mappings;
- allowed sheet visibility changes and rendering expectations.

The analyzer may receive the minimal contract target list needed to return
assignments. It must never return workbook paths, output filenames, style IDs,
or arbitrary sheet/cell coordinates. The generator validates every assignment
against the registered whitelist. A target without an admissible claim remains
blank and is visibly filled; the generator records its label, coordinate,
reason, and blocking status in the unresolved field register.

The exact keys below belong to the approved legacy AOSR semantic pipeline. Keep
using them when that legacy contract applies:

- object: `project.sap`, `project.name`, `project.district`, `project.address`, `project.installation`, `project.code`;
- actual dates: `actual.start`, `actual.end`, or more specific work keys containing `start` and `end`;
- contractor: `contractor.name`, `contractor.registration`, `contractor.address`, `contractor.director.position`, `contractor.director.name`, `contractor.construction_control.position`, `contractor.construction_control.name`, `contractor.construction_control.authority`, `contractor.work_supervisor.position`, `contractor.work_supervisor.name`, `contractor.work_supervisor.authority`;
- customer: `customer.name`, `customer.registration`, `customer.address`, `customer.construction_control.position`, `customer.construction_control.name`, `customer.construction_control.authority`, `customer.site_representative.position`, `customer.site_representative.name`, `customer.site_representative.authority`;
- designer: `designer.name`, `designer.registration`, `designer.address`, `designer.issue_city`;
- profile audit: `organization.profile.version`, `customer.profile.version`.

Use stable, work-specific keys for actual volume, material, and date claims and list those exact keys in `WorkItem.source_claim_keys`. A `DocumentPlan.field_values` entry may only repeat an admissible Claim with the same key and value; it cannot introduce a fact.

For a non-AOSR registered contract, do not force an unrelated field into
`WorkItem`, reuse an AOSR key with a different meaning, or infer a new
cross-template synonym from ETALON. A new cross-project semantic rule still
requires an approved reference and contract revision; a target whitelist by
itself is not such approval.

The unresolved field register uses, at minimum:

- `template_id`;
- sheet, cell, human-readable label, and any stable contract target identifier;
- reason: `missing`, `conflict`, `ambiguous`, `rejected`, or
  `unapproved_rule`;
- blocking status;
- relevant PDF page locators, if any.
