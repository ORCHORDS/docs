# Cloudflare Pages Redirect Rule Deploy Validation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a Cloudflare Pages site, redirect rules defined in `_redirects` or
`public/_redirects` either silently fail to apply, produce conflicting results, or break
paths that worked in a previous deployment. Developers discover these problems after traffic
hits production. The goal is to validate redirect rules statically and dynamically as a
required CI gate before every Pages deployment.

---

## Context

Cloudflare Pages supports two redirect mechanisms:

1. **`_redirects` file** — a Netlify-compatible plain-text file placed at the root of the
   publish directory. Pages parses this during build ingestion. Up to 2,000 rules are
   supported; rules beyond that limit are silently dropped.
2. **`_headers` / Functions middleware** — programmatic redirects executed at the edge via
   Pages Functions. These override `_redirects` for the same path.

Common failure modes:
- Rules exceed the 2,000-rule limit — excess rules silently ignored.
- Splat (`*`) syntax conflicts with function routes.
- Query string matching is unsupported in `_redirects` — developers add `?param=value` and
  wonder why it never fires.
- Redirect chains (A → B → C) cause browser loops and inflate redirect counts.
- Status codes other than 301 and 302 are not valid in `_redirects` — Pages will reject or
  silently ignore them.

---

## `_redirects` File Format Reference

```
# syntax: source [destination] [status] [!]
/old-path   /new-path        301
/docs       /documentation   302
/blog/*     /news/:splat     301
/           /home            302   !   # force redirect even for Direct Upload
https://old.example.com/*   https://new.example.com/:splat   301
```

Rules are evaluated top-to-bottom; the first match wins. The `!` force flag bypasses the
"serve file if it exists" default behaviour.

---

## Static Validation Script (TypeScript)

Run this during CI before `wrangler pages deploy` to catch structural problems.

```typescript
// scripts/validate-redirects.ts
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

interface RedirectRule {
  lineNumber: number;
  source: string;
  destination: string;
  status: number;
  force: boolean;
  raw: string;
}

const VALID_STATUSES = new Set([200, 301, 302, 303, 307, 308, 404, 410]);
const MAX_RULES = 2000;

function parseRedirects(filePath: string): RedirectRule[] {
  if (!existsSync(filePath)) {
    console.log(`No _redirects file found at ${filePath}; skipping.`);
    return [];
  }

  const lines = readFileSync(filePath, "utf-8").split("\n");
  const rules: RedirectRule[] = [];
  const errors: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i].trim();
    if (!raw || raw.startsWith("#")) continue;

    const parts = raw.split(/\s+/);
    if (parts.length < 2) {
      errors.push(`Line ${i + 1}: too few fields — "${raw}"`);
      continue;
    }

    const [source, destination, maybeStatus, maybeForce] = parts;
    const status = maybeStatus ? parseInt(maybeStatus, 10) : 302;
    const force = maybeForce === "!";

    if (!VALID_STATUSES.has(status)) {
      errors.push(
        `Line ${i + 1}: invalid status code ${status}. Valid: ${[...VALID_STATUSES].join(", ")}`
      );
    }

    if (source.includes("?")) {
      errors.push(
        `Line ${i + 1}: query string matching is not supported in _redirects — "${source}"`
      );
    }

    rules.push({ lineNumber: i + 1, source, destination, status, force, raw });
  }

  if (errors.length > 0) {
    console.error("Redirect validation errors:\n" + errors.map((e) => `  ${e}`).join("\n"));
    process.exit(1);
  }

  return rules;
}

function detectRedirectChains(rules: RedirectRule[]): void {
  const destinationSet = new Set(rules.map((r) => r.destination));
  const chains: string[] = [];

  for (const rule of rules) {
    if (destinationSet.has(rule.source)) {
      chains.push(
        `Line ${rule.lineNumber}: "${rule.source}" is both a source and a destination — potential redirect chain`
      );
    }
  }

  if (chains.length > 0) {
    console.warn("Redirect chain warnings:\n" + chains.map((c) => `  ${c}`).join("\n"));
  }
}

function detectDuplicateSources(rules: RedirectRule[]): void {
  const seen = new Map<string, number>();
  for (const rule of rules) {
    if (seen.has(rule.source)) {
      console.warn(
        `  Line ${rule.lineNumber}: duplicate source "${rule.source}" (first seen on line ${seen.get(rule.source)})`
      );
    } else {
      seen.set(rule.source, rule.lineNumber);
    }
  }
}

function validateRedirectFile(publishDir: string): void {
  const filePath = resolve(publishDir, "_redirects");
  const rules = parseRedirects(filePath);

  if (rules.length > MAX_RULES) {
    console.error(
      `ERROR: ${rules.length} redirect rules exceed the ${MAX_RULES}-rule limit. ` +
        `Rules beyond ${MAX_RULES} will be silently dropped.`
    );
    process.exit(1);
  }

  detectRedirectChains(rules);
  detectDuplicateSources(rules);

  console.log(`✔  ${rules.length} redirect rules validated (limit: ${MAX_RULES}).`);
}

const publishDir = process.argv[2] ?? "dist";
validateRedirectFile(publishDir);
```

---

## GitHub Actions Integration

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy with Redirect Validation

on:
  push:
    branches: [main]

jobs:
  build-and-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run build

      - name: Validate _redirects file
        run: npx tsx scripts/validate-redirects.ts dist

      - name: Validate redirect rule count
        run: |
          COUNT=$(grep -c '^[^#]' dist/_redirects || echo 0)
          echo "Total redirect rules: $COUNT"
          if [ "$COUNT" -gt 2000 ]; then
            echo "ERROR: Redirect rule count ($COUNT) exceeds 2000 limit."
            exit 1
          fi

      - name: Deploy to Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: pages deploy dist --project-name my-pages-project --branch main

  smoke-test-redirects:
    needs: build-and-validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Wait for Pages deployment to propagate
        run: sleep 30

      - name: Test critical redirect rules
        env:
          PAGES_URL: "https://my-pages-project.pages.dev"
        run: |
          test_redirect() {
            local path="$1"
            local expected_dest="$2"
            local expected_status="${3:-301}"
            local actual
            actual=$(curl -s -o /dev/null -w "%{http_code}:%{redirect_url}" \
              --max-redirs 0 "$PAGES_URL$path")
            local actual_status="${actual%%:*}"
            local actual_dest="${actual##*:}"

            if [ "$actual_status" != "$expected_status" ]; then
              echo "FAIL $path: expected $expected_status, got $actual_status"
              return 1
            fi
            echo "PASS $path → $actual_dest ($actual_status)"
          }

          test_redirect "/old-path" "https://my-pages-project.pages.dev/new-path" "301"
          test_redirect "/docs"     "https://my-pages-project.pages.dev/documentation" "302"
```

---

## Detecting Rules Shadowed by Pages Functions

Pages Functions routes take precedence over `_redirects`. If a `functions/` file covers the
same path as a redirect rule, the redirect will never fire.

```typescript
// scripts/check-function-shadows.ts
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { readFileSync } from "node:fs";

function getFunctionRoutes(functionsDir: string): string[] {
  const routes: string[] = [];
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (entry.endsWith(".ts") || entry.endsWith(".js")) {
        const rel = "/" + relative(functionsDir, full)
          .replace(/\.(ts|js)$/, "")
          .replace(/\/index$/, "")
          .replace(/\[([^\]]+)\]/g, ":$1");
        routes.push(rel);
      }
    }
  }
  walk(functionsDir);
  return routes;
}

function getRedirectSources(redirectsFile: string): string[] {
  return readFileSync(redirectsFile, "utf-8")
    .split("\n")
    .filter((l) => l && !l.startsWith("#"))
    .map((l) => l.split(/\s+/)[0]);
}

const functionRoutes = getFunctionRoutes("functions");
const redirectSources = getRedirectSources("dist/_redirects");

for (const source of redirectSources) {
  const base = source.split("*")[0].replace(/:splat$/, "");
  if (functionRoutes.some((r) => r.startsWith(base))) {
    console.warn(`WARNING: Redirect "${source}" may be shadowed by a Pages Function.`);
  }
}
```

---

## Anti-patterns

- **Not committing `_redirects` to the publish directory** — if your build tool outputs to
  `dist/` but `_redirects` lives in `public/`, it may not be copied. Always verify the file
  appears in the output directory after the build step.
- **Using 3xx status codes other than 301 and 302 in `_redirects`** — Pages ignores them
  silently. Use a Pages Function for 307/308 semantics.
- **Query string conditions in `_redirects`** — unsupported; move query-based routing to
  Functions middleware.
- **More than 2,000 rules** — the excess is dropped with no warning in deploy logs.
- **Redirect loops** — A → B where B also matches a rule back to A; always run chain
  detection before deploy.
- **Relying on order for security-sensitive redirects** — rule evaluation stops at first
  match; accidentally placing a catch-all early will swallow all subsequent rules.

---

## Gotchas

- When a Pages project uses `_redirects` AND a `_headers` file with `X-Frame-Options`,
  Pages evaluates `_headers` after `_redirects`; headers do not affect whether the redirect
  fires.
- The `!` force flag overrides the file-serving check but not Pages Functions. A function
  route still wins even with `!`.
- Preview deployments use the same `_redirects` file as production, so preview smoke tests
  validating redirects are meaningful for production correctness.
- Absolute URLs in `_redirects` (e.g., `https://old.example.com/*`) require the old domain
  to be verified in your Cloudflare account. Unverified source domains are skipped.
- Wrangler `pages deploy` does not output a summary of which redirect rules were ingested.
  Use the Cloudflare Pages dashboard or the `/deployments` API to inspect the parsed rules.

---

## Verification

```bash
# 1. Count redirect rules in the publish directory
grep -c '^[^#]' dist/_redirects

# 2. Test a specific redirect manually
curl -I --max-redirs 0 https://my-site.pages.dev/old-path

# 3. Use the Pages Deployments API to inspect redirect rules on the latest deploy
ACCOUNT_ID="abc123"
PROJECT="my-pages-project"
DEPLOY_ID=$(curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/deployments" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | \
  jq -r '.result[0].id')
echo "Latest deployment: $DEPLOY_ID"

# 4. Run validation script locally
npx tsx scripts/validate-redirects.ts dist
```

---

## Related

- `cloudflare-pages-build-cache-optimization.md`
- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-middleware-versioned-deploy-strategy.md`
- `pages-functions-env-var-management.md`
- `deploy-gate-e2e-tests-playwright-pages.md`

---

## Sources

- Cloudflare Docs: Redirects — https://developers.cloudflare.com/pages/configuration/redirects/
- Cloudflare Docs: Headers file — https://developers.cloudflare.com/pages/configuration/headers/
- Cloudflare Docs: Pages Functions routing — https://developers.cloudflare.com/pages/functions/routing/
- Cloudflare Docs: Pages build configuration — https://developers.cloudflare.com/pages/configuration/build-configuration/
- Cloudflare Blog: Pages Functions GA — https://blog.cloudflare.com/pages-functions-are-now-generally-available/
