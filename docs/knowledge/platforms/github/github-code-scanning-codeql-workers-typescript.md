# GitHub Code Scanning CodeQL for Cloudflare Workers TypeScript

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project / example.com backend is written in TypeScript and runs entirely on Cloudflare Workers. Standard CodeQL setup for TypeScript projects works well for Node.js backends, but Workers projects have unusual characteristics: there is no Node.js `require()`, globals like `Request`, `Response`, and `WebSocketPair` come from the Workers runtime rather than browser or Node typings, and `wrangler.toml` bindings inject globals that TypeScript does not know about unless a types file is generated. Without tuning, CodeQL raises false positives on Workers-specific patterns and misses genuine vulnerabilities because the build graph is incomplete.

## Context

GitHub Code Scanning with CodeQL performs static analysis by building a database from the project's source and then running queries against it. For TypeScript, CodeQL performs a "virtual build" — it reads source files and resolves module references without executing the compiler. Configuring a CodeQL query suite, exclusion paths, and a `packs` list optimised for the Workers TypeScript subset reduces noise and surfaces real issues like path traversal via `Request.url`, injection through `env` bindings, and missing input validation on anonymous content submissions.

## CodeQL Workflow for Workers

```yaml
# .github/workflows/codeql.yml
name: CodeQL Analysis

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 3 * * 1"   # Weekly on Monday at 03:00 UTC

jobs:
  analyse:
    name: Analyse TypeScript
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read

    strategy:
      fail-fast: false
      matrix:
        language: [typescript]

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "pnpm"

      # Generate Wrangler type stubs so CodeQL resolves binding globals
      - name: Generate Wrangler types
        run: |
          for dir in apps/*/; do
            if [ -f "$dir/wrangler.toml" ]; then
              (cd "$dir" && pnpm wrangler types --output-path worker-types.d.ts)
            fi
          done
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      - name: Initialise CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          config-file: .github/codeql-config.yml

      - name: Perform CodeQL analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{ matrix.language }}"
```

## CodeQL Config File

The config file controls which paths are excluded (generated worker-types stubs, build output, vendored polyfills) and which query suites run:

```yaml
# .github/codeql-config.yml
name: "example project CodeQL Config"

paths-ignore:
  - "**/*.d.ts"
  - "**/dist/**"
  - "**/.wrangler/**"
  - "**/node_modules/**"
  - "**/worker-types.d.ts"

queries:
  - uses: security-and-quality
  - uses: security-extended

query-filters:
  - exclude:
      id:
        # Workers never use eval; suppress the eval-injection alert noise
        - js/eval-injection
        # Workers use URL parsing idioms that trigger this without being vulnerable
        - js/server-side-unvalidated-url-redirection

packs:
  - codeql/javascript-queries
```

## Custom Query for Anonymous Content Injection

CodeQL supports custom queries that encode platform-specific vulnerability patterns. For an anonymous social platform, user-supplied post content reaching a D1 `db.prepare()` call without parameterisation is a SQL injection risk:

```typescript
// apps/feed/src/handlers/post.ts  — VULNERABLE pattern CodeQL should catch
export async function handlePost(request: Request, env: Env) {
  const body = await request.json() as { content: string };
  // Dangerous: string interpolation into SQL
  await env.DB.prepare(`INSERT INTO posts (content) VALUES ('${body.content}')`).run();
}
```

A QL query targeting this pattern:

```ql
/**
 * @name D1 SQL injection via string concatenation
 * @description User-controlled data flows into a D1 prepare() call without parameterisation.
 * @kind path-problem
 * @problem.severity error
 * @security-severity 9.0
 * @tags security cloudflare-workers d1
 */
import javascript
import DataFlow::PathGraph

class D1PrepareCall extends DataFlow::CallNode {
  D1PrepareCall() {
    this.getCalleeName() = "prepare" and
    this.getReceiver().toString().regexpMatch(".*\\.DB$|.*D1Database.*")
  }
}

from DataFlow::PathNode source, DataFlow::PathNode sink
where
  DataFlow::Configuration::hasFlowPath(source, sink) and
  sink.getNode() instanceof D1PrepareCall
select sink.getNode(), source, sink,
  "D1 prepare() call includes unsanitised user input from $@.", source.getNode(), "this source"
```

Store custom queries in `.github/codeql-queries/workers-d1-injection.ql` and reference them in `codeql-config.yml` under `queries:`.

## SARIF Upload and PR Annotations

CodeQL results upload as SARIF (Static Analysis Results Interchange Format). The `analyze` action uploads them automatically. To also block PRs with high-severity findings, enable code scanning as a required check in branch protection:

```yaml
# In branch protection (via GitHub UI or Terraform):
# Required status checks:
#   - "CodeQL / Analyse TypeScript"
```

To annotate PR diffs inline, GitHub renders SARIF results from `security-events: write` permission automatically. No additional step is needed.

To export SARIF for an external SIEM or audit log:

```yaml
      - name: Export SARIF for audit
        uses: github/codeql-action/analyze@v3
        with:
          output: /tmp/results
          upload: always

      - name: Upload SARIF to R2 for compliance
        run: |
          curl -X PUT \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT/r2/buckets/security-reports/objects/${{ github.sha }}/codeql.sarif" \
            -H "Authorization: Bearer ${{ secrets.CLOUDFLARE_API_TOKEN }}" \
            --data-binary @/tmp/results/typescript.sarif
```

## Anti-patterns

- Running CodeQL without generating `wrangler types` first — binding globals (`env.DB`, `env.KV`, `env.BUCKET`) are unresolved, leading to false positives for "undefined property access".
- Using the default `security-extended` suite without exclusions — Workers patterns like `URL` construction from `request.url` trigger false positives for SSRF that do not apply in the Workers routing model.
- Excluding all `*.d.ts` files globally — this also excludes `@cloudflare/workers-types` which provides types CodeQL needs to resolve built-in globals like `ExecutionContext` and `DurableObjectState`.
- Pinning `github/codeql-action` to a major version without a digest pin — supply chain risk in security tooling is high; pin to a full SHA.
- Blocking the PR on every CodeQL finding without triaging severity — `security-and-quality` includes style findings; only block on `error`-severity security alerts.

## Gotchas

- `wrangler types` requires a valid `CLOUDFLARE_API_TOKEN` even for type generation; use a token with `Workers Scripts:Read` scope only.
- CodeQL's TypeScript virtual build does not execute `tsc`; it resolves types independently. A project with errors in `tsc --noEmit` may still produce a valid CodeQL database.
- Workers using `module.exports` (CommonJS) in a monorepo that mixes CJS and ESM confuse the CodeQL module resolver; enforce ESM (`"type": "module"`) in all Worker `package.json` files.
- The `packs:` key in `codeql-config.yml` requires CodeQL CLI v2.13+; the `github/codeql-action/init@v3` step bundles a sufficiently recent CLI.
- Scheduled CodeQL runs on `cron:` only run on the default branch; findings from scheduled runs create alerts without attaching them to a PR.

## Verification

1. Introduce the vulnerable `db.prepare(\`INSERT ... '${body.content}'\`)` pattern in a PR branch and confirm CodeQL raises an alert and annotates the relevant line.
2. Merge a clean PR and verify no new security alerts appear in the repository's "Security > Code scanning" tab.
3. Check that `worker-types.d.ts` is generated before the `Initialise CodeQL` step by reviewing the Actions log timestamp order.
4. Run `gh api /repos/example project-app/backend/code-scanning/alerts --jq '.[].rule.severity' | sort | uniq -c` to audit alert distribution across severity levels.

## Related

- `github-code-scanning-codeql.md`
- `github-advanced-security-sarif-workers-upload.md`
- `github-ghas-code-scanning.md`
- `github-code-scanning-sarif-category-identity.md`
- `github-secret-scanning-custom-patterns.md`

## Sources

- https://docs.github.com/en/code-security/code-scanning/creating-an-advanced-setup-for-code-scanning/codeql-code-scanning-for-compiled-languages
- https://codeql.github.com/docs/writing-codeql-queries/codeql-queries/
- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning
