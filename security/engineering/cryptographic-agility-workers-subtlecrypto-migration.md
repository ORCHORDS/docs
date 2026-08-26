# Cryptographic Agility with Workers SubtleCrypto Algorithm Migration

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Hardcoding a single algorithm throughout a Workers application turns a routine cryptographic deprecation — SHA-1 retirement, AES-128 weakening, or a post-quantum mandate — into a flag-day breaking change requiring simultaneous re-encryption of all data. Encoding the algorithm identifier inside every ciphertext envelope enables live migration via a background cron with no downtime.

## Context

The Web Crypto API (`SubtleCrypto`) supports AES-GCM, RSA-OAEP, ECDH, HMAC, and HKDF, but production Workers often hard-code one choice with no migration path. A migration-ready design prefixes every encrypted payload with a 2-byte algorithm identifier, derives per-record keys via HKDF (binding the algorithm ID in the `info` parameter to prevent cross-algorithm key reuse), and writes all new records with the current preferred algorithm. A nightly cron walks the data store and re-encrypts old-algorithm records, converging the fleet onto the new algorithm without a single synchronous operation.

## Algorithm Registry

```typescript
type AlgorithmId = 'AES-GCM-128' | 'AES-GCM-256';

interface AlgorithmProfile {
  id: AlgorithmId;
  wireId: number;       // 2-byte big-endian value written into the envelope
  subtleName: string;
  keyBits: 128 | 256;
  nonceBytes: number;
  saltBytes: number;
}

const PROFILES: Record<AlgorithmId, AlgorithmProfile> = {
  'AES-GCM-128': { id: 'AES-GCM-128', wireId: 0x0001, subtleName: 'AES-GCM', keyBits: 128, nonceBytes: 12, saltBytes: 16 },
  'AES-GCM-256': { id: 'AES-GCM-256', wireId: 0x0002, subtleName: 'AES-GCM', keyBits: 256, nonceBytes: 12, saltBytes: 16 },
};

const WIRE_TO_PROFILE: Record<number, AlgorithmProfile> =
  Object.fromEntries(Object.values(PROFILES).map(p => [p.wireId, p]));

function getCurrentProfile(env: Env): AlgorithmProfile {
  const id = (env.CRYPTO_ALGORITHM ?? 'AES-GCM-256') as AlgorithmId;
  const profile = PROFILES[id];
  if (!profile) throw new Error(`Unknown CRYPTO_ALGORITHM: ${id}`);
  return profile;
}
```

## Envelope Format and Key Derivation

```typescript
// Envelope layout:
// [2 bytes wireId][16 bytes salt][12 bytes nonce][N bytes ciphertext+GCM tag]

async function deriveKey(
  masterSecret: string,
  profile: AlgorithmProfile,
  salt: Uint8Array,
): Promise<CryptoKey> {
  const raw = new TextEncoder().encode(masterSecret);
  const base = await crypto.subtle.importKey('raw', raw, 'HKDF', false, ['deriveKey']);

  // Including the algorithm ID in `info` ensures a key derived for AES-GCM-128
  // cannot be misused as an AES-GCM-256 key even with the same master secret + salt.
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt,
      info: new TextEncoder().encode(profile.id),
    },
    base,
    { name: profile.subtleName, length: profile.keyBits },
    false,
    ['encrypt', 'decrypt'],
  );
}

async function encrypt(plaintext: Uint8Array, masterSecret: string, env: Env): Promise<Uint8Array> {
  const profile = getCurrentProfile(env);
  const salt  = crypto.getRandomValues(new Uint8Array(profile.saltBytes));
  const nonce = crypto.getRandomValues(new Uint8Array(profile.nonceBytes));
  const key   = await deriveKey(masterSecret, profile, salt);

  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: profile.subtleName, iv: nonce }, key, plaintext),
  );

  const header = new Uint8Array(2);
  new DataView(header.buffer).setUint16(0, profile.wireId, false /* big-endian */);

  const envelope = new Uint8Array(2 + salt.length + nonce.length + ciphertext.length);
  let offset = 0;
  envelope.set(header,     offset); offset += 2;
  envelope.set(salt,       offset); offset += salt.length;
  envelope.set(nonce,      offset); offset += nonce.length;
  envelope.set(ciphertext, offset);

  return envelope;
}

async function decrypt(envelope: Uint8Array, masterSecret: string): Promise<Uint8Array> {
  let offset = 0;
  const wireId  = new DataView(envelope.buffer).getUint16(offset, false); offset += 2;
  const profile = WIRE_TO_PROFILE[wireId];
  if (!profile) throw new Error(`Unknown algorithm wire ID: 0x${wireId.toString(16)}`);

  const salt  = envelope.slice(offset, offset + profile.saltBytes); offset += profile.saltBytes;
  const nonce = envelope.slice(offset, offset + profile.nonceBytes); offset += profile.nonceBytes;
  const ciphertext = envelope.slice(offset);

  const key = await deriveKey(masterSecret, profile, salt);
  const plaintext = await crypto.subtle.decrypt(
    { name: profile.subtleName, iv: nonce }, key, ciphertext,
  );
  return new Uint8Array(plaintext);
}
```

## Workers Handler with Migration-Aware Store

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'PUT' && url.pathname.startsWith('/data/')) {
      const id = url.pathname.slice(6);
      const body = new Uint8Array(await request.arrayBuffer());
      const envelope = await encrypt(body, env.MASTER_SECRET, env);
      await env.DATA_KV.put(id, envelope);
      return new Response('Stored', { status: 200 });
    }

    if (request.method === 'GET' && url.pathname.startsWith('/data/')) {
      const id = url.pathname.slice(6);
      const raw = await env.DATA_KV.get(id, 'arrayBuffer');
      if (!raw) return new Response('Not Found', { status: 404 });
      const plaintext = await decrypt(new Uint8Array(raw), env.MASTER_SECRET);
      return new Response(plaintext);
    }

    return new Response('Not Found', { status: 404 });
  },

  // Nightly cron: re-encrypt records still using the old algorithm
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const target = getCurrentProfile(env);
    const cursorKey = 'reencrypt_cursor';
    const cursor = await env.MIGRATION_KV.get(cursorKey) ?? undefined;

    const list = await env.DATA_KV.list({ cursor, limit: 200 });

    let migrated = 0;
    for (const { name } of list.keys) {
      const raw = await env.DATA_KV.get(name, 'arrayBuffer');
      if (!raw) continue;

      const envelope = new Uint8Array(raw);
      const wireId = new DataView(envelope.buffer).getUint16(0, false);
      if (wireId === target.wireId) continue; // already current

      const plaintext   = await decrypt(envelope, env.MASTER_SECRET);
      const reencrypted = await encrypt(plaintext, env.MASTER_SECRET, env);
      await env.DATA_KV.put(name, reencrypted);
      migrated++;
    }

    console.log(`Re-encrypted ${migrated} records`);

    if (!list.list_complete) {
      await env.MIGRATION_KV.put(cursorKey, list.cursor ?? '');
    } else {
      await env.MIGRATION_KV.delete(cursorKey);
      console.log('Algorithm migration complete');
    }
  },
};
```

## Anti-patterns

- Deriving the key without a per-record random salt — makes nonce reuse across records trivially feasible; AES-GCM is catastrophically broken on nonce reuse
- Treating the wire algorithm ID as a trusted algorithm selector without validating against the registry — enables algorithm confusion by supplying an unknown or weaker ID
- Changing `CRYPTO_ALGORITHM` without running the background re-encryption job — leaves persisted data on the old algorithm indefinitely while new data uses the new one

## Gotchas

- Workers SubtleCrypto does not expose the AES-GCM key length in the resulting ciphertext; you must store it yourself in the envelope header, or the decrypt path cannot reconstruct the key correctly
- The HKDF `info` parameter binding the algorithm ID ensures cross-algorithm key isolation: a key derived for `AES-GCM-128` cannot decrypt a ciphertext produced by `AES-GCM-256` even with identical master secret and salt
- The cron re-encryption job must be idempotent — it can be interrupted by the Workers CPU wall-clock limit; the KV cursor ensures it resumes from where it stopped on the next firing

## Verification

```bash
# Set algorithm to AES-GCM-128, write a record
wrangler secret put CRYPTO_ALGORITHM  # enter: AES-GCM-128
curl -X PUT https://api.example.com/data/item1 -d "sensitive data"

# Switch to AES-GCM-256 — old record must still decrypt
wrangler secret put CRYPTO_ALGORITHM  # enter: AES-GCM-256
curl https://api.example.com/data/item1  # must return "sensitive data"

# Trigger migration cron and verify record is now on new algorithm
wrangler tail --format=json | grep "Re-encrypted"
```

## Related

- `security/post-quantum-cryptography-migration-readiness.md`
- `security/secrets-encryption-at-rest.md`
- `security/cryptographic-api-response-signing-workers.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-175Br1.pdf
