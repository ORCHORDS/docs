# Govern GitHub Code Security Campaign Scope and Closure

**Issue:** A remediation campaign can improve focus while still closing with vulnerable default-branch code, dismissed alerts, missing repositories, or fixes that never merge.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Define campaign scope by owned repositories, alert types/severity, branch state, due date, and accountable managers.
- Snapshot included alerts and explicitly record exclusions.
- Require closure evidence from merged fixes or reviewed dismissals with durable rationale.
- Reconcile campaign state with current default-branch alerts after merges and rescans.
- Track dependencies and common root causes separately from alert counts.
- Escalate overdue critical work through the existing vulnerability process.

## Verification
- Sample closed items from campaign to alert, PR, merge commit, rescan, and dismissal evidence.
- Add a qualifying alert after campaign creation and document whether scope is static or refreshed.
- Transfer/archive a repository and verify ownership and reporting behavior.
- Compare campaign completion with repository-level open-alert queries.

## Gotchas
Campaign completion is a coordination signal, not proof that every repository or vulnerability class is secure. Dismissal reduces counts without changing code.

## Official sources
- [GitHub: About security campaigns](https://docs.github.com/en/code-security/securing-your-organization/fixing-security-alerts-at-scale/about-security-campaigns)
