# Cloudflare Account Member Role Automation with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team provisions new engineers through a Slack bot or an internal HRIS webhook and
needs to add them as Cloudflare account members with specific roles (e.g., `Cloudflare
Workers Admin`, `Analytics`) without manual console clicks. You also need to remove
access automatically on offboarding. A Cloudflare Worker acts as the automation layer,
calling the Cloudflare REST API with a scoped API token.

---

## Context

Cloudflare accounts have **members** (identified by email or user ID) and **roles** (a
fixed catalog per account). The Cloudflare REST API under
`/client/v4/accounts/{account_id}/members` covers CRUD for membership. The **roles**
catalog is discoverable at `/client/v4/accounts/{account_id}/roles`.

A Worker running this automation needs an API token with the
`Account Settings: Edit` permission scope (not a global API key). Store that token as a
Worker secret, not in `wrangler.toml`.

---

## 1. Discover Available Roles

```typescript
// src/lib/cloudflare-members.ts

const CF_BASE = "https://api.cloudflare.com/client/v4";

interface CfRole {
  id: string;
  name: string;
  description: string;
  permissions: Record<string, { read: boolean; edit: boolean }>;
}

interface CfMember {
  id: string;
  user: { email: string; id: string };
  status: "accepted" | "pending";
  roles: CfRole[];
}

export async function listRoles(accountId: string, token: string): Promise<CfRole[]> {
  const res = await fetch(`${CF_BASE}/accounts/${accountId}/roles`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`listRoles HTTP ${res.status}`);
  const data = await res.json<{ result: CfRole[] }>();
  return data.result;
}

export async function findRoleByName(
  accountId: string,
  token: string,
  name: string,
): Promise<CfRole | undefined> {
  const roles = await listRoles(accountId, token);
  return roles.find((r) => r.name === name);
}
```

---

## 2. Add a Member with Specific Roles

```typescript
export async function addMember(
  accountId: string,
  token: string,
  email: string,
  roleIds: string[],
): Promise<CfMember> {
  const res = await fetch(`${CF_BASE}/accounts/${accountId}/members`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, roles: roleIds }),
  });

  if (res.status === 409) {
    // Already a member — fetch and return existing
    return getMemberByEmail(accountId, token, email);
  }
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`addMember HTTP ${res.status}: ${err}`);
  }
  const data = await res.json<{ result: CfMember }>();
  return data.result;
}
```

New invitations land in `status: "pending"` until the user accepts. The role assignment
is applied immediately regardless of acceptance state.

---

## 3. List and Find Members

```typescript
export async function listMembers(
  accountId: string,
  token: string,
  page = 1,
  perPage = 50,
): Promise<CfMember[]> {
  const url = new URL(`${CF_BASE}/accounts/${accountId}/members`);
  url.searchParams.set("page", String(page));
  url.searchParams.set("per_page", String(perPage));

  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`listMembers HTTP ${res.status}`);
  const data = await res.json<{ result: CfMember[]; result_info: { total_pages: number } }>();
  return data.result;
}

export async function getMemberByEmail(
  accountId: string,
  token: string,
  email: string,
): Promise<CfMember> {
  // CF API does not support direct email filter — page through all members
  let page = 1;
  while (true) {
    const members = await listMembers(accountId, token, page);
    if (members.length === 0) break;
    const found = members.find((m) => m.user.email === email);
    if (found) return found;
    page++;
  }
  throw new Error(`Member not found: ${email}`);
}
```

---

## 4. Update Member Roles (Replace, Not Append)

```typescript
export async function updateMemberRoles(
  accountId: string,
  token: string,
  memberId: string,
  roleIds: string[],
): Promise<CfMember> {
  const res = await fetch(`${CF_BASE}/accounts/${accountId}/members/${memberId}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ roles: roleIds.map((id) => ({ id })) }),
  });
  if (!res.ok) throw new Error(`updateMemberRoles HTTP ${res.status}`);
  const data = await res.json<{ result: CfMember }>();
  return data.result;
}
```

`PUT` **replaces** the entire role array. To add a role without removing existing ones,
fetch current roles first and merge.

---

## 5. Remove a Member

```typescript
export async function removeMember(
  accountId: string,
  token: string,
  memberId: string,
): Promise<void> {
  const res = await fetch(`${CF_BASE}/accounts/${accountId}/members/${memberId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 404) return; // idempotent
  if (!res.ok) throw new Error(`removeMember HTTP ${res.status}`);
}
```

---

## 6. Worker Handler — Webhook-Driven Provisioning

```typescript
// src/index.ts
import { addMember, findRoleByName, getMemberByEmail, removeMember } from "./lib/cloudflare-members";

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;       // Worker secret
  WEBHOOK_SECRET: string;     // HMAC secret for incoming webhook verification
}

type ProvisioningEvent =
  | { action: "add";    email: string; roles: string[] }
  | { action: "remove"; email: string };

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    // Verify HMAC signature from HRIS webhook
    const sig  = req.headers.get("X-Hub-Signature-256") ?? "";
    const body = await req.text();
    const valid = await verifyHmac(body, sig, env.WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const event: ProvisioningEvent = JSON.parse(body);

    if (event.action === "add") {
      const roleIds: string[] = [];
      for (const roleName of event.roles) {
        const role = await findRoleByName(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, roleName);
        if (!role) return new Response(`Unknown role: ${roleName}`, { status: 400 });
        roleIds.push(role.id);
      }
      const member = await addMember(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, event.email, roleIds);
      return Response.json({ status: "added", memberId: member.id });
    }

    if (event.action === "remove") {
      const member = await getMemberByEmail(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, event.email);
      await removeMember(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, member.id);
      return Response.json({ status: "removed" });
    }

    return new Response("Unknown action", { status: 400 });
  },
};

async function verifyHmac(body: string, signature: string, secret: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["verify"],
  );
  const expected = new TextEncoder().encode(
    "sha256=" + bufToHex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body))),
  );
  const actual = new TextEncoder().encode(signature);
  if (expected.length !== actual.length) return false;
  return crypto.subtle.verify("HMAC", key,
    hexToBuf(signature.replace("sha256=", "")),
    new TextEncoder().encode(body),
  );
}

function bufToHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function hexToBuf(hex: string): ArrayBuffer {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  return bytes.buffer;
}
```

---

## Anti-patterns

- **Using a Global API Key** — use scoped API tokens. A global key grants full account
  access and cannot be rotated independently.
- **Caching role IDs in `wrangler.toml`** — role IDs are stable but can change during
  account plan changes; always look them up by name at runtime or in a D1 table.
- **Ignoring 409 on `addMember`** — treat it as idempotent; the member already exists.
- **Storing the API token as a plain env var** — use `wrangler secret put CF_API_TOKEN`.
- **Running member enumeration on every request** — cache the member list in KV with a
  short TTL (60 s) for accounts with many members.

---

## Gotchas

- The account owner cannot be removed via the API — DELETE returns 400.
- Role IDs are UUIDs stable per account but differ between accounts (no global catalog).
- `status: "pending"` members count against your member limit.
- The `Account Settings: Edit` permission on the API token is required; `Account:Read`
  alone is insufficient for mutations.
- Cloudflare enforces a minimum of one Super Administrator per account — removing the
  last Super Admin via API is blocked with HTTP 400.

---

## Verification

```bash
# List current members
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/members" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {email: .user.email, roles: [.roles[].name]}'

# List available roles
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/roles" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name}'
```

---

## Related

- `cloudflare-account-organization-team-access.md`
- `cloudflare-account-audit-log-workers-monitoring.md`
- `cloudflare-workers-api-token-scoping.md`
- `cloudflare-api-pagination-automation-workers.md`

---

## Sources

- CF Account Members API: https://developers.cloudflare.com/api/operations/account-members-list-members
- CF API token scoping: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- Worker Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
