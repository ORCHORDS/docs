# GitHub Ruleset Metadata-Restriction Rollout

**Issue:** Commit, branch, and tag naming restrictions can unexpectedly block merges or accept malformed metadata when regex and squash behavior are not tested.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Scope metadata restrictions to the minimum branch or tag targets needed and test patterns before active enforcement.
- Use GitHub-supported RE2 behavior and account for an optional trailing newline with `\n?$` when anchoring commit-message patterns.
- For web-created commits, include GitHub noreply address forms when enforcing committer-email patterns.
- Document how squash merges are evaluated and align the repository's generated squash message with the rule.
- Keep metadata consistency rules separate from security controls such as reviews and required checks.

## Verification

- Test CLI push, web edit, API commit, merge commit, squash merge, revert, and automated release-tag creation.
- Exercise multiline messages, trailing newline, Unicode, maximum length, and lookalike branch names.
- Confirm a rejected object is not reachable from a protected reference even if its Git object remains retrievable.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
