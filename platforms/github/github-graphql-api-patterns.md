# github-graphql-api-patterns

**Issue:** Using GitHub's GraphQL API efficiently for complex data retrieval
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
REST API requires many round-trips (N+1) to fetch related data. GraphQL lets you fetch exactly what you need in one request.

## Pattern / Solution
```graphql
query OrgRepos($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $cursor, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { endCursor hasNextPage }
      nodes {
        name
        defaultBranchRef { name }
        vulnerabilityAlerts(first: 5) {
          nodes { securityVulnerability { severity package { name } } }
        }
      }
    }
  }
}
```
Using `gh` CLI:
```bash
gh api graphql -f query=@query.graphql -f org=myorg \
  --paginate --jq '.data.organization.repositories.nodes[].name'
```

## Gotchas
- Each field has a cost; deep nesting multiplies cost. Check `extensions.cost` in the response.
- Rate limit is measured in points (max 5,000/hour); a single complex query can cost 100+ points.
- Use `first:` + cursor pagination — GraphQL pagination is cursor-based, not offset-based.
- Always request `pageInfo { hasNextPage endCursor }` for paginated connections.
- The API endpoint is `https://api.github.com/graphql` (POST only).

## Related
- `github-api-rate-limiting.md`
- `github-audit-log-api.md`
