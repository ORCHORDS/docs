# GitHub code-scanning tool-status coverage gates

**Issue:** A green code-scanning workflow can upload partial analysis, scan the wrong language set, or stop running while dashboards still contain old alerts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Gate security coverage on tool health, scan freshness, rules, and analyzed-file reports—not workflow conclusion alone. GitHub's tool-status page is repository/default-branch scoped.

## Controls

- Inventory expected languages, generated sources, build variants, scan configuration, schedule, and rule suites.
- Capture first/latest scan times and fail on stale analysis.
- Review warning/critical status and diagnostic errors.
- Export integrated-tool file coverage and compare paths with the repository manifest.
- Define justified exclusions for vendored, generated, test, and migration code.
- Detect zero/low coverage by language and missing compiled build steps.
- Reconcile default and advanced setup; GitHub notes the page shows only default setup when both exist.
- Aggregate repository evidence centrally because tool status is not organization-wide.

## Verification

Add a harmless vulnerable fixture in a scanned test path, confirm detection, then remove it. Break a build step in a canary and prove health alerts. Compare the downloaded analyzed-file CSV to `git ls-files` using documented exclusions.

## Gotchas

A file counts as scanned if some lines were processed. Compiled-language generated files may not appear because the report considers files present before build. High percentage does not prove every rule or dataflow is correct.

## Sources

- [GitHub Docs: Tool status page](https://docs.github.com/en/code-security/concepts/code-scanning/tool-status-page)
