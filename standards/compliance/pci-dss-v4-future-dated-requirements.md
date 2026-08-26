# pci-dss-v4-future-dated-requirements

**Issue:** PCI DSS v4.0 shipped 64 new requirements, of which 51 were designated "future-dated" — treated as best practices only until March 31, 2025, after which they became fully mandatory and testable in every assessment. The v4.0.1 revision (June 2024) clarified wording but explicitly did not move that deadline, and v3.2.1 had already been retired on March 31, 2024. As of 2025-2026, organizations that never implemented the future-dated set are failing assessments on requirements they may not know exist — most painfully the ecommerce script-management (6.4.3) and payment-page tamper-detection (11.6.1) requirements, which apply even to many SAQ A merchants who never touch card data directly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The timeline that got teams stuck

1. **March 2022:** PCI DSS v4.0 published, introducing the 64 new requirements with a split effective-date model — most active immediately, 51 future-dated to March 31, 2025.
2. **March 31, 2024:** v3.2.1 retired; v4.0 becomes the only assessable standard, but assessors could still note future-dated requirements as "not yet applicable."
3. **June 2024:** v4.0.1 published as a limited revision — clarifications, no new requirements, no change to the March 2025 date; some requirements were split or renumbered (notably in the 3.3.x and 6.4.3.x ranges).
4. **March 31, 2025:** the future-dated set became mandatory everywhere. Every assessment since must test all 51 as fully in force; "best practice" status is gone.
5. **Practical consequence:** compensating controls are still available where a requirement cannot be met, but v4.x makes the compensating-control worksheet far more demanding (business rationale, risk analysis, target dates, and demonstrably-restrictive interim measures).

## The future-dated requirements that dominate findings

1. **Requirement 3.3.1 — PAN unreadable wherever stored.** Not just primary storage: every location PAN could land (databases, logs, backups, caches, debug files, session recordings) must render it unreadable via truncation, hashing, index tokens with strong cryptography, or full encryption — plus a documented inventory of those storage locations with retention/disposal dates.
2. **Requirement 6.4.3 — payment page script management.** An inventory of every script executing on payment pages (first- and third-party), written justification for each, assurance of script integrity (e.g., SRI/subresource integrity or equivalent), and confirmation each is authorized. This targets Magecart-style supply-chain skimming.
3. **Requirement 11.6.1 — payment page tamper detection.** A change- and tamper-detection mechanism that alerts on unauthorized modification of both HTTP headers and payment page contents. Distinct from script inventory: this is runtime detection, typically cryptographic hashing of page assets polled continuously.
4. **Requirement 8.4.2 — MFA into the CDE.** Multi-factor authentication for all access into the cardholder data environment, not just administrative or remote — including for accounts used by scripts/processes via compensating controls where factors are impossible.
5. **Requirement 8.5.1 — password/passphrase policy floor.** Minimum 12 characters (8 for accounts with system-facilitated change cycles under 90 days), change at least annually unless risk analysis justifies otherwise — note "change frequency" now generally defaults to annual, not the classic 90 days.
6. **Requirement 9.4.5 (POI device tamper).** Procedures and a training/log cadence to detect tampering with point-of-interaction devices; 9.4.5.1 adds the inventory of POI devices and their locations.
7. **Customized-approach TRA (12.3.1).** If you use the "customized approach" (meeting a requirement's intent your own way instead of the defined method), you must perform a targeted risk analysis documenting how your control meets the objective, its frequency, and the evidence — many first-time v4 users trip on TRA formalism even when the underlying control is fine.

## Implementation playbook for ecommerce teams

1. **Build the script inventory as code.** Generate the payment-page script list from the build (script manifests, CSP reporting, runtime crawlers) rather than a spreadsheet; drift between the manifest and the live page is itself a 6.4.3 finding.
2. **Enforce integrity with SRI plus CSP.** Subresource-integrity hashes on every static third-party script, a strict content-security-policy allowlist for hosts, and violation reporting piped to alerting — this covers both the justification and integrity-assurance sub-requirements in one mechanism.
3. **Deploy tamper detection on headers and content.** A scheduled fetcher that hashes the rendered payment page (DOM snapshot) and key HTTP headers, compares against a baseline, and alerts within minutes — commercial RASP/page-integrity products or a small homegrown checker both pass if evidenced.
4. **Purge PAN from logs and telemetry.** Add PAN-pattern detection (regex + Luhn) to log pipelines, redact or truncate at the collector, and add the storage-location inventory (3.3.1) to your data-map with owners and purge dates.
5. **Turn on MFA everywhere in the CDE.** Include jump hosts, databases, container registries, CI/CD deploy paths, and vendor remote-access accounts (which also carry their own v4 requirements around per-user credentials and monitoring).
6. **If a requirement truly cannot be met, use the compensating-control path deliberately.** Document the business constraint, the formal risk analysis, the compensating measure's restrictiveness versus the original control, and a remediation target date — ad-hoc "we'll fix it later" notes now fail.

## Gotchas

1. **SAQ A does not exempt you from 6.4.3/11.6.1.** Fully outsourced ecommerce (redirect/iframe to a PSP) still owns script management and tamper detection for the pages the customer reaches before the PSP frame — the most common 2025 surprise failure for small merchants.
2. **Assessors test "everywhere stored" literally.** One analytics tool logging raw request bodies with PANs will fail 3.3.1 even when the primary database is fully tokenized.
3. **Annual password change is the new default, not 90 days.** Teams that kept quarterly forced rotation are simultaneously over-rotating and missing the 12-character minimum.
4. **TRAs are per-requirement.** Each customized approach needs its own targeted risk analysis with named control owner, tested frequency rationale, and evidence plan; one blanket TRA does not cover them.

## Related

1. **`pci-dss-v4.md`.** General v4 structure and SAQ scoping.
2. **`pci-dss-tokenization-patterns.md`.** How to satisfy the 3.3.x family at the architecture level.
3. **`pci-dss-pen-test-requirements.md` / `pci-dss-network-segmentation.md`.** Adjacent v4 obligations (11.4 testing, scoping) unaffected by the future-dating but usually remediated in the same program.
