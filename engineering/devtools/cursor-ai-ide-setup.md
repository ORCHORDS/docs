# cursor-ai-ide-setup

**Issue:** Cursor AI features not configured for maximum effectiveness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers use Cursor like plain VS Code, missing Composer, @-mentions, and rules.

## Pattern / Solution
Set up .cursorrules at repo root with project context and coding standards. Use Composer (Ctrl+I) for multi-file edits. @Codebase embeds project context. @Docs links external documentation. Use Ctrl+K for inline edits.

## Gotchas
- .cursorrules has a token limit — be concise and prioritize conventions over explanations
- Cursor indexes codebase on first open; large repos take minutes before @Codebase works

## Related
- vscode-settings-json, vscode-extensions-essential
