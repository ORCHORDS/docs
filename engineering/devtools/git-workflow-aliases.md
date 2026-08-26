# Git Workflow Aliases

Optimize your Git workflow with these essential aliases and custom commands that save time and improve productivity.

## Essential Git Aliases

```bash
# Basic shortcuts
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.df diff
git config --global alias.lg "log --oneline --decorate --graph"
```

## Pretty Log Configuration

```bash
# Enhanced log with colors and formatting
git config --global alias.lg "log --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit --date=relative"

# Compact log view
git config --global alias.lc "log --oneline --graph --all"
```

## Interactive Rebase Shortcuts

```bash
# Quick interactive rebase
git config --global alias.rbi "!git rebase -i HEAD~"

# Rebase with specific commit
git config --global alias.rb "rebase -i --autosquash"

# Squash last N commits
git config --global alias.squash '!f() { git reset --soft HEAD~$1 && git commit -m "$2"; }; f'
```

## Stash Workflows

```bash
# Save with message
git config --global alias.stash-save "!git stash save"

# List stashes with details
git config --global alias.stash-list "stash list --verbose"

# Apply specific stash
git config --global alias.stash-apply "!f() { git stash apply stash@{$1}; }; f"

# Stash and switch branch
git config --global alias.stash-switch '!git stash && git checkout'
```

## Advanced Custom Commands

```bash
# Show uncommitted changes in a readable format
git config --global alias.changes "!git diff --name-status"

# Quick branch cleanup
git config --global alias.cleanup '!git branch --merged | grep -v "\\*\\|master\\|develop" | xargs -n 1 git branch -d'

# Show current branch status
git config --global alias.status-branch "!git status --porcelain | head -1"

# Push with upstream tracking
git config --global
