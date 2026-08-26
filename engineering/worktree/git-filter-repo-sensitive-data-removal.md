# Removing Sensitive Data from Git History with filter-repo

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A developer accidentally committed a Cloudflare API token, Wrangler secret, or `.dev.vars` file into the repository. The secret has been rotated, but the value still lives in git history and must be purged before the repo can be shared or made public.

## Context

`git filter-branch` is the legacy approach and is slow, error-prone, and officially deprecated. `git filter-repo` is the BFG-alternative blessed by the git project: it rewrites history in a single pass, preserves grafts and replace refs, and produces clean ref-logs. For Cloudflare Workers monorepos the typical offenders are `.dev.vars`, `wrangler.toml` values inlined with `[vars]`, and raw `CF_API_TOKEN` strings that crept into CI scripts.

## Installing filter-repo

`git filter-repo` is a standalone Python script distributed via pip or packaged in most distros. Pin the version in your devcontainer so CI can reproduce the rewrite deterministically.

```bash
pip install git-filter-repo==2.45.0

# Verify
git filter-repo --version
# 2.45.0

# In CI (GitHub Actions)
- name: Install filter-repo
  run: pip install --quiet git-filter-repo==2.45.0
```

Clone a **fresh mirror** before rewriting — never rewrite in-place against a working checkout that teammates are using.

```bash
git clone --mirror git@github.com:org/workers-monorepo.git workers-monorepo-mirror
cd workers-monorepo-mirror
```

## Identifying and Removing Secrets

Use `git filter-repo --analyze` first to audit blobs without mutating anything. The report lands in `.git/filter-repo/analysis/`.

```bash
git filter-repo --analyze
cat .git/filter-repo/analysis/path-all-sizes.txt | head -30
```

Remove a literal secret string across all commits and all branches with `--replace-text`. Create a replacements file:

```bash
# replacements.txt — one pattern per line
# Literal strings are matched exactly; regex requires "regex:" prefix
CF_API_TOKEN=abc123secretvalue==>CF_API_TOKEN=REMOVED
wrangler-secret-value-xyz==>REMOVED
```

```bash
git filter-repo \
  --replace-text replacements.txt \
  --force
```

To remove an entire file path (e.g. a committed `.dev.vars`):

```bash
git filter-repo \
  --path .dev.vars \
  --invert-paths \
  --force

# Multiple paths at once
git filter-repo \
  --path-glob '**/.dev.vars' \
  --path 'workers/api/.env.production' \
  --invert-paths \
  --force
```

## Distributing the Rewritten History

After rewriting, force-push all refs. Because the mirror has no remote named `origin` yet, re-add it:

```bash
# Inside the mirror clone
git remote add origin git@github.com:org/workers-monorepo.git
git push --mirror --force
```

Every contributor **must** re-clone or hard-reset their local copy — rebasing onto the new history is not safe:

```bash
# Communicate this to the team, then each dev runs:
cd workers-monorepo
git fetch origin
git reset --hard origin/main
# Or: delete local clone and re-clone fresh
```

In GitHub, go to **Settings → Branches → Branch protection** and temporarily disable "Require linear history" if it blocks the force-push, then re-enable it afterwards.

Invalidate any GitHub caches of the old commits:

```bash
# Contact GitHub Support with the list of old SHAs to purge from their CDN cache
# Alternatively, make the repository private during the purge window
```

## Anti-patterns

- Running `git filter-repo` directly on the main working clone instead of a mirror — this corrupts the working tree and remote-tracking refs.
- Using `git filter-branch` because it is "already installed" — it is 100x slower and leaves `refs/original/` polluters behind.
- Only removing the file from the latest commit with `git rm` and a new commit — the blob still exists in all prior history and is accessible via `git show <old-sha>:path`.
- Not rotating the secret before the purge — the rewrite invalidates the history, but if the credential was ever cloned or cached by GitHub Actions it is already compromised.

## Gotchas

- GitHub retains cached views of old commits for up to 90 days after a force-push. Open a support ticket to request immediate cache invalidation for sensitive blobs.
- `--replace-text` operates on raw bytes; if the secret appears in a binary blob (e.g. a compiled WASM file checked into the repo) it will still be rewritten, but the binary may become corrupt — verify with `wasm-validate` afterwards.
- Contributors who have local branches based on old commits will get diverged histories. Provide a migration script so they do not accidentally re-introduce old commits via `git merge`.

## Verification

```bash
# Confirm the secret string no longer appears in any blob reachable from any ref
git log --all --full-history -- '**/.dev.vars'
# Expected: no output

# Search raw blobs
git rev-list --all | xargs git grep -l 'CF_API_TOKEN=abc123secretvalue'
# Expected: no output

# Confirm filter-repo analysis shows no remaining match
git filter-repo --analyze
grep 'abc123secretvalue' .git/filter-repo/analysis/blob-shas-and-paths.txt
# Expected: no output
```

## Related

- `worktree/secret-scanning-2026.md`
- `worktree/signed-commits-2026.md`
- `worktree/git-hooks-2026.md`

## Sources

- https://htmlpreview.github.io/?https://github.com/newren/git-filter-repo/blob/docs/html/git-filter-repo.html
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- https://developers.cloudflare.com/workers/wrangler/secrets/
