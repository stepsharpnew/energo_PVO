# Token-efficient processing

Optimize cost without weakening evidence requirements.

1. Validate and index every source locally by SHA-256. Store page/sheet text and whether visual inspection is required.
2. Route out-of-pilot KTP, VL, GEO, GNB, AVK, and EMR files out of paid pilot context while preserving them in the inventory. Selection must be deterministic and independent of upload order.
3. Give the analyzer a compact evidence packet. Send full files only when selected pages cannot preserve the necessary visual evidence.
4. Use low-detail vision first. Every project page without a reliable text layer remains eligible even in economy mode. Use high detail only for small print, drawings, approval stamps, handwriting, or a documented ambiguity.
5. Treat scanned project pages, image evidence, and every page of an in-scope execution scheme as the minimum visual set. If that set exceeds the selected page budget, stop before the model call and require a larger profile/limit; never evict one required source with another.
6. Use a cost-efficient model for routine extraction and a balanced model for reconciliation. Reserve the highest-quality model for measured hard cases. Model names remain deployment configuration, not domain rules.
7. Keep static instructions first and dynamic project data last so supported prompt caching can match stable prefixes.
8. When replaying tool history manually, preserve all provider response items but restrict reusable reasoning context to the current turn when the selected model supports it.
9. Persist observed claims and extraction results immediately. After `NEEDS_INPUT`, retry only reconciliation with human-confirmed answers; do not upload unchanged sources again.
10. Count input tokens before a paid call when the provider supports it. Fail closed when exact counting fails unless an operator explicitly enables approximate preflight. Enforce per-call, whole-job, call-count, visual-page, and cost limits.
11. Record and persist input, cached, cache-write, output, reasoning tokens, model, stage, response ID, and estimated cost immediately after every paid response. Pricing is an operational estimate and must not affect document facts.
12. If the budget is insufficient, stop explicitly. Never silently omit a required source, act, validator, or final specialist review to meet a cost target.
