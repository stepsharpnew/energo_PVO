# Source priority

Policy approved by the user on 2026-09-07: the current uploaded PDF is the only
source of values for automatic selected-template filling. Organization, customer
and signatory profiles are retired. Neither a profile approval nor a human
answer is an alternative source. This supersedes the former profile-based
source table; it does not approve a template or authorize a new factual inference.
The 2026-09-08 draft extension allows explicit project-basis prefills under the
target contract, with a visible «по проекту» marker and retained `NEEDS_INPUT`.

Choose evidence within that PDF by value type, not by a universal document
ranking. The required record below must actually be present in the uploaded
PDF; its filename, an external profile or another project cannot substitute it.

| Value | Required evidence in the uploaded PDF | If absent or conflicting |
|---|---|---|
| Design decision | Explicit project statement for the relevant object/segment | NEEDS_INPUT |
| Draft project quantity, material, name or type | Explicit matching project statement and target `allow_project_basis: true`; preserve `value_basis="project"` and visible «по проекту» | Leave blank without permission; even an accepted project-basis prefill retains NEEDS_INPUT |
| Actual deviation | Execution scheme with unambiguous approval and version | NEEDS_INPUT |
| Actual quantity | Explicit actual/as-built quantity for the matching work | NEEDS_INPUT |
| Actual dates | Explicit actual execution dates for the matching work | NEEDS_INPUT |
| Material identity and quality document | Matching passport/certificate record, not a sample or specification requirement | NEEDS_INPUT |
| AVK details | Actual incoming-inspection record and relevant quality document | NEEDS_INPUT |
| Organization name, address, legal details | Explicit legal entity and matching customer/contractor/designer role | NEEDS_INPUT |
| Signatory and authority | Matching execution role and required authority/period, not merely a project-development signature | NEEDS_INPUT |

Keep related organization fields attached to the same evidenced legal entity.
A designer is not a construction contractor. A person approving a design is
not automatically a construction/customer representative for signing AOSR.
An object's territory does not identify the customer branch. An organization
address does not define an ambiguous project issue-city field.

Do not use a planned schedule as actual completion evidence or present a
design quantity as an actual quantity. A permitted project-basis draft prefill
is a separate evidence class, not an exception to this rule. Dates of document issue, technical
conditions and electronic signatures are not actual construction dates.
Require an unambiguous approval marker and version order to prefer one
execution scheme. Repetition, model confidence or a shared director does not
resolve contradictory legal entity names. Preserve both page locators and
leave dependent unresolved fields blank with visible fill.

Every accepted value retains file ID, source SHA-256, physical PDF page and an
evidence fragment. Safe formatting normalization may preserve an observed fact
without creating a new one or changing digits. Reuse one evidenced fact across
all registered targets of the same meaning; never duplicate it into a different
role or scope. An unreadable or omitted digit remains unresolved rather than
being supplied by normalization.

An omitted model record (`not_returned`) is not proof of absent evidence.
Preserve rejected proposed values as `rejected` with the reason and available
source pointers; reserve `missing_from_pdf` for explicitly reported absence.

Completed workbooks, ETALON, profiles and legacy `human_confirmed` records are
never evidence for a new selected-template PDF-only run. Legacy answer routes
remain compatibility features and do not alter this source boundary. Corpus
workbooks remain available for post-generation regression comparison and
separately reviewed structural findings only. Manual changes made by a
specialist in the downloaded draft are outside automatic extraction and must
not be represented as PDF-backed.
