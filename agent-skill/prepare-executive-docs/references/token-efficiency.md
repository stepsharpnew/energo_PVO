# Token-efficient processing

Optimize cost without weakening evidence requirements.

1. In selected-template v2, validate and index the one uploaded PDF locally by
   SHA-256. Store page text and whether visual inspection is required.
2. Use the operator-selected template contract to constrain the writable fields.
   The current MVP uses the general PDF index plus model selection for page
   routing; it has no per-contract routing metadata. Do not spend tokens asking
   the model to choose among templates or infer output composition.
3. Never upload the selected XLSX template, a completed workbook, or ETALON to
   the analyzer. Send only the minimal contract target whitelist and field
   descriptions needed for the selected run. If sheet/cell coordinates are used
   as assignment identifiers, expose only registered coordinates and reject any
   coordinate outside that whitelist.
4. For the legacy KL/VRS pilot, route explicitly out-of-scope KTP, VL, GEO, GNB,
   AVK, and EMR evidence out of paid context. Do not apply that legacy filter to
   a separately registered selected-template contract whose approved scope
   explicitly requires one of those families.
5. Give the analyzer a compact PDF evidence packet. Send the full PDF only when
   selected pages cannot preserve the necessary visual evidence.
6. Use low-detail vision first. Every project page without a reliable text layer
   remains eligible even in economy mode. Use high detail only for small print,
   drawings, approval stamps, handwriting, or a documented ambiguity.
7. Treat every scanned page required by the selected contract as part of the
   minimum visual set. If it exceeds the selected page budget, stop before the
   model call and require a larger profile/limit.
8. Use a cost-efficient model for routine extraction and a balanced model for
   reconciliation. Reserve the highest-quality model for measured hard cases.
   Model names remain deployment configuration, not domain rules.
9. Keep static instructions and the selected contract's semantic schema first,
   and dynamic project data last, so supported prompt caching can match stable
   prefixes.
10. When replaying tool history manually, preserve all provider response items
    but restrict reusable reasoning context to the current turn when supported.
11. Persist observed claims and extraction results immediately. If a future
    controlled follow-up flow accepts human-confirmed answers, retry only
    reconciliation and do not upload the unchanged PDF again. The current
    selected-template MVP stops after the marked `NEEDS_INPUT` draft.
12. Count input tokens before a paid call when supported. Fail closed when exact
    counting fails unless an operator explicitly enables approximate preflight.
    Enforce per-call, whole-job, call-count, visual-page, and cost limits.
13. Record and persist input, cached, cache-write, output, reasoning tokens,
    model, stage, response ID, and estimated cost immediately after every paid
    response. Pricing is an operational estimate and must not affect facts.
14. If the budget is insufficient, stop explicitly. Never silently omit a
    required PDF page, field, validator, or final specialist review to meet a
    cost target.
