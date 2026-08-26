# csam-detection-ncmec-reporting-plumbing

**Issue:** Any service that hosts, transmits, or moderates user media can encounter child sexual abuse material (CSAM), and the moment it does, a multi-jurisdictional legal machine activates: US providers have a statutory duty under 18 U.S.C. 2258A to report apparent CSAM to the NCMEC CyberTipline, while EU providers may only scan for it at all thanks to a temporary ePrivacy derogation that keeps being extended while the CSAR regulation is negotiated. Building the pipeline — hash matching, quarantining, reporting through the CyberTipline Reporting API, and preserving evidence — is sensitive engineering that must be designed before the first hit, not after, because mishandling detected material exposes staff to legal risk and the company to liability.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Legal Duty Landscape

1. **US 2258A mandatory reporting.** US-based electronic service providers (and foreign providers with US nexus in practice) must report facts giving rise to a belief that apparent CSAM was involved, via the CyberTipline. There is no minimum threshold: a single hash match on a known CSAM file makes the provider "aware" and triggers the duty.
2. **EU voluntary scanning derogation.** Detection in EU communications is only lawful under a temporary exemption to ePrivacy confidentiality that lapses repeatedly; it was extended to 3 April 2026 while trilogues on the CSAR continue, and member states have agreed a regime running to 2028. If the derogation lapses, EU traffic scanning — and the NCMEC reports it feeds — becomes unlawful, so the pipeline needs a region switch.
3. **Council position on CSAR (Nov 2025).** On 26 November 2025 the Council reached its negotiating position, rejecting mandatory scanning and instead making voluntary detection permanent, plus risk-assessment duties for providers. Expect detection obligations to be risk-tiered by service type when the final text lands.
4. **Preservation duty.** Reported content must be preserved for 90 days under 2258A so law enforcement can act, which conflicts with default object-lifecycle deletion and requires a legal-hold bucket.
5. **UK Online Safety Act overlay.** UK-facing services must proactively use accredited technology to detect priority offences including CSAM on public channels, and Ofcom can direct deployment on private channels — a distinct duty from the NCMEC reporting plumbing itself.

## Detection Pipeline Engineering

1. **Perceptual hash matching, not crypto hashes.** PhotoDNA-style perceptual hashes stay stable across resize, recompression, and color shifts; matching uses a distance metric, not exact equality. Tune the threshold consciously: looser thresholds raise false-positive rates, which sharply increases human review burden.
2. **Hash set sourcing.** Join the NCMEC hash-sharing initiatives or licensed commercial feeds; Google CSAI Match and hotline-derived lists are the practical sources. Keep hash-set versioning auditable so a report can state which list version and threshold produced the match.
3. **Known-hash scope only.** Only match against verified lists — do not run novel classifiers over user media hunting for unknown CSAM without counsel; voluntary novel detection sits in a legal gray zone in the EU and changes your reporting posture in the US.
4. **Quarantine before human eyes.** On a match, immediately strip the object from normal serving paths, CDN caches, and thumbnails, and move it to an access-controlled quarantine store. Mis-delivering detected material to other users is an independent legal catastrophe.
5. **Scan point selection.** Scan at upload for storage services, at ingestion for moderation queues, and on-report for user-flagged content; for E2EE services, server-side scanning is impossible by design, so detection duties concentrate on surfaces you can lawfully see (profiles, public channels, payment metadata).

## Reporting API Plumbing

1. **CyberTipline Reporting API mechanics.** Endpoints are HTTPS GET/POST with username/password credentials issued by NCMEC after ESP registration; API v2 defines the XML/JSON report schema. Treat credentials as high-value secrets — they can be used to file reports under your name.
2. **Report content.** Reports carry incident metadata (usernames, IP addresses with timestamps, service identifiers, match details) and, for image/video incidents, the actual files uploaded to NCMEC — not just hashes — unless you have agreed hash-only arrangements. Build the exporter to assemble this without analysts touching raw media.
3. **One incident, one report.** Aggregate a single user's burst of matches into one report with a file inventory; repeated identical matches of already-reported material are still reportable but should reference the pattern rather than spamming thousands of reports.
4. **Idempotency and audit.** Persist every report submission (report ID returned by NCMEC, payload hash, operator, timestamp) in a WORM-style log; you will need this for law-enforcement follow-up, for transparency-report numbers, and to defend the completeness of your reporting program.
5. **Failure handling.** The API is a third-party critical dependency: queue reports durably, alert on submission failures, and retry with backoff. A silently dropped report is an unmet statutory duty.

## Access Control And Data Hygiene

1. **Need-to-know isolation.** Restrict quarantine access to a small, trained, background-checked moderation team; every view is logged. Casual engineer access to confirmed CSAM creates personal legal exposure for the viewer.
2. **No training or analytics on hits.** Detected material must never flow into ML training corpora, analytics datasets, or debug dumps; enforce with data-classification tags that block egress from the quarantine domain.
3. **Retention discipline.** Keep matched content only for the preservation window and any hold notices; auto-purge afterwards with an immutable deletion log. Indefinite hoarding of CSAM is itself an offense in many jurisdictions.
4. **Incident comms minimization.** Tickets, Slack, and on-call pages must reference case IDs, never embed images or thumbnails; screenshot tooling must be blocked in the quarantine environment.

## Evidence And Operational Readiness

1. **Written escalation runbook.** Define who declares a reportable incident, who authorizes filing, and how law-enforcement requests against reports are validated and answered — before volume arrives.
2. **Transparency report alignment.** NCMEC publishes per-provider report counts; keep internal counts reconciled with what you publish so discrepancies do not look like underreporting.
3. **Regulatory change watch.** Assign an owner to track the CSAR trilogue, derogation expiry dates, and Ofcom technology notices; the lawful-basis switch for EU scanning is a config flag that must be flipped on the right date, with evidence of why.
