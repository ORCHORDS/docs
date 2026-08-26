# GitHub Actions reusable workflow limits

**Date:** 2026-08-26
**Status:** documented
**Source:** https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations

## Context

Reusable workflows reduce duplicated CI/CD logic, but GitHub documents structural limits and behavior that should influence workflow architecture.

## Current constraints to design for

GitHub currently documents:

- up to ten levels in a reusable-workflow call chain;
- up to 50 unique reusable workflows reachable from one top-level workflow file;
- workflow-level `env` values in the caller do not automatically propagate to the called workflow;
- actions and reusable-workflow references do not follow repository redirects after an owner/name change.

## Pattern

- Keep call graphs shallow and understandable.
- Pass required values explicitly through supported inputs/secrets rather than relying on caller `env` leakage.
- Treat workflow repository renames as dependency migrations.
- Inventory all reusable-workflow dependencies before large refactors.
- Prefer a few stable reusable workflows over deeply nested wrappers.

## Verification

Render/document the call graph for critical workflows, test required inputs in isolation, and exercise a caller using the exact immutable/stable reference policy expected in production.
