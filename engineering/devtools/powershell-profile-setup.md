# powershell-profile-setup

**Issue:** PowerShell starts bare with no aliases, prompt, or completions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers use PowerShell but lack muscle-memory shortcuts from bash/zsh.

## Pattern / Solution
Edit PROFILE file. Add Oh-My-Posh for prompt. Import PSReadLine with Set-PSReadLineOption -PredictionViewStyle ListView. Add Set-Alias for common commands.

## Gotchas
- Set-ExecutionPolicy RemoteSigned -Scope CurrentUser required to run profile scripts
- Profile location differs: PowerShell 5 vs 7 have separate profile paths

## Related
- windows-terminal-config, bash-aliases-functions, starship-prompt
