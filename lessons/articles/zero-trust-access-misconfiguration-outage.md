# Zero Trust Access Misconfiguration Locked Out All Internal Users for 4 Hours

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

All example project internal tools — the admin dashboard, the internal API explorer, and the staging environment — became inaccessible to every member of the engineering and operations teams simultaneously. Cloudflare Zero Trust served a `403 Access Denied` page to every user regardless of identity. The outage lasted 4 hours and 11 minutes because the single engineer with break-glass Cloudflare dashboard access was on annual leave and unreachable for the first two hours.

## Context

example project protects all internal-facing routes using Cloudflare Zero Trust Access policies. The policy architecture at the time consisted of a single Access Application (`example project-internal-*`) that matched all internal subdomains via a wildcard hostname policy, backed by an identity provider group rule requiring membership in the `example project-employees` group in the company's Okta tenant. The engineering team had recently undergone a directory migration: all Okta groups were renamed from `example project-*` to `orchords-example project-*` as part of a company-wide namespace cleanup. The Zero Trust policy was not updated to reflect the new group name.

## Timeline

- **09:00 UTC** – Okta directory migration completes. All internal groups renamed from `example project-employees` to `orchords-example project-employees`.
- **09:00 UTC** – Zero Trust Access policy still references the old `example project-employees` group name. The policy does not error — it simply evaluates the group membership rule against a group that no longer exists, yielding `false` for all users.
- **09:03 UTC** – First engineer tries to access `admin.example project-internal.example.com`. Receives `403 Access Denied`.
- **09:07 UTC** – Three more engineers report the same issue in Slack. Initial hypothesis: Okta SSO outage.
- **09:15 UTC** – Okta status page shows green. Engineers attempt to log in to the Okta admin console directly — this works. The issue is scoped to Zero Trust.
- **09:30 UTC** – Engineer with Cloudflare dashboard access identified. That engineer is on leave; Slack messages go unread.
- **09:45 UTC** – Escalation to CTO, who has Cloudflare `Super Administrator` access but does not know the Cloudflare login credentials. Password reset flow initiated.
- **10:20 UTC** – CTO regains Cloudflare access. Locates the Zero Trust Access Application policy.
- **10:35 UTC** – Policy group rule identified as `example project-employees` (stale). Updated to `orchords-example project-employees`.
- **10:40 UTC** – Policy saved and propagated. Engineers begin regaining access.
- **11:00 UTC** – All internal tools confirmed accessible. Full team access restored. Incident closed.
- **13:00 UTC** – Post-incident retro held.

## Root Cause

The Cloudflare Zero Trust Access policy group membership rule was tightly coupled to an Okta group name string. When the Okta directory migration renamed all groups, the Zero Trust policy became stale. Cloudflare Access evaluates an unknown group as "no match", which causes the policy to deny all requests — a fail-closed behaviour that is correct from a security standpoint but catastrophic for availability when the configuration is wrong. The change management process for the Okta migration did not include a checklist item for Zero Trust policy review, and no automated test validated that the Access policy would actually admit real employees after the migration.

## Fix: Policy Hardening and Break-Glass Access

The immediate fix was updating the group name. The structural fix was threefold: adopt policy-as-code via Terraform so changes to ZT policies go through code review, implement a break-glass bypass mechanism, and add a synthetic monitor that validates access for a canary service account.

```typescript
// scripts/validate-zero-trust-policy.ts
// Run as part of CI after any identity-provider or ZT policy change.
// Uses a dedicated service account whose credentials are stored in CI secrets.

const CANARY_INTERNAL_URL = "https://admin.example project-internal.example.com/health";
const CANARY_CF_ACCESS_CLIENT_ID = process.env.CF_CANARY_CLIENT_ID!;
const CANARY_CF_ACCESS_CLIENT_SECRET = process.env.CF_CANARY_CLIENT_SECRET!;

async function validateAccessPolicy(): Promise<void> {
  // Service token auth — use a dedicated Zero Trust service token for the canary
  const response = await fetch(CANARY_INTERNAL_URL, {
    headers: {
      "CF-Access-Client-Id": CANARY_CF_ACCESS_CLIENT_ID,
      "CF-Access-Client-Secret": CANARY_CF_ACCESS_CLIENT_SECRET,
    },
  });

  if (response.status === 403) {
    console.error(
      `❌ Zero Trust policy validation FAILED: canary received 403 from ${CANARY_INTERNAL_URL}. ` +
      `Check that the Access Application policy group rules are current.`
    );
    process.exit(1);
  }

  if (!response.ok) {
    console.error(`❌ Unexpected status ${response.status} from ${CANARY_INTERNAL_URL}`);
    process.exit(1);
  }

  console.log(`✅ Zero Trust Access policy is admitting the canary service account.`);
}

validateAccessPolicy().catch(err => {
  console.error("Validation script error:", err);
  process.exit(1);
});
```

Terraform policy-as-code (excerpt) to make group name changes visible in PRs:

```typescript
// infra/zero-trust/access-apps.tf (converted to HCL concept shown as inline comment)
// resource "cloudflare_access_application" "example project_internal" {
//   zone_id          = var.cloudflare_zone_id
//   name             = "example project Internal Tools"
//   domain           = "*.example project-internal.example.com"
//   session_duration = "8h"
// }
//
// resource "cloudflare_access_policy" "example project_employees" {
//   application_id = cloudflare_access_application.example project_internal.id
//   name           = "example project Employees"
//   precedence     = 1
//   decision       = "allow"
//
//   include {
//     okta { name = [var.okta_employee_group_name]  // ← single source of truth
//             identity_provider_id = var.okta_idp_id }
//   }
// }
//
// variable "okta_employee_group_name" {
//   description = "Okta group name for all example project employees. UPDATE THIS when groups are renamed."
//   type        = string
// }
```

Break-glass bypass procedure — a dedicated Zero Trust Service Token stored in 1Password emergency vault, documented for out-of-hours recovery without Cloudflare dashboard access:

```typescript
// src/internal/break-glass.ts
// Emergency service token usage — bypasses identity-provider group rules.
// Token is scoped to read-only admin paths only.

// Usage (curl):
// curl https://admin.example project-internal.example.com/api/status \
//   -H "CF-Access-Client-Id: $BREAKGLASS_CLIENT_ID" \
//   -H "CF-Access-Client-Secret: $BREAKGLASS_CLIENT_SECRET"

// NOTE: break-glass token use is logged and triggers a PagerDuty alert.
// Always file an incident report when the break-glass token is used.
export const BREAK_GLASS_POLICY_NOTE = `
  Break-glass service token is stored in 1Password vault: "example project Emergency Access".
  Rotation schedule: quarterly. Last rotated: 2026-07-01.
  Usage is audited in Cloudflare Zero Trust → Logs → Access Requests.
` as const;
```

## Prevention Checklist

- [ ] Manage all Cloudflare Zero Trust policies as Terraform (or equivalent IaC), so group name changes surface as code review diffs before deployment.
- [ ] Run a CI job after every identity-provider change that validates a canary service account can reach each critical internal application.
- [ ] Store a break-glass Zero Trust service token in the team password manager's emergency vault with documented retrieval steps and a quarterly rotation reminder.
- [ ] Ensure at least two engineers (not on the same leave schedule) have Cloudflare `Super Administrator` or equivalent access to the Zero Trust dashboard.
- [ ] Add Okta group renames to the company-wide change management checklist and cross-reference dependent systems (Zero Trust, GitHub SSO, Slack directory sync).

## Monitoring Gaps Identified

- No synthetic monitor existed that validated Zero Trust Access policies were admitting real users. The first signal of the lockout was human engineers hitting 403 errors, not an automated alert.
- Cloudflare Zero Trust does not natively emit a signal when a policy rule references a group that has ceased to exist in the connected IdP; the failure mode is invisible until a user is denied.

## Anti-patterns

- Storing identity provider group names as hardcoded strings in GUI-configured Access policies, making them invisible to code review and prone to drift.
- Having only one break-glass access path to Cloudflare (a single engineer's login) with no documented fallback.
- Treating a Zero Trust IdP migration as out-of-scope for application-layer change management because "it's just renaming groups."

## Gotchas

- Cloudflare Access Access Policy group rules that reference a non-existent IdP group silently evaluate to `false` (deny), not an error. There is no warning in the dashboard UI that a referenced group does not exist.
- The Cloudflare Zero Trust `Super Administrator` role is separate from the Cloudflare account owner role; ensure emergency credentials cover the Zero Trust product scope specifically.
- Service tokens (CF-Access-Client-Id / CF-Access-Client-Secret) bypass group membership rules but are still subject to the application's IP restriction rules, if any are configured — document which restrictions apply to the break-glass token.

## Verification

```bash
# Validate that the canary service account can reach an internal endpoint
curl -si "https://admin.example project-internal.example.com/health" \
  -H "CF-Access-Client-Id: $CF_CANARY_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_CANARY_CLIENT_SECRET" \
  | head -5

# Verify that an unauthenticated request is correctly denied (should be 302 to login or 403)
curl -si "https://admin.example project-internal.example.com/health" | head -5

# List current Access Application policies via Cloudflare API to confirm group names
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/apps" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {name: .name, id: .id}'

# Run policy validation script
pnpm run validate:zero-trust-policy
```

## Related

- `lessons/certificate-expiry-outage.md`
- `lessons/two-person-rule-for-production-access.md`
- `lessons/rate-limiter-misconfiguration-outage.md`
- `monitoring/zero-trust-access-synthetic-monitor.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/access_policy
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/
