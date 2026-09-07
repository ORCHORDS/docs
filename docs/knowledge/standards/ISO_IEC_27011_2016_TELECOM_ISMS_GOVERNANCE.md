# ISO/IEC 27011:2016 — Information Security Controls for Telecommunications Governance

## 1. Scope

This card governs how `orchords-docs` evaluates information security controls applied to
telecommunications organizations against ISO/IEC 27011:2016. It is the reference input for any
KB card that touches fixed, mobile, satellite, or converged carrier networks and the
operational support systems that run them. It binds the knowledge base to a recognised
profile of ISO/IEC 27001:2022 plus ISO/IEC 27002:2022 controls, supplemented by the
telecommunications-specific provisions that ISO/IEC 27011:2016 publishes.

## 2. Normative references

The following documents are referred to in the text in such a way that some or all of their
content constitutes requirements of this card. For dated references, only the edition cited
applies. For undated references, the latest edition applies.

- ISO/IEC 27011:2016, Information technology — Security techniques — Code of practice for
  Information security controls for telecommunications organizations based on ISO/IEC 27002.
- ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection —
  Information security management systems — Requirements.
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information
  security controls.
- ITU-T X.1051 (2008, revised), Information security management guideline for
  telecommunications organizations (the source from which ISO/IEC 27011:2016 is derived).

## 3. Terms and definitions

For the purposes of this card, the following terms apply.

- 3.1 telecommunications organization — public or private operator of fixed, mobile, satellite,
  cable, or converged networks that provides voice, data, or media transport services.
- 3.2 network operator obligations — legal, regulatory, or contractual duties imposed by
  national authorities, the ITU, or industry schemes that bind a telecommunications
  organization.
- 3.3 ISMS profile — the set of ISO/IEC 27002 controls plus the telecommunications-specific
  overlays defined in ISO/IEC 27011:2016 that an organization selects in its Statement of
  Applicability.
- 3.4 customer-premises equipment (CPE) — terminal apparatus installed at the subscriber site
  that falls within the security responsibility boundary defined by ISO/IEC 27011:2016.

## 4. Telecom-specific ISMS controls

ISO/IEC 27011:2016 organizes its sector guidance along the same Annex A themes as ISO/IEC
27002:2022 (A.5 Organizational, A.6 People, A.7 Physical, A.8 Technological) and adds explicit
telecommunications overlays. The KB uses the following overlay topics.

- A.5.x overlays — enhanced governance for lawful interception interfaces, regulator-facing
  reporting, and shared-infrastructure routing.
- A.6.x overlays — screening and continuous vetting of staff with access to signalling systems,
  lawful-intercept functions, and key custodians.
- A.7.x overlays — physical and environmental controls for central offices, points of presence,
  undersea cable landing stations, and mobile switching centres.
- A.8.x overlays — controls for signalling (SS7, Diameter), IMS core, RAN, and OSS/BSS
  platforms, including lawful-intercept fault tolerance.

## 5. Supplement to ISO/IEC 27002

ISO/IEC 27011:2016 does not replace ISO/IEC 27002:2022 — it supplements it. Each ISO/IEC
27011:2016 clause cites the underlying ISO/IEC 27002 control, then adds the
telecommunications-specific implementation guidance or additional objective. Author cards
must trace every telecom-specific overlay back to the base ISO/IEC 27002:2022 control it
extends; the KB rejects overlays that are not cited in ISO/IEC 27011:2016 or ITU-T X.1051.

## 6. Network operator obligations

KB cards that describe a carrier service or a service offered over a carrier must document
the obligations assumed by the operator and the obligations retained by the customer.

- 6.1 National regulatory duties — lawful interception readiness, emergency services
  access, number-portability integrity, retention of call-detail records.
- 6.2 Industry duties — SS7 and Diameter signalling hardening, SIM provisioning integrity,
  roaming-partner vetting, and abuse-handling time windows.
- 6.3 Customer duties — CPE hardening, anti-spoofing publication (RFC 7343, BCP 38), and
  cooperation with the operator on fault triage.
- 6.4 Boundary clarity — explicit demarcation between operator security zones and customer
  responsibility zones, recorded in the reference architecture card.

## 7. Audit and assurance

Audits against ISO/IEC 27011:2016 are conducted as ISO/IEC 27001:2022 audits with a
telecommunications-scope addendum. The KB requires the following assurance artefacts.

- 7.1 A Statement of Applicability that lists each ISO/IEC 27002:2022 control selected and
  references the ISO/IEC 27011:2016 overlay text for each selected control.
- 7.2 Evidence of conformity to the ISO/IEC 27011:2016 supplements, not only the base control.
- 7.3 Audit cycle aligned to the operator's risk environment; the KB default review cadence
  for this card is 180 days.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
