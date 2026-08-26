# direnv-env-setup

**Issue:** Environment variables not set automatically when entering project directories
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers forget to source .env or export vars; wrong environment used by mistake.

## Pattern / Solution
Install direnv, add eval to .zshrc. Create .envrc in project root: dotenv .env.local. Run direnv allow once per directory. Variables auto-load on cd, auto-unload on exit.

## Gotchas
- .envrc is committed but .env.local is not — never put secrets in .envrc
- direnv allow must be re-run after .envrc changes as a security measure

## Related
- dotenv-local-setup, mise-version-manager
