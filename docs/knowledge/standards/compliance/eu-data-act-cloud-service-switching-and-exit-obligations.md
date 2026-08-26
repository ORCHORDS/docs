# EU Data Act cloud-service switching and exit obligations

**Issue:** A cloud-service contract makes it technically or commercially difficult for a customer to switch provider or retrieve data, without a scoped assessment of the EU Data Act’s applicable obligations.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Scope

Regulation (EU) 2023/2854 applies from 12 September 2025. Chapter VI addresses switching between data-processing services, but applicability and exceptions must be assessed for the specific provider and service; do not describe it as a blanket obligation for every SaaS product.

**Source:** [Regulation (EU) 2023/2854 — EU Data Act](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2854)

## Operating controls

- keep an owned inventory of customer data, digital assets, configurations, identities, logs, interfaces, and dependencies required for exit;
- provide clear written switching terms, including notice, transition, assistance, continuity/security, and retrieval commitments where the regulation applies;
- design export and deletion workflows that are testable, documented, and usable without unreasonable barriers;
- assess technical, contractual, commercial, and organisational switching obstacles together;
- test an exit scenario periodically using a representative customer environment and record gaps;
- retain evidence of service portability, support hand-off, and post-transition retrieval/deletion handling.

## Verification

- an independent operator can produce the portability inventory and execute a sample export;
- the export contains documented formats, schemas, metadata, and integrity checks;
- critical customer dependencies and third-party subprocessors are included in the exit plan;
- transition time, support ownership, costs, and security controls are contractually reviewable;
- the legal/compliance owner has recorded the scope and exception analysis.

## Gotchas

- Data export alone is not switching readiness: configuration, identities, interfaces, and operational knowledge matter.
- Avoid proprietary exports with no usable schema or validation route.
- A contractual promise without a rehearsed technical exit path is not evidence of portability.
- Sector-specific rules and customer contracts can impose stricter obligations.

## Related

- `compliance/eu-data-act-implementation.md`
- `compliance/eu-dora-ict-third-party-register-of-information.md`
- `architecture/data-portability.md`
