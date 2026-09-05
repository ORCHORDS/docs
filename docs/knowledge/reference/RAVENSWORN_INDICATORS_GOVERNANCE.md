---
title: Cyber Threat Intelligence and STIX/TAXII Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OASIS STIX 2.1 (June 2021); OASIS TAXII 2.1 (June 2021); MITRE ATT&CK (https://attack.mitre.org/); CVE/NVD (https://nvd.nist.gov/); CWE (https://cwe.mitre.org/); https://oasis-open.github.io/cti-documentation/
---

# Cyber Threat Intelligence and STIX/TAXII Version Governance

## Scope

This card governs how `orchords-docs` evaluates Cyber Threat Intelligence (CTI) feeds and the STIX/TAXII standard that transports them. It is the reference input for any KB card that describes threat intel ingestion, sharing, or correlation.

## Why this card exists

STIX is the OASIS standard for structured cyber-threat intelligence. TAXII is the OASIS standard for transport. ATT&CK is MITRE's curated knowledge base of adversary tactics and techniques. A KB card that recommends a CTI pipeline without binding to these standards produces a feed-handling configuration that cannot interop with the broader intel ecosystem.

## Document set

- **STIX 2.1** — OASIS Standard (June 2021) — Structured Threat Information Expression.
- **TAXII 2.1** — OASIS Standard (June 2021) — Trusted Automated Exchange of Intelligence Information.
- **MITRE ATT&CK** — Matrix of adversary tactics, techniques, and procedures.
- **CWE** — Common Weakness Enumeration.
- **CVE / NVD** — Common Vulnerabilities and Exposures / National Vulnerability Database.
- **CVSS** — Common Vulnerability Scoring System (v4.0 and v3.1).

References: `https://oasis-open.github.io/cti-documentation/`, `https://attack.mitre.org/`.

## STIX 2.1 object types

STIX 2.1 defines 18 SDO (STIX Domain Object) types and 4 SRO (STIX Relationship Object) types. The most-used for KB cards:

| SDO | Purpose |
|---|---|
| `indicator` | pattern to detect (e.g., hash, IP, domain) |
| `malware` | malware instance or family |
| `threat-actor` | adversary entity |
| `attack-pattern` | technique (maps to ATT&CK) |
| `campaign` | grouping of activity over time |
| `intrusion-set` | collection of related activity |
| `tool` | software used by adversary |
| `vulnerability` | CVE reference |
| `identity` | organization or person |
| `infrastructure` | network resource used by adversary |
| `course-of-action` | mitigation or response |
| `note` | free-form annotation |
| `observed-data` | raw observed telemetry |

| SRO | Purpose |
|---|---|
| `relationship` | connects two SDOs (e.g., `indicates`, `uses`, `targets`) |
| `sighting` | SDO observed at a specific time |
| `marking-definition` | data classification / sharing rules |
| `language-content` | localized content |

References: `https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html`.

## TAXII 2.1

TAXII 2.1 is the transport protocol for STIX 2.1:

- Uses HTTP/1.1 or HTTP/2.
- TLS 1.2+ mandatory.
- JSON serialization.
- Authentication: OAuth 2.0 / API token / client cert.
- Discovery endpoint: `/taxii2/`.
- API root: `/taxii2/<name>/`.
- Collections: `/taxii2/<name>/collections/<id>/`.
- Manifest: `GET /taxii2/<name>/collections/<id>/manifest/`.
- Objects: `GET /taxii2/<name>/collections/<id>/objects/`.

References: `https://docs.oasis-open.org/cti/taxii/v2.1/taxii-v2.1.html`.

## MITRE ATT&CK matrices

| Matrix | Domain |
|---|---|
| ATT&CK Enterprise | Windows, macOS, Linux, Cloud (Azure AD, Office 365, GCP, AWS), Containers, Network |
| ATT&CK Mobile | Android, iOS |
| ATT&CK ICS | Industrial Control Systems |

ATT&CK Enterprise tactics (14):

1. Reconnaissance
2. Resource Development
3. Initial Access
4. Execution
5. Persistence
6. Privilege Escalation
7. Defense Evasion
8. Credential Access
9. Discovery
10. Lateral Movement
11. Collection
12. Command and Control
13. Exfiltration
14. Impact

Each tactic contains techniques; each technique contains sub-techniques; each technique has a unique ID (e.g., `T1078`, `T1059.001`).

References: `https://attack.mitre.org/tactics/`.

## CVE / NVD / CVSS

| Resource | Purpose |
|---|---|
| CVE | unique identifier for a vulnerability (e.g., CVE-2024-12345) |
| NVD | NIST-maintained database of CVEs with CVSS scores |
| CVSS v3.1 | base scoring (legacy) |
| CVSS v4.0 | base scoring + threat + environmental + supplemental metrics |
| CWE | weakness type |

The KB binds CVE references to the corresponding CWE for analysis and to ATT&CK techniques for adversary-model alignment.

## Indicator patterns

STIX patterns support:

- File hashes: `file:hashes.'SHA-256' = '...'`
- IP addresses: `ipv4-addr:value = '...'` or `ipv6-addr:value = '...'`
- Domain: `domain-name:value = '...'`
- URL: `url:value = '...'`
- Email: `email-addr:value = '...'`
- Windows registry: `windows-registry-key:key = '...'`
- AND / OR / parentheses: standard boolean composition

## Mandatory pre-flight (before adopting a new CTI feed)

1. Feed uses STIX 2.1 (older STIX 1.x feeds must be translated via STIX 2.1 forwarding).
2. Transport is TAXII 2.1 with TLS 1.2+ and OAuth 2.0 authentication.
3. Sharing marking (TLP:RED/AMBER/GREEN/WHITE) is documented.
4. Feed cadence is published.
5. Feed producer reputation is documented.
6. Feed health is monitored.

## Observability

- Indicator count (gauge, by TLP).
- Feed freshness (per source).
- Indicator-to-event correlation rate.
- False-positive rate (per indicator class).

## Sources

- OASIS CTI Documentation: `https://oasis-open.github.io/cti-documentation/`
- STIX 2.1 Spec: `https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html`
- TAXII 2.1 Spec: `https://docs.oasis-open.org/cti/taxii/v2.1/taxii-v2.1.html`
- MITRE ATT&CK: `https://attack.mitre.org/`
- CVE / NVD: `https://nvd.nist.gov/`
- CWE: `https://cwe.mitre.org/`
- FIRST CVSS 4.0: `https://www.first.org/cvss/v4.0/specification-document`
