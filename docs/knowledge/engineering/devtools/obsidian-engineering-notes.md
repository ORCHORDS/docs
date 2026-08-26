# obsidian-engineering-notes

**Issue:** Engineering notes scattered across tools with no local search or linking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Decision records, debugging notes, and runbooks spread across Notion, Slack, and email with no local backup.

## Pattern / Solution
Obsidian stores notes as Markdown files in local vault. [[wiki links]] connect notes. Graph view shows relationships. Daily notes for engineering journal. Git-sync vault for team sharing. Community plugins: Dataview (query notes as DB), Templater.

## Gotchas
- Obsidian Sync is paid — use git (obsidian-git plugin) for free sync
- Large vaults with many attachments slow graph rendering — exclude media dirs

## Related
- notion-engineering-wiki, mermaid-diagram-as-code
