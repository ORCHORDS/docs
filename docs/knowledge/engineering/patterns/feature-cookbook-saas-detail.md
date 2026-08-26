# feature-cookbook-saas-detail

**Issue:** SaaS patterns — auth, billing, scale
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a SaaS app. You add a per-user pricing.
The user has 1000 employees. They want enterprise
pricing. You rebuild. You wish you'd started with
tenants.

## Root cause
**SaaS is multi-tenant.** Plan for it.

**Source:** Various SaaS guides.

## The "tenant model" pattern

For the tenant model:
```ts
interface Tenant {
  id: string;
  name: string;
  plan: 'free' | 'pro' | 'enterprise';
  status: 'trial' | 'active' | 'past_due' | 'suspended' | 'deleted';
  createdAt: string;
  trialEndsAt?: string;
  quota: {
    users: number;
    apiCallsPerMonth: number;
    storageGB: number;
  };
}
```

The tenant has a plan + status + quota.

## The "user model" pattern

For the user model:
```ts
interface User {
  id: string;
  tenantId: string;
  email: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  status: 'active' | 'invited' | 'suspended';
  createdAt: string;
}
```

The user is in a tenant with a role.

## The "owner role" pattern

For the owner role:
- **Can:** Everything (manage billing, delete tenant)
- **Single per tenant:** The original signup

```ts
async function isOwner(user: User, tenant: Tenant): Promise<boolean> {
  return user.id === tenant.ownerId;
}
```

The owner has full rights.

## The "invitation" pattern

For invitations:
1. **Admin invites:** Email + role
2. **Send email:** With link
3. **User accepts:** Account is created
4. **User is in tenant:** Active

```ts
async function inviteUser(tenantId: string, email: string, role: Role, env: Env): Promise<void> {
  const token = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO invitations (id, tenant_id, email, role, token) VALUES (?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), tenantId, email, role, token).run();

  await sendEmail(email, {
    subject: 'You\'re invited',
    html: `<a href="https://example.com/invite?token=<redacted-secret>
  }, env);
}
```

The invitation is sent.

## The "billing model" pattern

For billing, per plan:
- **Free:** Limited features
- **Pro:** All features + higher quota
- **Enterprise:** Custom + dedicated support

```ts
const PLANS = {
  free: {
    price: 0,
    features: ['basic'],
    quota: { users: 5, apiCallsPerMonth: 1000, storageGB: 1 },
  },
  pro: {
    price: 49,
    features: ['basic', 'advanced'],
    quota: { users: 50, apiCallsPerMonth: 100000, storageGB: 100 },
  },
  enterprise: {
    price: 499,
    features: ['basic', 'advanced', 'priority'],
    quota: { users: -1, apiCallsPerMonth: -1, storageGB: 1000 },
  },
};
```

The plan has features + quota.

## The "Stripe subscription" pattern

For Stripe:
```ts
const session = await stripe.checkout.sessions.create({
  mode: 'subscription',
  line_items: [{
    price: STRIPE_PRICE_IDS[tenant.plan],
    quantity: 1,
  }],
  success_url: 'https://example.com/billing/success',
  cancel_url: 'https://example.com/billing/cancel',
  metadata: { tenantId: tenant.id },
});
```

The subscription is created.

## The "webhook" pattern

For Stripe webhooks:
```ts
app.post('/webhooks/stripe', async (req) => {
  const event = stripe.webhooks.constructEvent(
    await req.text(),
    req.headers.get('stripe-signature'),
    STRIPE_WEBHOOK_SECRET,
  );

  switch (event.type) {
    case 'customer.subscription.created':
    case 'customer.subscription.updated':
      await handleSubscriptionChange(event.data.object);
      break;
    case 'customer.subscription.deleted':
      await handleSubscriptionCancelled(event.data.object);
      break;
  }

  return new Response('OK');
});
```

The webhook handles the events.

## The "feature gating" pattern

For feature gating:
```ts
function can(tenant: Tenant, feature: string): boolean {
  return PLANS[tenant.plan].features.includes(feature);
}

if (!can(tenant, 'advanced')) {
  return new Response('Upgrade required', { status: 402 });
}
```

The feature is gated.

## The "usage tracking" pattern

For usage tracking:
```ts
async function recordUsage(tenantId: string, metric: string, value: number, env: Env): Promise<void> {
  await env.DB!.prepare(
    `INSERT INTO usage (id, tenant_id, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), tenantId, metric, value, new Date().toISOString()).run();
}
```

The usage is recorded.

## The "overage handling" pattern

For overage:
- **Hard limit:** Block
- **Soft limit:** Allow + alert
- **Overage billing:** Charge per use

```ts
async function isOverLimit(tenant: Tenant, metric: string, value: number, env: Env): Promise<boolean> {
  const usage = await getUsage(tenant.id, metric, env);
  return usage + value > PLANS[tenant.plan].quota[metric];
}
```

The overage is handled.

## The "tenant admin" pattern

For tenant admin:
- **Manage users:** Invite, remove, change role
- **Manage billing:** Upgrade, cancel
- **View audit:** What happened

```ts
app.get('/api/tenants/:id/users', withAuth('admin', async (user, env) => {
  return getTenantUsers(user.tenantId, env);
}));
```

The admin has API access.

## The "audit log" pattern

For audit:
```sql
CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_id TEXT,
  metadata TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The audit is queryable.

## The "SaaS anti-pattern" anti-patterns

### 1. No tenants
- **Issue:** Per-user pricing only
- **Fix:** Tenants from day 1

### 2. No quota
- **Issue:** One tenant kills the DB
- **Fix:** Per-tenant quota

### 3. No plan
- **Issue:** All features for all
- **Fix:** Plan-based gating

### 4. No audit
- **Issue:** No traceability
- **Fix:** Audit log

### 5. No soft delete
- **Issue:** Accidental delete
- **Fix:** Soft delete

### 6. No trial
- **Issue:** No conversion
- **Fix:** 14-day trial

## Verification
- **Test:** Tenant isolation works
- **Test:** Plan gating works
- **Test:** Quota is enforced
- **Test:** Webhook is processed
- **Live:** Per-tenant metrics
- **Audit:** Quarterly review

## Gotchas
- **The "no tenants" anti-pattern.** Tenants from day 1.
- **The "no quota" anti-pattern.** Per-tenant quota.
- **The "no audit" anti-pattern.** Audit log.

## Related
- `feature-cookbook-multi-tenancy-detail.md`
- `feature-cookbook-billing.md`
- `feature-cookbook-feature-flags.md`
- `feature-cookbook-onboarding.md`
- `feature-cookbook-permission-modeling.md`
- Stripe: https://stripe.com/
