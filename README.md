# ORCHORDS Public Documentation

This repository is the public company-wide knowledge base for ORCHORDS governance, security, privacy, data, AI, engineering, operations, resilience, people, supplier risk, compliance/assurance, legal governance, physical security, financial controls, releases, product, accessibility, standards, templates, and standard operating procedures (SOPs).

It is intentionally **not** a system inventory or architecture repository. Product-specific implementation details, deployment topology, credentials, private endpoints, customer information, internal identifiers, banking details, facility security details, and unannounced work do not belong here.

## Categories

| Category | Purpose |
|---|---|
| [Governance](./governance/README.md) | Decision rights, enterprise risk, document control, assurance, retention |
| [Security](./security/README.md) | Security architecture, identity, endpoint/network, threats, secrets, testing and disclosure |
| [Privacy](./privacy/README.md) | Privacy governance, assessments, rights and incident handling |
| [Data](./data/README.md) | Inventory, classification, lineage, lifecycle, retention, sharing and disposal |
| [AI](./ai/README.md) | Responsible AI governance, inventory, evaluation, security and agent safeguards |
| [Engineering](./engineering/README.md) | Secure design, coding, review, source control, CI/CD, testing and dependencies |
| [Operations](./operations/README.md) | Service ownership, access, change, incidents, alerts, runbooks, assets and reliability |
| [Resilience](./resilience/README.md) | Business impact, recovery, dependency resilience, crisis communications and exercises |
| [People](./people/README.md) | Acceptable use, personnel security, awareness, remote work and reporting culture |
| [Third-party](./third-party/README.md) | Supplier onboarding, due diligence, contracts, dependency chains, monitoring and exit |
| [Compliance](./compliance/README.md) | Obligations, evidence, control testing, remediation, audit readiness and claims |
| [Legal](./legal/README.md) | Legal requests, holds, contracts and intellectual-property governance |
| [Physical security](./physical-security/README.md) | Physical access, visitors, workspace protection and lost assets |
| [Financial controls](./finance/README.md) | Financial approval, payment-change verification, record integrity and fraud resistance |
| [Releases](./releases/README.md) | Release governance, evidence, signing, integrity, versioning and rollback |
| [Product](./product/README.md) | Planning, user safety, experimentation, launch and deprecation governance |
| [Accessibility](./accessibility/README.md) | Accessibility policy, testing, issue management and content guidance |
| [SOPs](./sop/README.md) | Repeatable procedures that implement policy |
| [Standards](./standards/README.md) | Standards register, documentation style and control mapping |
| [Templates](./templates/README.md) | Public-safe reusable records for governed processes |

## Publication boundary

Public documentation may describe **principles, responsibilities, controls, decision criteria, and repeatable procedures**. It must not expose operational secrets or create false assurance.

Statements about controls use these evidence levels:

- **Required** — the policy expectation.
- **Implemented** — supported by current evidence.
- **Planned** — approved work that is not yet implemented.
- **Not applicable** — formally assessed as outside scope.

A document must never present a planned control as implemented or imply certification, audit results, service capability, or security guarantees without current evidence.

## Contribution model

Documentation is managed as code: branch, review, automated checks, accountable ownership, and evidence-based merge.

See [CONTRIBUTING.md](./CONTRIBUTING.md) and [Document Control](./governance/DOCUMENT_CONTROL.md).

## Security reports

Do not report security-sensitive findings in a public issue. Follow [SECURITY.md](./SECURITY.md).

## License

See [LICENSE](./LICENSE).
