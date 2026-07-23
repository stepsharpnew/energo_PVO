# Validation rules

All errors block finalization.

Technical checks: valid OOXML ZIP, unchanged worksheet order and names, no new external links, no forbidden formula errors, no structural changes outside the contract, correct candidate-sheet visibility, unique consecutive numbers, no stale project tokens, and successful open without repair.

Semantic checks: one work per act; all planned works covered once; actual dates have evidence and end is not before start; actual quantities do not masquerade as project values; changed work has an approved scheme; unknown change state is blocked; every material has an acceptable quality document; selected branch/profile is approved; object and organization identifiers agree across acts; no rejected or conflicting critical claims.

Cross-workbook checks: for books with the same project identity, detect duplicate act numbers, route/installation text copied from another segment, incompatible object-card values, and repeated work instances that cannot be represented by the current contract. A completed example's apparent error must be reported; it must not be learned as an exception.

Visual checks: render only a selected sheet and its print area, A4, correct intended orientation, no clipped text, unexpected blank pages, broken fonts, hidden utility sheets, or unrelated acts.

Independent model review receives final claims, document plans, deterministic findings, source pointers for critical fields, and rendered previews in a fresh context. It does not receive prior private reasoning and cannot override deterministic errors.
