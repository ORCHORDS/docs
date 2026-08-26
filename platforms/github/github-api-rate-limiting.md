# github-api-rate-limiting

**Issue:** Handling GitHub REST API rate limits in scripts and automation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Scripts that loop over repos, issues, or PRs hit the 5,000 req/hour primary rate limit and fail with HTTP 403.

## Pattern / Solution
Check remaining quota:
```bash
gh api rate_limit --jq '.resources.core'
# { "limit": 5000, "remaining": 4832, "reset": 1723385600 }
```
Read headers from curl:
```bash
curl -I -H "Authorization: Bearer $TOKEN" https://api.github.com/repos/owner/repo \
  | grep -i x-ratelimit
# x-ratelimit-remaining: 4832
# x-ratelimit-reset: 1723385600
```
Exponential back-off on 429/403:
```python
import time, requests

def call_api(url, headers):
    for attempt in range(5):
        r = requests.get(url, headers=headers)
        if r.status_code == 429:
            reset = int(r.headers.get("x-ratelimit-reset", time.time() + 60))
            time.sleep(max(reset - time.time(), 1))
        else:
            return r
```

## Gotchas
- GitHub Apps get 15,000 req/hour per installation — prefer them over PATs for automation.
- Secondary rate limits (abuse detection) are separate; they trigger on burst patterns, not totals.
- GraphQL has a separate limit based on query cost points, not request count.
- `Retry-After` header is returned on secondary rate limit responses.

## Related
- `github-graphql-api-patterns.md`
- `github-apps-installation-tokens.md`
