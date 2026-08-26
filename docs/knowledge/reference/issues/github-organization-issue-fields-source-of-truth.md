# GitHub Organization Issue Fields as a Source of Truth

**Issue:** Duplicating priority, effort, and dates across labels and project-only fields creates conflicting values for the same issue.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define organization issue fields only for metadata that should remain consistent across repositories and projects.
- Choose field types and controlled options deliberately; assign descriptions and an owner for taxonomy changes.
- Pin fields to the relevant issue types or untyped issues and set public versus organization-only visibility explicitly.
- Migrate from equivalent project fields in stages and declare which value is authoritative during transition.
- Automations must update field identifiers or exact supported option values and handle notifications and API permissions.

## Verification

- Place one issue in multiple projects and verify its organization field remains one shared value.
- Test field-added and field-removed webhook paths, API replacement semantics, and unauthorized updates.
- Before deleting a field or option, inventory populated issues because deletion can permanently remove values.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization
- https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-and-managing-issue-fields
- https://docs.github.com/en/rest/orgs/issue-fields
