# Standard Status Is Part of the Control

**Issue:** A technically accurate control can become misleading when it cites a draft, preview, retired edition, or superseded document as though it were the current final authority.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Record publication status and exact edition beside every external authority used by a control.
- Use final normative baselines for mandatory claims; isolate draft or preview guidance as forward-looking input.
- Recheck authoritative status on a schedule and before audits, releases, migrations, or public compliance statements.
- Keep the old-to-new impact assessment with the control rather than replacing links silently.
- State tool or platform preview status where behavior can change without compatibility guarantees.

## Verification

- Resolve every source URL and compare title, edition, publication date, status, and replacement notices.
- Seed a retired and a draft source into a validation sample and require the review to flag both.
- When a source becomes final, diff its normative changes before promoting it into the baseline.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://csrc.nist.gov/pubs/sp/800/218/r1/ipd
- https://slsa.dev/spec/v1.2/
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema
