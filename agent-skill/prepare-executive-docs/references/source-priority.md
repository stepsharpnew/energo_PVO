# Source priority

Choose evidence by value type, not by a universal document ranking.

| Value | Primary evidence | Fallback |
|---|---|---|
| Design decision | Approved project | NEEDS_INPUT |
| Actual deviation | Approved execution scheme | NEEDS_INPUT |
| Actual quantity | Approved execution scheme | Builder-confirmed answer |
| Actual dates | Builder-confirmed record or answer | NEEDS_INPUT |
| Material identity and quality document | Passport or certificate | NEEDS_INPUT |
| AVK details | Passport/certificate and attestation | Out of pilot |
| Organization details | Approved organization profile | NEEDS_INPUT |
| Signatory | Approved branch profile valid for the period | NEEDS_INPUT |

Do not use a planned work schedule as actual completion evidence. Do not substitute a project quantity for an actual quantity. When multiple scheme versions exist, require an unambiguous approval marker and version order. Preserve page, sheet/cell, or bounding-box provenance for every critical claim.

A human answer is valid only when it includes the confirmer and is stored as `human_confirmed`. Derived values are valid only when they name an approved rule ID.
