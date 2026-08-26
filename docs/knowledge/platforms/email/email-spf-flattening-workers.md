# SPF Record Flattening with Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

SPF records are limited to 10 DNS lookups (RFC 7208 §4.6.4). Modern senders using multiple ESPs,
CRMs, and marketing tools quickly exceed this limit, causing `permerror` and failed authentication.
Manual flattening becomes stale within days. A scheduled Worker can automatically resolve every
`include:`, `a:`, and `mx:` mechanism to raw IP ranges and write a flattened SPF record back to
Cloudflare DNS — keeping it accurate without human intervention.

## Context

SPF flattening resolves all nested DNS references into explicit `ip4:` and `ip6:` CIDR blocks.
The resulting record has zero additional lookups. The trade-off is that the record must be
refreshed whenever an ESP changes their sending IPs — a scheduled Worker handles this. The
Cloudflare DNS API (`/zones/{zoneId}/dns_records`) is used to update the TXT record atomically.

## Reading the Existing SPF Record

```typescript
// scheduled-spf-flatten/src/index.ts
async function fetchCurrentSpf(zone: string, apiToken: string): Promise<string | null> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zone}/dns_records?type=TXT&name=@`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const data = await res.json<{ result: Array<{ id: string; content: string }> }>();
  const record = data.result.find(r => r.content.startsWith('v=spf1'));
  return record ? record.content : null;
}
```

## Resolving SPF Mechanisms Recursively

```typescript
async function resolveSpf(domain: string, depth = 0): Promise<string[]> {
  if (depth > 10) throw new Error(`SPF resolution depth exceeded for ${domain}`);

  const res = await fetch(`https://cloudflare-dns.com/dns-query?name=${domain}&type=TXT`, {
    headers: { Accept: 'application/dns-json' },
  });
  const data = await res.json<{ Answer?: Array<{ data: string }> }>();
  const spfRecord = data.Answer?.map(a => a.data.replace(/"/g, ''))
    .find(s => s.startsWith('v=spf1'));

  if (!spfRecord) return [];

  const cidrs: string[] = [];
  const tokens = spfRecord.split(' ');

  for (const token of tokens) {
    if (token.startsWith('include:')) {
      const nested = await resolveSpf(token.slice(8), depth + 1);
      cidrs.push(...nested);
    } else if (token.startsWith('ip4:') || token.startsWith('ip6:')) {
      cidrs.push(token);
    } else if (token.startsWith('a:') || token === 'a') {
      const host = token === 'a' ? domain : token.slice(2);
      const aRes = await fetch(`https://cloudflare-dns.com/dns-query?name=${host}&type=A`, {
        headers: { Accept: 'application/dns-json' },
      });
      const aData = await aRes.json<{ Answer?: Array<{ data: string }> }>();
      for (const a of aData.Answer ?? []) cidrs.push(`ip4:${a.data}`);
    }
  }

  return [...new Set(cidrs)];
}
```

## Building the Flat Record

```typescript
function buildFlatSpf(cidrs: string[], qualifier = '~all'): string {
  // SPF record must stay under 255 chars per string, 10 strings max in DNS TXT
  // Google/Yahoo require hard fail (-all) or soft fail (~all) at minimum
  const mechanisms = cidrs.join(' ');
  return `v=spf1 ${mechanisms} ${qualifier}`;
}

function validateLength(record: string): void {
  if (record.length > 512) {
    // Single TXT value limit before multi-string encoding needed
    console.warn(`SPF record is ${record.length} chars — consider pruning stale ESPs`);
  }
  if (record.length > 4096) {
    throw new Error('SPF record exceeds RFC safe limit; remove unused ESP includes');
  }
}
```

## Writing the Updated Record to Cloudflare DNS

```typescript
async function updateSpfRecord(
  zoneId: string,
  recordId: string,
  flatRecord: string,
  apiToken: string
): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/dns_records/${recordId}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'TXT',
        name: '@',
        content: flatRecord,
        ttl: 300, // Low TTL so stale CIDRs expire quickly
      }),
    }
  );
  if (!res.ok) throw new Error(`DNS update failed: ${await res.text()}`);
}
```

## Scheduled Worker Entry Point

```typescript
// wrangler.toml: [triggers] crons = ["0 */6 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const domain = env.SENDING_DOMAIN; // e.g. "mail.example.com"
    const cidrs = await resolveSpf(domain);
    const flatRecord = buildFlatSpf(cidrs, '~all');
    validateLength(flatRecord);

    const current = await fetchCurrentSpf(env.CF_ZONE_ID, env.CF_API_TOKEN);
    if (current === flatRecord) {
      console.log('SPF unchanged, skipping update');
      return;
    }

    // Store record ID on first run via KV or hard-code it
    const recordId = await env.SPF_KV.get('spf_record_id');
    if (!recordId) throw new Error('SPF_RECORD_ID not set in KV');

    await updateSpfRecord(env.CF_ZONE_ID, recordId, flatRecord, env.CF_API_TOKEN);
    await env.SPF_KV.put('spf_last_updated', new Date().toISOString());
    console.log(`SPF updated: ${flatRecord}`);
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- **Hardcoding IPs**: ESPs rotate IPs; the whole point of this Worker is to stay current.
- **Using `+all`**: Never. Qualifiers must be `~all` or `-all`.
- **Ignoring length**: A 10 KB SPF record will be silently truncated by many resolvers.
- **Not deduplicating CIDRs**: Multiple ESPs sharing Fastly or AWS IPs inflate the record needlessly.
- **Single-run on deploy**: Schedule this; stale IPs break delivery silently weeks later.

## Gotchas

- The 10-lookup limit counts `exists:`, `ptr:`, `mx`, and `a` mechanisms, not just `include:`.
- Cloudflare's DNS-over-HTTPS endpoint (`cloudflare-dns.com/dns-query`) respects TTL — cache
  resolver results in KV for the record TTL to avoid re-fetching within a run.
- Some ESPs use `include:` chains 3–4 levels deep; set `depth` limit and alert on breach.
- `mx:` mechanism resolves to A/AAAA records of MX hosts — expensive and rarely needed for sends.
- The Cloudflare DNS API requires `Zone:DNS:Edit` permission on the API token.

## Verification

```bash
# Confirm zero lookup count on flattened record
dig TXT mail.example.com +short | grep spf1

# Count mechanisms that would trigger lookups (should be 0 after flattening)
dig TXT mail.example.com +short | grep -oE '(include|mx|a|exists|ptr):[^ ]+' | wc -l

# Validate SPF via MXToolbox
curl -s "https://mxtoolbox.com/SuperTool.aspx?action=spf%3Amail.example.com"
```

## Related

- `spf-record-setup.md`
- `spf-dkim-dmarc-alignment-debugging-workers.md`
- `email-mx-dns-validation-workers.md`
- `dmarc-policy-setup.md`

## Sources

- RFC 7208 — Sender Policy Framework (SPF) §4.6.4 DNS Lookup Limits
- Cloudflare DNS Records API — https://developers.cloudflare.com/api/operations/dns-records-for-a-zone-update-dns-record
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
