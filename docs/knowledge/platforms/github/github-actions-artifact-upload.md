# github-actions-artifact-upload

**Issue:** Uploading and downloading build artifacts between jobs and runs
**Date:** 2026-08-11
**Last reviewed:** 2026-08-19
**Status:** documented

## Symptom / Context

Build outputs, test reports, SBOMs, provenance, and other evidence sometimes need to persist beyond a single job or be shared between jobs. Artifact storage is finite and shared against account or organization billing limits, so retaining recomputable outputs can block required evidence uploads later.

The old v3 artifact backend is retired for GitHub.com. Use a currently supported artifact action release, pin external actions to reviewed immutable commit SHAs, and confirm self-hosted runners satisfy the action runtime's minimum runner version before upgrading.

## Pattern / Solution

### 1. Pin the reviewed action commit, not a mutable major tag

The examples below use reviewed GitHub-owned release commits current at the last-review date. Keep the human-readable release comment for maintainability, but the 40-character SHA is the supply-chain control.

**Upload from a build job:**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - run: npm ci && npm run build
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: dist-${{ github.sha }}
          path: dist/
          retention-days: 7
          if-no-files-found: error
```

**Download in a dependent job:**

```yaml
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3 # v8.0.0
        with:
          name: dist-${{ github.sha }}
          path: dist/
      - run: ./deploy.sh dist/
```

`download-artifact` v8 fails on digest mismatch by default. Do not weaken that integrity behavior for release or security evidence without a documented reason and compensating verification.

### 2. Classify artifacts before retaining them

Treat artifacts as one of two classes:

- **Irreplaceable or required evidence:** release provenance, signed attestations, required SBOMs, audit evidence, or outputs whose absence would invalidate a release/security gate. Upload these fail-closed with `if-no-files-found: error`; do not use `continue-on-error` to hide quota failures.
- **Recomputable outputs:** ordinary build directories, transient test logs, generated reports, or diagnostics that can be reproduced from an immutable commit and locked dependencies. Prefer job summaries, caches where appropriate, or short retention. Avoid storing the same output in multiple workflows.

Before adding an artifact upload, ask whether a downstream job really needs the exact bytes. If it can reproducibly rebuild from the same validated SHA, retaining a second copy may be unnecessary storage waste.

### 3. Keep retention deliberately short for recomputable outputs

```yaml
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always()
        with:
          name: test-report-${{ github.run_id }}
          path: reports/junit.xml
          retention-days: 5
          if-no-files-found: error
```

Use repository/organization retention policy for evidence that genuinely needs longer retention; do not mechanically use the maximum. A shorter retention period reduces storage pressure but is not a substitute for removing duplicate uploads.

### 4. Matrix fan-in

Artifact names must be unique per run. Include matrix dimensions in producer names, then merge deliberately:

```yaml
      - uses: actions/download-artifact@70fc10c6e5e1ce46ad2ea6f2b72d43f7d47b13c3 # v8.0.0
        with:
          pattern: test-results-*
          merge-multiple: true
          path: all-results/
```

## Quota behavior and fail-closed evidence

Artifact creation can fail when shared storage quota is exhausted even when build, tests, and evidence generation itself succeeded. Treat that as an **infrastructure/storage failure**, not as proof that the evidence gate passed.

For required SBOM/provenance/security evidence:

- keep the upload required;
- surface the quota error prominently;
- free capacity or increase approved capacity through the proper owner process;
- rerun the exact revision after capacity is available;
- never replace the required artifact with a silent job-summary-only success just to make CI green.

For recomputable diagnostics, a job summary may be a better persistent record than a retained JSON/text artifact. This keeps human-readable evidence without consuming artifact storage for data that is cheap to regenerate.

## Gotchas

- Artifact backend/action major versions can have breaking compatibility changes; migrate producer and consumer deliberately.
- Artifact names must be unique per run; matrix producers need the matrix value embedded in the name.
- Artifacts are immutable after creation in the modern backend; overwriting creates a new artifact identity.
- Cross-repository or cross-run downloads require an explicit token and sufficient `actions:read` permission.
- Retention is capped by repository, organization, or enterprise policy.
- `path:` globs should be reviewed carefully; avoid unintentionally uploading secrets, `.env` files, credentials, browser storage state, or other sensitive data.
- Self-hosted runners must meet the action release's runtime/minimum-runner requirements before a major-version upgrade.
- Keep release comments synchronized with the pinned SHA. A correct SHA with a stale version comment is operational/documentation drift and can mislead future reviews.

## Related

- `github-actions-matrix-2026.md`
- `github-packages-npm-registry.md`
- `github-actions-caching-2026.md`
- `github-sbom-generation.md`
- `../lessons/ci-pipeline-leaked-secrets.md`
