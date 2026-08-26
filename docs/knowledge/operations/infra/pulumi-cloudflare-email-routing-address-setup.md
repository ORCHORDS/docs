# Pulumi Cloudflare Email Routing Address Setup

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to provision Cloudflare Email Routing for one or more zones using Pulumi: enabling
the feature, adding destination addresses (with their verification workflow), creating
catch-all and address-specific routing rules, and plumbing the required DNS records — all
as repeatable, reviewable IaC rather than a sequence of dashboard clicks. You already have
a Terraform example (`cloudflare-email-routing-terraform-dns.md`) but are standardising on
Pulumi TypeScript across your stack.

## Context

Cloudflare Email Routing rewrites inbound SMTP for a zone and forwards messages to
verified destination addresses. The provisioning sequence is:

1. Enable Email Routing on the zone (`cloudflare.EmailRoutingSettings`).
2. Add destination addresses (`cloudflare.EmailRoutingAddress`) — triggers a
   verification email; the address is unusable until the link in the email is clicked.
3. Create routing rules (`cloudflare.EmailRoutingRule`) — match patterns to action/destinations.
4. Optionally set a catch-all rule (`cloudflare.EmailRoutingCatchAll`).
5. Cloudflare auto-creates the required MX and SPF DNS records when Email Routing is
   enabled; do not create conflicting MX records manually.

Pulumi resources map 1:1 to these API objects. All resources live under
`@pulumi/cloudflare` v5+.

---

## Section 1 — Enable Email Routing for a Zone

```typescript
// infra/email-routing/index.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();
const zoneId = config.require("cloudflareZoneId");
const zoneName = config.require("cloudflareZoneName");

// Step 1: Enable Email Routing on the zone
const emailRouting = new cloudflare.EmailRoutingSettings("email-routing-enabled", {
  zoneId,
  enabled: true,
  // skipWizard: true skips the interactive setup in the dashboard (API-only management)
  skipWizard: true,
});

export const emailRoutingEnabled = emailRouting.enabled;
```

---

## Section 2 — Add and Verify Destination Addresses

```typescript
// infra/email-routing/destinations.ts

interface DestinationConfig {
  email: string;
  label: string;
}

const destinations: DestinationConfig[] = [
  { email: "support@company.com",     label: "support" },
  { email: "billing@company.com",     label: "billing" },
  { email: "alerts@pagerduty.com",    label: "pagerduty-alerts" },
  { email: "dev+github@company.com",  label: "github-notifications" },
];

const destinationAddresses = destinations.map(dest =>
  new cloudflare.EmailRoutingAddress(`email-dest-${dest.label}`, {
    accountId: config.require("cloudflareAccountId"),
    email: dest.email,
  }, { dependsOn: [emailRouting] })
);

// NOTE: Cloudflare sends a verification email to each address.
// The address is in 'pending' state until the link in the email is clicked.
// Pulumi does not block on verification — check status via:
//   curl https://api.cloudflare.com/client/v4/accounts/<id>/email-routing/addresses

export const destinationEmails = destinationAddresses.map(d => d.email);
```

---

## Section 3 — Create Per-Address Routing Rules

```typescript
// infra/email-routing/rules.ts

// Routing rules are evaluated top-to-bottom; first match wins.
// matchers[].field: "to" | "from" | "subject"
// matchers[].type: "literal" | "all"
// actions[].type: "forward" | "worker" | "drop"

const supportRule = new cloudflare.EmailRoutingRule("route-support", {
  zoneId,
  name:     "Support inbox",
  enabled:  true,
  priority: 10,
  matchers: [{
    type:  "literal",
    field: "to",
    value: `support@${zoneName}`,
  }],
  actions: [{
    type:   "forward",
    values: ["support@company.com"],
  }],
}, { dependsOn: [emailRouting, ...destinationAddresses] });

const billingRule = new cloudflare.EmailRoutingRule("route-billing", {
  zoneId,
  name:     "Billing inbox",
  enabled:  true,
  priority: 20,
  matchers: [{
    type:  "literal",
    field: "to",
    value: `billing@${zoneName}`,
  }],
  actions: [{
    type:   "forward",
    values: ["billing@company.com"],
  }],
}, { dependsOn: [emailRouting, ...destinationAddresses] });

// Route to a Worker for custom processing (e.g., ticket creation)
const alertRule = new cloudflare.EmailRoutingRule("route-alerts", {
  zoneId,
  name:     "Alert processing via Worker",
  enabled:  true,
  priority: 5,
  matchers: [{
    type:  "literal",
    field: "to",
    value: `alerts@${zoneName}`,
  }],
  actions: [{
    type:   "worker",
    values: ["email-alert-processor"],  // Worker script name
  }],
}, { dependsOn: [emailRouting] });

export const routingRules = [supportRule, billingRule, alertRule];
```

---

## Section 4 — Catch-All Rule

```typescript
// infra/email-routing/catchall.ts

// The catch-all rule applies to all messages not matched by a priority rule.
// Only one catch-all can exist per zone; this resource replaces the existing one.

const catchAll = new cloudflare.EmailRoutingCatchAll("email-catch-all", {
  zoneId,
  name:    "Default catch-all",
  enabled: true,
  matchers: [{
    type: "all",
  }],
  actions: [{
    type:   "forward",
    values: ["support@company.com"],
  }],
  // Alternative: drop unmatched mail silently
  // actions: [{ type: "drop" }],
}, { dependsOn: [emailRouting] });

export const catchAllEnabled = catchAll.enabled;
```

---

## Section 5 — Multi-Zone Email Routing with ComponentResource

Wrap the full setup in a `ComponentResource` for clean reuse across zones.

```typescript
// infra/email-routing/EmailRoutingZone.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

export interface EmailRoutingZoneArgs {
  zoneId: pulumi.Input<string>;
  zoneName: pulumi.Input<string>;
  destinations: Array<{ email: string; label: string }>;
  rules: Array<{
    name: string;
    toAddress: pulumi.Input<string>;
    forwardTo: string;
    priority: number;
  }>;
  catchAllEmail: string;
}

export class EmailRoutingZone extends pulumi.ComponentResource {
  public readonly settingsEnabled: pulumi.Output<boolean>;
  public readonly ruleIds: pulumi.Output<string>[];

  constructor(name: string, args: EmailRoutingZoneArgs, opts?: pulumi.ComponentResourceOptions) {
    super("orchords:infra:EmailRoutingZone", name, {}, opts);

    const settings = new cloudflare.EmailRoutingSettings(`${name}-settings`, {
      zoneId:     args.zoneId,
      enabled:    true,
      skipWizard: true,
    }, { parent: this });

    const destResources = args.destinations.map(dest =>
      new cloudflare.EmailRoutingAddress(`${name}-dest-${dest.label}`, {
        accountId: config.require("cloudflareAccountId"),
        email: dest.email,
      }, { parent: this, dependsOn: [settings] })
    );

    const ruleResources = args.rules.map(rule =>
      new cloudflare.EmailRoutingRule(`${name}-rule-${rule.name}`, {
        zoneId:   args.zoneId,
        name:     rule.name,
        enabled:  true,
        priority: rule.priority,
        matchers: [{ type: "literal", field: "to", value: rule.toAddress }],
        actions:  [{ type: "forward", values: [rule.forwardTo] }],
      }, { parent: this, dependsOn: [settings, ...destResources] })
    );

    new cloudflare.EmailRoutingCatchAll(`${name}-catchall`, {
      zoneId:   args.zoneId,
      name:     "default",
      enabled:  true,
      matchers: [{ type: "all" }],
      actions:  [{ type: "forward", values: [args.catchAllEmail] }],
    }, { parent: this, dependsOn: [settings] });

    this.settingsEnabled = settings.enabled;
    this.ruleIds = ruleResources.map(r => r.id);
    this.registerOutputs({ settingsEnabled: this.settingsEnabled });
  }
}

// Usage:
const primaryZoneEmail = new EmailRoutingZone("primary-zone", {
  zoneId:   primaryZoneId,
  zoneName: "example.com",
  destinations: [
    { email: "hello@company.com", label: "hello" },
  ],
  rules: [
    { name: "hello-rule", toAddress: "hello@example.com", forwardTo: "hello@company.com", priority: 10 },
  ],
  catchAllEmail: "hello@company.com",
});
```

---

## Section 6 — Verify DNS Records Created by Cloudflare

When Email Routing is enabled, Cloudflare automatically manages required MX and TXT
records. Use a Pulumi dynamic provider or a TypeScript check to assert they exist.

```typescript
// infra/email-routing/verify-dns.ts
// Assertion script; run after `pulumi up` in CI.

async function verifyEmailRoutingDns(zoneName: string, cfApiToken: string, zoneId: string): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/dns_records?type=MX`,
    { headers: { Authorization: `Bearer ${cfApiToken}` } }
  );
  const { result } = (await resp.json()) as { result: Array<{ name: string; content: string }> };

  const requiredMx = ["route1.mx.cloudflare.net", "route2.mx.cloudflare.net", "route3.mx.cloudflare.net"];
  const presentMx = result.map(r => r.content);

  for (const mx of requiredMx) {
    if (!presentMx.includes(mx)) {
      throw new Error(`Required MX record missing: ${mx} for zone ${zoneName}`);
    }
  }

  console.log(`[DNS CHECK] All required MX records present for ${zoneName}`);
}

await verifyEmailRoutingDns(
  process.env.ZONE_NAME!,
  process.env.CF_API_TOKEN!,
  process.env.CF_ZONE_ID!
);
```

---

## Anti-patterns

- **Creating MX records manually** — Cloudflare auto-manages the required MX records when
  Email Routing is enabled. Adding your own MX records conflicts and breaks delivery.
  Never create `cloudflare_record` resources of type MX in the same zone.
- **Skipping `dependsOn` chains** — `EmailRoutingRule` resources will silently fail to
  create if `EmailRoutingSettings` has not finished enabling the feature. Always chain.
- **Using destination addresses before verification** — Pulumi creates the resource
  immediately, but the address is in `pending` state until the verification link is
  clicked. Routing rules referencing unverified addresses silently drop mail.
- **Setting `priority` conflicts** — two rules with the same priority number produce
  undefined evaluation order. Use increments of 10 to leave room for future insertion.

---

## Gotchas

- `EmailRoutingAddress` is an **account-level** resource (uses `account_id`), not
  zone-level. The same destination address can be shared across multiple zones in the
  same account — you only verify it once.
- `pulumi destroy` on `EmailRoutingSettings` disables Email Routing but does NOT remove
  the auto-managed DNS records immediately. Cloudflare removes them asynchronously after
  a delay; running another apply against a fresh Terraform/Pulumi stack on the same zone
  shortly after destroy may see stale MX records.
- Pulumi state will show `EmailRoutingAddress.verified = false` until the verification
  email is acted on. Do not treat a green `pulumi up` as confirmation that routing is
  operational.
- The `Worker` action type in `EmailRoutingRule` requires the target Worker to have an
  **email** handler (`export default { async email(message, env, ctx) {...} }`). A Worker
  without this handler will silently discard the message.
- Cloudflare Email Routing has a limit of 200 rules per zone and 200 destination
  addresses per account as of mid-2026.

---

## Verification

```bash
# Check Email Routing is enabled for the zone
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email-routing/settings" \
  | jq '{enabled, status, name}'

# List destination addresses and their verification status
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/email-routing/addresses" \
  | jq '.result[] | {email, verified}'

# List routing rules
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email-routing/rules" \
  | jq '.result[] | {name, priority, enabled, matchers, actions}'

# Pulumi stack output showing rule IDs
pulumi stack output --json | jq '.ruleIds'

# Send a test email (requires an MX test tool or mail client)
echo "Test body" | mail -s "Test subject" support@example.com
```

---

## Related

- `cloudflare-email-routing-terraform-dns.md`
- `pulumi-cloudflare-provider-advanced.md`
- `cloudflare-dns-api.md`
- `smtp-relay-outbound-architecture.md`
- `reverse-dns-ptr-deliverability.md`

---

## Sources

- Cloudflare Docs — Email Routing: https://developers.cloudflare.com/email-routing/
- Cloudflare Docs — Email Routing API: https://developers.cloudflare.com/email-routing/setup/api/
- Pulumi cloudflare.EmailRoutingSettings: https://www.pulumi.com/registry/packages/cloudflare/api-docs/emailroutingsettings/
- Pulumi cloudflare.EmailRoutingAddress: https://www.pulumi.com/registry/packages/cloudflare/api-docs/emailroutingaddress/
- Pulumi cloudflare.EmailRoutingRule: https://www.pulumi.com/registry/packages/cloudflare/api-docs/emailroutingrule/
- Pulumi cloudflare.EmailRoutingCatchAll: https://www.pulumi.com/registry/packages/cloudflare/api-docs/emailroutingcatchall/
