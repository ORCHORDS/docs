# Server-Side Pre-Receive Hooks for Cloudflare Workers CI Gates

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Client-side git hooks (pre-commit, pre-push) are easily bypassed with `--no-verify`. The team needs server-side enforcement that prevents broken `wrangler.toml` configs, missing secrets declarations, or commits directly to `main` from ever landing in the remote repository, regardless of how the developer pushed.

## Context

Pre-receive hooks run on the git server before any ref is updated. On GitHub Enterprise Server and self-hosted Gitea/Forgejo instances they are supported natively. On GitHub.com they are not available — the closest equivalents are branch protection rules and GitHub Actions status checks configured as required. This article covers the self-hosted case (Gitea/GitHub Enterprise) with a fallback pattern for GitHub.com using a required check approach that mimics the same gate semantics. The hooks are shell scripts that receive a list of ref updates on stdin and exit non-zero to reject the entire push.

## Writing a Pre-Receive Hook Script

A pre-receive hook receives lines of `<old-sha> <new-sha> <ref-name>` on stdin. Use this to enforce Cloudflare Workers-specific invariants:

```bash
#!/usr/bin/env bash
# hooks/pre-receive
# Install to: /path/to/project
set -euo pipefail

PROTECTED_BRANCHES=("refs/heads/main" "refs/heads/release/*")
WRANGLER_CONFIG_GLOB="**/wrangler.toml"

reject() {
  echo "REJECTED: $1" >&2
  exit 1
}

while IFS=' ' read -r old_sha new_sha ref_name; do
  # 1. Block direct pushes to protected branches that bypass PRs
  for protected in "${PROTECTED_BRANCHES[@]}"; do
    if [[ "$ref_name" == $protected ]]; then
      reject "Direct push to $ref_name is not allowed. Open a pull request."
    fi
  done

  # 2. Validate wrangler.toml in every new or modified file in the push
  if [[ "$old_sha" == "0000000000000000000000000000000000000000" ]]; then
    range="$new_sha"
  else
    range="$old_sha..$new_sha"
  fi

  changed_configs=$(git diff --name-only "$range" | grep -E 'wrangler\.toml$' || true)
  for config_path in $changed_configs; do
    content=$(git show "$new_sha:$config_path" 2>/dev/null || true)
    if [[ -z "$content" ]]; then
      continue
    fi

    # Require 'name' field
    if ! echo "$content" | grep -qE '^name\s*='; then
      reject "$config_path is missing required 'name' field"
    fi

    # Require 'compatibility_date' field
    if ! echo "$content" | grep -qE '^compatibility_date\s*='; then
      reject "$config_path is missing required 'compatibility_date' field"
    fi

    # Forbid hardcoded secrets in [vars] section
    if echo "$content" | grep -qE '(TOKEN|SECRET|PASSWORD|KEY)\s*=\s*"[^"]+"'; then
      reject "$config_path contains a hardcoded secret in [vars]. Use wrangler secret put instead."
    fi
  done
done

exit 0
```

## Enforcing Wrangler Config Integrity on Push

Extend the hook to validate `compatibility_date` is not stale (older than one year) and that `workers_dev = false` is set for production workers that should not be exposed via the `*.workers.dev` subdomain:

```bash
#!/usr/bin/env bash
# Appended to the pre-receive hook above

validate_wrangler_toml() {
  local sha="$1"
  local path="$2"
  local content
  content=$(git show "$sha:$path")

  # Extract compatibility_date value
  local compat_date
  compat_date=$(echo "$content" | grep -E '^compatibility_date' | \
    sed 's/.*=\s*"\(.*\)"/\1/' | tr -d ' ')

  if [[ -n "$compat_date" ]]; then
    local compat_epoch today_epoch cutoff_epoch
    compat_epoch=$(date -d "$compat_date" +%s 2>/dev/null || echo 0)
    today_epoch=$(date +%s)
    # Warn if compatibility_date is more than 365 days old
    cutoff_epoch=$(( today_epoch - 365 * 86400 ))
    if [[ "$compat_epoch" -lt "$cutoff_epoch" ]]; then
      echo "WARNING: $path has a compatibility_date older than 1 year ($compat_date)." >&2
      echo "  Run 'wrangler deploy --compatibility-date $(date +%Y-%m-%d)' to update." >&2
    fi
  fi

  # Production workers must disable the workers.dev route
  if echo "$content" | grep -qE '^workers_dev\s*=\s*true'; then
    echo "REJECTED: $path sets workers_dev = true. Production workers must use custom routes." >&2
    return 1
  fi
}

# Call from inside the main while loop above:
# validate_wrangler_toml "$new_sha" "$config_path" || exit 1
```

Register the hook on a Gitea instance:

```bash
# On the Gitea server as the git user
REPO_PATH="/path/to/project
cp hooks/pre-receive "$REPO_PATH/hooks/pre-receive"
chmod +x "$REPO_PATH/hooks/pre-receive"

# Test the hook with a dry-run push from a developer machine
git push --dry-run origin feature/my-branch
```

## GitHub.com Equivalent: Required Status Check Gate

On GitHub.com, replace the server-side hook with a required GitHub Actions status check that runs the same validations:

```yaml
# .github/workflows/wrangler-config-gate.yml
name: Wrangler Config Gate

on:
  pull_request:
    paths:
      - '**/wrangler.toml'

jobs:
  validate-wrangler-config:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Find changed wrangler.toml files
        id: changed
        run: |
          files=$(git diff --name-only origin/${{ github.base_ref }}...HEAD | \
                  grep 'wrangler\.toml$' | tr '\n' ' ')
          echo "files=$files" >> "$GITHUB_OUTPUT"

      - name: Validate each wrangler.toml
        run: |
          for f in ${{ steps.changed.outputs.files }}; do
            echo "Validating $f..."
            grep -qE '^name\s*=' "$f" || { echo "Missing name in $f"; exit 1; }
            grep -qE '^compatibility_date\s*=' "$f" || \
              { echo "Missing compatibility_date in $f"; exit 1; }
            grep -qE '(TOKEN|SECRET|PASSWORD|KEY)\s*=\s*"[^"]+"' "$f" && \
              { echo "Hardcoded secret in $f"; exit 1; } || true
          done
          echo "All wrangler.toml files passed validation."
```

Mark `validate-wrangler-config` as a required status check in **Settings → Branches → Branch protection rules** for `main`.

## Anti-patterns

- Relying solely on client-side `pre-commit` or `pre-push` hooks for security-sensitive checks — they are skipped with `--no-verify` and are not enforced for CI bots.
- Writing pre-receive hooks in Python or Node.js and expecting those runtimes to be available on the git server — keep hooks in bash for maximum portability.
- Exiting non-zero from a pre-receive hook inside the `while read` loop without also printing the rejection reason — git swallows hook stderr unless you write to it explicitly.
- Running `wrangler validate` inside the pre-receive hook using the CLI — the hook runs on the server and `wrangler` binary may not be installed there; parse the TOML with grep/awk instead.

## Gotchas

- Pre-receive hooks run as the `git` system user on self-hosted servers — they do not have access to developer environment variables or Cloudflare credentials, so avoid any hook that calls `wrangler` commands requiring authentication.
- On Gitea, a hook that takes longer than the server's `[git] TIMEOUT` setting (default 360 seconds) is killed and the push is allowed through silently — keep hook execution under 10 seconds.
- When using GitHub Enterprise Server, pre-receive hook scripts must be uploaded via the admin console or the `ghe-repo-admin-hook` API, not by direct filesystem access to the `.git/hooks/` directory.

## Verification

```bash
# Attempt to push a wrangler.toml with a missing name field — should be rejected
git stash
echo -e 'compatibility_date = "2026-01-01"\nworkers_dev = false' > /tmp/bad.toml
cp /tmp/bad.toml workers/test-worker/wrangler.toml
git add workers/test-worker/wrangler.toml
git commit -m "test: bad wrangler config"
git push origin test/hook-validation
# Expected output: REJECTED: workers/test-worker/wrangler.toml is missing required 'name' field
git reset --hard HEAD~1

# Confirm the hook is executable on the server
ssh git@gitserver "ls -la /path/to/project
```

## Related

- `worktree/git-hooks-2026.md`
- `worktree/branch-protection-codeowners-2026.md`
- `worktree/wrangler-environments-staging-production.md`
- `worktree/secret-scanning-2026.md`

## Sources

- https://git-scm.com/docs/githooks#pre-receive
- https://docs.gitea.com/administration/git-hooks
- https://docs.github.com/en/enterprise-server/admin/policies/enforcing-policies-for-your-enterprise/enforcing-repository-management-policies
