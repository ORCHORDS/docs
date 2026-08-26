# bash-aliases-functions

**Issue:** Repetitive command sequences not aliased, slowing down daily workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Typing git status, docker-compose up -d, cd ../.. hundreds of times per day.

## Pattern / Solution
Add aliases to ~/.bashrc or ~/.zshrc. Use functions for parameterized shortcuts. Organize in ~/.aliases sourced from rc file. Common: alias gs=git-status, alias ll=ls-la, mkcd function for mkdir+cd.

## Gotchas
- Alias names can shadow system commands — use which before naming
- Functions vs aliases: use functions when you need arguments

## Related
- terminal-zsh-setup, oh-my-zsh-plugins
