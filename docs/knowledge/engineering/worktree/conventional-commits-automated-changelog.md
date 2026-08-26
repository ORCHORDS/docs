# Conventional Commits + Automated Changelog for Cloudflare Workers

Date:   2026-08-22
Author: example.com
Status: stable

## Symptom

Releases are named arbitrarily ("v2 final", "hotfix-revert"), changelogs
are hand-written and drift from reality, and Cloudflare Workers deployments
carry no meaningful version string that ops teams can trace back to a
commit. Automated tooling fails because commit messages have no parseable
structure.

## Context

The Conventional Commits specification (conventionalcommits.org) defines a
lightweight message grammar on top of Git. Tools like `commitlint`,
`semantic-release`, and `release-please` read that grammar to derive
version bumps (semver), generate CHANGELOG.md, create GitHub Releases, and
trigger downstream actions such as a tagged Wrangler deploy.

Cloudflare Workers expose the `CF_VERSION_METADATA` binding in v8 isolates,
letting running Workers know their own deploy version. Coupling that with a
semver Git tag closes the observability loop: every request can report its
release version.

---

## 1. Commit Message Grammar

```
<type>(<optional scope>): <description>

[optional body]

[optional footer(s)]
```

Core types and their semver impact:

```
┌─────────────┬─────────────────────────────────┬────────────┐
│ Type        │ Meaning                         │ Bump       │
├─────────────┼─────────────────────────────────┼────────────┤
│ feat        │ new capability                  │ MINOR      │
│ fix         │ bug correction                  │ PATCH      │
│ perf        │ performance improvement         │ PATCH      │
│ refactor    │ code restructure, no behaviour  │ none       │
│ docs        │ documentation only              │ none       │
│ test        │ add or fix tests                │ none       │
│ chore       │ tooling, deps, CI               │ none       │
│ BREAKING    │ footer "BREAKING CHANGE:" or !  │ MAJOR      │
└─────────────┴─────────────────────────────────┴────────────┘
```

Breaking change syntax (either form is valid):

```
feat!: remove legacy KV namespace binding

feat(auth): migrate to R2 token store

BREAKING CHANGE: KV_AUTH binding is no longer read at startup.
Existing workers must update wrangler.toml before deploying.
```

Scopes are project-defined. Recommended scopes for a Workers+Pages
monorepo: `worker`, `pages`, `api`, `db`, `auth`, `ci`.

---

## 2. commitlint Configuration

Install:

```bash
pnpm add -D @commitlint/cli @commitlint/config-conventional
```

`commitlint.config.cjs` at the repo root:

```js
/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Enforce known scopes; remove if you prefer freeform.
    'scope-enum': [
      2,
      'always',
      ['worker', 'pages', 'api', 'db', 'auth', 'ci', 'deps'],
    ],
    'header-max-length': [2, 'always', 100],
    'body-max-line-length': [1, 'always', 100],
  },
};
```

Wire it into Husky so every local commit is validated:

```bash
pnpm add -D husky
pnpm exec husky init
echo "pnpm exec commitlint --edit \$1" > .husky/commit-msg
chmod +x .husky/commit-msg
```

Validate the last commit manually:

```bash
pnpm exec commitlint --from HEAD~1 --to HEAD --verbose
```

---

## 3. release-please Integration (Recommended)

`release-please` is Google's tool that opens a Release PR whenever
releasable commits land on the main branch. Merging the PR creates the
GitHub Release and Git tag. It integrates cleanly with Cloudflare Workers
because it does not publish to npm unless explicitly told to.

`.github/workflows/release-please.yml`:

```yaml
name: Release Please

on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    outputs:
      release_created: ${{ steps.rp.outputs.release_created }}
      tag_name:        ${{ steps.rp.outputs.tag_name }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: rp
        with:
          release-type: node
          # Monorepo: use manifest mode instead.
          # config-file: release-please-config.json
          # manifest-file: .release-please-manifest.json
```

After a release is created, trigger a tagged deploy:

```yaml
  deploy-worker:
    needs: release-please
    if: needs.release-please.outputs.release_created == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm install --frozen-lockfile
      - name: Deploy tagged Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          RELEASE_TAG: ${{ needs.release-please.outputs.tag_name }}
        run: |
          # Embed the version so the Worker can self-report it.
          echo "RELEASE_VERSION=$RELEASE_TAG" >> worker/.env.deploy
          pnpm exec wrangler deploy \
            --config worker/wrangler.toml \
            --env production
```

`release-please-config.json` for monorepo manifest mode:

```json
{
  "packages": {
    "worker":   { "release-type": "node", "changelog-path": "CHANGELOG.md" },
    "frontend": { "release-type": "node", "changelog-path": "CHANGELOG.md" }
  },
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"
}
```

---

## 4. Embedding the Release Version in a Worker

`wrangler.toml` (production environment):

```toml
[vars]
RELEASE_VERSION = "0.0.0"   # overwritten by CI via --var flag
```

CI step that injects the real version at deploy time:

```bash
pnpm exec wrangler deploy \
  --config worker/wrangler.toml \
  --env production \
  --var RELEASE_VERSION:"$RELEASE_TAG"
```

Reading it inside the Worker:

```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return new Response(null, {
      headers: { 'X-Worker-Version': env.RELEASE_VERSION },
    });
  },
};
```

For finer-grained traceability, combine with `CF_VERSION_METADATA`:

```toml
[version_metadata]
binding = "CF_VERSION"
```

```ts
// env.CF_VERSION.id is Cloudflare's internal deploy UUID.
// env.RELEASE_VERSION is our semver tag.
```

---

## 5. Changelog Structure

`release-please` writes a keep-a-changelog-style file automatically.
If you use `semantic-release` instead, configure the changelog plugin:

```js
// release.config.cjs
module.exports = {
  branches: ['main'],
  plugins: [
    '@semantic-release/commit-analyzer',
    '@semantic-release/release-notes-generator',
    ['@semantic-release/changelog', { changelogFile: 'CHANGELOG.md' }],
    ['@semantic-release/git', { assets: ['CHANGELOG.md', 'package.json'] }],
    '@semantic-release/github',
  ],
};
```

Example generated CHANGELOG entry:

```markdown
## [1.4.0] - 2026-08-22

### Features
- **worker**: add R2 signed URL generation endpoint (#87)
- **auth**: migrate to Workers KV session store (#91)

### Bug Fixes
- **api**: return 404 instead of 500 for missing D1 rows (#93)

### BREAKING CHANGES
- **db**: D1 binding renamed from DB to MAIN_DB; update wrangler.toml
```

---

## Anti-patterns

- Writing "fix" or "update" with no scope or body; changelogs become
  useless noise with no context.
- Combining unrelated changes in one commit to skip a bump. Atomic commits
  per concern are a hard requirement of this workflow.
- Skipping `commitlint` in CI (only running it locally). Always add a
  `commitlint` job in the PR workflow so bots and contributors are covered.
- Using `semantic-release` to publish npm packages from a Workers repo that
  does not actually ship a library. Prefer `release-please` for Workers.
- Hardcoding `RELEASE_VERSION = "1.0.0"` in `wrangler.toml` and never
  updating it. The version must come from the tag at deploy time.

---

## Gotchas

- `release-please` only processes commits since the last release tag. If
  you push many commits in one go with no tags, it opens one PR covering
  all of them, which is correct but can surprise teams.
- commitlint `scope-enum` rule is case-sensitive. Enforce lowercase in the
  `scope-case` rule to avoid `Worker` vs `worker` mismatch.
- Wrangler's `--var` flag does NOT persist to `wrangler.toml`; it only
  applies to the current deploy invocation. Do not rely on it for local dev.
- `CF_VERSION_METADATA` UUID changes on every Wrangler deploy, not only on
  tagged releases. Correlate it with your semver tag via a log annotation,
  not as a stable identifier.

---

## Verification

```bash
# Lint the last 10 commits (run in CI on PR branches):
pnpm exec commitlint --from HEAD~10 --to HEAD --verbose

# Dry-run release-please to preview what it would do:
npx release-please release-pr \
  --token "$GITHUB_TOKEN" \
  --repo-url owner/repo \
  --dry-run

# Confirm the version var reaches the Worker after deploy:
curl -sI https://api.example.workers.dev/ | grep x-worker-version
```

---

## Related

- documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md
- documentation/docs/policies/worktree/pr-readiness-checklist-workers-projects.md
- documentation/docs/policies/worktree/monorepo-workspace-cloudflare-workers.md
- documentation/docs/policies/worktree/git-branching-cloudflare-preview-environments.md

---

## Source URLs

- https://www.conventionalcommits.org/en/v1.0.0/
- https://github.com/googleapis/release-please
- https://github.com/conventional-changelog/commitlint
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
