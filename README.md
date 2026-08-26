<p align="center">
  <img src="./assets/1080x360.jpg" width="1080" alt="ORCHORDS — BUILD DIFFERENT.">
</p>

# ORCHORDS Public Documentation

[![Documentation quality](https://github.com/ORCHORDS/docs/actions/workflows/docs-quality.yml/badge.svg)](https://github.com/ORCHORDS/docs/actions/workflows/docs-quality.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

**Independent software studio founded in 2025.**

This repository publishes ORCHORDS company-wide documentation — over 1,700
controlled documents across 42 categories covering governance, security,
privacy, engineering, compliance, standards, and related policy areas. It is
useful for customers and partners conducting due diligence, engineers and
researchers comparing public policy practices, and anyone evaluating how a
small independent studio documents security and governance expectations.

## Start here

| If you need… | Start with |
| --- | --- |
| Security posture and reporting | [Security Policy](./categories/security/SECURITY_POLICY.md) |
| Engineering expectations | [Engineering Standards](./categories/engineering/ENGINEERING_STANDARDS.md) |
| How decisions and policies are structured | [Governance](./categories/governance/GOVERNANCE.md) · [Policy Hierarchy](./categories/governance/POLICY_HIERARCHY.md) |
| Customer/due-diligence material | [Customer Trust](./categories/customer-trust/README.md) — assurance package, shared-responsibility guidance |
| Which standards and versions are referenced | [Standards Register](./categories/standards/REFERENCES.md) |
| How documents are controlled and reviewed | [Document Control](./categories/governance/DOCUMENT_CONTROL.md) |

## How to read this repository

These documents describe **public policy expectations, not certifications or
verified implementations**. Nothing here is evidence that a control is
certified, audited, or implemented.

Every controlled document carries YAML front matter:

- `status` — `approved`, `review`, `draft`, or `deprecated`;
- `last-reviewed` / `next-review` / `review-cycle` — when it was last checked
  and when it is due again (typically 90 days).

Normative meaning follows [RFC-style normative language](./categories/standards/NORMATIVE_LANGUAGE.md)
and restricted assurance terms are governed by
[Public Assurance Terminology](./categories/standards/PUBLIC_ASSURANCE_TERMINOLOGY.md).

## Evidence and sources

Factual and standards-based content follows the
[Citation Source Policy](./categories/standards/CITATION_SOURCE_POLICY.md):
primary authoritative sources are preferred, secondary sources are
non-normative, drafts are labeled as drafts ([Framework Status
Policy](./categories/standards/FRAMEWORK_STATUS_POLICY.md)), and the
versioned [Standards Register](./categories/standards/REFERENCES.md) records
which edition each claim tracks.

## Documentation map

All content lives under [`categories/`](./categories/README.md) (42
categories, ~1,724 documents):

- **Trust & assurance** — security, privacy, compliance, customer-trust, accessibility
- **Governance & corporate** — governance, legal, ethics, finance, tax, treasury, internal-audit, records
- **Building & operating** — engineering, data, AI, product, operations, resilience, quality, project-delivery, releases
- **Organization** — people, workplace-safety, human-rights, communications, marketing, knowledge, strategy, research
- **Commercial & partners** — commercial, partnerships, procurement, third-party, customer-success, support, corporate-development
- **Working artifacts** — standards, SOPs, templates

Tip: for a repository this size, use GitHub's file finder (`t`) or code
search to jump directly to a document.

## Public-repository boundary

This repository must not expose product-specific implementation details, deployment topology, credentials, private endpoints, customer information, internal identifiers, banking details, tax identifiers or filings, treasury balances, facility-security details, personal medical information, worker grievance identities, active transaction details, or unannounced work.

Public documentation may describe principles, responsibilities, controls, decision criteria, and repeatable procedures. It must not create false assurance or present planned controls as implemented.

## Documentation workflow

Authorized routine documentation maintenance is performed directly on **`main`**. Feature branches and pull requests are not required for routine documentation growth or maintenance; external contributions and larger changes use pull requests — see [CONTRIBUTING.md](./CONTRIBUTING.md).

Changes must be evidence-based, duplicate-checked, narrowly scoped, and reviewed for public-safety and sensitive-data boundaries before commit. Use current primary or authoritative sources for standards, regulatory, security, and vendor claims.

See [CONTRIBUTING.md](./CONTRIBUTING.md), [SECURITY.md](./SECURITY.md), and [SUPPORT.md](./SUPPORT.md).

## Citing this documentation

Content is MIT-licensed (see [LICENSE](./LICENSE)). When citing a document,
reference its URL together with the document's `last-reviewed` date. Because
`main` changes frequently, pin durable citations to a specific commit SHA
until tagged releases exist.

## Brand

**ORCHORDS — BUILD DIFFERENT.**

## License

See [LICENSE](./LICENSE).
