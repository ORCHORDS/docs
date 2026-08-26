# github-ip-allow-list

**Issue:** Restricting GitHub access to known IP ranges using the IP allow list feature
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Enterprises want to ensure GitHub can only be accessed from corporate networks or VPN, preventing credential theft from off-network devices.

## Pattern / Solution
Enable via Org Settings → Security → IP allow list → Enable:
```bash
# Add CIDR range via API
gh api -X POST /orgs/myorg/ip-allow-list-entries \
  -f allow_list_value="203.0.113.0/24" \
  -f name="Corporate VPN" \
  -f is_active=true

# List current entries
gh api /orgs/myorg/ip-allow-list-entries \
  --jq '.nodes[] | [.allowListValue, .name] | @tsv'
```
Also allow GitHub Actions runner IPs (needed for API calls from Actions):
```bash
# Get GitHub meta IPs
gh api /meta --jq '.actions[]'
```
Add those CIDR blocks to the allow list before enabling enforcement.

## Gotchas
- Enabling the allow list without including GitHub Actions IP ranges will break all workflows that call the API.
- GitHub publishes meta IPs at `/meta` — they change; automate updates via a scheduled workflow.
- Allow list blocks access to the web UI, API, and Git operations — test thoroughly before enforcing.
- Enterprise Managed Users (EMUs) enforce allow lists automatically for SAML sessions.

## Related
- `github-saml-sso-enforcement.md`
- `github-organization-settings.md`
- `github-enterprise-managed-users.md`
