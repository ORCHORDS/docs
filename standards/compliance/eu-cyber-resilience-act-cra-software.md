# EU Cyber Resilience Act (CRA) — Software Product Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your company sells a connected IoT device with a companion mobile
app in the EU market. In September 2026, ENISA contacts you about
a vulnerability report — you have 24 hours to submit an early warning
but your team has no coordinated vulnerability disclosure process,
no SBOM to identify affected components, and no established contact
point for security notifications. By December 2027, your product
needs CE marking for cybersecurity, but you have not started the
conformity assessment process.

## Context

The EU Cyber Resilience Act (Regulation (EU) 2024/2847) establishes
mandatory cybersecurity requirements for products with digital
elements placed on the EU market — both hardware and software. It
entered into force on 10 December 2024 with a phased timeline:
conformity assessment body notifications apply from June 2026,
vulnerability reporting obligations from September 2026, and full
compliance (essential cybersecurity requirements, CE marking,
conformity assessment) from December 2027. Penalties reach €15
million or 2.5% of global annual turnover. The CRA creates a
distinct "open-source software steward" category with lighter
obligations for non-commercial open-source development.

## Timeline

```
Date                   Obligation
──────────────────────────────────────────────────────────────
10 Dec 2024            CRA entered into force
11 Jun 2026            Conformity assessment body notifications
11 Sep 2026            Vulnerability/incident reporting begins
11 Dec 2027            Full compliance mandatory
                       (CE marking, essential requirements)
```

## Vulnerability reporting obligations

```
Starting 11 September 2026:

  24-hour early warning:
    → Upon becoming aware of an actively exploited vulnerability
    → Or a severe security incident
    → Report to ENISA / national CSIRT

  72-hour follow-up notification:
    → More detail on the vulnerability
    → Corrective and mitigating measures taken or planned

  14-day final report:
    → After a fix is made available
    → Complete analysis and remediation details

  Ongoing obligations:
    → Maintain coordinated vulnerability disclosure process
    → Publish a security contact for the product
    → Provide security updates for product's expected lifetime
```

## Product classification and CE marking

```
Category              Assessment            Examples
──────────────────────────────────────────────────────────────
Default products      Self-assessment       Most consumer software,
                      (internal control,    general IoT devices
                      no notified body)

Important — Class I   Harmonised standards  Password managers,
(Annex III)           conformity OR         firewalls, VPNs,
                      notified body         identity management

Important — Class II  Notified body         Operating systems,
(Annex III)           involvement           industrial control,
                      required              hypervisors

Critical              Mandatory third-      Hardware security
(Annex IV)            party certification   modules, smart-meter
                                            gateways

Passing conformity assessment yields:
  → EU Declaration of Conformity
  → CE marking affixed to product
  → Technical documentation maintained
```

## SBOM requirement

```
CRA mandates machine-readable Software Bill of Materials
covering top-level dependencies.

  Formally required: December 2027
  Practically needed: September 2026

  Why earlier: accurate component inventory is a prerequisite
  for meeting the 24-hour reporting deadline. You cannot
  disclose exploitation of a component you cannot identify.

  Formats:
    → CycloneDX (security-audit focused)
    → SPDX (license-compliance focused)

  Integration:
    → Generate in CI/CD pipeline automatically
    → Attach to release artifacts
    → Version and maintain across product lifecycle
    → Update when dependencies change
```

## Open-source carve-outs

```
Non-commercial open-source: generally OUT of scope.

  "Open-source software steward" (Article 24):
    → Foundations, consortia, or firms providing sustained
      systematic support for OSS used commercially by others
    → Lighter regime than full CRA compliance
    → Must maintain cybersecurity policy for supported projects
    → Must cooperate with market surveillance authorities
    → EXEMPT from CRA fines

  What is NOT exempt:
    → Commercial software using open-source components
      (the commercial product is in scope, not the OSS itself)
    → OSS distributed as part of a commercial product
    → Companies monetizing open-source (SaaS, support contracts)
```

## Engineering controls needed

```
Controls to implement now (before September 2026):

  1. Automated SBOM generation in CI/CD
     → CycloneDX or SPDX format
     → Generated on every release build

  2. Vulnerability monitoring pipeline
     → Capable of 24h/72h/14-day disclosure timelines
     → Automated alerts from NVD, OSV, GitHub Advisory
     → Runbook for each reporting deadline

  3. Coordinated vulnerability disclosure (CVD) policy
     → Published security contact (security.txt)
     → Responsible disclosure process documented
     → Bug bounty or vulnerability intake channel

  4. Secure-by-design engineering practices
     → Documented risk assessments per product
     → Security requirements in design phase
     → Threat modeling for new features

  5. Security update policy
     → Defined support lifetime per product
     → End-of-support communication to users
     → Automated update delivery mechanism
```

## Anti-patterns

- **Treating CRA as a December 2027 problem** — vulnerability
  reporting obligations start September 2026. Without SBOM
  generation and a disclosure process by then, the 24-hour
  reporting window is unmeetable.
- **Generating SBOMs only at release** — dependencies change
  between releases. Generate SBOMs in CI/CD on every build and
  continuously monitor against vulnerability databases.
- **Assuming open-source exemption applies to commercial use** —
  the exemption covers non-commercial OSS development, not
  commercial products that incorporate open-source components.
- **Self-assessing Class I/II products** — Important and Critical
  products require harmonised standards conformity or notified-body
  involvement. Self-assessment alone is insufficient for these
  categories.

## Gotchas

- **"Products with digital elements" is broad** — includes
  standalone software, connected devices, and remote data-
  processing solutions tied to a product. Cloud-only SaaS is
  generally excluded, but companion apps and firmware are in scope.
- **SBOM covers top-level dependencies** — the CRA specifies
  top-level, not full transitive dependency trees. However,
  vulnerability monitoring needs transitive visibility to be
  effective for the 24-hour reporting obligation.
- **Penalties are tiered** — €15M / 2.5% for essential
  cybersecurity requirement breaches; lower caps for other
  infringements (e.g., failure to cooperate with authorities).
- **CE marking is per-product** — each distinct product with
  digital elements needs its own conformity assessment and
  declaration, not a company-wide certification.

## Verification

- SBOM generation automated in CI/CD pipeline.
- Vulnerability monitoring configured with 24h/72h alert thresholds.
- Coordinated vulnerability disclosure policy published.
- Security contact (security.txt) deployed and maintained.
- Product classification determined (Default, Class I/II, Critical).
- Conformity assessment path identified for each product.
- Security update policy and end-of-support timeline defined.

## Related

- `documentation/categories/compliance/dora-engineering-controls-financial.md`
- `documentation/categories/security/supply-chain-slsa-sigstore-verification.md`
- `documentation/categories/issues/eu-ai-act-risk-classification-compliance.md`

## Source URLs (verified 2026-08-16)

- The Cyber Resilience Act — Full Regulation Text — https://www.cyberresilienceact.eu/the-cyber-resilience-act/
- European Commission CRA Summary — https://digital-strategy.ec.europa.eu/en/policies/cra-summary
- CRA Scope, Classes, and Deadlines Explained — https://www.cyberresilienceact.eu/explained.html
- EU Cyber Resilience Act Compliance Guide — https://www.mend.io/blog/eu-cyber-resilience-act-compliance-guide/
