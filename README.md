<p align="center">
  <img src="./assets/1080x360.jpg" width="1080" alt="ORCHORDS — BUILD DIFFERENT.">
</p>

# ORCHORDS Public Documentation

[![Documentation quality](https://github.com/ORCHORDS/docs/actions/workflows/docs-quality.yml/badge.svg)](https://github.com/ORCHORDS/docs/actions/workflows/docs-quality.yml)
[![CodeQL workflow status](https://github.com/ORCHORDS/docs/actions/workflows/codeql.yml/badge.svg)](https://github.com/ORCHORDS/docs/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/ORCHORDS/docs/badge)](https://securityscorecards.dev/viewer/?uri=github.com/ORCHORDS/docs)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14247/badge)](https://www.bestpractices.dev/projects/14247)
[![Zenodo DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22109314.svg)](https://doi.org/10.5281/zenodo.22109314)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> ⭐ If you like this documentation or find it useful, please consider starring this repository. It helps more people discover the project.

> **Interested in sponsoring ORCHORDS?** Sponsorships start at **US$1,000**. Depending on the sponsorship level, sponsors may receive public recognition, logo and website placement, sponsor updates and early previews, roadmap-feedback briefings, priority issue triage, and engineering or integration discussions. Sponsorship does not buy control of the roadmap or guarantee feature implementation. Contact **[crm@orchords.com](mailto:crm@orchords.com)**.

**Independent software studio founded in 2025.**

This repository publishes ORCHORDS company-wide documentation — currently
9,966 Markdown files covering governance, security, privacy, engineering,
compliance, standards, reusable technical knowledge, and related policy areas.
It is useful for customers and partners conducting due diligence, engineers and
researchers comparing public policy practices, and anyone evaluating how a
small independent studio documents security and governance expectations.

## Start here

| If you need… | Start with |
| --- | --- |
| Security posture and reporting | [Security Policy](docs/policies/security/SECURITY_POLICY.md) |
| Engineering expectations | [Engineering Standards](docs/policies/engineering/ENGINEERING_STANDARDS.md) |
| How decisions and policies are structured | [Governance](docs/policies/governance/GOVERNANCE.md) · [Policy Hierarchy](docs/policies/governance/POLICY_HIERARCHY.md) |
| Customer/due-diligence material | [Customer Trust](docs/policies/customer-trust/README.md) — assurance package, shared-responsibility guidance |
| Which standards and versions are referenced | [Standards Register](docs/policies/standards/REFERENCES.md) |
| How documents are controlled and reviewed | [Document Control](docs/policies/governance/DOCUMENT_CONTROL.md) |

## How to read this repository

These documents describe **public policy expectations, not certifications or
verified implementations**. Nothing here is evidence that a control is
certified, audited, or implemented.

Every controlled document carries YAML front matter:

- `status` — `approved`, `review`, `draft`, or `deprecated`;
- `last-reviewed` / `next-review` / `review-cycle` — when it was last checked
  and when it is due again (typically 90 days).

Normative meaning follows [RFC-style normative language](docs/policies/standards/NORMATIVE_LANGUAGE.md)
and restricted assurance terms are governed by
[Public Assurance Terminology](docs/policies/standards/PUBLIC_ASSURANCE_TERMINOLOGY.md).

## Evidence and sources

Factual and standards-based content follows the
[Citation Source Policy](docs/policies/standards/CITATION_SOURCE_POLICY.md):
primary authoritative sources are preferred, secondary sources are
non-normative, drafts are labeled as drafts ([Framework Status
Policy](docs/policies/standards/FRAMEWORK_STATUS_POLICY.md)), and the
versioned [Standards Register](docs/policies/standards/REFERENCES.md) records
which edition each claim tracks.

## Documentation map

The established controlled-document collection remains under
[`docs/policies/`](docs/policies/README.md), with 42 subject categories spanning:

- **Trust & assurance** — security, privacy, compliance, customer-trust, accessibility
- **Governance & corporate** — governance, legal, ethics, finance, tax, treasury, internal-audit, records
- **Building & operating** — engineering, data, AI, product, operations, resilience, quality, project-delivery, releases
- **Organization** — people, workplace-safety, human-rights, communications, marketing, knowledge, strategy, research
- **Commercial & partners** — commercial, partnerships, procurement, third-party, customer-success, support, corporate-development
- **Working artifacts** — standards, SOPs, templates

Reusable project-neutral knowledge is organized under
[`docs/knowledge/`](docs/knowledge/README.md), grouped into domain families.

Tip: for a repository this size, use GitHub's file finder (`t`) or code
search to jump directly to a document.

## Public-repository boundary

This repository must not expose product-specific implementation details, deployment topology, credentials, private endpoints, customer information, internal identifiers, banking details, tax identifiers or filings, treasury balances, facility-security details, personal medical information, worker grievance identities, active transaction details, or unannounced work.

Public documentation may describe principles, responsibilities, controls, decision criteria, and repeatable procedures. It must not create false assurance or present planned controls as implemented.

Bulk or externally sourced knowledge is accepted only after project-neutral
sanitization, sensitive-data screening, duplicate and collision checks,
relative-link validation, manifest/file-count verification, and cryptographic
checksum verification. The reusable-knowledge migration validated 8,006 source Markdown files before
publication. Six previously reviewed articles remain the canonical public copies
and replace their transfer duplicates; all other accepted files are published under
`docs/knowledge/` in project-neutral domain families.

## Documentation workflow

Authorized routine documentation maintenance is performed directly on **`main`**. Feature branches and pull requests are not required for routine documentation growth or maintenance; external contributions and larger changes use pull requests — see [CONTRIBUTING.md](CONTRIBUTING.md).

Changes must be evidence-based, duplicate-checked, narrowly scoped, and reviewed for public-safety and sensitive-data boundaries before commit. Use current primary or authoritative sources for standards, regulatory, security, and vendor claims.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](docs/reference/SUPPORT.md).

## Citing this documentation

Content is MIT-licensed (see [LICENSE](LICENSE)). When citing a document,
reference its URL together with the document's `last-reviewed` date. The
[concept DOI `10.5281/zenodo.22109314`](https://doi.org/10.5281/zenodo.22109314)
identifies the documentation series across archived versions, as recorded in
[the citation metadata](docs/reference/CITATION.cff). Do not treat the concept DOI as a
version-specific identifier. For a reproducible citation to `v1.0.0`, a later
release, or an untagged state of `main`, pin the Git tag or exact commit SHA and
use a version-specific archive DOI only when that DOI has been independently verified.

## Brand

**ORCHORDS — BUILD DIFFERENT.**

## License

See [LICENSE](LICENSE).