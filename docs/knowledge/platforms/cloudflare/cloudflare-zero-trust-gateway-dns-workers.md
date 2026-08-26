# Cloudflare Gateway DNS Policies for Workers Infrastructure

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to enforce DNS-layer filtering for all outbound requests originating from your Workers infrastructure — blocking malicious domains, enforcing allowed-list egress, or categorizing traffic — using Cloudflare Zero Trust Gateway without a WARP client.

## Context
Cloudflare Zero Trust Gateway provides DNS, HTTP, and network filtering at the Cloudflare edge. Workers scripts can route their DNS resolution through Gateway by setting a custom resolver via a `fetch` service binding or by using the `cloudflare:sockets` TCP API to query a Gateway DNS-over-HTTPS (DoH) endpoint scoped to a specific Zero Trust location. Gateway policies are evaluated server-side before the upstream DNS query fires, making them enforceable even when Workers have outbound `fetch` calls. The Zero Trust REST API lets Workers cron triggers dynamically add/remove DNS policies as infrastructure changes.

## Architecture / Setup

Gateway location creation (via Cloudflare API from a cron Worker):
```typescript
// cron-setup/src/index.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string; // needs Zero Trust: Edit permission
}

interface GatewayLocation {
  id: string;
  name: string;
  doh_subdomain: string;
}

async function createGatewayLocation(
  env: Env,
  name: string
): Promise<GatewayLocation> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/gateway/locations`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name,
        networks: [], // DOH-only location, no source IP restriction
        doh_subdomain: name.toLowerCase().replace(/\s+/g, "-"),
      }),
    }
  );
  const data = (await resp.json()) as { result: GatewayLocation };
  return data.result;
}
```

## DNS Policy Management from Workers

Create and update DNS policies programmatically via the Gateway Policy API:
```typescript
// policy-manager/src/index.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  GATEWAY_LOCATION_ID: string;
}

type PolicyAction = "block" | "allow" | "log";

interface GatewayPolicy {
  name: string;
  action: PolicyAction;
  filters: string[];
  traffic: string; // GCRE expression
  enabled: boolean;
  priority: number;
}

async function upsertDnsPolicy(
  env: Env,
  policy: GatewayPolicy
): Promise<void> {
  // List existing to check for name collision
  const listResp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/gateway/rules`,
    {
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
    }
  );
  const list = (await listResp.json()) as {
    result: Array<{ id: string; name: string }>;
  };

  const existing = list.result.find((r) => r.name === policy.name);

  const url = existing
    ? `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/gateway/rules/${existing.id}`
    : `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/gateway/rules`;

  await fetch(url, {
    method: existing ? "PUT" : "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(policy),
  });
}

// Example: block known malware categories for Workers egress
const malwareBlockPolicy: GatewayPolicy = {
  name: "workers-malware-block",
  action: "block",
  filters: ["dns"],
  traffic: `dns.security_category in {2 3 4 5 6 7 8 9}`, // Cloudflare security categories
  enabled: true,
  priority: 1,
};
```

## DoH Query from a Worker via the Gateway Endpoint

Workers can route individual DNS lookups through a Gateway location's DoH endpoint to enforce policy on resolution:
```typescript
// dns-resolver/src/index.ts
interface Env {
  GATEWAY_DOH_URL: string; // e.g. https://<doh_subdomain>.cloudflare-gateway.com/dns-query
}

async function resolveViGateway(
  env: Env,
  hostname: string
): Promise<string[]> {
  const url = new URL(env.GATEWAY_DOH_URL);
  url.searchParams.set("name", hostname);
  url.searchParams.set("type", "A");

  const resp = await fetch(url.toString(), {
    headers: { Accept: "application/dns-json" },
  });

  if (!resp.ok) {
    throw new Error(`Gateway DoH error: ${resp.status}`);
  }

  const json = (await resp.json()) as {
    Status: number; // RCODE: 0=NOERROR, 3=NXDOMAIN, 5=REFUSED (blocked)
    Answer?: Array<{ data: string }>;
  };

  if (json.Status === 5) {
    throw new Error(`Domain ${hostname} is blocked by Gateway policy`);
  }

  return (json.Answer ?? []).map((a) => a.data);
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(req.url);
    const host = searchParams.get("host") ?? "";

    try {
      const ips = await resolveViGateway(env, host);
      return Response.json({ host, ips });
    } catch (err) {
      return Response.json(
        { error: (err as Error).message },
        { status: 403 }
      );
    }
  },
};
```

## Cron Trigger: Sync Block-list to Gateway

Periodically refresh a domain block-list (e.g., from a threat intel feed) into a Gateway DNS policy:
```typescript
// blocklist-sync/src/index.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  BLOCKLIST_URL: string; // plaintext newline-separated domain list
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Fetch the latest block-list
    const raw = await fetch(env.BLOCKLIST_URL).then((r) => r.text());
    const domains = raw
      .split("\n")
      .map((d) => d.trim())
      .filter((d) => d && !d.startsWith("#"));

    // Build the GCRE traffic expression
    // Gateway supports up to 1000 domains per rule; chunk if needed
    const chunkSize = 1000;
    for (let i = 0; i < domains.length; i += chunkSize) {
      const chunk = domains.slice(i, i + chunkSize);
      const expr = chunk.map((d) => `dns.fqdn == "${d}"`).join(" or ");

      await fetch(
        `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/gateway/rules`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.CF_API_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: `threat-intel-block-${i / chunkSize}`,
            action: "block",
            filters: ["dns"],
            traffic: expr,
            enabled: true,
            priority: 10 + Math.floor(i / chunkSize),
          }),
        }
      );
    }
  },
};
```

## Anti-patterns
- **Using Gateway DNS as a security boundary for Workers outbound `fetch`** — Gateway DoH only filters resolution; a Worker can still call a raw IP directly via `fetch("http://1.2.3.4/...")`. Combine with network egress policies and WAF rules.
- **Creating unlimited Gateway rules** — Cloudflare imposes account-level rule limits; consolidate large domain lists using `dns.domains` list objects (Gateway Lists) instead of per-domain expressions.
- **Storing CF API tokens in `wrangler.toml`** — use Workers Secrets (`wrangler secret put CF_API_TOKEN`) and reference via `env.CF_API_TOKEN`.
- **Polling Gateway rule state inside request handlers** — management API calls are slow; use cron triggers for sync and cache the result in KV.

## Gotchas
- Gateway DNS-over-HTTPS endpoints are per-location; each location has a unique `doh_subdomain` — store it as a Worker secret, not a hard-coded constant.
- RCODE 5 (`REFUSED`) is the Gateway block signal in DoH JSON responses — treat it as a policy violation, not a network error.
- Zero Trust Gateway rules use Cloudflare's Gateway Configuration Rule Expression (GCRE), not standard Wireshark filter syntax.
- The Zero Trust API uses `/gateway/rules` for all policy types (DNS, HTTP, Network); filter by `filters: ["dns"]` to avoid modifying HTTP policies unintentionally.
- Gateway location creation requires `Zero Trust: Edit` scope — a narrower `DNS: Edit` token is insufficient.

## Verification
```bash
# Test DoH query through your Gateway location (RCODE 0 = allowed, 5 = blocked)
curl -s "https://<doh_subdomain>.cloudflare-gateway.com/dns-query?name=example.com&type=A" \
  -H "Accept: application/dns-json" | jq '.Status'

# List all Gateway DNS rules in your account
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/gateway/rules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name,action,enabled}'

# Trigger cron sync manually via Wrangler
wrangler trigger cron --name blocklist-sync --schedule now
```

## Related
- [cloudflare-teams-gateway.md](cloudflare-teams-gateway.md)
- [cloudflare-dns-over-https-workers-doh-proxy.md](cloudflare-dns-over-https-workers-doh-proxy.md)
- [zero-trust-access.md](zero-trust-access.md)
- [cloudflare-access-zero-trust-service-tokens.md](cloudflare-access-zero-trust-service-tokens.md)
- [workers-cron-triggers.md](workers-cron-triggers.md)

## Sources
- https://developers.cloudflare.com/cloudflare-one/policies/gateway/dns-policies/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/agentless/dns/locations/
- https://developers.cloudflare.com/cloudflare-one/api-crud-operations/
- https://developers.cloudflare.com/cloudflare-one/policies/gateway/dns-policies/dns-over-https/
