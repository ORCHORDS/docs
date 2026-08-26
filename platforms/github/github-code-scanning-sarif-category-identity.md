# GitHub Code-Scanning SARIF Category Identity

**Issue:** Repeated SARIF uploads for the same commit and analysis can overwrite or fragment results when the category is missing or unstable, especially for matrix builds and monorepos.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Assign a stable SARIF category for each tool, language, build variant, and independently analyzed component.
- Keep category identity deterministic across reruns of the same analysis scope.
- Upload the commit SHA and ref that were actually analyzed.
- Retire old categories deliberately when a matrix or monorepo layout changes.

## Verification

- Upload two matrix variants for one commit and confirm both result sets remain visible.
- Rerun one variant and verify it updates only its own category.
- Rename a category in a test branch and observe stale-result behavior before production rollout.

## Gotchas

- The SARIF run automationDetails identifier and the upload category participate in result identity.
- More categories can preserve results but also create stale alerts if lifecycle cleanup is ignored.

## Official sources

- https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github
- https://docs.github.com/en/rest/code-scanning/code-scanning#upload-an-analysis-as-sarif-data
