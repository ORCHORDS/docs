# asdf-version-manager

**Issue:** Multiple language-specific version managers (nvm, pyenv, rbenv) to maintain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Team manages Node, Python, Ruby, Elixir versions with separate tools, each with different commands.

## Pattern / Solution
asdf is a universal version manager. asdf plugin add nodejs. asdf install nodejs 20.0.0. asdf local nodejs 20.0.0 creates .tool-versions file. One command interface for all runtimes. Commit .tool-versions to repo.

## Gotchas
- asdf shims add startup overhead; mise is a faster Rust-based alternative
- Plugin install is separate from runtime install — must add plugin before installing version

## Related
- mise-version-manager, nvm-node-version-manager, fnm-node-manager
