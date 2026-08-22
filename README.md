# ORCHORDS Public Documentation

This repository contains ORCHORDS company-wide public governance, engineering,
security, operations, product, release, and standard operating procedure (SOP)
documentation.

It is intentionally **not** a system inventory or architecture repository.
Product-specific implementation details, deployment topology, credentials,
private endpoints, customer information, internal identifiers, and unannounced
work do not belong here.

## Start here

| Area | Purpose |
|---|---|
| [Governance](./GOVERNANCE.md) | Decision rights, accountability, policy hierarchy |
| [Document control](./DOCUMENT_CONTROL.md) | How public documentation is approved, reviewed, and retired |
| [Security](./SECURITY_POLICY.md) | Company-wide security principles and control expectations |
| [Engineering](./engineering/ENGINEERING_STANDARDS.md) | Engineering quality and secure-development expectations |
| [Operations](./operations/OPERATIONS_MANUAL.md) | Operational governance and service-management expectations |
| [Planning](./product/PLANNING_PRIORITIZATION.md) | Evidence-based prioritization and planning |
| [Releases](./releases/RELEASE_MANAGEMENT.md) | Release governance and readiness |
| [SOPs](./sop/README.md) | Repeatable operational procedures |
| [Standards register](./REFERENCES.md) | External standards and guidance used by this repository |

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
5. Merge only when the content is accurate, public-safe, and supported by
   evidence where it makes factual claims.

See [CONTRIBUTING.md](./CONTRIBUTING.md) and
[DOCUMENT_CONTROL.md](./DOCUMENT_CONTROL.md).

## Security reports

Do not report security-sensitive findings in a public issue. Follow
[SECURITY.md](./SECURITY.md).

## License

See [LICENSE](./LICENSE).
