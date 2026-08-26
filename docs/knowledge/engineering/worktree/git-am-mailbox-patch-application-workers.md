# Applying Email Patches to Cloudflare Workers Monorepos with git am

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A security researcher sends a fix as a `.patch` file attachment, or a vendor backports a change from upstream OSS and emails it in mbox format. You need to apply the patch cleanly to a Workers monorepo, preserve authorship for audit trails, and trigger the right CI pipeline without creating a messy merge commit.

## Context

`git am` (apply mailbox) reads one or more patch files in Unix mbox format—exactly what `git format-patch` produces—and applies each as a real commit preserving the original author, date, and commit message. In a Cloudflare Workers monorepo this matters because patch provenance is required by SOC 2 audit logs, and the standard `git apply` alternative strips commit metadata. The workflow is especially common when coordinating hotfixes across organizations that do not share a GitHub account, when applying upstream patches to pinned third-party Workers shared libraries, or when a contractor cannot push directly to the repo and must send changes out-of-band.

## Generating a Patch with git format-patch

On the sender's side, generate the mbox-compatible patch from a branch or commit range:

```bash
# Single commit as one patch file
git format-patch -1 HEAD --stdout > fix-rate-limiter-kv-ttl.patch

# Range of commits (e.g. a full feature branch off main)
git format-patch main..HEAD -o /tmp/patches/

# Include binary files (e.g. wasm assets bundled into a Worker)
git format-patch -1 HEAD --binary --stdout > fix-with-wasm.patch

# Add a cover letter for multi-patch series
git format-patch main..HEAD --cover-letter -o /tmp/patches/
# Edit /tmp/patches/0000-cover-letter.patch, then send the whole dir
```

## Applying the Patch with git am

On the receiver's side, apply the patch to a clean branch:

```bash
# Create an isolation branch first — never apply directly to main
git switch -c patch/fix-rate-limiter-kv-ttl origin/main

# Apply a single patch file
git am fix-rate-limiter-kv-ttl.patch

# Apply a directory of numbered patches in order
git am /tmp/patches/*.patch

# Apply with 3-way merge fallback (safer in large monorepos)
git am --3way fix-rate-limiter-kv-ttl.patch

# Preserve commit timestamps from the patch
git am --committer-date-is-author-date fix-rate-limiter-kv-ttl.patch

# Apply and sign-off (records your review in the commit message)
git am --signoff fix-rate-limiter-kv-ttl.patch
```

## Resolving Conflicts During git am

When context lines no longer match, `git am` stops and leaves the repo in a suspended state:

```bash
# See which file conflicted
git status

# Option A: fix conflicts manually, then continue
git add packages/rate-limiter/src/kv.ts
git am --continue

# Option B: skip this patch and move to the next (use with care)
git am --skip

# Option C: abort entirely and return to clean state
git am --abort

# Increase fuzz factor if whitespace or context changed slightly
git am --3way --whitespace=fix fix-rate-limiter-kv-ttl.patch

# Re-apply with more context tolerance
git am -C1 fix-rate-limiter-kv-ttl.patch
```

## CI Integration After Applying

Once the patch applies cleanly, push the isolation branch and open a PR so the standard Workers CI pipeline validates it:

```bash
# Push the patched branch
git push origin patch/fix-rate-limiter-kv-ttl

# Confirm authorship metadata carried through (important for audit)
git log --format="%H %an <%ae> %ad" -1

# Run monorepo affected detection before the PR
pnpm turbo run test --filter=...[origin/main]

# In GitHub Actions the patch branch triggers the same wrangler deploy preview
# as any feature branch — no special-casing needed
gh pr create \
  --title "fix(rate-limiter): correct KV TTL overflow [patch]" \
  --body "Patch sourced from security@vendor.example — applied via git am" \
  --base main
```

## Verifying Patch Integrity Before Applying

```bash
# Inspect the patch without applying
git apply --stat fix-rate-limiter-kv-ttl.patch

# Dry-run: check if the patch would apply cleanly
git apply --check fix-rate-limiter-kv-ttl.patch

# Verify PGP signature if the sender signs patches
gpg --verify fix-rate-limiter-kv-ttl.patch

# Confirm the patch targets the right packages in the monorepo
grep "^--- a/" fix-rate-limiter-kv-ttl.patch
```

## Anti-patterns

- Applying patches directly to `main` without an isolation branch—if `git am` fails mid-series the working tree is left dirty and `git status` is confusing.
- Using `git apply` instead of `git am` when authorship provenance matters; `git apply` stages changes but creates no commit, so the original author is lost.
- Sharing patches as plain `.diff` files rather than mbox format—`git am` requires the `From ` envelope line and headers (`From:`, `Date:`, `Subject:`) to reconstruct commit metadata.
- Running `git am` on a branch with uncommitted local changes—always start from a clean working tree or `git stash` first.

## Gotchas

- Patch files generated on Windows may have CRLF line endings; pass `--whitespace=fix` or strip them with `sed -i 's/\r//' *.patch` before applying.
- The `--3way` flag requires the base commit the patch was generated against to be reachable in your local repository; if the repo was shallow-cloned in CI, deepen it first with `git fetch --deepen=100`.
- `git am` ignores the `GIT_COMMITTER_DATE` env var by default; pass `--committer-date-is-author-date` explicitly if your audit tooling compares committer and author timestamps.

## Verification

```bash
# Confirm the patch landed as a real commit with original author
git log --oneline -5
git show --stat HEAD

# Check the committer vs author fields are both present
git cat-file commit HEAD | head -10

# Ensure CI workflow triggered on the patch branch
gh run list --branch patch/fix-rate-limiter-kv-ttl --limit 5

# Verify the affected Worker package builds
pnpm --filter @monorepo/rate-limiter build
```

## Related

- `worktree/git-cherry-pick-2026.md`
- `worktree/git-hooks-husky-lint-staged-commitlint.md`
- `worktree/hotfix-process.md`
- `worktree/github-actions-wrangler-deploy-pipeline.md`

## Sources

- https://git-scm.com/docs/git-am
- https://git-scm.com/docs/git-format-patch
- https://developers.cloudflare.com/workers/wrangler/
