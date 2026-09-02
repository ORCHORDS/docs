# Security Champions Program Governance

## Purpose

Govern the operation of a security champions program so that security capacity scales through embedded, trained advocates in delivery teams: champions selected deliberately, equipped with training and a defined role scope, sustained through community cadence, and measured by outcomes rather than title counts.

## Scope

Applies to the studio's security champions program across delivery teams. Covers champion selection, role definition, training, community operation, and program measurement. Does not cover the security team's own staffing or application security review processes.

## Workflow

1. Define the champion role scope before recruiting: champions extend security capacity — threat-model facilitation, security review preparation, secure-coding practice reinforcement, vulnerability triage escalation — not a shadow security team with review authority.
2. Select champions per team with manager commitment: each delivery team names a champion with allocation (a fraction of their time, agreed and visible) — champions without allocated time decay into mailing-list members.
3. Train to a defined curriculum: threat modelling basics, the studio's secure SDN practices, vulnerability handling, and escalation paths; certification of completion recorded.
4. Operate the community on cadence: regular champion syncs sharing findings, patterns, and new threats; a channel for rapid security questions; the community is the program's multiplier.
5. Route work through champions first where appropriate: security reviews prepared by champions arrive faster and educate the team; the security team handles what champions cannot.
6. Measure program outcomes: review readiness, findings caught pre-review, security-fix latency in championed teams versus baseline — outcome metrics, not headcount.
7. Rotate and refresh deliberately: champion turnover is natural; succession keeps coverage continuous, and refresher training follows the security landscape.

## Controls and evidence

- Role scope definition with explicit boundaries.
- Champion roster with teams, allocation, and training completion.
- Community cadence records (syncs, channel activity).
- Escalation records demonstrating champion-to-security handoffs.
- Outcome metrics comparing championed teams against baseline.

## Validation

- Confirm each delivery team has a champion with recorded allocation.
- Sample five escalations: confirm the champion path added value (earlier detection, prepared context).
- Confirm outcome metrics are tracked and reviewed at program cadence.

## Failure correction

- **Champion without allocated time** → renegotiate the allocation with management or reselect; unallocated champions are nominal.
- **Community cadence lapsed** → reinstate with a named driver; lapsed communities do not restart themselves.
- **Metrics stuck at headcount** → implement outcome measurement; headcount-only measurement hides program decay.

## Limitations

- Champions extend but do not replace security expertise; high-stakes reviews remain the security team's.
- Program value compounds slowly; leadership patience through the first cycles is a success factor.
- Champions rotate roles; institutional memory lives in the program's records, not individuals.

## Scope note

This article is part of the security leaf. Cross-reference: `NIST_SSDF_SP_800_218A_TAGGING_GOVERNANCE.md`, `GENAI_SSDF_COMMUNITY_PROFILE.md` (engineering leaf), and `IEEE_1028_2008_REVIEW_TYPES_SELECTION_GOVERNANCE.md` (engineering leaf).

## Canonical sources

- OWASP — Security Champions Guide: https://owasp.org/www-project-security-champions-guidebook/
- OWASP SAMM v2 — Security Champions practice area: https://owasp.org/www-project-samm/
- NIST SP 800-218 — Secure Software Development Framework (SSDF): https://csrc.nist.gov/pubs/sp/800/218/final
- BSIMM — Building Security In Maturity Model (champions observations): https://www.bsimm.com/
- ISO/IEC 27002:2022 — Information security controls (awareness and training): https://www.iso.org/obp/ui/#iso:std:iso-iec:27002:ed-4
