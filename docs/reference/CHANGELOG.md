# Changelog

Notable changes to the ORCHORDS public documentation repository. Routine
document additions and corrections are not listed individually; see the
commit history for those.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Repository support guide ([SUPPORT.md](SUPPORT.md)) routing documentation
  issues, security reports, and general questions.
- Repository governance guide ([GOVERNANCE.md](GOVERNANCE.md)) covering
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

- Imported the validated 8,006-file reusable-knowledge snapshot into the
  project-neutral top-level domain families.
- Six previously reviewed canonical articles replace their corresponding
  transfer duplicates; non-identical path collisions remain refused.
- Destination-side public checks caught and neutralized two remaining source
  identifiers and validated the full imported corpus before publication.

### Fixed

- Documentation-quality gate (`.github/scripts/check_docs.py`) again enforces
  controlled-document front matter after the `docs/policies/` reorganization;
  CODEOWNERS paths and the documentation-issue template were updated to the
  new layout.

### Removed

- One-time category-reorganization workflow after successful execution.
