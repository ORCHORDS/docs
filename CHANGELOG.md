# Changelog

Notable changes to the ORCHORDS public documentation repository. Routine
document additions and corrections are not listed individually; see the
commit history for those.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Repository support guide ([SUPPORT.md](./SUPPORT.md)) routing documentation
  issues, security reports, and general questions.
- Repository governance guide ([GOVERNANCE.md](./GOVERNANCE.md)) covering
  maintainers, change acceptance, and dispute resolution.
- This changelog and a `CITATION.cff` for citing the repository.
- README: "Start here" entry points, reading guide, evidence-policy summary,
  citation guidance, and grouped category map.
- CodeQL and OpenSSF Scorecard workflows for continuous code and supply-chain
  security analysis.
- Project-neutral top-level knowledge families for reusable business,
  engineering, platform, data/AI, operations, security, playbook, lessons,
  standards, template, reference, and archive material.
- A fail-closed knowledge-import pipeline that verifies sanitization,
  neutrality, duplicates/collisions, relative links, manifest counts, and
  cryptographic checksums before publication.

### Changed

- Repository layout now supports both the established controlled-document
  categories and top-level project-neutral knowledge families.
- Public documentation rules now explicitly require imported or bulk knowledge
  to be sanitized and validated before it can enter the published corpus.
- Canonical ORCHORDS banner asset (`assets/1080x360.jpg`) used across README,
  CONTRIBUTING, and SECURITY.

### Migration status

- A prepared public-safe knowledge snapshot contains 8,006 Markdown files.
- The snapshot passed the sanitization/public-safety gate with zero unresolved
  findings and the relative-link gate with zero broken links.
- The snapshot is not recorded as published until the receiving import,
  deduplication/collision checks, and repository quality checks complete.

### Fixed

- Documentation-quality gate (`scripts/check_docs.py`) again enforces
  controlled-document front matter after the `categories/` reorganization;
  CODEOWNERS paths and the documentation-issue template were updated to the
  new layout.

### Removed

- One-time category-reorganization workflow after successful execution.
