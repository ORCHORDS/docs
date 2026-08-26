# Draft versus final standards adoption

**Issue:** Teams cite a newer draft as though it supersedes the final standard, creating unstable control identifiers and inaccurate compliance claims.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Lesson

Publication status is part of every external requirement. A draft can guide experiments and gap analysis, but the approved baseline remains the latest applicable final publication until a governed migration occurs.

## Adoption record

For every framework or standard, record publisher, title, identifier, version, status, publication date, retrieval date, applicability, owner, approved baseline, and successor watch. Link the authoritative publication page rather than an unversioned summary.

## Workflow

1. Detect a new draft from the publisher.
2. Preserve the current final mapping.
3. Build an isolated delta: added, removed, renamed, or materially changed controls.
4. Mark draft-derived work as anticipatory and reversible.
5. Monitor comments, errata, and final publication.
6. On final release, validate identifiers and content again.
7. Approve a migration plan with evidence impact, tooling changes, training, and effective date.
8. Archive the old mapping without destroying historical assessment evidence.

## Verification

- Lint policy documents for version and status.
- Sample citations and confirm they point to authoritative publisher pages.
- Ensure reports cannot combine draft and final control IDs without labels.
- Test rollback of draft-only automation.
- Review watch items on a defined cadence.

## Example

As of the researched baseline, NIST lists SSDF 1.1 as final and SP 800-218 Revision 1 / SSDF 1.2 as draft. Likewise, NIST identifies Privacy Framework 1.1 as an initial public draft. These are status facts, not predictions of final content.

## Gotchas

A newer date does not mean final. A closed comment period does not itself make a draft final. Vendor blogs can lag or overstate publication status.

## Sources

- [NIST SSDF publications and status](https://csrc.nist.gov/Projects/ssdf/publications)
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework)
