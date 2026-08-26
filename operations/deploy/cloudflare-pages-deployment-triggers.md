# Cloudflare Pages Deployment Triggers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need fine-grained control over when Cloudflare Pages builds run — you want some
branches to trigger production deploys, others to create preview deployments only on
pull-requests, and certain paths to be ignored entirely. You also need the ability to
kick off an out-of-band deploy from a CI system or external webhook without pushing a
new commit.

## Context

Cloudflare Pages supports three trigger categories:
- **Git push triggers** — automatic builds on push to a configured branch
- **Pull-request preview triggers** — automatic preview deployments for each PR
- **Direct Upload / Build Hook triggers** — API-driven builds, no Git event required

Configuration lives in the Pages project settings (dashboard or Wrangler) and in an
optional `wrangler.toml`. Branch include/exclude rules are glob-pattern lists. Build
hooks are project-scoped HTTPS endpoints that accept a `POST` from any caller.

---

## Git Push Trigger Configuration

### Via wrangler.toml (Pages project config)

```toml
# wrangler.toml — at repo root, used by Cloudflare Pages build system
name = "my-app"
pages_build_output_dir = "dist"

[env.production]
branch = "main"           # production trigger

[env.staging]
branch = "staging"        # separate production-grade environment

# Branch deploy controls — glob patterns
[build]
# Branches that DO trigger a build when pushed
watch_branches = ["main", "staging", "release/*"]
# Paths that, when the only changes, skip the build
ignore_paths   = ["docs/**", "*.md", ".github/**"]
```

### Via Dashboard (Settings → Builds & Deployments)

- **Production branch**: the single branch that publishes to the production URL
- **Preview branches**: any branch not matching production triggers a preview deploy
- **Branch inclusion/exclusion rules** (regex or glob)
  - Include pattern: `release/*` — only release branches get previews
  - Exclude pattern: `renovate/*` — skip dependency-update branches

---

## Pull-Request Preview Trigger Configuration

Every PR opened against a watched branch automatically triggers a preview build whose
URL is posted back as a GitHub / GitLab check status.

### GitHub Actions — Post preview URL as comment

```yaml
# .github/workflows/pages-preview.yml
name: Pages Preview URL

on:
  deployment_status:

jobs:
  comment:
    if: github.event.deployment_status.state == 'success' &&
        github.event.deployment.environment != 'Production'
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - name: Find associated PR
        id: find-pr
        uses: actions/github-script@v7
        with:
          script: |
            const { data: prs } = await github.rest.repos.listPullRequestsAssociatedWithCommit({
              owner: context.repo.owner,
              repo: context.repo.repo,
              commit_sha: context.sha,
            });
            return prs[0]?.number ?? null;

      - name: Post preview URL
        if: steps.find-pr.outputs.result != 'null'
        uses: actions/github-script@v7
        with:
          script: |
            const url = "${{ github.event.deployment_status.environment_url }}";
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: ${{ steps.find-pr.outputs.result }},
              body: `🔍 Preview deployed: ${url}`,
            });
```

### Disabling PR Previews for forks

In Dashboard → Settings → Builds & Deployments → Preview Deployments:
- Set **Preview deployment policy** to `Only preview deployments from branches within
  your repository` to block fork PRs from triggering builds.

---

## Build Hook (Manual / External) Triggers

A build hook is a project-specific secret URL. Any `POST` to it enqueues a production
or branch-scoped build.

### Creating a hook via Wrangler

```bash
# List existing hooks
wrangler pages deployment list --project-name my-app

# Build hooks are created through the API; Wrangler wraps it:
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/my-app/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"branch":"main"}'
```

### GitHub Actions — Trigger via hook on schedule

```yaml
# .github/workflows/nightly-deploy.yml
name: Nightly Pages Deploy

on:
  schedule:
    - cron: "0 2 * * *"   # 02:00 UTC every day
  workflow_dispatch:

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Cloudflare Pages build
        run: |
          curl -X POST \
            -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" \
            -H "Content-Type: application/json" \
            "https://api.cloudflare.com/client/v4/accounts/${{ secrets.CF_ACCOUNT_ID }}/pages/projects/${{ vars.CF_PAGES_PROJECT }}/deployments"
```

### Trigger script (Node.js utility)

```typescript
// scripts/trigger-pages-deploy.ts
const CF_API = "https://api.cloudflare.com/client/v4";

interface TriggerOptions {
  accountId: string;
  project: string;
  branch?: string;
  token: string;
}

export async function triggerPagesDeploy(opts: TriggerOptions): Promise<string> {
  const res = await fetch(
    `${CF_API}/accounts/${opts.accountId}/pages/projects/${opts.project}/deployments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${opts.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ branch: opts.branch ?? "main" }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Pages deploy trigger failed [${res.status}]: ${err}`);
  }

  const data = (await res.json()) as { result: { id: string; url: string } };
  console.log(`Deployment started: ${data.result.url}`);
  return data.result.id;
}
```

---

## Ignore Paths (Skipping Unnecessary Builds)

Reduce build minutes by telling Pages which file paths are irrelevant to the output.

```toml
# wrangler.toml
[build]
ignore_paths = [
  "docs/**",
  "*.md",
  "tests/**",
  ".github/**",
  "scripts/**",
  "*.test.ts",
]
```

The filter is evaluated against the diff of the triggering push. If **every** changed
file matches an ignore path, the build is skipped and no deployment is created.

---

## Anti-patterns

- **Triggering prod deploys from every branch** — use `watch_branches` to restrict
  production triggers to `main` / `release/*` only.
- **Storing build hook URLs in plain text** — treat them as secrets; they accept
  unauthenticated POSTs from anyone who has the URL.
- **Missing ignore_paths for docs** — heavy documentation repos waste build minutes
  and inflate deploy history noise.
- **Relying only on push triggers for external content** — CMS-driven sites need build
  hooks wired to the CMS publish event; a git push never comes.

## Gotchas

- Preview deployment URLs are stable per-branch (`<branch>.<project>.pages.dev`) but
  the underlying deployment ID changes on every build — permalink your smoke test URLs
  to the branch URL, not the deployment ID URL.
- Ignore paths are glob-matched against file paths relative to the repo root. A path
  like `tests` (no trailing `/**`) will NOT match `tests/unit/foo.test.ts`.
- The API-triggered deploy always uses the latest commit on the specified branch, not
  the commit that existed at hook creation time — ensure the branch is in the expected
  state before firing.
- Pages build hooks do not accept a `commit_sha` parameter; to pin a specific commit
  use the Wrangler direct upload flow instead.

## Verification

```bash
# Check most recent deployment status
wrangler pages deployment list --project-name my-app --env production | head -5

# Poll until the latest deployment is 'active'
watch -n 10 "wrangler pages deployment list --project-name my-app | head -3"

# Confirm ignored-path skip in build logs
# Dashboard → Project → Deployments → latest → Build log
# Should show: "Build skipped: all changed files matched ignore paths"
```

## Related

- `cloudflare-pages-preview-deployments.md`
- `pages-build-hook-external-trigger-ci.md`
- `cloudflare-pages-build-watch-paths-optimization.md`
- `wrangler-pages-direct-upload-ci.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://developers.cloudflare.com/pages/configuration/branch-build-controls/
- https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/create/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
