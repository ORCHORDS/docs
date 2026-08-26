# confluence-documentation

**Issue:** Confluence pages not structured for engineering discoverability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers cannot find runbooks or ADRs in Confluence because space structure is inconsistent.

## Pattern / Solution
Space structure: Home > Architecture > Services > Service Name. Use page templates for ADRs, runbooks, incident reports. Labels for cross-space search. Confluence macros for live Jira issue lists. Restrict edit access, open read for entire engineering org.

## Gotchas
- Page tree depth over 4 levels makes navigation painful — flatten structure with labels
- Atlassian Intelligence (AI) available for summarization on paid plans

## Related
- notion-engineering-wiki, jira-engineering-workflow
