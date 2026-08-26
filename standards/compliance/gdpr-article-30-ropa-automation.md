# gdpr-article-30-ropa-automation

**Issue:** GDPR Article 30 requires every controller and processor to maintain a records of processing activities (RoPA) that is complete and current, but hand-maintained spreadsheets rot within months as teams add new data stores, vendors, and features. Supervisory authorities treat the RoPA as the first artifact requested in any inquiry — the Irish DPC explicitly frames it as proof that a controller actually knows what it processes — and gaps between the documented register and real infrastructure read as Art. 5(2) accountability failures, not paperwork oversights. This article covers what the register must contain and how to generate and keep it current from schema metadata, infrastructure-as-code, and sub-processor feeds.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Article 30 actually requires

1. **Mandatory content per activity.** Each record must state the purposes, categories of data subjects and personal data, recipients (including third-country recipients and transfer safeguards), envisaged retention periods, and a general description of security measures (Art. 30(1), full text at [gdpr-info.eu](https://gdpr-info.eu/art-30-gdpr/)).
2. **Separate controller and processor registers.** Processors keep a lighter register under Art. 30(2) — categories of processing carried out on behalf of each controller, sub-processors, transfers, and security measures. A SaaS provider almost always maintains both registers, one per role, because it is controller for its own CRM/analytics and processor for customer tenant data.
3. **The small-organisation exemption is a trap.** Organisations under 250 employees are exempt only where processing is occasional and unlikely to pose a risk — but operating a SaaS with authentication logs, marketing lists, or any profiling fails that test, so almost no software company qualifies (see [ICO guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/documentation/how-do-we-document-our-processing-activities/)).
4. **Production on request, in intelligible form.** The register must be handed to the supervisory authority on request; the [Irish DPC's Article 30 guidance](https://www.dataprotection.ie/en/dpc-guidance/records-of-processing-article-30-guidance) sets the bar as demonstrating real knowledge of purposes, not a template filled with boilerplate.
5. **A living document, not an annual project.** The register must reflect current processing; a RoPA last touched at the previous audit cycle is treated as evidence that governance lags the systems, which colours the rest of an inspection.

## Generating the register from the stack

1. **Schema metadata scanning.** Extract tables and columns tagged as personal data from Postgres/warehouse information schemas or dbt model metadata; the classification tiers defined in `data-classification-policy.md` map directly onto the RoPA field "categories of personal data". Discovery tooling such as [Privado](https://www.privado.ai/post/gdpr-article-30) automates this by scanning code and schemas.
2. **IaC and the service catalog as the activity inventory.** Each service in the catalog carries a `processing_activity` annotation with purpose and lawful basis, so the list of activities falls out of the deployment configuration rather than someone's memory. When a new service is created without the annotation, that is a pipeline failure, not an audit finding.
3. **Sub-processor and DPA feeds fill "recipients".** The procurement/DPA registry (the contract store behind `vendor-security-assessment.md`) is the source of truth for recipients and third-country transfers; a scheduled job joins vendor records to activities so the register never names a vendor legal entity that procurement cannot trace.
4. **Retention read from lifecycle configs.** TTL expressions, S3 lifecycle rules, and log rotation settings are parsed into the "envisaged retention periods" field, which forces the uncomfortable but required alignment between what policy says and what infrastructure actually enforces.
5. **Assemble a versioned RoPA artifact.** Render the collected YAML/JSON entries into the authority-facing template (e.g., a Practical Law-style layout) and store it in git, so every rendered register is reproducible from source data at any historical revision.

## Keeping it current

1. **Change hooks in CI.** A pipeline check fails when a new table, topic, or bucket tagged with PII has no corresponding RoPA entry — the same gate that catches missing classification tags in `data-classification-policy.md`.
2. **Quarterly drift reports.** Diff the scanner's discovered inventory against the register and auto-open tickets for each orphan store or vendor; drift older than one quarter is escalated to the DPO rather than silently absorbed.
3. **Named owner per activity.** Every activity entry carries an owning team and individual; ownership transfers on reorg are a reviewed checklist item, because orphaned activities are where registers go stale first.
4. **Scheduled review with DPO sign-off.** A quarterly (or on-major-change) review updates purposes and lawful bases and records sign-off, matching the cadence expected in accountability inspections.
5. **Immutable revision history.** Git history (or an append-only audit log) over the register entries demonstrates continuous accountability under Art. 5(2) and gives auditors a per-day answer to "what were you processing in March?".

## Gotchas

1. **Shadow SaaS.** Teams adopting analytics or support tools without procurement leave recipients and transfers out of the register; the drift report plus expense-feed reconciliation is the practical detection method.
2. **Backups, logs, and analytics replicas.** These are separate stores with different retention and recipients; list them explicitly per activity instead of assuming "the database" covers them.
3. **Hidden third-country recipients.** AI sub-processors, crash-reporting SDKs, and support inboxes routinely move data to the US; every one needs a transfer mechanism recorded, cross-referencing `gdpr-international-transfers-schrems2.md`.
4. **The Digital Omnibus is not law yet.** The November 2025 proposal would simplify Art. 30 (including a higher small-organisation exemption), and Parliament adopted amendments in June 2026 — but until final adoption, current Article 30 duties apply in full; track it in `digital-omnibus-2026-gdpr-ai-act-reform.md` and do not pause RoPA work.
5. **Copy-paste template rot.** Descriptions inherited from a template ("processing for business purposes") satisfy no one; the DPC guidance expects concrete, activity-specific language, and vague entries are treated as missing entries.
