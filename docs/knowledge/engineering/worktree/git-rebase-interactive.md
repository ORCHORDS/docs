# git-rebase-interactive

Interactive rebase is a powerful Git workflow for cleaning up and organizing commit history before merging into main branches.

## Basic Usage

```bash
git rebase -i HEAD~n
```

Replace `n` with number of commits to edit. This opens an editor showing commits in reverse chronological order.

## Core Operations

### Squash (s)
Combines multiple commits into one, merging their changes and messages into a single commit. Use when you want to consolidate related changes.

### Reword (r)
Changes the commit message without modifying files. Useful for fixing typos or improving clarity.

### Reorder (move)
Changes commit order by moving lines up or down in the editor. Helps organize commits logically.

### Drop (d)
Removes commits entirely from history. Use to eliminate unnecessary or broken commits.

## Force Push Safety

Interactive rebase modifies commit history, requiring force push:
```bash
git push --force-with-lease
```

Never force push to shared branches without coordination. Use `--force-with-lease` instead of `--force` for safety.

## Golden Rule of Rebase

**Never rebase commits that have been pushed to a shared repository** unless you're certain no one else is working on them.

## Practical Workflow

1. Identify commits needing cleanup
2. Run interactive rebase: `git rebase -i HEAD~3`
3. Edit the commit list (s, r, m, d operations)
4. Save and close editor
5. Resolve any conflicts if they arise
6. Force push changes to remote repository

## Best Practices

- Always backup branches before major rebasing
- Use `git reflog` to recover if something goes wrong
- Keep rebase operations focused on a single logical change
- Communicate with team members when rebasing shared work
- Test code thoroughly after rebasing to ensure no regressions

## Common Scenarios

Squashing: Combine feature commits into one clean commit before merging
Rewording: Improve commit messages for clarity and consistency
Reordering: Group related changes together logically
Dropping: Remove broken or irrelevant commits from history

Interactive rebase is essential for maintaining clean, readable Git history while preserving the integrity of your codebase.
