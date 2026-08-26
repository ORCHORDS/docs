# volta-node-manager

**Issue:** Node version needs to be pinned per project and enforced for all contributors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
.nvmrc is opt-in; new developers use wrong Node version and hit subtle bugs.

## Pattern / Solution
Install Volta. volta pin node@20 adds to package.json. Volta intercepts node/npm/yarn calls and uses pinned version automatically — no manual nvm use. Works on Windows without WSL.

## Gotchas
- Volta installs tools per-user — first volta pin triggers download
- Does not read .nvmrc — migration requires volta pin in each project

## Related
- nvm-node-version-manager, fnm-node-manager
