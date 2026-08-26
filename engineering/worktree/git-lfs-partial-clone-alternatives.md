# git-lfs-partial-clone-alternatives

**Issue:** Git LFS vs partial clone vs DVC
**Date:** 2026-08-09
**Status:** documented

## Symptom
Repo has 5 GB of model weights. Clone takes 14
min. You commit another 200 MB. Costs are
mounting. You wonder if LFS is the right tool.

## Root cause
**LFS has a 100 MB file cap + 10 GB free quota.** Alternatives exist.

**Source:** GitHub Docs + blog 2026.

## The "LFS" concept

Git LFS:
- **Pointer:** Commit hash
- **Payload:** Remote server
- **Cap:** 100 MB per file
- **Free:** 10 GiB
- **Paid:** 250 GiB
- **Cost:** ~$0.07/GiB-month

The LFS is the legacy choice.

## The "partial clone" pattern

For monorepo:
- **`--filter=blob:none`:** No blobs at clone
- **`--filter=blob:limit=1m`:** Skip > 1MB
- **`--filter=tree:0`:** No tree
- **Result:** 5 GB → seconds
- **Use:** Code-only

The partial is the modern way.

## The "sparse-checkout" pattern

For scope:
```bash
git sparse-checkout init
git sparse-checkout set src/ docs/
```

The sparse is per dir.

## The "DVC" pattern

For ML:
- **Metafile:** Pointer + data
- **Storage:** S3/GCS
- **Lineage:** Pipeline tracking
- **Use:** Datasets, models
- **Why:** ML-shaped

The DVC is for ML.

## The "100 MB cap" pattern

For file:
- **Hard limit:** GitHub LFS
- **Above:** Reject
- **Fix:** S3 + DVC
- **Why:** LFS policy

The cap is enforced.

## The "quota" pattern

For budget:
- **Free:** 10 GiB
- **Paid:** 250 GiB
- **Metered:** $0.0875/GiB bandwidth
- **Alert:** 90%, 100%
- **Cap:** Set to $0 fail-closed

The quota is tracked.

## The "LFS for build artifacts" anti-pattern

For artifacts:
- **Issue:** node_modules in LFS
- **Fix:** Regenerate in CI
- **Why:** Track is wrong

The artifact is regenerated.

## The "LFS for secrets" anti-pattern

For secrets:
- **Issue:** Pointer leaks
- **Fix:** Secret manager
- **Why:** Second store

The secret is external.

## The "LFS as backup" anti-pattern

For backup:
- **Issue:** Wrong tool
- **Fix:** S3 versioning
- **Why:** DVC cheaper

The backup is S3.

## The "LFS + partial blind" anti-pattern

For mixed:
- **Issue:** Conflict
- **Fix:** Plan one
- **Why:** Both defers

The choice is one.

## The "no quota alert" anti-pattern

For overage:
- **Issue:** Bill shock
- **Fix:** Alert at 90%
- **Why:** Metered

The alert is set.

## The "decision tree" pattern

For choice:
- **Code only:** Partial clone
- **ML data:** DVC
- **Co-versioned binaries:** LFS
- **Large files:** S3 + pointer
- **Why:** Each fits

The tree is per need.

## The ".gitattributes" pattern

For control:
```
*.psd filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
```

The attribute is per type.

## The "lock" pattern

For prevent:
```bash
git lfs lock design.psd
# other users can't push to it
```

The lock is exclusive.

## The "audit" pattern

For track:
```bash
git lfs ls-files
git lfs status
```

The audit is per file.

## The "LFS checklist" pattern

For checklist:
- [ ] 100 MB cap respected
- [ ] Quota budgeted
- [ ] Alert at 90%
- [ ] Co-versioned only
- [ ] No secrets
- [ ] No artifacts
- [ ] gitattributes set
- [ ] Partial clone for code
- [ ] DVC for ML

The checklist is 9.

## Verification
- **Test:** Clone works
- **Test:** Files fetch
- **Test:** Quota tracked
- **Audit:** Monthly

## Gotchas
- **The "artifacts" anti-pattern.** Regenerate.
- **The "secrets" anti-pattern.** External.
- **The "no quota alert" anti-pattern.** Set.

## Related
- `worktree/git-submodules-vs-subtrees.md`
- `worktree/rebase-vs-merge-detail.md`
- `infra/monorepo-2026.md`
- `patterns/repository-pattern.md`
- Git LFS: https://git-lfs.github.com/
- GitHub billing: https://docs.github.com/en/billing/managing-billing-for-git-large-file-storage/about-billing-for-git-large-file-storage
- Partial clone: https://github.blog/open-source/git/introducing-partial-clone-for-monorepos/
