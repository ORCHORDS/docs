# github-audit-log-api

**Issue:** Querying GitHub's audit log API for security monitoring and compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Compliance teams need evidence of who changed settings, added members, or accessed secrets. The audit log API provides this.

## Pattern / Solution
```bash
# List recent org audit events
gh api /orgs/myorg/audit-log \
  --paginate \
  --jq '.[] | [.created_at, .actor, .action] | @tsv' \
  | sort

# Filter by action type
gh api "/orgs/myorg/audit-log?phrase=action:repo.create" \
  --jq '.[].actor'

# Filter by actor
gh api "/orgs/myorg/audit-log?phrase=actor:suspicioususer"

# Export for SIEM
gh api "/orgs/myorg/audit-log?phrase=&include=all" \
  --paginate > audit-$(date +%Y%m%d).json
```

## Gotchas
- Audit log is available only for org owners and Enterprise admins.
- Retention is 90 days for GitHub Team; 180 days for Enterprise.
- GitHub Enterprise has a streaming audit log that ships events to S3, Azure Blob, Datadog, etc. in real time.
- The `phrase` query parameter supports boolean operators: `action:repo.create actor:alice`.
- IP address is included in Enterprise audit log but not Team.

## Related
- `github-organization-settings.md`
- `github-ip-allow-list.md`
- `github-enterprise-managed-users.md`
