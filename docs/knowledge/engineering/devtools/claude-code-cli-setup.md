# claude-code-cli-setup

**Issue:** Claude Code CLI not configured for team workflow and project context
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers use Claude Code without project-specific configuration, missing key context.

## Pattern / Solution
Create CLAUDE.md at repo root with project context, conventions, and commands. Configure .claude/settings.json for allowed tools and permissions. Use /init to generate initial CLAUDE.md from codebase. Set up MCP servers for project-specific tools.

## Gotchas
- CLAUDE.md has token limits — keep it concise and link to detailed docs
- Tool permissions in settings.json are additive — start restrictive and expand as needed

## Related
- github-cli-daily-workflow, vscode-settings-json
