# us-cloud-act-eu-data-sovereignty-conflict

- **Issue**: You host EU personal data in an EU region of a US-headquartered
  cloud provider and believe "data residency = data sovereignty." The US
  CLOUD Act (2018) lets US authorities compel US providers to hand over data
  they can access, **wherever it is stored**. GDPR Art. 48 forbids complying
  with such requests without an international agreement. This is the trap the
  Schrems line of cases keeps re-opening.
- **Date**: 2026-08-13
- **Repo**: example-org/example-repo
- **Author**: kb-batch-3-compliance
- **Status**: Active; complements
  `documentation/categories/compliance/gdpr-international-transfers-schrems2.md`.

## The legal collision

- **CLOUD Act (US)**: amends the Stored Communications Act. Courts can order
  any US-based "electronic communication service provider" to produce data in
  its "possession, custody, or control" regardless of storage location. It
  also enables executive agreements (e.g., the US-UK and US-Australia data
  access agreements) for cross-border demands.
- **GDPR Art. 48**: a controller may only transfer personal data to a
  third-country *authority* if an MLAT or similar agreement exists — a
  US court order alone is NOT a lawful basis under Chapter V.
- **The practical conflict**: an EU subsidiary of a US provider can be
  ordered (via the parent's ability to access the systems) to produce EU
  data, and either GDPR or the CLOUD Act is violated depending on who
  complies first.

## Symptom

- Architecture diagrams show "EU region, Frankfurt" and compliance signs off
  — but the console is operated by US staff under a US parent with technical
  ability to access the data. Residency was confused with sovereignty.
- A questionnaire from an EU enterprise customer asks "how do you handle
  CLOUD Act exposure?" and the answer is "we use EU regions." That is not an
  answer; procurement teams increasingly reject it.
- A transfer impact assessment (TIA) copies a 2021 template and never
  mentions the DPF's survival status or the provider's access model.

## Gotchas

- **"EU region" is a latency feature, not a legal shield.** If the US parent
  holds keys, break-glass access, or admin control, the data is likely within
  its "possession, custody, or control" for CLOUD Act purposes.
- **The EU-US Data Privacy Framework is still young.** Latombe's challenge
  was dismissed by the EU General Court (3 Sept 2025) but an appeal to the
  CJEU is possible. A second Schrems would invalidate adequacy overnight —
  always keep SCCs + TIA as a documented fallback, never DPF alone.
- **Encryption helps only if the provider can't decrypt.** Provider-managed
  keys (SSE with service keys) don't stop a CLOUD Act order; customer-held or
  EU-held keys (BYOK/HSM in EU control) materially change the analysis.
- **Workload metadata counts.** Logs, telemetry, backups, and support
  bundles often replicate to US-controlled systems even when the primary
  dataset stays in-region. Audit the full data map, not just the database.
- **Sub-processors inherit the problem.** A SaaS vendor hosted in an EU
  region but owned by a US company passes the same exposure to you.
- **Government-use data is the hottest zone.** Public-sector, critical
  infrastructure, and health workloads increasingly demand sovereign-cloud
  options contractually, and some EU tenders now require them.

## Practical example — sovereign posture checklist

```text
1. DATA MAP
   - inventory: primary stores + logs + backups + telemetry + support
     bundles; flag anything leaving the EU or US-parent-accessible.

2. ACCESS MODEL
   - EU-resident workforce + EU entity contracts with the provider.
   - no US-parent break-glass without EU-side co-approval; document it.

3. CRYPTO
   - customer-managed keys, generated and stored in an EU HSM/external KMS
     the provider cannot reach; rotation under customer control.

4. PAPERWORK
   - SCCs (Module 2/3) + TIA that explicitly analyzes FISA 702 / EO 12333
     exposure for THIS provider (query/intent considerations).
   - DPF as belt, SCCs as suspenders; re-check DPF status quarterly.

5. ESCALATION PATH
   - written protocol: any authority request -> notify DPO + EU counsel;
     never silent compliance (GDPR Art. 48) and never silent deletion.

6. SOVEREIGN OPTIONS WHEN THE CUSTOMER DEMANDS MORE
   - EU-sovereign clouds (e.g., AWS European Sovereign Cloud, Azure
     sovereign variants, EU-owned providers like T-Systems/OWS) where
     operational control sits with an EU entity insulated from the parent.
```

Tie this file to `store-region-matrix.md` when choosing regions and to
`gdpr-international-transfers-schrems2.md` for the transfer-mechanics layer.
