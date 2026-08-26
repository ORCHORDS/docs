# feature-cookbook-feature-isolation-detail

**Issue:** Feature isolation — bounded contexts, micro-services
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your monolith has 50 features. One feature is changed.
A different feature breaks. The team is scared to ship.
Deploys are weekly.

## Root cause
**Without isolation, every change is risky.** Use
bounded contexts.

**Source:** DDD — Bounded Contexts:
https://martinfowler.com/bliki/BoundedContext.html

## The "bounded context" pattern

For each context, a clear boundary:
```
Auth context: login, signup, session, MFA
Billing context: charges, subscriptions, invoices
Content context: posts, comments, tags
User context: profile, preferences, settings
```

Each context has its own data + logic.

## The "code structure" pattern

For code structure, organize by context:
```
/src
  /auth
    - login.ts
    - signup.ts
    - session.ts
  /billing
    - charge.ts
    - subscription.ts
  /content
    - post.ts
    - comment.ts
```

The directories are the contexts.

## The "data isolation" pattern

For data isolation:
- **Single DB, separate schemas:** One DB, multiple
  schemas
- **Single DB, prefixed tables:** `auth_users`,
  `billing_charges`
- **Multiple DBs:** One DB per context

For most apps, **prefixed tables** is enough.

```ts
// auth context
const user = await env.DB!.prepare(`SELECT * FROM auth_users WHERE id = ?`).bind(id).first();

// billing context
const charge = await env.DB!.prepare(`SELECT * FROM billing_charges WHERE id = ?`).bind(id).first();
```

The tables are prefixed.

## The "API boundary" pattern

For API, define clear boundaries:
- **Internal API:** Used by the same context
- **External API:** Used by other contexts
- **Public API:** Used by clients

The external API is stable; the internal API can change.

## The "anti-corruption layer" pattern

For the boundary, the ACL:
```ts
function toAuthUser(externalUser: ExternalUser): AuthUser {
  return {
    id: externalUser.uuid,
    email: externalUser.email_address,
    displayName: externalUser.full_name,
  };
}
```

The ACL translates between contexts.

## The "events" pattern

For cross-context communication:
```ts
// auth context: user signed up
await env.QUEUE.send({
  type: 'auth.user.signed_up',
  userId: user.id,
  email: user.email,
});

// billing context: receives the event
async function handleUserSignedUp(event: Event, env: Env) {
  await createFreeTrial(event.userId, env);
}
```

The contexts communicate via events.

## The "monorepo" pattern

For code sharing:
```
/packages
  /auth
  /billing
  /content
  /shared
```

The packages are independent.

## The "microservice" pattern

For services, split by context:
- **Auth service:** Login, signup, MFA
- **Billing service:** Charges, subscriptions
- **Content service:** Posts, comments

For most apps, **monorepo with modules** is enough.

## The "synchronous vs asynchronous" choice

For cross-context communication:
- **Synchronous (HTTP):** For real-time needs
- **Asynchronous (queue):** For non-blocking

Use async unless sync is required.

## The "synchronous coupling" anti-pattern

For synchronous coupling:
### 1. Direct DB access
- **Issue:** Context A reads Context B's tables
- **Fix:** Use an event or API

### 2. Shared state
- **Issue:** Context A and B share a global
- **Fix:** Each context owns its state

### 3. Tight coupling
- **Issue:** A change in A breaks B
- **Fix:** Loose coupling via events

### 4. Cross-context transactions
- **Issue:** 2PC between contexts
- **Fix:** Saga pattern

## The "strangler" pattern

For a legacy system, replace piece by piece:
1. **Identify:** What's the legacy part?
2. **Build new:** Build the new context
3. **Migrate:** Move traffic gradually
4. **Cutover:** Remove the legacy
5. **Repeat:** For each piece

The legacy is replaced without a big-bang rewrite.

## The "feature flag" pattern

For safe rollout:
```ts
if (await isFeatureEnabled('new_billing', user, env)) {
  return newBillingFlow(user, env);
} else {
  return legacyBillingFlow(user, env);
}
```

The new feature is rolled out gradually.

## The "isolation metrics" pattern

For isolation health:
- **Cross-context calls:** Should be minimal
- **Shared tables:** Should be 0
- **Coupling:** Should be loose
- **Deploys:** Each context can deploy independently

The metrics show the isolation health.

## Verification
- **Test:** Each context can be deployed independently
- **Test:** Cross-context calls are monitored
- **Live:** Coupling is reviewed
- **Audit:** Annual review of context boundaries

## Gotchas
- **The "no context boundary" anti-pattern.** One big
  monolith.
- **The "tight coupling" anti-pattern.** Loose
  coupling.
- **The "shared tables" anti-pattern.** Per-context
  tables.

## Related
- `feature-cookbook-feature-isolation.md`
- `code-organization-monorepo.md`
- `event-driven-architecture.md`
- `saga-pattern.md`
- DDD: https://martinfowler.com/bliki/BoundedContext.html
