# pipl-china-cross-border-transfers

**Issue:** A SaaS or marketplace that stores or processes personal information of individuals in mainland China, and then moves that data to servers, support staff, analytics, or parent-company systems outside China, is executing a cross-border transfer under PIPL Article 38 and must route it through one of three mechanisms: a CAC security assessment, a filed standard contract, or Personal Information Protection certification. The regime shifted materially in 2024-2025 — the March 2024 "Provisions on Promoting and Regulating Cross-Border Data Flows" relaxed several thresholds and created exemptions, the third edition of the security-assessment guidelines took effect June 27, 2025 (adding a validity-extension mechanism), and the certification route finally became operational with rules finalized October 14, 2025. Teams that sized their obligations under 2022-era thresholds are frequently either over-complying (unnecessary assessments) or missing mandatory PIPIA documentation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three transfer mechanisms and when each applies

1. **CAC security assessment (the strictest route).** Mandatory where an operator is a Critical Information Infrastructure Operator (CIIO), where the export includes "important data," where sensitive personal information of more than 10,000 individuals is transferred, or where non-sensitive personal information of more than 1,000,000 individuals is transferred (thresholds as relaxed by the March 2024 Provisions). The application goes through provincial CAC up to the CAC itself; under the third-edition guidelines effective June 27, 2025, a passed assessment remains valid for three years, with a new extension mechanism for materially unchanged transfers.
2. **Standard Contract (SCC) filing.** For transfers below the assessment thresholds — non-sensitive personal information of 100,000 to 1,000,000 individuals, or sensitive personal information of up to 10,000 individuals — the exporter signs China's official standard contract with the overseas recipient and files the contract plus a PIPIA with the provincial CAC within 10 working days of the contract taking effect.
3. **PIP certification (now operational).** Rules finalized October 14, 2025 establish two Personal Information Protection certification types — a domestic certification and one specifically for cross-border transfer scenarios — issued by accredited professional certification bodies. This is the practical route for multinational groups with continuous, multi-entity transfers that do not fit the one-contract-per-recipient SCC model.

## Exemptions and thresholds introduced by the 2024-2025 reforms

1. **Contract-necessity exemption.** Transfers genuinely necessary to perform a contract with the individual — cross-border shopping, shipping, payment settlement, account recovery, travel booking — are exempt from all three mechanisms, though general PIPL obligations (separate consent where required, PIPIA for sensitive data) still apply.
2. **Small-volume exemption.** Transfers of non-sensitive personal information concerning fewer than 10,000 individuals (measured per exporter, per year since January 1 of the current year) are exempt from the mechanisms without condition.
3. **HR management exemption.** Transfers of employee personal information necessary for HR management under lawfully adopted workplace policies are exempt from the mechanisms.
4. **Sensitive-data note.** The small-volume exemption is generally read to require non-sensitive data; exporting sensitive personal information above 10,000 individuals always pulls you into security assessment, and below that count into SCC or certification — there is no fully exempt path for bulk sensitive data.
5. **The Network Data Security Regulation (effective January 1, 2025)** layers additional obligations on network data handlers on top of PIPL, DSL, and CSL, and reiterates the transfer-mechanism duties — treat it as the umbrella statute when inventorying China obligations.

## The PIPIA requirement and engineering workflow

1. **PIPIA is unconditional for cross-border transfers.** Regardless of which mechanism (or exemption) applies to the mechanism requirement, a Personal Information Protection Impact Assessment must be completed before transferring — covering the purpose and necessity of the export, the destination country's legal environment, the recipient's safeguards, and transfer risks — and retained for at least three years.
2. **Separate consent for sensitive PI and exports.** PIPL Articles 23, 29, and 39 require separate, specific consent (not bundled acceptance) to disclose to or transfer personal information overseas, plus notification of the recipient's identity, contact, processing purpose, method, and categories, and the individual's right to withdraw.
3. **Data inventory and region routing.** Build a registry of China-resident personal information (fields, sensitivity classification, volumes, storage region, downstream recipients); route China data to a China region by default and treat any egress (analytics pipelines, support tooling, CRM sync, LLM APIs) as a gated transfer requiring a mechanism check in code review.
4. **Egress controls as enforcement.** Enforce the registry technically: China-region buckets with deny-by-default cross-region replication, egress proxies for support and analytics access, and DLP rules on the China tenant. The CAC's enforcement pattern penalizes undocumented exports more heavily than late filings.
5. **Annual threshold recount.** The 10,000/100,000/1,000,000 counters reset each calendar year — a transfer program that was exempt in year one can cross into SCC or assessment territory in year two as user counts grow, so recount quarterly and calendar the mechanism upgrade before it becomes a violation.

## Gotchas

1. **Important data has no exhaustive list.** Sectoral regulators publish important-data catalogs; a transfer you classified as ordinary PI can be reclassified by a catalog update, instantly making security assessment mandatory.
2. **Support access is a transfer.** A support engineer in another country querying a China database is a cross-border transfer even though no data "moves" architecturally — remote access counts.
3. **SCC filing is not approval-free forever.** Provincial CAC can question or require corrections post-filing; material changes to the processing require re-filing, and the PIPIA must be updated on the same cycle.
4. **PIPL applies to offshore processors.** Analyzing or profiling individuals located in China from abroad is within PIPL's extraterritorial reach (Article 3), so "we store nothing in China" does not end the analysis.
5. **Penalties are entity-and-person.** Violations of cross-border rules carry fines up to 50M RMB or 5% of prior-year revenue for serious cases, plus personal liability (fines, suspension) for responsible individuals.

## Related

1. **`cross-border-data-transfer-mechanisms.md`.** Comparative view of EU SCCs, adequacy, and other regimes.
2. **`data-localization-requirements.md`.** China storage-localization duties for CIIOs and important data.
3. **`gdpr-dpa-standard-contractual-clauses.md`.** The EU analogue for contract-based transfers, useful when the same pipeline serves both regions.
