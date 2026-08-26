# dac7-platform-seller-tax-reporting

**Issue:** Council Directive (EU) 2021/514 ("DAC7") makes platform operators — including pure software intermediaries that merely facilitate sales — the tax-transparency reporting agent for their sellers. Platforms must identify reportable sellers, complete due diligence by 31 December of each reporting year, and file an XML report with an EU member state tax authority by 31 January for the prior calendar year, covering identity data, financial accounts, and quarterly fees/commissions. Non-compliance is enforced by national penalties (per-seller fines, with some regimes scaling far higher — one summary reports maximums up to 5% of global revenue for incorrect reporting, [Tecalis](https://www.tecalis.com/blog/dac7-what-is-it-regulations-fines-digital-platforms)). This article covers the obligations and the reporting pipeline to build; it pairs with `dsa-online-platform-obligations-2026.md` (DSA Art. 30 KYBC reuses the same data).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Who and what is reportable

1. **Platform operator is defined functionally.** Any entity that contracts with sellers to make available all or part of the infrastructure for "relevant activities" — marketplaces, app stores, booking platforms, or software that connects suppliers and buyers — is an operator, even if it never touches the money (EC [DAC7 page](https://taxation-customs.ec.europa.eu/taxation/tax-transparency-cooperation/administrative-co-operation-and-mutual-assistance/dac7_en)).
2. **Relevant activities are a closed list.** Sale of goods, personal services, and rental of immovable property or means of transport — anything else on the platform (e.g., employment relationships or pure consumer-to-consumer gifts) is out of scope.
3. **Reportable seller test.** A seller is reportable if resident in an EU member state, or an EU resident seller selling through a non-EU platform, or a non-EU-resident seller with an EU financial account or providing relevant activities to EU customers — the platform must run this test on registration data.
4. **De minimis carve-out.** Sellers with fewer than 30 relevant activities **and** no more than €2,000 total consideration paid or credited in the reporting period can be excluded — both conditions must fail before exclusion is lawful, and member-state guidance on first-year sellers varies, so route edge cases through tax counsel.
5. **Excluded entities.** Government entities and sellers of listed securities (and their corporate-group sellers with equivalent disclosure) are excluded, but the exclusion must be evidenced from verified data, not from the seller's own checkbox.

## Data collection and due diligence

1. **Required data elements.** Legal name, address, taxpayer identification number (TIN), VAT number (where the seller is VAT-registered), date of birth for individuals, financial account identifiers, the member state of residence/establishment, and per-quarter fees, commissions, and taxes withheld — collected at seller onboarding.
2. **Verification to documentary standard.** Data must be corroborated by reliable evidence (identity documents, certificates, extracts from public registries) collected within defined windows before and during the reporting period; the due-diligence file is what a tax audit will ask for first ([Ondato overview](https://ondato.com/blog/dac7-directive-all-you-need-to-know/)).
3. **Re-verification triggers.** When a document expires, when reported data becomes unreliable, or when the platform has reason to believe the seller changed status, the verification must be redone — model documents with expiry dates, not one-time checks.
4. **Deadline: 31 December.** Due diligence must be complete by the end of the reporting year so the January filing is an aggregation exercise, not a scramble to chase missing TINs ([Quaderno guide](https://quaderno.io/blog/digital-tax/dac7-reporting/)).
5. **Seller statement rights.** By 31 January the platform must provide each reported seller a copy of the information reported about them, and operate a correction procedure for 60 days thereafter — seller-facing report generation is part of the pipeline, not an optional courtesy.

## Reporting pipeline engineering

1. **Annual aggregation job.** A scheduled pipeline joins verified-seller profiles with per-quarter ledger totals, applies the reportable/exclusion tests, and emits the population to file — reusing ledger data rather than letting the report become a second book of record.
2. **XML schema filing.** Reports are filed as XML under the standardised Commission schema (derived from the OECD model rules for reporting by platform operators), submitted to the tax authority of the member state of establishment via its portal or CCN channel — build with schema validation (XSD) in CI so an invalid file is a test failure, not a January surprise.
3. **Member-state portals differ.** Each tax administration exposes its own submission channel, credentials, and acknowledgement flow; abstract the transport layer and pre-register credentials for every state you file in.
4. **Seller report generation.** The same aggregation job renders per-seller PDF/CSV statements with the correction-request channel attached, timestamped and archived for evidence of the 31 January delivery.
5. **Audit trail and penalty exposure.** Keep the full evidence chain (verification documents, exclusion decisions, XML submissions, acknowledgements) for the statutory retention period; penalties are member-state set and typically accrue per unreported or mis-reported seller ([Bird & Bird practical tips](https://www.twobirds.com/en/insights/2024/uk/5-practical-tips-for-online-platforms-to-navigate-and-comply-with-dac7-in-eu-and-drr-in-the-uk)).

## Gotchas

1. **The UK mirror regime (DRR).** The UK Digital Reporting Requirements largely copy DAC7 from January 2024, including HMRC-specific XML and a £100-per-seller-per-month style penalty regime for unreported sellers — one pipeline, two national filers.
2. **TIN failures dominate rejections.** Missing, malformed, or unvalidated TINs (and non-EU TINs for non-EU sellers) are the main cause of rejected XML; validate at entry and flag sellers who cannot produce one before Q4.
3. **GDPR interplay.** DAC7 collection is a legal obligation (Art. 6(1)(c) GDPR basis), but the KYC document retention period and access controls still need to be defined in the RoPA entry (see `gdpr-article-30-ropa-automation.md`) — do not archive identity documents indefinitely "just in case".
4. **Fees versus gross payments.** Report the required financial fields per the schema (consideration paid or credited, fees, commissions, taxes withheld) with ledger-level precision; approximations surface as "incorrectly reported seller" findings that penalties attach to.
5. **Calendar discipline is the control.** Two dates drive everything — 31 December (due diligence complete) and 31 January (XML filing plus seller statements); put both on the compliance calendar with checkpoints in October and December, because there is no extension mechanism.
