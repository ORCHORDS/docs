# Programmatic DNS Record Management via Cloudflare API from Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your deployment pipeline needs to create or update DNS records programmatically — for example, blue-green deployments that switch a CNAME, automated cert-validation TXT records, or bulk DNS migrations. You want a Worker that wraps the Cloudflare DNS API so other internal services can manage DNS records through a secure HTTP interface without exposing the API token broadly.

## Context

The Cloudflare DNS REST API (`/zones/{zone_id}/dns_records`) supports full CRUD for all record types. A Worker acts as a secure proxy: it holds the API token as a Wrangler secret, validates caller auth, and translates simplified requests into Cloudflare API calls. This pattern also enables DNS record management from CI pipelines, other Workers, and external services with no direct API token exposure.

Record types covered: A, AAAA, CNAME, MX, TXT, SRV. The blue-green DNS switch pattern is covered in detail.

## Solution

### Types

```typescript
// src/types.ts
export type DnsRecordType = "A" | "AAAA" | "CNAME" | "MX" | "TXT" | "SRV";

export interface DnsRecord {
  id?: string;
  type: DnsRecordType;
  name: string;     // FQDN or relative name
  content: string;  // IP, hostname, text value
  ttl?: number;     // 1 = automatic
  proxied?: boolean;
  priority?: number; // MX, SRV
  comment?: string;
}

export interface CfDnsRecord extends DnsRecord {
  id: string;
  zone_id: string;
  created_on: string;
  modified_on: string;
}

export interface Env {
  CF_API_TOKEN: string;  // wrangler secret put CF_API_TOKEN
  CF_ZONE_ID: string;    // wrangler secret put CF_ZONE_ID
  DNS_ADMIN_TOKEN: string; // token for callers of this Worker
}

const CF_API_BASE = "https://api.cloudflare.com/client/v4";
```

### Cloudflare DNS API client

```typescript
// src/cf-dns.ts
import type { DnsRecord, CfDnsRecord, Env } from "./types";

const CF_API_BASE = "https://api.cloudflare.com/client/v4";

function cfHeaders(env: Env): HeadersInit {
  return {
    Authorization: `Bearer ${env.CF_API_TOKEN}`,
    "Content-Type": "application/json",
  };
}

async function cfRequest<T>(
  env: Env,
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const resp = await fetch(`${CF_API_BASE}${path}`, {
    method,
    headers: cfHeaders(env),
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await resp.json<{ success: boolean; result: T; errors: any[] }>();
  if (!json.success) {
    throw new Error(`CF API error: ${JSON.stringify(json.errors)}`);
  }
  return json.result;
}

/** List all DNS records, optionally filtered by name and/or type */
export async function listRecords(
  env: Env,
  filter?: { name?: string; type?: string }
): Promise<CfDnsRecord[]> {
  const params = new URLSearchParams();
  if (filter?.name) params.set("name", filter.name);
  if (filter?.type) params.set("type", filter.type);
  const query = params.size ? `?${params}` : "";
  return cfRequest<CfDnsRecord[]>(
    env, "GET", `/zones/${env.CF_ZONE_ID}/dns_records${query}`
  );
}

/** Create a DNS record */
export async function createRecord(
  env: Env,
  record: DnsRecord
): Promise<CfDnsRecord> {
  return cfRequest<CfDnsRecord>(
    env, "POST", `/zones/${env.CF_ZONE_ID}/dns_records`, record
  );
}

/** Update an existing DNS record by ID */
export async function updateRecord(
  env: Env,
  id: string,
  record: Partial<DnsRecord>
): Promise<CfDnsRecord> {
  return cfRequest<CfDnsRecord>(
    env, "PATCH", `/zones/${env.CF_ZONE_ID}/dns_records/${id}`, record
  );
}

/** Delete a DNS record by ID */
export async function deleteRecord(
  env: Env,
  id: string
): Promise<{ id: string }> {
  return cfRequest<{ id: string }>(
    env, "DELETE", `/zones/${env.CF_ZONE_ID}/dns_records/${id}`
  );
}

/** Upsert: update existing record matching name+type, or create if not found */
export async function upsertRecord(
  env: Env,
  record: DnsRecord
): Promise<CfDnsRecord> {
  const existing = await listRecords(env, { name: record.name, type: record.type });
  if (existing.length > 0) {
    return updateRecord(env, existing[0].id, record);
  }
  return createRecord(env, record);
}
```

### Blue-green DNS switch

```typescript
// src/blue-green.ts
import type { Env } from "./types";
import { listRecords, updateRecord } from "./cf-dns";

export type Slot = "blue" | "green";

interface BlueGreenConfig {
  hostname: string;   // e.g. "api.example.com"
  blue: string;       // e.g. "blue.api.example.com"
  green: string;      // e.g. "green.api.example.com"
  ttl: number;        // seconds — use low TTL (60) during deployment
}

/**
 * Switch the CNAME for `hostname` to point to the target slot.
 * Optionally sets a low TTL before the switch and restores it after.
 */
export async function switchSlot(
  env: Env,
  config: BlueGreenConfig,
  targetSlot: Slot,
  options: { preSwitchTtl?: number; postSwitchTtl?: number } = {}
): Promise<{ previousSlot: Slot | null; record: any }> {
  const { hostname, blue, green, ttl } = config;
  const targetContent = targetSlot === "blue" ? blue : green;

  // Find current CNAME
  const records = await listRecords(env, { name: hostname, type: "CNAME" });
  if (records.length === 0) {
    throw new Error(`No CNAME record found for ${hostname}`);
  }
  const current = records[0];
  const previousSlot: Slot | null =
    current.content === blue ? "blue" :
    current.content === green ? "green" : null;

  // Step 1: Lower TTL before switch for fast propagation
  if (options.preSwitchTtl) {
    await updateRecord(env, current.id, { ttl: options.preSwitchTtl });
    // Wait for TTL to drain (callers should wait preSwitchTtl seconds)
  }

  // Step 2: Switch CNAME content
  const updated = await updateRecord(env, current.id, {
    content: targetContent,
    ttl: options.preSwitchTtl ?? ttl,
  });

  // Step 3: Restore TTL after switch
  if (options.postSwitchTtl) {
    await updateRecord(env, current.id, { ttl: options.postSwitchTtl });
  }

  return { previousSlot, record: updated };
}
```

### Bulk record operations

```typescript
// src/bulk.ts
import type { DnsRecord, CfDnsRecord, Env } from "./types";
import { createRecord, updateRecord, deleteRecord, listRecords } from "./cf-dns";

export interface BulkOperation {
  action: "upsert" | "delete";
  record: DnsRecord;
}

export interface BulkResult {
  action: string;
  record: DnsRecord;
  result?: CfDnsRecord;
  error?: string;
}

export async function bulkApply(
  env: Env,
  operations: BulkOperation[]
): Promise<BulkResult[]> {
  // Execute in parallel with a concurrency limit to avoid rate-limiting
  const CONCURRENCY = 5;
  const results: BulkResult[] = [];

  for (let i = 0; i < operations.length; i += CONCURRENCY) {
    const batch = operations.slice(i, i + CONCURRENCY);
    const batchResults = await Promise.allSettled(
      batch.map(async (op): Promise<BulkResult> => {
        if (op.action === "delete") {
          const existing = await listRecords(env, {
            name: op.record.name,
            type: op.record.type,
          });
          if (existing.length === 0) {
            return { action: "delete", record: op.record, error: "not found" };
          }
          await deleteRecord(env, existing[0].id);
          return { action: "delete", record: op.record };
        }
        // upsert
        const existing = await listRecords(env, {
          name: op.record.name,
          type: op.record.type,
        });
        const result =
          existing.length > 0
            ? await updateRecord(env, existing[0].id, op.record)
            : await createRecord(env, op.record);
        return { action: "upsert", record: op.record, result };
      })
    );
    for (const r of batchResults) {
      results.push(
        r.status === "fulfilled"
          ? r.value
          : { action: "error", record: {} as DnsRecord, error: String((r as PromiseRejectedResult).reason) }
      );
    }
  }
  return results;
}
```

### HTTP Worker entry point

```typescript
// src/index.ts
import type { Env } from "./types";
import { createRecord, updateRecord, deleteRecord, listRecords, upsertRecord } from "./cf-dns";
import { switchSlot } from "./blue-green";
import { bulkApply } from "./bulk";

function authCheck(request: Request, env: Env): Response | null {
  const token = request.headers.get("Authorization")?.replace("Bearer ", "");
  if (token !== env.DNS_ADMIN_TOKEN) {
    return new Response("Unauthorized", { status: 401 });
  }
  return null;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const deny = authCheck(request, env);
    if (deny) return deny;

    const url = new URL(request.url);
    const json = async () => request.json<any>();

    // GET /records?name=...&type=...
    if (request.method === "GET" && url.pathname === "/records") {
      const records = await listRecords(env, {
        name: url.searchParams.get("name") ?? undefined,
        type: url.searchParams.get("type") ?? undefined,
      });
      return Response.json(records);
    }

    // POST /records  — create
    if (request.method === "POST" && url.pathname === "/records") {
      const body = await json();
      const record = await createRecord(env, body);
      return Response.json(record, { status: 201 });
    }

    // PUT /records  — upsert
    if (request.method === "PUT" && url.pathname === "/records") {
      const body = await json();
      const record = await upsertRecord(env, body);
      return Response.json(record);
    }

    // PATCH /records/:id  — partial update
    if (request.method === "PATCH" && url.pathname.startsWith("/records/")) {
      const id = url.pathname.split("/")[2];
      const body = await json();
      const record = await updateRecord(env, id, body);
      return Response.json(record);
    }

    // DELETE /records/:id
    if (request.method === "DELETE" && url.pathname.startsWith("/records/")) {
      const id = url.pathname.split("/")[2];
      await deleteRecord(env, id);
      return new Response(null, { status: 204 });
    }

    // POST /blue-green/switch
    if (request.method === "POST" && url.pathname === "/blue-green/switch") {
      const body = await json();
      const result = await switchSlot(env, body.config, body.targetSlot, body.options ?? {});
      return Response.json(result);
    }

    // POST /bulk
    if (request.method === "POST" && url.pathname === "/bulk") {
      const { operations } = await json();
      const results = await bulkApply(env, operations);
      return Response.json(results);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

### wrangler.toml

```toml
name = "example project-dns-manager"
main = "src/index.ts"
compatibility_date = "2024-09-23"
```

## Implementation Details

### TTL management for blue-green

1. Set TTL to 60 seconds **before** a planned switch.
2. Wait `old_TTL` seconds so all resolvers have flushed the cached record.
3. Switch the CNAME content.
4. Restore TTL to 3600 seconds after the switch is confirmed.

Skipping step 2 means some resolvers will serve the old content for up to the full previous TTL.

### MX record creation

```typescript
await createRecord(env, {
  type: "MX",
  name: "example.com",
  content: "mail.example.com",
  priority: 10,
  ttl: 3600,
  proxied: false, // MX records cannot be proxied
});
```

### TXT record for domain verification

```typescript
await createRecord(env, {
  type: "TXT",
  name: "_acme-challenge.example.com",
  content: "verification-token-from-acme",
  ttl: 60,
});
// Delete after verification
await deleteRecord(env, record.id!);
```

## Anti-patterns

- **Proxying MX or TXT records** — MX, TXT, and SRV records cannot be Cloudflare-proxied; always set `proxied: false` for these types.
- **Using TTL 1 (automatic) for records during a blue-green switch** — automatic TTL is ~300 seconds, which creates a long propagation window during switchover. Explicitly set TTL to 60 before switching.
- **Deleting and recreating records instead of updating** — a delete+create cycle causes a brief DNS NXDOMAIN window. Use PATCH/update to change record content in place.
- **Parallelising all bulk operations without rate-limit awareness** — Cloudflare's DNS API rate limit is 1200 requests/5 minutes per zone per token. Batch in groups of 5 and add backoff on 429 responses.

## Gotchas

- `proxied: true` only works for A, AAAA, and CNAME records on zones using Cloudflare's nameservers. Attempting to proxy other record types returns a `1004` API error.
- The `name` field in Cloudflare's API is always stored as the FQDN. If you submit a relative name (e.g., `api`), the API expands it to `api.example.com`. Compare FQDNs when checking for existing records.
- Cloudflare CNAME flattening: if the CNAME is at the zone apex, Cloudflare flattens it to an A record in responses. The record type in the API remains `CNAME`.
- API tokens scoped to `Zone > DNS > Edit` are sufficient for all DNS operations. Do not use global API keys.
- DNS propagation after an API update is immediate within Cloudflare's network but can take up to the record's TTL for external resolvers that have cached the old value.

## Verification

```bash
# Create an A record
curl -X POST https://dns-manager.example.com/records \
  -H "Authorization: Bearer ${DNS_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type":"A","name":"test.example.com","content":"1.2.3.4","ttl":60}'

# Verify it exists
curl "https://dns-manager.example.com/records?name=test.example.com&type=A" \
  -H "Authorization: Bearer ${DNS_ADMIN_TOKEN}" | jq .

# Check DNS resolution
dig test.example.com A @1.1.1.1

# Blue-green switch
curl -X POST https://dns-manager.example.com/blue-green/switch \
  -H "Authorization: Bearer ${DNS_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"config":{"hostname":"api.example.com","blue":"blue.api.example.com","green":"green.api.example.com","ttl":3600},"targetSlot":"green","options":{"preSwitchTtl":60}}'

# Confirm switch
dig api.example.com CNAME @1.1.1.1
```

## Related

- `documentation/categories/infra/workers-terraform-cloudflare-provider.md`
- `documentation/categories/infra/workers-multi-region-failover-routing.md`

## Sources

- https://developers.cloudflare.com/api/resources/dns/
- https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/
- https://developers.cloudflare.com/dns/additional-options/cname-flattening/
