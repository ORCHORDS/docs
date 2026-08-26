# just-in-time-access

**Issue:** Standing privileged access creates persistent high-value credentials that attackers can steal and abuse at any time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Permanent admin access means compromised credentials give an attacker immediate, unlimited access. Just-In-Time (JIT) access grants elevated permissions only when needed, for a limited duration, with approval and full audit trail.

## Pattern / Solution
```bash
# AWS — temporary role assumption via STS
aws sts assume-role \
  --role-arn arn:aws:iam::123456789:role/ProductionAdmin \
  --role-session-name "incident-2026-08-11-john" \
  --duration-seconds 3600  # 1 hour max

# Teleport — request elevated access with approval
tsh request create --roles=db-admin --reason="Debugging prod issue #<number>"
# Reviewer approves via Slack/PagerDuty integration
# Credentials auto-expire after session ends
```
```yaml
# Terraform — no permanent IAM users; only roles assumed via SSO
# aws-sso.yaml
permission_sets:
  - name: ProductionAdmin
    session_duration: PT1H  # 1 hour
    managed_policies:
      - AdministratorAccess
    customer_managed_policies: []
```

## Gotchas
- JIT is ineffective if the approval process is a rubber stamp — require a second engineer approval for Tier 0/1 access.
- Break-glass procedures need pre-approved emergency access that bypasses normal approval flow but triggers immediate alerts.
- Session recordings (Teleport, AWS SSM) are essential — JIT without audit is just inconvenient, not secure.
- Integrate JIT requests with your ticketing system so every access elevation has a linked incident or change request.

## Related
- `privileged-access-workstation.md`
- `zero-trust-network-access.md`
- `audit-log-security.md`
