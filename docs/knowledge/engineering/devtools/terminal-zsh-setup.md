# terminal-zsh-setup

**Issue:** Default shell setup is slow, lacks completions, and has no history search
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tab completion is basic, no syntax highlighting, slow prompt from unoptimized rc file.

## Pattern / Solution
Install zsh, set as default with chsh -s. Add zsh-autosuggestions and zsh-syntax-highlighting. Enable HISTSIZE=50000, SAVEHIST=50000, HIST_IGNORE_DUPS. Use Ctrl+R with fzf for history search.

## Gotchas
- Source order matters: syntax-highlighting plugin must be last sourced
- setopt SHARE_HISTORY shares history across terminals in real time

## Related
- oh-my-zsh-plugins, starship-prompt, bash-aliases-functions
