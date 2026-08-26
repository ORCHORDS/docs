# github-cli-scripting

**Issue:** Writing automation scripts using the `gh` CLI tool
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The `gh` CLI provides a fast path to GitHub API operations without managing authentication, headers, or pagination manually.

## Pattern / Solution
```bash
# List open PRs as TSV
gh pr list --state open --json number,title,author \
  --jq '.[] | [.number, .author.login, .title] | @tsv'

# Bulk-close stale issues
gh issue list --label stale --json number -q '.[].number' | \
  xargs -I{} gh issue close {} --comment "Closing as stale"

# Create PR and auto-merge
gh pr create --fill --base main
gh pr merge --auto --squash

# Fetch raw API endpoint
gh api repos/:owner/:repo/topics --jq '.names[]'

# Paginate all org repos
gh api --paginate /orgs/myorg/repos --jq '.[].full_name'
```

## Gotchas
- `:owner` and `:repo` are magic placeholders resolved from the current git remote.
- `--jq` is applied per page when used with `--paginate`.
- `gh auth token` outputs the token for use in `curl` or scripts that need it explicitly.
- Environment variable `GH_TOKEN` overrides the stored credential — useful in CI.
- `gh extension install` adds community subcommands (e.g., `gh dash`).

## Related
- `github-cli-gh-2026.md`
- `github-api-rate-limiting.md`
