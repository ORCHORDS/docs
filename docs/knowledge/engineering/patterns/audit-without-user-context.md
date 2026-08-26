# audit-without-user-context

**Issue:** Writing audit log entries when no authenticated user is present (SAML, SCIM, cron, webhooks)
**Date:** 2026-08-11
**Status:** documented

## Symptom

Your `writeAudit` function requires a `Pick<McContext, 'tenant' | 'user' | 'request_id' | 'ip' | 'user_agent'>`.
But several flows don't have a real `McUser`:

- **SAML ACS**: User is authenticating — they don't have a session yet
- **SCIM provisioning**: IdP calls with a bearer token, not a user session
- **Cron jobs / scheduled Workers**: No request actor
- **Webhook receivers**: External system, not a platform user

TypeScript errors:

```
error TS2739: Type '{ id: string; }' is missing properties from type 'McTenant': slug, name, product_type...
error TS2322: Type 'null' is not assignable to type 'McUser'
```

## Root cause

Audit logs must always be written (for compliance), but the data model was designed assuming a
fully-authenticated user. When the actor is the system, an IdP, or an anonymous principal,
there is no `McUser` to provide.

## Fix

### Pattern 1: Anonymous stub user (SAML, OAuth callbacks)

```typescript
await writeAudit(env, {
  tenant: { id: session.tenant_id } as McTenant,  // only id is known; cast for TS
  user: {
    id: 'anonymous',
    tenant_id: session.tenant_id,
    role: 'anonymous',
    email: '',
    display_name: '',
  },
  request_id: relayState,   // use correlator from the flow (e.g. SAML RelayState)
  ip: request.headers.get('cf-connecting-ip') ?? 'unknown',
  user_agent: request.headers.get('user-agent') ?? 'unknown',
}, { action: 'saml.acs.success', metadata: { name_id: nameId } });
```

### Pattern 2: System actor (cron, scheduled Workers)

```typescript
const SYSTEM_ACTOR = {
  id: 'system',
  tenant_id: 'system',
  role: 'system',
  email: 'system@system',
  display_name: 'Scheduled Job',
} as const;

await writeAudit(env, {
  tenant: { id: tenantId } as McTenant,
  user: SYSTEM_ACTOR,
  request_id: crypto.randomUUID(),
  ip: '0.0.0.0',
  user_agent: 'cron/1.0',
}, { action: 'ingestion.run.completed', metadata: { source, inserted } });
```

### Pattern 3: Service actor (SCIM, webhook receiver)

```typescript
interface ScimCtx {
  tenant: { id: string };
  request_id: string;
  ip: string;
  user_agent: string;
}

// Call writeAudit with explicit cast when ScimCtx isn't McContext-compatible:
await writeAudit(env, ctx as any, {
  action: 'user.scim_created',
  resource_kind: 'user',
  resource_id: userId,
  metadata: { external_id: externalId, role, active },
});
```

### Pattern 4: Make writeAudit accept partial context

If you own the `writeAudit` implementation, make the user field optional:

```typescript
type AuditCtx = {
  tenant: Pick<McTenant, 'id'>;
  user?: Pick<McUser, 'id' | 'role'> | null;
  request_id: string;
  ip: string;
  user_agent: string;
};

export async function writeAudit(env: Env, ctx: AuditCtx, event: AuditEvent): Promise<void> {
  await env.DB!.prepare(`INSERT INTO audit_log ...`).bind(
    ctx.tenant.id,
    ctx.user?.id ?? 'anonymous',
    ctx.user ? 'user' : 'system',
    event.action,
    // ...
  ).run();
}
```

This is the cleanest solution and removes all the casting.

## Gotchas

- **Don't skip audit on auth failures**: A failed SAML signature, a rejected SCIM token, or a bad OAuth callback are exactly the events you most need in the audit log.
- **Correlate with flow ID**: Use SAML RelayState, webhook delivery ID, or cron run ID as `request_id` — it's your only cross-system trace anchor.
- **Tenant scope**: Always write `tenant_id`. A global cron that iterates all tenants should write one audit entry per tenant, not one global entry.
- **Don't cast McTenant to `as McTenant`** in production audit code unless the DB row actually has all required fields — do so only in flows where you demonstrably have only the tenant ID (SAML in-flight, SCIM auth).

## Related

- `saml-sp-workers.md`
- `scim-20-2026.md`
- `audit-log-mandatory.md`
- `audit-chain-durable-object.md`
- `mccontext-gate-pattern.md`
