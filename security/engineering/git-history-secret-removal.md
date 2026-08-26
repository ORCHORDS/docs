# git-history-secret-removal

**Issue:** Secrets removed from HEAD still exist in git history and must be purged and rotated immediately
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A `git revert` or file deletion does not remove a secret from git history. Anyone with access to the repository can `git log -p` to find the secret. If the repository is public even briefly, assume the secret is compromised — rotation is mandatory.

## Pattern / Solution
```bash
# Step 1: ROTATE THE SECRET IMMEDIATELY — do not wait for history cleanup
# Step 2: Remove from history using git-filter-repo (preferred over BFG)

pip install git-filter-repo

# Remove a specific file from all history
git filter-repo --path secrets.env --invert-paths

# Replace a secret string everywhere in history
git filter-repo --replace-text replacements.txt
# replacements.txt:
# ACTUAL_SECRET_VALUE==>REMOVED

# Step 3: Force push (coordinate with all collaborators)
git push origin --force --all
git push origin --force --tags

# Step 4: All collaborators must re-clone — cached local histories still contain the secret
```
```bash
# BFG Repo Cleaner (alternative, faster on large repos)
java -jar bfg.jar --replace-text replacements.txt my-repo.git
cd my-repo.git && git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

## Gotchas
- GitHub caches repository data — contact GitHub Support to purge cached views after rewriting history.
- Forks retain their own copy of history — you cannot clean forks you don't control.
- CI/CD systems may have the secret cached in environment variables or artifact stores — audit all.
- `git filter-repo` requires a fresh clone — do not run on a working copy.

## Related
- `secrets-detection-pre-commit.md`
- `api-key-rotation-zero-downtime.md`
