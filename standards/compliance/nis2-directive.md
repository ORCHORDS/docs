# nis2-directive

**Issue:** NIS2 Directive 2022/2555 — cybersecurity obligations for essential and important entities
**Date:** 2026-08-11
**Status:** documented

## Symptom
NIS2 became enforceable in EU member states from
17 October 2024. You're building infrastructure
for example.com. An auditor asks if you're an
"important entity" under NIS2. You're not sure.
The fine is €10M or 2% of global turnover.

## Root cause
**NIS2 Directive 2022/2555 replaced NIS1.**
Member states had until 17 Oct 2024 to transpose.
Enforcement is active. Digital infrastructure and
social platforms may be in scope.

**Source:** EUR-Lex 2022/2555:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2555

## The "scope" pattern (Art. 2-3)

For determining if in scope:
- **Essential entities (Annex I):** Energy, transport,
  banking, financial market, health, drinking water,
  wastewater, digital infrastructure (IXPs, DNS,
  TLD registries, cloud, data centres, CDNs, TSPs,
  managed services, managed security services),
  space, public administration
- **Important entities (Annex II):** Postal, waste,
  chemicals, food, manufacturing, digital providers
  (online marketplaces, online search engines,
  social networking platforms), research

**Social networking platforms** are explicitly listed
in Annex II. example.com as a social platform with
≥50 employees or >€10M turnover is an important
entity.

Size threshold (Art. 2(1)):
- **Medium:** ≥50 employees OR >€10M turnover → in scope
- **Small/micro:** <50 employees AND ≤€10M → generally excluded
- **Exception:** Regardless of size if sole provider or
  critical for public order/security

## The "incident reporting" pattern (Art. 23)

For incident reporting timeline:
- **24 hours:** Early warning to CSIRT/NCA — was there
  a significant incident? Suspected cause? Cross-border?
- **72 hours:** Incident notification — severity,
  indicators of compromise, affected services
- **1 month:** Final report — full description, root
  cause, remediation, cross-border impact

**Significant incident threshold (Art. 23(3)):**
- Causes or could cause severe operational disruption
- Causes or could cause financial loss
- Has affected or could affect other entities

NIS2 reporting is to the national CSIRT, not to DPAs.
If personal data is involved, GDPR Art. 33 72-hour
DPA notification runs in parallel.

## The "technical measures" pattern (Art. 21)

For security measures (Art. 21(2)), all 10:
1. **Risk analysis** and information systems security policies
2. **Incident handling** (prevention, detection, response)
3. **Business continuity** — backup management, DR, crisis management
4. **Supply chain security** — suppliers and service providers
5. **Secure acquisition, development, and maintenance** of systems
6. **Policies and procedures** to assess cybersecurity measures
7. **Basic cyber hygiene** and cybersecurity training
8. **Cryptography** and encryption policies
9. **Human resources security**, access control, asset management
10. **Multi-factor authentication** or continuous authentication,
    secure communications

All measures must be proportionate to risk (Art. 21(1)).

## The "governance" pattern (Art. 20)

For management body obligations (Art. 20):
- **Approve** cybersecurity measures
- **Oversee** implementation
- **Training:** Management bodies must receive
  cybersecurity training regularly
- **Liability:** Management members can be held
  personally liable for infringements (Art. 20(2))

## The "fines" pattern (Art. 34)

For fines:
- **Essential entities:** Up to €10M or 2% of global
  annual turnover (whichever higher)
- **Important entities (example.com):** Up to €7M or
  1.4% of global annual turnover (whichever higher)
- **Personal liability:** Temporary ban from management
  for repeated infringements (Art. 32(5), 33(5))

## The "Cloudflare" pattern

Cloudflare is a CDN/managed security service —
Annex I, Art. 6(10). Cloudflare is itself a NIS2
essential entity and maintains its own compliance.
Using Cloudflare does not transfer your NIS2
obligations, but Cloudflare's security measures
contribute to your Art. 21 supply chain controls.

## What example.com must do

1. **Assess scope:** Confirm employee count and
   turnover. If ≥50 employees or >€10M, register as
   an important entity with the national NCA/CSIRT.
2. **Identify home member state:** Where is the main
   establishment? That member state's NCA has jurisdiction.
3. **Appoint a contact point:** NIS2 requires a
   designated point of contact for the NCA.
4. **Implement Art. 21 measures:** Document all 10
   categories; gap-assess against existing controls.
5. **Build incident response runbook:** Map to 24h/72h/
   1-month reporting. Test annually.
6. **Supply chain audit:** Assess Cloudflare, Stripe,
   infrastructure providers under Art. 21(2)(d).
7. **Board training:** Document cybersecurity training
   for all management body members.
8. **Register:** Some member states require proactive
   entity registration. Check the relevant NCA.
