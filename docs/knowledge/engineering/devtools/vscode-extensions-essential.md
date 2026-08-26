# vscode-extensions-essential

**Issue:** No standard set of extensions across team machines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New devs spend hours hunting extensions. Teams drift in tooling causing lint/format inconsistencies.

## Pattern / Solution
Commit .vscode/extensions.json with recommendations array. Use @recommended in Extensions panel. Core set: ESLint, Prettier, GitLens, Error Lens, Path Intellisense, REST Client, Docker, Remote Containers.

## Gotchas
- unwantedRecommendations can block conflicting extensions workspace-wide
- Extensions still install per-user; the file only recommends, not enforces

## Related
- vscode-settings-json, vscode-workspace-settings
