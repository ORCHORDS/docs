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

### Changed

- Repository layout: all documentation categories now live under
  `categories/`, keeping the repository root compact.
- Canonical ORCHORDS banner asset (`assets/1080x360.jpg`) used across README,
  CONTRIBUTING, and SECURITY.

### Fixed

- Documentation-quality gate (`scripts/check_docs.py`) again enforces
  controlled-document front matter after the `categories/` reorganization;
  CODEOWNERS paths and the documentation-issue template were updated to the
  new layout.

### Removed

- One-time category-reorganization workflow after successful execution.
