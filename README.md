# ORCHORDS Public Documentation

This repository is the public company-wide knowledge base for ORCHORDS
governance, security, privacy, data, AI, engineering, operations, supplier
risk, releases, accessibility, standards, templates, and standard operating
procedures (SOPs).

It is intentionally **not** a system inventory or architecture repository.
Product-specific implementation details, deployment topology, credentials,
private endpoints, customer information, internal identifiers, and unannounced
work do not belong here.

## Categories

| Category | Purpose |
|---|---|
| [Governance](./governance/README.md) | Decision rights, enterprise risk, document control, assurance, retention |
| [Security](./security/README.md) | Security principles, disclosure, cryptography and control expectations |
| [Privacy](./privacy/README.md) | Privacy governance, privacy-by-design and rights principles |
| [Data](./data/README.md) | Classification, handling and lifecycle governance |
| [AI](./ai/README.md) | Responsible AI governance, acceptable use and risk assessment |
| [Engineering](./engineering/README.md) | Secure development, source control, CI/CD, testing and dependencies |
| [Operations](./operations/README.md) | Incidents, access, monitoring, continuity, change and onboarding |
| [Third-party](./third-party/README.md) | Supplier due diligence, third-party risk and security expectations |
| [Releases](./releases/README.md) | Release governance, signing and versioning |
| [Product](./product/README.md) | Company-wide planning and prioritization principles |
| [Accessibility](./accessibility/README.md) | Accessibility policy and verification expectations |
| [SOPs](./sop/README.md) | Repeatable procedures that implement policy |
| [Standards](./standards/README.md) | Standards register, documentation style and control mapping |
| [Templates](./templates/README.md) | Public-safe reusable records for governed processes |

## Publication boundary

Public documentation may describe **principles, responsibilities, controls,
decision criteria, and repeatable procedures**. It must not expose operational
secrets or create false assurance.

Statements about controls use these evidence levels:

- **Required** — the policy expectation.
- **Implemented** — supported by current evidence.
- **Planned** — approved work that is not yet implemented.
- **Not applicable** — formally assessed as outside scope.

A document must never present a planned control as implemented or imply a
certification, audit result, service capability, or security guarantee without
current evidence.

## Contribution model

Documentation is managed as code:

1. Make changes in a branch.
2. Open a pull request.
3. Pass automated documentation checks.
4. Obtain review from the responsible owner.
5. Merge only when content is accurate, public-safe, and evidence-based.

See [CONTRIBUTING.md](./CONTRIBUTING.md) and
[Document Control](./governance/DOCUMENT_CONTROL.md).

## Security reports

Do not report security-sensitive findings in a public issue. Follow
[SECURITY.md](./SECURITY.md).

## License

See [LICENSE](./LICENSE).
