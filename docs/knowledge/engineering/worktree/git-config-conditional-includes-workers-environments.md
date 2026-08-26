# git config Conditional Includes for Cloudflare Workers Environments

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A developer works across three Cloudflare Workers contexts simultaneously: a client project, an open-source Workers package, and their personal SaaS. Each requires a different git user identity (work email, OSS email, personal email), a different signing key, and different Wrangler defaults. Manually switching `git config user.email` before every commit is error-prone and causes misattributed commits that require an embarrassing rewrite with `git filter-repo`.

`git config` conditional includes (`includeIf`) solve this by loading per-directory configuration automatically — no manual switching required.

---

## Context

Git's global `~/.gitconfig` supports `[includeIf "gitdir:..."]` blocks that load an additional `.gitconfig` file when the current repository path matches a pattern. Combined with `[includeIf "hasconfig:remote.*.url:..."]` (git 2.36+) which matches on remote URL, teams can automatically apply:

- Different user identities per client/project
- Different GPG or SSH signing keys per context
- Wrangler-related environment variables via `core.hooksPath`
- Commit template paths pointing to project-specific templates
- Different push defaults per remote type

This is especially powerful for Cloudflare Workers teams where staging and production deploy credentials live in separate Cloudflare accounts.

---

## Directory-Based Conditional Includes

Structure projects under distinct parent directories, then include per-directory config:

```
~/
  work/
    client-a/
    client-b/
  oss/
    workers-package/
  personal/
    my-saas/
```

```ini
# ~/.gitconfig

[user]
  name = Dev Name
  email = dev@personal.dev
  signingKey = ~/.ssh/personal_id_ed25519.pub

[includeIf "gitdir:~/work/"]
  path = ~/.config/git/work.gitconfig

[includeIf "gitdir:~/oss/"]
  path = ~/.config/git/oss.gitconfig

[includeIf "gitdir:~/personal/"]
  path = ~/.config/git/personal.gitconfig
```

```ini
# ~/.config/git/work.gitconfig
[user]
  email = dev@company.com
  signingKey = ~/.ssh/work_id_ed25519.pub

[commit]
  gpgsign = true

[core]
  hooksPath = ~/.config/git/hooks/work
```

```ini
# ~/.config/git/oss.gitconfig
[user]
  email = dev@oss-alias.com

[commit]
  gpgsign = false

[push]
  default = current
```

---

## Remote URL-Based Conditional Includes (git 2.36+)

For scenarios where the same parent directory contains multiple clients (common in agency repos), match by remote URL instead:

```ini
# ~/.gitconfig

[includeIf "hasconfig:remote.*.url:git@github.com:client-a/**"]
  path = ~/.config/git/client-a.gitconfig

[includeIf "hasconfig:remote.*.url:git@github.com:client-b/**"]
  path = ~/.config/git/client-b.gitconfig

[includeIf "hasconfig:remote.*.url:*cloudflare-workers-oss*"]
  path = ~/.config/git/oss.gitconfig
```

```ini
# ~/.config/git/client-a.gitconfig
[user]
  email = dev@client-a.com
  signingKey = ~/.ssh/client_a_ed25519.pub

[core]
  hooksPath = ~/.config/git/hooks/client-a
```

---

## Per-Context Wrangler Defaults via Hooks

Use `core.hooksPath` to point to a directory of git hooks that export Wrangler-relevant environment variables. A `post-checkout` hook is a convenient place to print a reminder of the active Cloudflare account:

```bash
# ~/.config/git/hooks/work/post-checkout
#!/usr/bin/env bash
set -euo pipefail

ACCOUNT=$(git config --get cloudflare.accountId 2>/dev/null || echo "not configured")
echo "[workers] Active Cloudflare account: $ACCOUNT"
echo "[workers] Wrangler env: ${WRANGLER_ENV:-production}"
```

Store account IDs in the per-context gitconfig (not secrets — just identifiers):

```ini
# ~/.config/git/client-a.gitconfig
[cloudflare]
  accountId = abc123def456
```

Read them in scripts:

```typescript
// scripts/active-account.ts
import { execSync } from "node:child_process";

const accountId = execSync(
  "git config --get cloudflare.accountId",
  { encoding: "utf8" }
).trim();

if (!accountId) {
  throw new Error(
    "No cloudflare.accountId in git config. " +
    "Check ~/.config/git/<context>.gitconfig"
  );
}

console.log(`Deploying to Cloudflare account: ${accountId}`);
// Use accountId with Cloudflare API or as a guard before wrangler deploy
```

---

## Commit Templates per Workers Project

Different Workers projects have different conventional commit scopes (e.g., `feat(kv):`, `fix(d1):`). Use per-context commit templates:

```ini
# ~/.config/git/client-a.gitconfig
[commit]
  template = ~/.config/git/templates/client-a-commit.txt
```

```text
# ~/.config/git/templates/client-a-commit.txt
# <type>(<scope>): <subject>
#
# Types: feat | fix | perf | refactor | docs | test | chore
# Scopes: worker | d1 | kv | r2 | queue | pages | wrangler | deps
#
# Body (optional):
#
# Footer (optional):
# Refs: #<issue>
# Breaking-change: <description>
```

---

## Verifying Which Config is Active

```bash
# Show the effective config for the current repository (with origins)
git config --list --show-origin | grep -E "(user\.|core\.hooks|cloudflare)"

# Example output:
# file:/path/to/project         user.email=dev@personal.dev
# file:/path/to/project  user.email=dev@company.com
# file:/path/to/project  core.hookspath=/path/to/project

# The LAST value for a key wins — so work.gitconfig overrides ~/.gitconfig
git config user.email
# dev@company.com  ✓
```

---

## GitHub Actions: No Conditional Includes Needed

Conditional includes are a local-developer tool. In CI, set git identity directly in the workflow:

```yaml
# .github/workflows/wrangler-deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure git identity for deploy commit
        run: |
          git config user.email "ci-bot@company.com"
          git config user.name "CI Deploy Bot"

      - name: Deploy Workers
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PRODUCTION }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID_PRODUCTION }}
```

---

## Anti-patterns

- **Storing secrets in gitconfig** — `cloudflare.apiToken` must never appear in any `.gitconfig`. Use gitconfig only for non-secret identifiers (account IDs, scopes). Secrets belong in a secrets manager or environment variables.
- **Using `[include]` (unconditional) instead of `[includeIf]`** — an unconditional include always applies and overrides subsequent sections, making the config order-dependent and fragile.
- **Forgetting the trailing slash in `gitdir:` patterns** — `gitdir:~/work` matches a file named `work` in the home directory, not the directory. Always use `gitdir:~/work/` with a trailing slash.
- **Sharing a `hooksPath` across contexts** — hooks that assume a specific Cloudflare account will fail silently in another context. Keep hook directories per-context.

---

## Gotchas

- `includeIf "gitdir:..."` resolves `~` to the home directory at include-evaluation time, not at parse time. On some systems, explicit absolute paths (`/path/to/project) are more reliable than tilde expansion.
- `hasconfig:remote.*.url:` was introduced in git 2.36. Older git versions silently ignore unknown `includeIf` conditions rather than erroring — always verify with `git config --list --show-origin`.
- In git worktrees, `gitdir:` matches the worktree's `.git` file path (e.g., `/repo/.git/worktrees/<name>/`), not the main repository's `.git/` path. Use `gitdir/i:` (case-insensitive) or `gitdir:` with a wildcard (`~/work/**/`) to match worktrees under a parent.
- The `core.hooksPath` from an included config applies globally for that repository. If the hooks directory does not exist, git prints a warning on every hook-triggering operation.

---

## Verification

```bash
# 1. Check which config file provides user.email in current repo
git config --show-origin user.email

# 2. Confirm signingKey is from the right context
git config --show-origin user.signingKey

# 3. Verify hook path is set and hooks directory exists
git config core.hooksPath
ls "$(git config core.hooksPath)"

# 4. Test commit signature would use the correct key
git config --show-origin gpg.format
git config --show-origin user.signingKey

# 5. Simulate a commit (no actual commit) to see the resolved identity
git commit --dry-run --allow-empty -m "test identity" 2>&1 | head -5
```

---

## Related

- `git-hooks-2026.md`
- `pre-push-hooks-comprehensive-validation.md`
- `wrangler-environments-staging-production.md`
- `signed-commits-2026.md`
- `gpg-ssh-commit-signing.md`

---

## Sources

- git-config conditional includes: https://git-scm.com/docs/git-config#_conditional_includes
- git 2.36 hasconfig: https://github.blog/open-source/git/highlights-from-git-2-36/
- Cloudflare Workers authentication: https://developers.cloudflare.com/workers/wrangler/ci-cd/
- SSH commit signing: https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgsshallowedSignersFile
