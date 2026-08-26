# dora-regulation

**Issue:** DORA — Digital Operational Resilience Act (EU) 2022/2554, ICT risk for financial entities
**Date:** 2026-08-11
**Status:** documented

## Symptom
Stripe processes payments for example.com. A lawyer
asks if DORA applies to your platform because
you're "in the payments chain." You think DORA is
only for banks. The fine under DORA for ICT
third-party providers can reach €5M or 1% of
daily global turnover.

## Root cause
**DORA (Regulation (EU) 2022/2554) applies from
17 January 2025.** It covers financial entities
and their critical ICT third-party service
providers (CTPPs). SaaS platforms that are not
financial entities are not directly in scope —
but if Stripe or a bank classifies example.com
as a critical third-party service provider, DORA
obligations can flow through contracts.

**Source:** EUR-Lex 2022/2554:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2554

## The "who is in scope" pattern (Art. 2)

For 20 categories of financial entities in scope:
- Credit institutions (banks)
- Payment institutions (Stripe Europe)
- E-money institutions
- Investment firms
- Crypto-asset service providers (under MiCA)
- Insurance/reinsurance undertakings
- Pension funds
- Central counterparties
- Trade repositories
- Data reporting service providers
- …and others

**example.com is NOT a financial entity.** It does
not require DORA compliance as a direct obligation.

**But:** Cloudflare, AWS, or similar services used
by example.com may be classified as Critical Third-
Party ICT Providers (CTPPs) under Art. 31. If
so, the ESA (EBA/ESMA/EIOPA) can directly supervise
them. This does not create example.com obligations.

## The "ICT risk management" pattern (Art. 5-16)

For financial entities' ICT framework (not example.com,
but relevant if example.com sells B2B to financial entities):
- **Art. 5:** Management body oversight and accountability
- **Art. 6:** ICT risk management framework
- **Art. 8:** Risk identification — asset inventory, threats
- **Art. 9:** Protection and prevention — access control,
  patching, encryption
- **Art. 10:** Detection — monitoring, logging, anomalies
- **Art. 11:** Response and recovery — RTO/RPO, BCP, DR
- **Art. 12:** Backup — policies, procedures, restoration
- **Art. 13:** Learning and evolving — post-incident reviews
- **Art. 16:** Simplified ICT framework for small entities

## The "incident classification" pattern (Art. 18-20)

For ICT-related incident classification:
- **Major incident criteria (Art. 18(1)):** Number of
  clients affected, duration, geographic spread, data
  losses, criticality of affected services, economic impact
- **Major incident reporting (Art. 19):**
  - Initial notification: within 4 hours of classifying
    as major (max 24h after awareness)
  - Intermediate: within 72 hours
  - Final report: within 1 month
- **Voluntary reporting:** Significant cyber threats
  can be reported voluntarily even if no incident

## The "TLPT" pattern (Art. 26-27)

For Threat-Led Penetration Testing:
- Required for **significant financial entities** only
- Frequency: at least every 3 years
- Covers production systems, live data
- TIBER-EU framework is the reference methodology
- Scope: critical functions and supporting systems
- **Not applicable to example.com** directly

## The "third-party contractual requirements" pattern (Art. 28-30)

For ICT third-party risk management:
- Financial entities must ensure contracts with ICT
  providers include (Art. 30):
  - Audit rights
  - Data location disclosure
  - Business continuity provisions
  - Security incident notification obligations
  - RTO/RPO guarantees
  - Exit/portability provisions

**What this means for example.com:** If Stripe
(a payment institution subject to DORA) classifies
example.com as a significant ICT service provider,
Stripe may require DORA-aligned contract terms —
audit rights, security notification SLAs, BCP
documentation. This is a contractual obligation
flowing from Stripe's DORA duties, not a regulatory
obligation of example.com itself.

## The "CTPP oversight" pattern (Art. 31-44)

For Critical Third-Party ICT Provider designation:
- **ESAs designate CTPPs** annually based on systemic
  importance to EU financial sector
- **Designated CTPPs** must: participate in oversight,
  provide info, remediate findings, pay oversight fees
- **First CTPP list:** Expected from ESAs in 2025
- Likely candidates: AWS, Azure, GCP, Cloudflare, Salesforce

If Cloudflare is designated a CTPP, the ESA Lead
Overseer can conduct inspections. Cloudflare absorbs
compliance cost; example.com is unaffected directly.

## What example.com must do

1. **Confirm non-scope:** Document that example.com
   is not a financial entity under Art. 2. File this
   assessment. Review if a payments feature ever
   constitutes e-money issuance (which would bring
   you in scope).
2. **Review Stripe contract:** Stripe may issue DORA-
   required addenda for ICT services you provide to
   them (e.g. webhook endpoints, data feeds). Review
   and respond promptly — Stripe is subject to DORA.
3. **Contractual readiness:** Even out of scope, adopt
   DORA-aligned security minimums in your own vendor
   contracts with cloud providers — this supports NIS2
   Art. 21 supply chain requirements simultaneously.
4. **MiCA intersection:** If example.com later becomes a
   CASP (crypto-asset service provider), DORA applies
   directly. Plan accordingly.
5. **B2B SaaS to financial entities:** If example.com
   ever sells a white-label product to a bank or
   insurer, expect DORA-mandated audit rights and
   security questionnaires. Start ISO 27001 or SOC 2
   Type 2 to satisfy these efficiently.
