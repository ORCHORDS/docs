# ORCHORDS Public Documentation

This repository is the public company-wide knowledge base for ORCHORDS governance, security, privacy, data, AI, engineering, operations, resilience, people, supplier risk, compliance/assurance, legal governance, physical security, financial controls, ethics/integrity, public communications, marketing, partnerships, procurement, quality management, internal audit, customer/support governance, commercial governance, project/delivery governance, knowledge management, strategy, research, customer success, releases, product, accessibility, standards, templates, and standard operating procedures (SOPs).

It is intentionally **not** a system inventory or architecture repository. Product-specific implementation details, deployment topology, credentials, private endpoints, customer information, internal identifiers, banking details, facility security details, and unannounced work do not belong here.

## Categories

| Category | Purpose |
|---|---|
| [Governance](./governance/README.md) | Decision rights, enterprise risk, document control, assurance, retention |
| [Security](./security/README.md) | Architecture principles, identity, endpoints/networks, threats, secrets, testing and disclosure |
| [Privacy](./privacy/README.md) | Privacy governance, assessments, rights and incident handling |
| [Data](./data/README.md) | Inventory, classification, lineage, lifecycle, retention, sharing and disposal |
| [AI](./ai/README.md) | Responsible AI governance, inventory, evaluation, security and agent safeguards |
| [Engineering](./engineering/README.md) | Secure design, coding, review, source control, CI/CD, testing and dependencies |
| [Operations](./operations/README.md) | Service ownership, access, change, incidents, alerts, runbooks, assets and reliability |
| [Resilience](./resilience/README.md) | Business impact, recovery, dependency resilience, crisis communications and exercises |
| [People](./people/README.md) | Acceptable use, personnel security, awareness, remote work and reporting culture |
| [Third-party](./third-party/README.md) | Supplier onboarding, due diligence, dependency chains, monitoring and exit |
| [Compliance](./compliance/README.md) | Obligations, evidence, control testing, remediation, audit readiness and claims |
| [Legal](./legal/README.md) | Legal requests, holds, contracts and intellectual-property governance |
| [Physical security](./physical-security/README.md) | Physical access, visitors, workspace protection and lost assets |
| [Financial controls](./finance/README.md) | Financial approval, payment-change verification, record integrity and fraud resistance |
| [Ethics and integrity](./ethics/README.md) | Conflicts, anti-bribery, gifts/hospitality, speak-up and fair dealing |
| [Communications](./communications/README.md) | Public statements, claims, social accounts, change/incident communications and disclosure boundaries |
| [Marketing](./marketing/README.md) | Campaigns, claims, audiences, consent, brand, channels, measurement and marketing partners |
| [Partnerships](./partnerships/README.md) | Strategic partner selection, joint objectives, responsibilities, commitments, risk, performance and exit |
| [Procurement](./procurement/README.md) | Purchasing, software/service acquisition, approvals, renewals and emergency procurement |
| [Quality](./quality/README.md) | Quality objectives, nonconformities, CAPA, root cause and measurement integrity |
| [Internal audit](./internal-audit/README.md) | Independent audit planning, evidence, objectivity and finding follow-up |
| [Support](./support/README.md) | Support identity verification, sensitive-data handling, escalation and complaints |
| [Commercial](./commercial/README.md) | Customer commitments, proposals, pilots, assurance responses and delivery handover |
| [Project delivery](./project-delivery/README.md) | Project initiation, governance, stage gates, risk/change, handover and closure |
| [Knowledge](./knowledge/README.md) | Critical knowledge, decision records, knowledge transfer and content lifecycle |
| [Strategy](./strategy/README.md) | Objectives, assumptions, scenarios, investment choices and strategic review |
| [Research](./research/README.md) | Research planning, participant consent, recruitment, data handling and reporting integrity |
| [Customer success](./customer-success/README.md) | Onboarding, adoption, health, success planning and renewal risk |
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
