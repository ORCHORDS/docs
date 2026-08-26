# csrd-reporting

**Issue:** CSRD — Corporate Sustainability Reporting Directive 2022/2464, mandatory ESG disclosure
**Date:** 2026-08-11
**Status:** documented

## Symptom
An investor asks for your ESG report under CSRD.
You're not sure if you're in scope yet. The rules
use terms like "double materiality" and "ESRS."
You want to know if and when example.com must
comply, and what it actually has to report.

## Root cause
**CSRD (Directive 2022/2464) amends the NFRD.**
It introduces mandatory sustainability reporting
under European Sustainability Reporting Standards
(ESRS). Phased rollout 2024–2028.

**Source:** EUR-Lex 2022/2464:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464

## The "phased scope" pattern (Art. 5)

For rollout deadlines:
- **Wave 1 (FY 2024, report 2025):** Large public-
  interest entities (PIEs) already under NFRD, >500
  employees — typically listed companies, banks, insurers
- **Wave 2 (FY 2025, report 2026):** Large companies
  not previously subject to NFRD — ≥2 of 3 thresholds:
  >250 employees, >€50M net turnover, >€25M balance sheet
- **Wave 3 (FY 2026, report 2027):** Listed SMEs,
  small and non-complex credit institutions, captive
  insurance undertakings
- **Wave 4 (FY 2028, report 2029):** Non-EU companies
  with >€150M EU turnover and EU subsidiary/branch

**example.com assessment:**
- If <250 employees AND ≤€50M turnover AND ≤€25M
  balance sheet → not in scope until Wave 3 (if listed)
  or Wave 4 (if non-EU parent >€150M)
- If ≥2 Wave 2 thresholds by FY2025 → mandatory from 2026

## The "ESRS standards" pattern

For European Sustainability Reporting Standards
(adopted by Commission Delegated Regulation 2023/2772):
- **Cross-cutting:**
  - ESRS 1: General requirements (not a disclosure itself)
  - ESRS 2: General disclosures (mandatory for all in scope)
- **Environmental (E):**
  - E1: Climate change (GHG emissions, Scope 1/2/3)
  - E2: Pollution
  - E3: Water and marine resources
  - E4: Biodiversity and ecosystems
  - E5: Resource use and circular economy
- **Social (S):**
  - S1: Own workforce
  - S2: Workers in the value chain
  - S3: Affected communities
  - S4: Consumers and end-users
- **Governance (G):**
  - G1: Business conduct (anti-corruption, lobbying)

Only ESRS 2 + material topics require reporting.

## The "double materiality" pattern (ESRS 1, Ch. 3)

For double materiality assessment:
- **Impact materiality:** Does the company cause,
  contribute to, or is linked to positive or negative
  impacts on people or environment?
- **Financial materiality:** Do sustainability matters
  pose financial risks or opportunities to the company?

A topic is material if it is material from either
perspective. Document the assessment methodology.
This is the starting point before identifying which
ESRS topics to report.

For example.com specifically:
- **S4 (consumers/users):** Content moderation,
  adult content safety, user welfare — likely impact-material
- **S1 (own workforce):** Working conditions, diversity
- **G1 (business conduct):** Data practices, anti-corruption
- **E1 (climate):** Digital infrastructure energy use,
  Cloudflare/hosting emissions (Scope 3 Category 1)

## The "assurance" pattern (Art. 26a)

For third-party assurance:
- **Phase 1:** Limited assurance (reasonable effort
  to conclude nothing is materially misstated)
- **Phase 2 (later):** Reasonable assurance (full audit
  standard) — date TBD by Commission

## The "taxonomy alignment" pattern

CSRD reporting must include EU Taxonomy alignment
(Regulation 2020/852) for covered activities:
- Which revenue/capex/opex is taxonomy-eligible?
- Of eligible: what % is taxonomy-aligned?
- Digital content platforms are assessed under
  ICT sector criteria (Delegated Act 2023/2486)

## What example.com must do

1. **Check scope now:** Calculate employees, turnover,
   balance sheet for FY2025. Know which wave applies.
2. **Double materiality assessment:** Even pre-mandatory,
   conduct the assessment to understand gaps. S4 and
   G1 are likely material for an adult content platform.
3. **Data collection:** Start collecting Scope 1 and 2
   GHG data (energy use), workforce metrics, and
   governance indicators in FY2025 — data lag makes
   retroactive collection impossible.
4. **Value chain Scope 3:** Identify Cloudflare, data
   centre providers, Stripe. Request emissions data.
5. **ESRS 2 baseline:** ESRS 2 (general disclosures) is
   mandatory for all in-scope entities — governance,
   strategy, risk, and materiality process.
6. **Policy review:** Adult content platforms face
   S4 scrutiny. Document content moderation, age
   verification, and user welfare policies as
   impact management measures.
7. **Not yet in scope:** If confirmed out of Wave 2,
   monitor Wave 3/4 thresholds and CSRD omnibus
   amendment (Commission proposal Feb 2025 to simplify
   for smaller companies).
