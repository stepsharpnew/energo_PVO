# Semantic fields

Use these exact keys so the restricted workbook contracts can consume claims:

- object: `project.sap`, `project.name`, `project.district`, `project.address`, `project.installation`, `project.code`;
- actual dates: `actual.start`, `actual.end`, or more specific work keys containing `start` and `end`;
- contractor: `contractor.name`, `contractor.registration`, `contractor.address`, `contractor.director.position`, `contractor.director.name`, `contractor.construction_control.position`, `contractor.construction_control.name`, `contractor.construction_control.authority`, `contractor.work_supervisor.position`, `contractor.work_supervisor.name`, `contractor.work_supervisor.authority`;
- customer: `customer.name`, `customer.registration`, `customer.address`, `customer.construction_control.position`, `customer.construction_control.name`, `customer.construction_control.authority`, `customer.site_representative.position`, `customer.site_representative.name`, `customer.site_representative.authority`;
- designer: `designer.name`, `designer.registration`, `designer.address`, `designer.issue_city`;
- profile audit: `organization.profile.version`, `customer.profile.version`.

Use stable, work-specific keys for actual volume, material, and date claims and list those exact keys in `WorkItem.source_claim_keys`. A `DocumentPlan.field_values` entry may only repeat an admissible Claim with the same key and value; it cannot introduce a fact.
