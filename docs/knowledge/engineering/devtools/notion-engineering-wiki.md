# notion-engineering-wiki

**Issue:** Engineering documentation in Confluence is hard to keep current
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Architecture decisions, runbooks, and onboarding docs in Notion become stale or hard to find.

## Pattern / Solution
Structure: top-level Engineering space with Database-driven pages. Use linked databases for cross-team visibility. Template for ADRs. Notion API for automated doc generation from code. Sync with GitHub via actions.

## Gotchas
- Notion search has latency; bookmark critical pages
- Permission inheritance can accidentally expose sensitive pages — audit permissions quarterly

## Related
- obsidian-engineering-notes, confluence-documentation
