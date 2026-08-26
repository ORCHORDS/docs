# nvm-node-version-manager

**Issue:** Different projects need different Node versions; global install conflicts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Project requires Node 18 but global is 20; npm scripts fail with engine errors.

## Pattern / Solution
Install nvm, add to shell rc. nvm install 20, nvm use 20. Add .nvmrc file to project root with version. nvm use without args reads .nvmrc. Add nvm use auto-invocation to .zshrc with directory change hook.

## Gotchas
- nvm is shell function, not binary — does not work in scripts without sourcing
- Windows: use nvm-windows (different project, different commands)

## Related
- fnm-node-manager, volta-node-manager, pnpm-workspace-setup
