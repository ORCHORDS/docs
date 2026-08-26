# Destructive Git Force-Push: How to Recover from Data Loss

## Symptom

You've executed a `git push --force` or `git push --force-with-lease` to a shared branch, only to discover that commits have been permanently deleted from the remote repository. Your colleagues' work is gone, and you're staring at a broken build pipeline or missing feature branches.

## Gotchas

Force-pushing to shared branches is one of Git's most dangerous operations. Unlike regular pushes that add new commits, force-pushes rewrite history by replacing existing commits with new ones. When multiple developers work on the same branch, this can silently overwrite others' work without warning.

The damage is particularly severe because Git's default behavior doesn't warn you about destructive operations. You can easily lose hours of work from multiple team members in a single command. Additionally, force-pushes don't automatically trigger branch protection rules that might otherwise prevent such destructive changes.

## Recovery Strategies

### Using Reflog
If you're lucky and the branch was recently modified, use `git reflog` to find the lost commits:
```bash
git reflog
git checkout <commit-hash>
git checkout -b recovered-branch
git push origin recovered-branch
```

### Remote Branch Recovery
Check remote reflog if your Git server supports it:
```bash
git ls-remote --heads origin
git fetch origin
git checkout <commit-hash>
```

## Prevention

### Configure Defaults
Set safer defaults in your `.gitconfig`:
```ini
[push]
  default = simple
[receive]
  denyCurrentBranch = ignore
```

### Branch Protection
Enable branch protection rules on your Git server to prevent force-pushes to critical branches. Most platforms (GitHub, GitLab, Bitbucket) offer this feature.

### Team Workflow
Establish clear guidelines: never force-push to shared branches unless absolutely necessary. Use feature branches and pull requests instead. Always communicate with your team before force-pushing.

## Practical Example

```bash
# Before force-pushing, always check what you're about to lose:
git log --oneline --graph --all

# If you must force-push, create a backup branch first:
git checkout -b backup-branch
git push origin backup-branch

# Then proceed with your destructive operation
git push --force-with-lease origin main
```

The key is prevention through proper workflow and understanding Git's history rewriting capabilities
