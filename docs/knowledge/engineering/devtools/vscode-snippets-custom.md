# vscode-snippets-custom

**Issue:** Repetitive boilerplate typed by hand across the team
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Console.log, React components, test scaffolding written from memory, inconsistently.

## Pattern / Solution
Create .vscode/[language].code-snippets files and commit them. Use TM_FILENAME_BASE, CLIPBOARD, and tabstops. Trigger with short prefix like rfc for React functional component.

## Gotchas
- JSON inside snippets body must escape backslashes double
- Snippet files are per-language or global; global snippets appear in all file types

## Related
- vscode-workspace-settings, vscode-extensions-essential
