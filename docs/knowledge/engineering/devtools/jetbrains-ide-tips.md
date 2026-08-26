# jetbrains-ide-tips

**Issue:** JetBrains IDEs underused — developers miss productivity features
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers use IDEs like text editors, missing refactoring, database, and analysis tools.

## Pattern / Solution
Key shortcuts: Shift+Shift (Search Everywhere), Ctrl+Shift+A (Find Action), Alt+Enter (Quick Fix), Ctrl+Alt+L (Reformat). Use Database tool window for SQL. Structural Search/Replace for complex refactors.

## Gotchas
- Settings Sync requires JetBrains account — configure what syncs carefully
- .idea/ folder: commit modules.xml, *.iml, runConfigurations/; ignore workspace.xml

## Related
- vscode-settings-json, git-config-global
