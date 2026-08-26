# GitHub Issue Transfer Taxonomy Preflight

**Issue:** Transferring an issue can preserve discussion while silently losing labels or milestones that do not exist compatibly in the destination repository.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Confirm the issue is open, both repositories share the same owner or organization, and the operator has write access to both.
- Block private-to-public transfers and review whether destination readers should gain access to the discussion.
- Preflight label names and milestone name-plus-due-date because only matching destination metadata is retained.
- Review assignees, mentions, projects, dependencies, automations, and external links before transfer.
- Record the new canonical URL while preserving the original redirect for traceability.

## Verification

- Transfer a non-sensitive test issue and compare body, comments, assignees, labels, milestone, and relationships.
- Verify users without destination read access receive no content through old links or notifications.
- Run destination triage automation and confirm the issue is not double-counted by source dashboards.

## Gotchas

- Validate feature and specification maturity against the cited official source.
- Avoid secrets, personal data, and restricted operational details in examples or evidence.
- Reassess after scope, dependency, protocol, or policy changes.

## Sources

- https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/transferring-an-issue-to-another-repository
