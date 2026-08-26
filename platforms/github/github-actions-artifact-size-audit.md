# github-actions-artifact-size-audit

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) Cloudflare Worker bundles have grown silently from 180 KB to 940 KB over six months. No CI gate flags the growth; developers only notice when Wrangler warns about approaching the 1 MB script size limit. There is no per-PR visibility into which change caused a size regression, no historical baseline to compare against, and no automated budget enforcement to block a PR that crosses a threshold.

## Context

Artifact size auditing in GitHub Actions works by: (1) building the bundle and recording its size as a workflow artifact or job output, (2) retrieving the size from the base branch's last successful run, (3) computing the delta and rendering a comparison table in a PR comment, and (4) optionally failing the workflow when the bundle exceeds a configured budget. The key tools are `actions/upload-artifact`, the GitHub REST API for artifact retrieval, and `peter-evans/create-or-update-comment` for sticky PR comments. No third-party size-tracking SaaS is required.

## Build step: measure and record size

```yaml
    - name: Build Worker bundle
      run: pnpm turbo build --filter=workers/api

    - name: Measure bundle size
      id: size
      run: |
        BUNDLE=workers/api/dist/index.js
        SIZE_BYTES=$(stat -c%s "$BUNDLE")
        SIZE_KB=$(echo "scale=1; $SIZE_BYTES / 1024" | bc)
        echo "bytes=$SIZE_BYTES" >> $GITHUB_OUTPUT
        echo "kb=$SIZE_KB" >> $GITHUB_OUTPUT
        echo "Bundle size: ${SIZE_KB} KB (${SIZE_BYTES} bytes)"

    - name: Upload size artifact
      uses: actions/upload-artifact@v4
      with:
        name: bundle-size-${{ github.sha }}
        path: workers/api/dist/index.js
        retention-days: 30
        compression-level: 0   # don't compress — we want the real file size
```

Store the raw file, not a compressed archive. `compression-level: 0` tells `upload-artifact@v4` to skip gzip so the artifact size in the GitHub UI reflects the actual bundle size. Alternatively, write a `size.json` sidecar:

```yaml
    - name: Write size report
      run: |
        echo '{"bytes": ${{ steps.size.outputs.bytes }}, "sha": "${{ github.sha }}"}' \
          > size-report.json

    - name: Upload size report
      uses: actions/upload-artifact@v4
      with:
        name: size-report-${{ github.sha }}
        path: size-report.json
        retention-days: 90
```

## Retrieving the base branch artifact

On a PR run, fetch the most recent size artifact from the base branch (usually `main`) via the GitHub API:

```yaml
    - name: Fetch base branch size
      id: base
      env:
        GH_TOKEN: ${{ github.token }}
      run: |
        BASE_SHA=$(gh api \
          repos/${{ github.repository }}/commits/${{ github.base_ref }} \
          --jq '.sha')

        # Find the most recent successful workflow run on the base branch
        RUN_ID=$(gh api \
          "repos/${{ github.repository }}/actions/workflows/ci.yml/runs?branch=${{ github.base_ref }}&status=success&per_page=1" \
          --jq '.workflow_runs[0].id')

        if [ -z "$RUN_ID" ] || [ "$RUN_ID" = "null" ]; then
          echo "No base run found — treating base size as 0"
          echo "bytes=0" >> $GITHUB_OUTPUT
          exit 0
        fi

        # Download the size-report artifact
        gh api \
          "repos/${{ github.repository }}/actions/runs/${RUN_ID}/artifacts" \
          --jq '.artifacts[] | select(.name | startswith("size-report-"))' \
          | head -1 | jq -r '.archive_download_url' > /tmp/artifact_url

        ARTIFACT_URL=$(cat /tmp/artifact_url)
        curl -sL -H "Authorization: Bearer $GH_TOKEN" \
          "$ARTIFACT_URL" -o /tmp/size-report.zip
        unzip -p /tmp/size-report.zip size-report.json | jq -r '.bytes' \
          | xargs -I{} echo "bytes={}" >> $GITHUB_OUTPUT
```

## Delta table and PR comment

Compute the delta and render a markdown table to post as a sticky PR comment:

```yaml
    - name: Compute size delta
      id: delta
      run: |
        PR_BYTES=${{ steps.size.outputs.bytes }}
        BASE_BYTES=${{ steps.base.outputs.bytes }}
        DELTA=$((PR_BYTES - BASE_BYTES))
        PCT=$(echo "scale=1; $DELTA * 100 / ($BASE_BYTES + 1)" | bc)
        SIGN=""
        [ "$DELTA" -gt 0 ] && SIGN="+"
        echo "delta=$DELTA" >> $GITHUB_OUTPUT
        echo "pct=${SIGN}${PCT}" >> $GITHUB_OUTPUT
        echo "sign=${SIGN}" >> $GITHUB_OUTPUT

    - name: Post PR comment
      if: github.event_name == 'pull_request'
      uses: peter-evans/create-or-update-comment@v4
      with:
        issue-number: ${{ github.event.pull_request.number }}
        comment-author: github-actions[bot]
        body: |
          ### Bundle Size Report

          | Bundle | Base (`main`) | PR (`${{ github.sha }}`) | Delta |
          |---|---|---|---|
          | workers/api | ${{ steps.base.outputs.bytes }} B | ${{ steps.size.outputs.bytes }} B | ${{ steps.delta.outputs.sign }}${{ steps.delta.outputs.delta }} B (${{ steps.delta.outputs.pct }}%) |

          > Budget limit: 900 KB. Status: ${{ steps.budget.outputs.status }}
        edit-mode: replace
```

`create-or-update-comment` finds any existing comment from `github-actions[bot]` on the PR and replaces it in-place, so each push updates the same comment rather than flooding the PR timeline.

## Budget gate step

Fail the workflow when the bundle exceeds the budget. Set the budget below the Cloudflare 1 MB Worker script limit with a comfortable margin:

```yaml
    - name: Budget gate
      id: budget
      env:
        BUDGET_BYTES: 921600   # 900 KB
      run: |
        PR_BYTES=${{ steps.size.outputs.bytes }}
        if [ "$PR_BYTES" -gt "$BUDGET_BYTES" ]; then
          echo "status=EXCEEDED" >> $GITHUB_OUTPUT
          echo "::error::Bundle size ${PR_BYTES} B exceeds budget ${BUDGET_BYTES} B (900 KB)"
          exit 1
        else
          REMAINING=$((BUDGET_BYTES - PR_BYTES))
          echo "status=OK (${REMAINING} B remaining)" >> $GITHUB_OUTPUT
          echo "Bundle OK: ${PR_BYTES} B / ${BUDGET_BYTES} B"
        fi
```

Place the budget gate **after** the PR comment step so the comment is always posted even when the gate fails. Use `if: always()` on the comment step:

```yaml
    - name: Post PR comment
      if: always() && github.event_name == 'pull_request'
```

## Size tracking across time

For trend visibility, write size data to a repository-hosted JSON file (in a `gh-pages` or `metrics` branch) or use GitHub Actions job summaries:

```yaml
    - name: Write job summary
      run: |
        cat >> $GITHUB_STEP_SUMMARY << EOF
        ## Bundle Size
        | Metric | Value |
        |---|---|
        | Size | ${{ steps.size.outputs.kb }} KB |
        | Delta vs base | ${{ steps.delta.outputs.pct }}% |
        | Budget used | $(echo "scale=1; ${{ steps.size.outputs.bytes }} * 100 / 921600" | bc)% |
        EOF
```

Job summaries appear in the Actions run UI under the "Summary" tab and persist with the run. They are not queryable via API for trend analysis; for that, write to an artifact or a time-series store.

## Anti-patterns

- Measuring the `.zip` archive size instead of the raw bundle — `upload-artifact` always zips, so the artifact size in the UI is the compressed size, not the Worker script size Cloudflare enforces.
- Using `github.sha` on the base branch query — the base branch HEAD SHA changes; query by branch name and filter by workflow success status instead.
- Hard-coding the base run SHA — the base branch advances; the comparison drifts and becomes meaningless within days.
- Setting the budget at exactly the Cloudflare limit (1 MB = 1,048,576 B) — leaves no margin for variance in minifier output between runs.
- Using a floating `peter-evans/create-or-update-comment` version tag — this action updates frequently; pin to a SHA or explicit semver tag.

## Gotchas

- `actions/upload-artifact@v4` compresses artifacts by default. Retrieving an artifact and reading its size via the API returns the compressed ZIP size, not the raw file size. Always measure with `stat` before uploading, and store the byte count separately (in a JSON sidecar or job output).
- Artifact download via the API requires `actions: read` permission on the `GITHUB_TOKEN` for private repos. The default `github.token` has this on the repo where the workflow runs.
- The `artifact_download_url` in the API response is a redirect — `curl -L` (follow redirects) is required.
- `create-or-update-comment` matches on comment author (`github-actions[bot]`) AND the comment body must not have changed — use a unique marker string or `comment-id` input to reliably find and update the comment.
- On the first run (no base branch artifact), the delta comparison will fail if not guarded. Always check for empty `$RUN_ID` and fall back to `base_bytes=0` or skip the delta step.

## Verification

1. Merge a PR that increases the bundle size by 1 KB — confirm the PR comment appears with the correct delta row.
2. Merge a PR that decreases bundle size — confirm delta is shown as negative (green visually if using emoji).
3. Artificially set `BUDGET_BYTES` to 1 B — confirm the budget gate step fails the workflow and the comment still posts (due to `if: always()`).
4. Check the artifact list in the Actions run — `size-report-{sha}` artifacts should appear with `retention-days: 90`.
5. Verify that re-pushing to the same PR branch updates the existing comment rather than adding a new one.

```bash
# List recent size artifacts via CLI
gh api repos/example project-app/example project/actions/artifacts \
  --jq '.artifacts[] | select(.name | startswith("size-report-")) | {name, size_in_bytes, created_at}' \
  | head -20
```

## Related

- `github-actions-artifact-upload.md`
- `github-actions-job-summaries-annotations-reporting.md`
- `github-actions-pr-comment-bot.md`
- `github-actions-lighthouse-ci.md`
- `github-actions-deployment-gates.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
- https://github.com/peter-evans/create-or-update-comment
- https://docs.github.com/en/rest/actions/artifacts
- https://developers.cloudflare.com/workers/platform/limits/#script-size
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary
