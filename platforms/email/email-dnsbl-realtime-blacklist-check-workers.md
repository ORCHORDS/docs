# Real-Time DNSBL Blacklist Checking with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Before delivering a transactional email — or before accepting an inbound message from an unknown sender — you need to know whether the originating IP is listed on one or more DNS-based Blocklists (DNSBLs). Checking at processing time lets you skip blacklisted IPs in your shared sending pool, route through a clean IP, or refuse inbound mail from known spam sources before content filtering even begins.

DNSBL queries are lightweight DNS lookups. A Cloudflare Worker can run them inline during inbound processing or as a pre-send validation step, with results cached in KV to avoid redundant lookups for the same IP within a configurable TTL window.

## Context

A DNSBL lookup reverses the IP address octets, appends the blocklist domain, and performs an `A` record DNS query. A response of `127.0.0.x` indicates the IP is listed; `NXDOMAIN` means it is clean. The low-order octet encodes the listing category (spam source, malware command-and-control, snowshoe, etc.). Popular public DNSBLs include Spamhaus ZEN (`zen.spamhaus.org`), SpamCop (`bl.spamcop.net`), and SORBS (`dnsbl.sorbs.net`).

Cloudflare Workers do not expose raw UDP sockets, so traditional DNSBL queries cannot be issued directly. Instead, use Cloudflare's DNS over HTTPS (DoH) endpoint (`cloudflare-dns.com/dns-query`) via the `fetch` API. DoH returns identical answers to recursive DNS and is available from any Worker with no additional configuration.

## DNSBL Lookup via DNS over HTTPS

```typescript
export interface Env {
  DNSBL_CACHE: KVNamespace;
}

const DNSBLS = [
  "zen.spamhaus.org",
  "bl.spamcop.net",
  "dnsbl.sorbs.net",
];

function reverseIpv4(ip: string): string {
  return ip.split(".").reverse().join(".");
}

async function dohQuery(hostname: string): Promise<string[]> {
  const url =
    `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(hostname)}&type=A`;

  const response = await fetch(url, {
    headers: { Accept: "application/dns-json" },
  });

  if (!response.ok) return [];

  const json = await response.json<{
    Status?: number;
    Answer?: Array<{ data: string }>;
  }>();

  // Status 3 = NXDOMAIN = IP is not listed on this DNSBL
  if (json.Status === 3 || !json.Answer) return [];

  return json.Answer.map((a) => a.data);
}

async function checkIpOnDnsbl(
  ip: string,
  dnsbl: string
): Promise<{ listed: boolean; returnCodes: string[] }> {
  const query = `${reverseIpv4(ip)}.${dnsbl}`;
  const codes = await dohQuery(query);
  return { listed: codes.length > 0, returnCodes: codes };
}
```

## KV-Cached Multi-DNSBL Check

Cache results to avoid re-querying the same IP within the TTL window. Listed IPs get a longer cache entry so subsequent messages from the same source are blocked cheaply.

```typescript
interface DnsblResult {
  listed: boolean;
  lists: string[];
  returnCodes: string[];
  checkedAt: number;
}

const CLEAN_TTL_SECONDS = 3_600;   // 1 hour
const LISTED_TTL_SECONDS = 86_400; // 24 hours

async function checkIpWithCache(
  ip: string,
  env: Env
): Promise<DnsblResult> {
  const cacheKey = `dnsbl:v1:${ip}`;
  const cached = await env.DNSBL_CACHE.get<DnsblResult>(cacheKey, "json");
  if (cached) return cached;

  // Run all DNSBL checks in parallel to minimise latency
  const checks = await Promise.allSettled(
    DNSBLS.map(async (dnsbl) => {
      const result = await checkIpOnDnsbl(ip, dnsbl);
      return { dnsbl, ...result };
    })
  );

  const listedOn = checks
    .filter(
      (r): r is PromiseFulfilledResult<{ dnsbl: string; listed: boolean; returnCodes: string[] }> =>
        r.status === "fulfilled" && r.value.listed
    )
    .map((r) => r.value);

  const result: DnsblResult = {
    listed: listedOn.length > 0,
    lists: listedOn.map((c) => c.dnsbl),
    returnCodes: listedOn.flatMap((c) => c.returnCodes),
    checkedAt: Date.now(),
  };

  const ttl = result.listed ? LISTED_TTL_SECONDS : CLEAN_TTL_SECONDS;
  await env.DNSBL_CACHE.put(cacheKey, JSON.stringify(result), {
    expirationTtl: ttl,
  });

  return result;
}
```

## Inbound Email Worker Integration

Extract the originating MTA IP from the topmost `Received:` header and reject if listed.

```typescript
import { EmailMessage } from "cloudflare:email";

// Matches the first IPv4 address in square brackets in a Received: header
const RECEIVED_IP_RE = /\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]/;

// RFC 5737 / RFC 3927 private ranges to skip DNSBL checks on
const SKIP_PREFIXES = ["10.", "192.168.", "172.", "127.", "169.254."];

function isPrivateOrLoopback(ip: string): boolean {
  return SKIP_PREFIXES.some((p) => ip.startsWith(p));
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const received = message.headers.get("received") ?? "";
    const ipMatch = received.match(RECEIVED_IP_RE);

    if (ipMatch) {
      const senderIp = ipMatch[1];

      if (!isPrivateOrLoopback(senderIp)) {
        const dnsblResult = await checkIpWithCache(senderIp, env);

        if (dnsblResult.listed) {
          console.warn(
            JSON.stringify({
              event: "dnsbl_reject",
              ip: senderIp,
              lists: dnsblResult.lists,
              returnCodes: dnsblResult.returnCodes,
              from: message.from,
              to: message.to,
            })
          );
          await message.setReject(
            `550 5.7.1 ${senderIp} is listed on ${dnsblResult.lists.join(", ")}`
          );
          return;
        }
      }
    }

    // IP is clean or private — forward normally
    await message.forward("inbox@yourdomain.com");
  },
};
```

## Pre-send Outbound IP Pool Validation

Before sending via a shared IP pool, check each candidate IP and select the first clean one.

```typescript
const IP_POOLS: Record<string, string[]> = {
  primary:   ["203.0.113.10", "203.0.113.11"],
  secondary: ["198.51.100.20", "198.51.100.21"],
};

async function selectCleanSendingIp(env: Env): Promise<string | null> {
  for (const pool of ["primary", "secondary"] as const) {
    for (const ip of IP_POOLS[pool]) {
      const result = await checkIpWithCache(ip, env);
      if (!result.listed) return ip;
    }
  }
  return null; // All IPs are listed — trigger an alert
}

// Usage before dispatch:
// const sendingIp = await selectCleanSendingIp(env);
// if (!sendingIp) {
//   // Alert ops — all sending IPs are blacklisted
//   throw new Error("No clean sending IP available");
// }
```

## Decoding Return Codes

Different return codes indicate different listing reasons. Map them to human-readable descriptions for alerting:

```typescript
const SPAMHAUS_ZEN_CODES: Record<string, string> = {
  "127.0.0.2": "SBL — Spamhaus Block List (spam source)",
  "127.0.0.3": "SBL CSS — snowshoe spam operation",
  "127.0.0.4": "XBL — CBL exploited system",
  "127.0.0.9": "SBL DROP — Don't Route Or Peer network",
  "127.0.0.10": "PBL ISP — end-user IP (ISP-submitted)",
  "127.0.0.11": "PBL Spamhaus — end-user IP",
};

function describeReturnCodes(
  dnsbl: string,
  codes: string[]
): string[] {
  if (dnsbl === "zen.spamhaus.org") {
    return codes.map((c) => SPAMHAUS_ZEN_CODES[c] ?? `Unknown ZEN code ${c}`);
  }
  return codes;
}
```

## Anti-patterns

- Checking DNSBLs sequentially with `await` inside a loop — each DoH request adds ~50–150 ms; always use `Promise.allSettled` to run checks in parallel
- Querying DNSBLs on every request without caching — DNSBL operators enforce rate limits on query volumes; uncached high-frequency workers will be blocked
- Using raw UDP DNS — Cloudflare Workers do not expose raw socket APIs; DoH is the only DNS query mechanism available
- Blocking inbound processing indefinitely on slow DNSBL responses — use `Promise.race` with a timeout and fail open (accept) on timeout rather than hang
- Treating a DNSBL listing as definitive spam proof — false positives exist; combine with DMARC, SPF/DKIM alignment, and content scoring for a composite signal

## Gotchas

- Spamhaus ZEN requires registration of your query IP for production data access; the free tier is rate-limited and may return NXDOMAIN for all queries once the limit is hit
- Cloudflare Workers' egress IPs are not fixed; the query IP seen by Spamhaus may change between invocations, making per-IP registration impossible — use a data subscription instead
- IPv6 DNSBL lookups require nibble-reversed format: `2001:db8::1` → `1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa` style query; implement separately from IPv4
- Some DNSBLs (e.g., `b.barracudacentral.org`) require your sending IP to be registered for queries; anonymous lookups return NXDOMAIN for all IPs, giving a false "clean" result
- KV `get` with `"json"` type returns `null` on a cache miss, not an empty object — always null-check before treating as a valid cached result

## Verification

1. Test the DoH lookup directly: `curl "https://cloudflare-dns.com/dns-query?name=2.0.0.127.zen.spamhaus.org&type=A" -H "Accept: application/dns-json"` — the Spamhaus test IP `127.0.0.2` should return an A record
2. Send a test inbound message through your Worker with a known-listed source IP (use Spamhaus test IPs in a lab environment) and confirm the Worker logs `dnsbl_reject`
3. Confirm a `dnsbl:v1:<ip>` key with a 24-hour TTL appears in the KV namespace for listed IPs
4. Confirm clean IPs produce a KV entry with ~3600-second TTL
5. Verify that a subsequent request for the same IP does not issue a DoH query (observe via `console.log` in the cache-hit path)

## Related

- email-spam-score-preflight-workers.md
- email-blocklist-remediation.md
- workers-inbound-email-spam-filtering-custom-rules.md
- email-reputation-monitoring.md

## Sources

- Spamhaus ZEN DNSBL documentation: https://www.spamhaus.org/zen/
- Cloudflare DNS over HTTPS API: https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/
- DNSBL query format reference: https://www.dnsbl.info/dnsbl-list.php
