# sourcegraph-code-search

**Issue:** Searching across multiple repositories simultaneously is impossible with grep
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Finding all usages of a deprecated API across 30 microservice repos requires cloning each.

## Pattern / Solution
Sourcegraph indexes all repos for cross-repo search. Structural search: patternType:structural func(\, error). Use repo: filter to scope. Batch changes for multi-repo PRs. Local search via src-cli. Code insights for tracking tech debt trends.

## Gotchas
- Self-hosted Sourcegraph requires significant resources (4+ CPU, 8GB+ RAM)
- Sourcegraph.com is free for public repos; enterprise license for private

## Related
- ripgrep-patterns, github-cli-daily-workflow
