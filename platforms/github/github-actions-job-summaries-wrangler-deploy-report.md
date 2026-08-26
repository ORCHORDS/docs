# GitHub Actions Job Summaries for Wrangler Deploy Reports

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After deploying a Cloudflare Worker for example project / example.com, the CI log is a raw wall of `wrangler deploy` output. Developers must scroll through ANSI escape codes to find the deployed URL, the binding list, the bundle size, and the compatibility date. When 8 Workers deploy in parallel across staging and production, determining which environment each one landed on requires opening individual job logs. A structured Job Summary surfaces the essential deploy facts directly on the Actions run page without opening a single log.

## Context

GitHub Actions provides `$GITHUB_STEP_SUMMARY`, an environment file that accepts Markdown appended by any `run` step. Content is rendered as HTML on the workflow run page and on the repository's Actions tab. Unlike annotations (which appear inline in files), Job Summaries are job-scoped and persist for the lifetime of the workflow run. For Wrangler deploys, parsing `wrangler deploy` stdout lets you emit a formatted table of worker name, environment, bundle size, compatibility date, and deployed URL into the summary.

## Basic Summary from Wrangler Output

Capture Wrangler's output to a variable, extract key fields with grep/awk, and append Markdown to `$GITHUB_STEP_SUMMARY`:

```yaml
      - name: Deploy and summarise
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          OUTPUT=$(pnpm wrangler deploy 2>&1)
          echo "$OUTPUT"

          # Parse fields from wrangler output
          WORKER_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev' | tail -1)
          BUNDLE_SIZE=$(echo "$OUTPUT" | grep -oP '\d+(\.\d+)?\s*(KiB|MiB)' | head -1)
          COMPAT_DATE=$(echo "$OUTPUT" | grep -oP 'compatibility_date = "\K[^"]+')

          # Write summary
          {
            echo "## Wrangler Deploy Report"
            echo ""
            echo "| Field | Value |"
            echo "| --- | --- |"
            echo "| Worker | \`${{ inputs.worker_name }}\` |"
            echo "| Environment | \`${{ inputs.environment }}\` |"
            echo "| Bundle size | $BUNDLE_SIZE |"
            echo "| Compatibility date | \`$COMPAT_DATE\` |"
            echo "| Deployed URL | $WORKER_URL |"
            echo "| Commit | \`${{ github.sha }}\` |"
            echo "| Triggered by | @${{ github.actor }} |"
          } >> "$GITHUB_STEP_SUMMARY"

          echo "url=$WORKER_URL" >> "$GITHUB_OUTPUT"
```

## Multi-Worker Summary via a Shared Script

When the reusable deploy workflow runs for 8 Workers in parallel, each job writes its own summary. To additionally write a consolidated summary, use a `notify` job that runs after all deploy jobs and reads their outputs:

```yaml
# In the top-level orchestrator workflow
jobs:
  deploy-feed:
    uses: ./.github/workflows/_worker-deploy.yml
    with:
      worker_name: "example project-feed"
      environment: "staging"
    secrets: inherit

  deploy-auth:
    uses: ./.github/workflows/_worker-deploy.yml
    with:
      worker_name: "example project-auth"
      environment: "staging"
    secrets: inherit

  summarise:
    needs: [deploy-feed, deploy-auth]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Write consolidated summary
        run: |
          {
            echo "## Staging Deploy Summary — $(date -u '+%Y-%m-%d %H:%M UTC')"
            echo ""
            echo "| Worker | Status | URL |"
            echo "| --- | --- | --- |"
            echo "| example project-feed | ${{ needs.deploy-feed.result }} | ${{ needs.deploy-feed.outputs.deploy_url }} |"
            echo "| example project-auth | ${{ needs.deploy-auth.result }} | ${{ needs.deploy-auth.outputs.deploy_url }} |"
          } >> "$GITHUB_STEP_SUMMARY"
```

## Enriching Summaries with Bundle Analysis

Wrangler respects the `--outdir` flag to emit the bundled worker script before uploading. A bundle analysis step can measure file sizes and emit a warning if a Worker exceeds an internal size threshold:

```yaml
      - name: Dry-run bundle analysis
        run: |
          pnpm wrangler deploy --dry-run --outdir .wrangler/dist
          BUNDLE_BYTES=$(wc -c < .wrangler/dist/*.js)
          BUNDLE_KB=$(( BUNDLE_BYTES / 1024 ))
          LIMIT_KB=512

          {
            echo "### Bundle Analysis"
            echo ""
            echo "- Raw bundle: **${BUNDLE_KB} KB**"
            if [ "$BUNDLE_KB" -gt "$LIMIT_KB" ]; then
              echo "- :warning: Exceeds ${LIMIT_KB} KB soft limit — review dependencies"
            else
              echo "- Bundle within ${LIMIT_KB} KB soft limit"
            fi
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Deploy
        run: pnpm wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

## Adding Binding and Route Metadata

For anonymous social platforms, knowing which KV namespaces, D1 databases, and R2 buckets a Worker has access to after a deploy confirms that bindings are wired correctly. Parse `wrangler.toml` with a small Node script instead of fragile grep:

```yaml
      - name: Parse bindings for summary
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const toml = fs.readFileSync('apps/feed/wrangler.toml', 'utf8');

            const d1 = [...toml.matchAll(/database_name\s*=\s*"([^"]+)"/g)].map(m => m[1]);
            const kv  = [...toml.matchAll(/binding\s*=\s*"([^"]+)"/g)].map(m => m[1]);

            let md = '### Bindings\n\n';
            if (d1.length) md += `- **D1**: ${d1.join(', ')}\n`;
            if (kv.length) md += `- **KV / R2**: ${kv.join(', ')}\n`;

            await core.summary
              .addRaw(md)
              .write();
```

`core.summary` is the JavaScript equivalent of appending to `$GITHUB_STEP_SUMMARY` and supports fluent builder methods.

## Anti-patterns

- Writing the full `wrangler deploy` stdout into the summary — it contains ANSI codes that render as literal escape sequences in the Markdown renderer.
- Making the summary step fail-fast (`set -e`) if `grep` finds no match — Wrangler's output format changes between minor versions; use default values when parsing fails.
- Relying on the summary for compliance audit purposes — summaries are ephemeral (deleted with the run after 90 days); use Cloudflare's deploy history or a D1 audit log for long-term records.
- Writing HTML directly to `$GITHUB_STEP_SUMMARY` — the renderer supports Markdown only (GitHub Flavoured Markdown); raw HTML tags other than basic inline elements are stripped.
- Truncating the deploy URL — the full URL is needed for smoke tests in downstream jobs.

## Gotchas

- `$GITHUB_STEP_SUMMARY` has a maximum size of 1 MB per step and 20 MB per job; a very large bundle analysis output can be truncated silently.
- Summaries from reusable workflow jobs appear on the reusable workflow's own run page, not the caller's run page — they are not automatically merged into the caller's summary.
- The `actions/github-script` `core.summary` builder overwrites the entire job summary by default; use `.addRaw(...).write()` with `overwrite: false` to append.
- Job summaries are not available in `post:` steps of composite actions.
- `wrangler deploy` exits 0 even when some bindings fail validation at upload time (they surface as warnings); always grep for "Error" in the output before writing a success summary.

## Verification

1. Trigger a deploy workflow and navigate to the run's "Summary" tab — the deploy table should appear without opening any individual job log.
2. Introduce an artificially large dependency and confirm the bundle analysis step emits the warning in the summary.
3. Deploy two Workers concurrently and check that each job's summary tab shows only that Worker's data (not the other's).
4. Inspect the consolidated `summarise` job summary to confirm both Worker URLs are hyperlinked and statuses are accurate.

## Related

- `actions-job-summaries-annotations-reporting.md`
- `github-actions-reusable-workflows-workers-deploy.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-workflow-status-badge-dashboard.md`
- `github-deployment-api-workers-status-tracking.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary
- https://github.blog/news-insights/product-news/supercharging-github-actions-with-job-summaries/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/actions/github-script#actionsgithub-script
