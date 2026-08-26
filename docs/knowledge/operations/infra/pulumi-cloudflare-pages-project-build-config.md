# Pulumi Cloudflare Pages Project Build Config

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example project frontend (example.com) is a Next.js static export deployed to Cloudflare Pages.
As the platform grew, preview deployments started drifting from production: build commands
changed in the dashboard without a corresponding code review, environment variables were
added by hand across branches, and the production project's root directory was accidentally
reset. Codifying the Pages project in Pulumi ensures that build config, environment variables,
and branch deploy rules are version-controlled and reproducible across staging and production.

## Context

The Pulumi Cloudflare provider (`@pulumi/cloudflare` ≥ 5.x) exposes `cloudflare.PagesProject`
which manages the full Pages project lifecycle including the build configuration, deployment
config, and environment-specific settings. Unlike wrangler Pages commands, Pulumi tracks
project state and can detect drift between what was declared and what Cloudflare actually
has configured, then reconcile on the next `pulumi up`.

## Resource Definition — cloudflare.PagesProject

The core resource maps to a Cloudflare Pages project. The `buildConfig` block defines how
Cloudflare's build system compiles the frontend on every push.

```typescript
// infra/pages/index.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const config = new pulumi.Config();
const accountId = config.requireSecret("cloudflareAccountId");

const waspPages = new cloudflare.PagesProject("example project-frontend", {
  accountId,
  name: "example project-app",
  productionBranch: "main",

  buildConfig: {
    buildCommand:       "npm run build",
    destinationDir:     "out",          // Next.js static export output dir
    rootDir:            "/",            // repo root; set to "apps/web" for monorepos
    webAnalyticsTag:    "",             // leave blank to avoid injecting analytics JS
    buildCaching:       true,           // reuse node_modules cache between builds
  },

  source: {
    type: "github",
    config: {
      owner:                     "example project-app",
      repoName:                  "example project-frontend",
      productionBranch:          "main",
      prCommentsEnabled:         true,
      deploymentsEnabled:        true,
      previewDeploymentSetting:  "custom",        // only named branches get previews
      previewBranchIncludes:     ["staging", "feat/*"],
      previewBranchExcludes:     ["dependabot/*"],
    },
  },
});
```

## Configuration — Environment Variables per Deployment Context

Pages environment variables are scoped to `production` or `preview`. Sensitive values are
marked `secret: true` so they are encrypted at rest and never returned by the API in plaintext.

```typescript
const waspPagesWithEnv = new cloudflare.PagesProject("example project-frontend-env", {
  accountId,
  name: "example project-app",
  productionBranch: "main",

  buildConfig: {
    buildCommand:   "npm run build",
    destinationDir: "out",
    buildCaching:   true,
  },

  deploymentConfigs: {
    production: {
      environmentVariables: {
        NEXT_PUBLIC_API_URL:     { value: "https://api.example.com" },
        NEXT_PUBLIC_ENV:         { value: "production" },
        NEXT_PUBLIC_SENTRY_DSN:  { value: config.require("sentryDsnProd") },
      },
      secrets: {
        // Secrets are write-only; Pulumi cannot read them back to diff
        INTERNAL_API_SECRET: { value: config.requireSecret("internalApiSecret") },
      },
      compatibilityDate:  "2025-09-01",
      compatibilityFlags: ["nodejs_compat"],
      failOpen:           false,  // block requests if the Pages Function throws
    },
    preview: {
      environmentVariables: {
        NEXT_PUBLIC_API_URL: { value: "https://api-staging.example.com" },
        NEXT_PUBLIC_ENV:     { value: "preview" },
      },
      compatibilityDate:  "2025-09-01",
      compatibilityFlags: ["nodejs_compat"],
      failOpen:           true,   // allow degraded UX in preview rather than hard-blocking
    },
  },
});

// Export the Pages URL for downstream DNS CNAME target
export const pagesUrl = waspPagesWithEnv.subdomain;
```

## CI Integration — Pulumi Preview on PRs, Up on Merge

```yaml
# .github/workflows/pages-pulumi.yml
name: Cloudflare Pages Project IaC

on:
  pull_request:
    branches: [main]
    paths: ["infra/pages/**"]
  push:
    branches: [main]
    paths: ["infra/pages/**"]

jobs:
  preview:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
        working-directory: infra/pages

      - uses: pulumi/actions@v5
        with:
          command: preview
          stack-name: org/example project/production
          work-dir: infra/pages
          comment-on-pr: true          # posts diff as a PR comment
          comment-on-summary: true
        env:
          PULUMI_ACCESS_TOKEN:      ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN:     ${{ secrets.CF_API_TOKEN }}
          PULUMI_CONFIG_PASSPHRASE: ${{ secrets.PULUMI_PASSPHRASE }}

  deploy:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
        working-directory: infra/pages
      - uses: pulumi/actions@v5
        with:
          command: up
          stack-name: org/example project/production
          work-dir: infra/pages
        env:
          PULUMI_ACCESS_TOKEN:      ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN:     ${{ secrets.CF_API_TOKEN }}
          PULUMI_CONFIG_PASSPHRASE: ${{ secrets.PULUMI_PASSPHRASE }}
          PULUMI_VAR_sentryDsnProd: ${{ secrets.SENTRY_DSN_PROD }}
          PULUMI_VAR_internalApiSecret: ${{ secrets.INTERNAL_API_SECRET }}
```

## Custom Domains via cloudflare_pages_domain

Pages custom domains are a separate resource that must be created after the project exists.

```typescript
// Attach the production custom domain
const prodDomain = new cloudflare.PagesDomain("example project-prod-domain", {
  accountId,
  projectName: waspPagesWithEnv.name,
  domain:      "example.com",
}, { dependsOn: [waspPagesWithEnv] });

// Attach the www redirect domain
const wwwDomain = new cloudflare.PagesDomain("example project-www-domain", {
  accountId,
  projectName: waspPagesWithEnv.name,
  domain:      "www.example.com",
}, { dependsOn: [waspPagesWithEnv] });

export const prodDomainStatus = prodDomain.status;
```

After `pulumi up`, the domain status will be `initializing` then `active` once Cloudflare
verifies DNS. Ensure a CNAME record pointing `example.com` → `example project-app.pages.dev` exists
(managed in the DNS stack, not here).

## Anti-patterns

- Managing Pages project config via the Cloudflare dashboard and Pulumi simultaneously — the
  dashboard will overwrite Pulumi-managed config on the next Pages build if someone clicks
  "Save"; use Pulumi as the single source of truth and remove dashboard edit permissions.
- Storing plaintext secrets in `environmentVariables` instead of `secrets` — environment
  variable values are visible in the Pages deployment log; secrets are redacted.
- Using `buildCaching: false` in production — cold builds take 2-4x longer; only disable
  caching to debug stale dependency issues.
- Setting `previewDeploymentSetting: "all"` — all branches get preview deployments including
  Dependabot PRs, exhausting the Pages deployment quota quickly.
- Putting the Pulumi Pages stack in the same directory as application code — infra and app
  code should have separate `package.json` and CI pipelines to avoid lock-step deploys.

## Gotchas

- Pulumi cannot read back `secrets` values once written (Cloudflare returns them masked);
  Pulumi will always show secrets as "changed" in `preview` unless you use `ignoreChanges`.
- Changing `productionBranch` on an existing project requires destroying and recreating it;
  Cloudflare does not support in-place branch changes through the API.
- `buildCaching` is a project-level toggle; it cannot be overridden per branch.
- The `source.config.repoName` must exactly match the GitHub repository name (case-sensitive).
- Custom domains require the Pages project to have at least one successful deployment before
  `cloudflare_pages_domain` can transition from `initializing` to `active`.

## Verification

```bash
# Confirm project config matches Pulumi state
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/example project-app" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '{name, production_branch, build_config}'

# Check custom domain status
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/example project-app/domains" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {domain: .name, status}'

# Trigger a manual deployment to verify build config
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/example project-app/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result | {id, url, environment}'
```

## Related

- `terraform-cloudflare-pages-deployment.md` — Terraform equivalent for Pages deployments
- `next-static-export-pages.md` — Next.js static export configuration for Pages
- `cloudflare-workers-api-token-scoping.md` — scoping tokens for Pages project management
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — managing Workers alongside Pages

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/api-docs/pagesproject/
- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://developers.cloudflare.com/pages/configuration/preview-deployments/
- https://developers.cloudflare.com/pages/functions/bindings/
