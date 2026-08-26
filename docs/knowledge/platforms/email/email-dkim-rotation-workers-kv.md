# Automated DKIM Key Rotation with Workers and KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
DKIM private keys should be rotated every 6–12 months per NIST and M3AAWG guidance; doing it manually causes downtime when the old selector is removed before propagation.
A Workers Cron Trigger generates a new RSA-2048 key, stores it in KV, publishes the new DNS TXT record via the Cloudflare DNS API, and retires the old selector after a grace period.

## Context
Cloudflare Workers can call the Cloudflare REST API (zones/dns_records) using an API token stored as a Worker secret, making the rotation fully self-contained.
Private keys are stored encrypted-at-rest in KV (Cloudflare encrypts KV values at the infrastructure level).
The active selector name is also tracked in KV so the signing Worker always reads the current key without redeployment.

---

## Architecture / KV Key Schema

```
kv: dkim:active_selector          → "s20260823"         (current live selector)
kv: dkim:pending_selector         → "s20260823"         (selector being propagated)
kv: dkim:selector:<name>:private  → PEM private key
kv: dkim:selector:<name>:public   → PEM public key
kv: dkim:selector:<name>:created  → ISO-8601 timestamp
kv: dkim:selector:<name>:dns_id   → Cloudflare DNS record ID (for deletion)
```

```typescript
export interface Env {
  DKIM_KV: KVNamespace;
  CF_API_TOKEN: string;      // Workers secret: `wrangler secret put CF_API_TOKEN`
  CF_ZONE_ID: string;        // Workers secret or env var
  SIGNING_DOMAIN: string;    // e.g. "example.com"
  KEY_GRACE_DAYS: string;    // e.g. "7" — days old selector stays in DNS after rotation
}
```

## Cron Handler — Key Generation and DNS Publication

```typescript
// src/dkim-rotation.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(rotateDkim(env));
  },
};

async function rotateDkim(env: Env): Promise<void> {
  const graceDays = parseInt(env.KEY_GRACE_DAYS ?? '7', 10);
  const domain = env.SIGNING_DOMAIN;

  // 1. Generate new RSA-2048 key pair using SubtleCrypto
  const keyPair = await crypto.subtle.generateKey(
    { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true,   // extractable
    ['sign', 'verify']
  );

  const privateKeyPkcs8 = await crypto.subtle.exportKey('pkcs8', keyPair.privateKey);
  const publicKeySpki  = await crypto.subtle.exportKey('spki', keyPair.publicKey);

  const toPem = (type: string, buf: ArrayBuffer) =>
    `-----BEGIN ${type}-----\n` +
    btoa(String.fromCharCode(...new Uint8Array(buf)))
      .match(/.{1,64}/g)!
      .join('\n') +
    `\n-----END ${type}-----`;

  const privatePem = toPem('PRIVATE KEY', privateKeyPkcs8);
  const publicPem  = toPem('PUBLIC KEY', publicKeySpki);

  // 2. Build selector name: sYYYYMMDD
  const selector = `s${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`;

  // 3. Derive DKIM public key DNS value (base64 of raw SPKI DER)
  const pubBase64 = btoa(String.fromCharCode(...new Uint8Array(publicKeySpki)));
  const dnsValue = `v=DKIM1; k=rsa; p=${pubBase64}`;
  const dnsName  = `${selector}._domainkey.${domain}`;

  // 4. Publish TXT record via Cloudflare DNS API
  const createResp = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/dns_records`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'TXT',
        name: dnsName,
        content: dnsValue,
        ttl: 300,
        comment: `DKIM selector ${selector} — auto-rotated`,
      }),
    }
  );

  if (!createResp.ok) {
    const err = await createResp.text();
    throw new Error(`DNS record creation failed: ${err}`);
  }

  const { result } = (await createResp.json()) as { result: { id: string } };
  const dnsRecordId = result.id;

  // 5. Store new key material in KV
  await Promise.all([
    env.DKIM_KV.put(`dkim:selector:${selector}:private`, privatePem),
    env.DKIM_KV.put(`dkim:selector:${selector}:public`, publicPem),
    env.DKIM_KV.put(`dkim:selector:${selector}:created`, new Date().toISOString()),
    env.DKIM_KV.put(`dkim:selector:${selector}:dns_id`, dnsRecordId),
    // Mark as pending until DNS propagation confirmed
    env.DKIM_KV.put('dkim:pending_selector', selector),
  ]);

  console.log(`DKIM: generated selector ${selector}, DNS record ${dnsRecordId}`);

  // 6. After grace period, promote pending to active and retire old selector
  await retireOldSelector(env, selector, graceDays);
}

async function retireOldSelector(
  env: Env,
  newSelector: string,
  graceDays: number
): Promise<void> {
  const oldSelector = await env.DKIM_KV.get('dkim:active_selector');

  // Promote the new key
  await env.DKIM_KV.put('dkim:active_selector', newSelector);

  if (!oldSelector || oldSelector === newSelector) return;

  // Check old key age — only delete if older than graceDays
  const createdIso = await env.DKIM_KV.get(`dkim:selector:${oldSelector}:created`);
  if (createdIso) {
    const ageMs = Date.now() - new Date(createdIso).getTime();
    const ageDays = ageMs / (1000 * 60 * 60 * 24);
    if (ageDays < graceDays) {
      console.log(`DKIM: old selector ${oldSelector} is only ${ageDays.toFixed(1)} days old — skip DNS deletion`);
      return;
    }
  }

  const oldDnsId = await env.DKIM_KV.get(`dkim:selector:${oldSelector}:dns_id`);
  if (oldDnsId) {
    const delResp = await fetch(
      `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/dns_records/${oldDnsId}`,
      {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      }
    );
    if (delResp.ok) {
      console.log(`DKIM: deleted old DNS record for ${oldSelector}`);
      // Clean up KV for old selector
      await Promise.all([
        env.DKIM_KV.delete(`dkim:selector:${oldSelector}:private`),
        env.DKIM_KV.delete(`dkim:selector:${oldSelector}:public`),
        env.DKIM_KV.delete(`dkim:selector:${oldSelector}:created`),
        env.DKIM_KV.delete(`dkim:selector:${oldSelector}:dns_id`),
      ]);
    }
  }
}
```

## Signing Worker — Reading Active Selector from KV

```typescript
// src/dkim-signer.ts  (called by outbound mailer via Service Binding)
export async function getDkimCredentials(env: Env): Promise<{
  selector: string;
  privateKeyPem: string;
  domain: string;
}> {
  const selector = await env.DKIM_KV.get('dkim:active_selector');
  if (!selector) throw new Error('No active DKIM selector in KV');

  const privateKeyPem = await env.DKIM_KV.get(`dkim:selector:${selector}:private`);
  if (!privateKeyPem) throw new Error(`Private key missing for selector ${selector}`);

  return { selector, privateKeyPem, domain: env.SIGNING_DOMAIN };
}
```

## wrangler.toml Cron Configuration

```toml
[triggers]
crons = ["0 3 1 */3 *"]   # 03:00 UTC on the 1st of every 3rd month
```

## Anti-patterns
- Deleting the old DNS TXT record immediately — mail in-flight signed with the old selector will fail verification; always wait the grace period.
- Storing the private key in a plain env var — env vars appear in `wrangler.toml` and logs; use Worker secrets or KV (which is encrypted at rest).
- Using RSA-1024 — rejected by modern validators; minimum is RSA-2048; prefer RSA-2048 over Ed25519 until broader support lands in mail servers.
- Running rotation in the fetch handler — use Cron Triggers; rotation must be idempotent and retried on failure, which Cron handles automatically.
- Not validating the new DNS record is resolvable before promoting — add a `dig @1.1.1.1 TXT ${selector}._domainkey.${domain}` check via Workers `fetch` before switching `active_selector`.

## Gotchas
- `crypto.subtle.generateKey` with `RSASSA-PKCS1-v1_5` is available in Workers runtime; `NODE:crypto` is not — do not attempt to import it.
- KV consistency is eventual; after writing `dkim:active_selector`, the signing Worker on a different edge PoP may still see the old value for up to 60 seconds.
- The Cloudflare DNS API token needs the `Zone:DNS:Edit` permission scoped to the specific zone — do not use a Global API Key.
- DNS TTL 300 (5 min) is the minimum Cloudflare allows on free/pro plans for TXT records; factor this into the grace period calculation.
- DKIM selectors must be ≤ 63 characters per DNS label limit; `sYYYYMMDD` (10 chars) is safe.

## Verification

```bash
# Check active selector in KV
wrangler kv key get --binding DKIM_KV "dkim:active_selector" --remote

# Verify DNS record is live
dig TXT s20260823._domainkey.example.com @1.1.1.1 +short

# List all selector keys in KV
wrangler kv key list --binding DKIM_KV --prefix "dkim:selector:" --remote

# Manually trigger rotation (useful after initial deploy)
wrangler triggers invoke --cron "0 3 1 */3 *" --remote
```

## Related
- `dkim-selector-rollover-and-key-strength.md` — rollover strategy and key size guidance
- `dkim-ed25519-sha256-deployment.md` — Ed25519 DKIM for modern senders
- `email-dkim-signing-mailchannels-workers.md` — MailChannels DKIM integration
- `spf-dkim-dmarc-alignment-debugging-workers.md` — alignment debugging

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/api/operations/dns-records-for-a-zone-create-dns-record
- https://datatracker.ietf.org/doc/html/rfc6376 (DKIM Signatures)
- https://www.m3aawg.org/sites/default/files/m3aawg-dkim-key-rotation-bp-2019-07.pdf
