# github-actions-job-outputs

**Issue:** Passing data between jobs using job outputs and step outputs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Jobs run in isolated VMs. Sharing computed values (version strings, environment names, artifact paths) between jobs requires explicit output declarations — environment files alone don't cross job boundaries.

## Pattern / Solution
Step outputs flow through `$GITHUB_OUTPUT`; job outputs are declared in the job's `outputs:` block and consumed via `needs.<job>.outputs.<name>`.

**Step output → job output → downstream job:**
```yaml
jobs:
  compute-version:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.tag.outputs.version }}
      sha: ${{ steps.sha.outputs.sha }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Compute version
        id: tag
        run: |
          VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")
          echo "version=$VERSION" >> $GITHUB_OUTPUT

      - name: Short SHA
        id: sha
        run: echo "sha=${GITHUB_SHA::8}" >> $GITHUB_OUTPUT

  build:
    needs: compute-version
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "Building version ${{ needs.compute-version.outputs.version }}"
          echo "SHA: ${{ needs.compute-version.outputs.sha }}"
```

**Matrix job outputs (fan-in pattern):**
```yaml
  matrix-job:
    runs-on: ubuntu-latest
    outputs:
      # Only one matrix leg's output survives — use artifacts for multi-value fan-in
      result: ${{ steps.run.outputs.result }}
    strategy:
      matrix:
        service: [api, web, worker]
```

**Boolean/conditional outputs:**
```yaml
      - name: Check feature flag
        id: flag
        run: |
          if [[ "${{ github.ref_name }}" == "main" ]]; then
            echo "deploy=true" >> $GITHUB_OUTPUT
          else
            echo "deploy=false" >> $GITHUB_OUTPUT
          fi

  deploy:
    needs: flag-check
    if: needs.flag-check.outputs.deploy == 'true'
```

## Gotchas
- Output values are strings — booleans become `'true'`/`'false'`; compare accordingly in `if:` expressions
- Multiline outputs require the heredoc syntax: `echo "key<<EOF" >> $GITHUB_OUTPUT; echo "line1" >> $GITHUB_OUTPUT; echo "EOF" >> $GITHUB_OUTPUT`
- Matrix jobs with outputs: only the last-completing leg's value is captured in `needs.<job>.outputs` — use artifacts for fan-in aggregation
- Step output set via the deprecated `::set-output::` command is ignored in runner v2.298+; use `$GITHUB_OUTPUT` file
- Outputs from skipped jobs return empty string, not null — guard with `if: needs.job.result == 'success'`

## Related
- `github-actions-matrix-2026.md`
- `github-actions-artifact-upload.md`
- `github-actions-reusable-workflows.md`
