---
title: "EU NIS2 Directive Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Directive (EU) 2022/2555 (NIS2 Directive); https://eur-lex.europa.eu/eli/dir/2022/2555/oj"
---

# EU NIS2 Directive Governance

## Purpose

Directive (EU) 2022/2555 (the **NIS2 Directive**, "Network and Information Security 2") replaces Directive 2016/1148 with effect from 18 October 2024 (transposition deadline). NIS2 expands the scope to 18 sectors (energy; transport; banking; financial market infrastructures; health; drinking water; waste water; digital infrastructure; public administration; space), sets minimum cybersecurity risk-management measures (Article 21), introduces management-body accountability (Article 20), and defines incident-handling and reporting obligations (Article 23).

## Current context and source status

NIS2 is in force as an EU directive; member-state transposition into national law is the binding instrument for in-scope entities. The companion Implementing Regulation (EU) 2024/2690 specifies the technical and methodological requirements (Annexes I and II). The NIS2 Implementing and Delegated Acts on critical ICT third-party providers (DORA's framework-aligned designation regime) also apply where relevant.

## Governance workflow and controls

1. Determine essential vs important entity status (Annex I / Annex II), and per-sector applicability.
2. Article 21 — Risk-management measures: policies on risk analysis and information system security; incident handling; business continuity, incl. backup management and disaster recovery; supply chain security (incl. security-related aspects of relationships with direct suppliers / service providers); network security; effectiveness assessment / training; cryptography / encryption and where applicable access control; HR security; asset management; multi-factor authentication; secured communications; secured emergency communication.
3. Article 20 — Management bodies approve the risk-management measures, oversee implementation, and face personal liability for non-compliance; ensure training is provided to management bodies.
4. Article 23 — Incident handling and reporting:
   - Early warning to the CSIRT / competent authority within 24 hours of becoming aware.
   - Incident notification within 72 hours.
   - Final report within one month.
   - Intermediate reports on the body's request.
5. Article 24 — Significant impact criteria for early warning: affected service, number of users, duration, geographical spread, impact on economic / societal activities.
6. Align to ENISA technical implementation guidance and the relevant sectoral CSIRT procedures.

## Validation and evidence

- Documented Article 21 control implementation map.
- Article 20 management-body attestation of approval, training records, accountability framework.
- Article 23 incident reporting timeline evidence (24 hours / 72 hours / one month) with CSIRT communications.
- Cross-border impact assessment; supplier / supply chain risk register.
- Cooperation with ECCC (European Cyber Crisis Coordination) where applicable; competent authority / CSIRT records.

## Failure correction

Common defects include misclassifying essential / important status, missing Article 20 management-body attestations, and treating article 21 controls as "addressable". Corrective actions include an in-scope re-classification review, a formal management-board training programme, and an incident-reporting playbook with explicit timelines.

## Limitations

- NIS2 is an EU Member-State directive; non-EU headquartered providers serving the EU market must coordinate with the EU-representative regime and applicable national law.
- DORA (Regulation (EU) 2022/2554) and CER (Directive (EU) 2022/2557) overlap; coordinate across NIS2 / DORA / CER for cross-sector scenarios.
- The sector-specific implementing acts (and ISO/IEC 27001 + ISO/IEC 27002 alignment) provide additional grounding but are not substitutes for the directive's risk-management measures.

## Canonical sources

- Directive (EU) 2022/2555 (NIS2 Directive).
- Regulation (EU) 2022/2554 (DORA), Regulation (EU) 2022/2553 (Cyber Resilience Act baseline).
- Directive (EU) 2022/2557 (CER, critical-entities resilience).
- Implementing Regulation (EU) 2024/2690.
- ENISA technical implementation guidance (NIS2).

## Scope note

This article belongs to the standards leaf and cross-references the operations leaf for incident-reporting cadences, the engineering leaf for Article 21 control implementation, and the legal/compliance leaf for management-body accountability and reporting.
