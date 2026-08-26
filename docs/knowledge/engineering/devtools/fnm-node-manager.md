# fnm-node-manager

**Issue:** nvm is slow to initialize; faster alternative needed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
nvm adds 200-500ms to shell startup; large teams notice slowdown.

## Pattern / Solution
Install fnm (Fast Node Manager) via brew or cargo. eval fnm-env --use-on-cd in shell rc. Reads .nvmrc and .node-version. fnm install 20, fnm use 20. Approximately 10x faster than nvm at startup.

## Gotchas
- --use-on-cd flag enables automatic version switching on directory change
- Compatible with .nvmrc — no migration needed for existing projects

## Related
- nvm-node-version-manager, volta-node-manager, mise-version-manager
