# Verifying PGP-Signed Inbound Emails in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your inbound email pipeline receives messages from external partners who sign
their emails with PGP. You need to verify those signatures inside a Cloudflare
Worker to ensure authenticity before processing the payload, then record trusted
senders in a D1 trust store.

## Context

PGP/MIME signatures follow RFC 3156. A signed message arrives as:

```
multipart/signed; protocol="application/pgp-signature"; micalg=pgp-sha256
  ├─ <signed body part>
  └─ application/pgp-signature  (armored detached signature)
```

Cloudflare Workers support WebCrypto (`crypto.subtle`) but not the OpenPGP
packet format natively. The `openpgp` npm package (pure JS) runs in Workers and
provides the necessary primitives.

---

## Section 1 – D1 Schema: Trust Store

```sql
-- migrations/0001_pgp_trust.sql

CREATE TABLE IF NOT EXISTS pgp_trusted_senders (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  email        TEXT    NOT NULL UNIQUE,
  fingerprint  TEXT    NOT NULL,   -- 40-char uppercase hex
  public_key   TEXT    NOT NULL,   -- ASCII-armored public key
  verified_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  notes        TEXT
);

CREATE TABLE IF NOT EXISTS pgp_verification_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  from_email   TEXT    NOT NULL,
  fingerprint  TEXT,
  verified     INTEGER NOT NULL,   -- 1 = ok, 0 = failed
  reason       TEXT,
  checked_at   INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Section 2 – Fetching a Public Key from a Keyserver

When a sender is not yet in the trust store, fetch their key from a public
keyserver (keys.openpgp.org supports HKP over HTTPS).

```typescript
// src/lib/pgp/keyserver.ts

const KEYSERVER = 'https://keys.openpgp.org';

export async function fetchPublicKeyByEmail(
  email: string
): Promise<string | null> {
  const url = `${KEYSERVER}/vks/v1/by-email/${encodeURIComponent(email)}`;
  const res = await fetch(url, { headers: { Accept: 'application/pgp-keys' } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Keyserver error ${res.status}`);
  return res.text(); // returns ASCII-armored public key
}

export async function fetchPublicKeyByFingerprint(
  fingerprint: string
): Promise<string | null> {
  // HKP format: 0x + uppercase fingerprint
  const url = `${KEYSERVER}/vks/v1/by-fingerprint/${fingerprint.toUpperCase()}`;
  const res = await fetch(url, { headers: { Accept: 'application/pgp-keys' } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Keyserver error ${res.status}`);
  return res.text();
}
```

---

## Section 3 – D1 Trust Store Helpers

```typescript
// src/lib/pgp/trust-store.ts

export interface TrustedSender {
  email: string;
  fingerprint: string;
  public_key: string;
}

export async function getTrustedSender(
  db: D1Database,
  email: string
): Promise<TrustedSender | null> {
  return db
    .prepare('SELECT email, fingerprint, public_key FROM pgp_trusted_senders WHERE email = ?')
    .bind(email)
    .first<TrustedSender>() ?? null;
}

export async function upsertTrustedSender(
  db: D1Database,
  sender: TrustedSender
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pgp_trusted_senders (email, fingerprint, public_key)
       VALUES (?, ?, ?)
       ON CONFLICT(email) DO UPDATE SET
         fingerprint = excluded.fingerprint,
         public_key  = excluded.public_key,
         verified_at = unixepoch()`
    )
    .bind(sender.email, sender.fingerprint, sender.public_key)
    .run();
}

export async function logVerification(
  db: D1Database,
  fromEmail: string,
  fingerprint: string | null,
  verified: boolean,
  reason?: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pgp_verification_log (from_email, fingerprint, verified, reason)
       VALUES (?, ?, ?, ?)`
    )
    .bind(fromEmail, fingerprint, verified ? 1 : 0, reason ?? null)
    .run();
}
```

---

## Section 4 – Signature Verification with OpenPGP.js

Install: `npm install openpgp`

```typescript
// src/lib/pgp/verify.ts

import * as openpgp from 'openpgp';
import { fetchPublicKeyByEmail } from './keyserver';
import { getTrustedSender, upsertTrustedSender, logVerification } from './trust-store';

export interface VerifyResult {
  valid: boolean;
  fingerprint: string | null;
  reason?: string;
}

export async function verifyPgpSignedEmail(
  db: D1Database,
  fromEmail: string,
  signedBody: string,      // the canonical signed body part (CRLF-normalized)
  armoredSignature: string // contents of the application/pgp-signature part
): Promise<VerifyResult> {
  // 1. Resolve public key: trust store first, then keyserver
  let armoredPublicKey: string | null = null;
  let expectedFingerprint: string | null = null;

  const trusted = await getTrustedSender(db, fromEmail);
  if (trusted) {
    armoredPublicKey = trusted.public_key;
    expectedFingerprint = trusted.fingerprint;
  } else {
    armoredPublicKey = await fetchPublicKeyByEmail(fromEmail);
    if (!armoredPublicKey) {
      const reason = 'No public key found for sender';
      await logVerification(db, fromEmail, null, false, reason);
      return { valid: false, fingerprint: null, reason };
    }
  }

  // 2. Parse key and signature
  const publicKey = await openpgp.readKey({ armoredKey: armoredPublicKey });
  const fingerprint = publicKey.getFingerprint().toUpperCase();

  // Guard: reject if the key doesn't match what we have on record
  if (expectedFingerprint && fingerprint !== expectedFingerprint) {
    const reason = `Fingerprint mismatch: expected ${expectedFingerprint}, got ${fingerprint}`;
    await logVerification(db, fromEmail, fingerprint, false, reason);
    return { valid: false, fingerprint, reason };
  }

  const signature = await openpgp.readSignature({ armoredSignature });
  const message = await openpgp.createMessage({ text: signedBody });

  // 3. Verify
  const verifyResult = await openpgp.verify({
    message,
    signature,
    verificationKeys: publicKey,
  });

  const { verified } = verifyResult.signatures[0];

  let valid = false;
  let reason: string | undefined;

  try {
    await verified; // throws if signature is invalid
    valid = true;
  } catch (err) {
    reason = err instanceof Error ? err.message : 'Unknown verification error';
  }

  // 4. Persist
  await logVerification(db, fromEmail, fingerprint, valid, reason);

  if (valid && !trusted) {
    // First-time verified sender: add to trust store
    await upsertTrustedSender(db, {
      email: fromEmail,
      fingerprint,
      public_key: armoredPublicKey,
    });
  }

  return { valid, fingerprint, reason };
}
```

---

## Section 5 – Inbound Email Worker (Email Routing)

```typescript
// src/index.ts
// Deploy as an Email Worker via Cloudflare Email Routing

import { verifyPgpSignedEmail } from './lib/pgp/verify';

export interface Env {
  DB: D1Database;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const rawEmail = await new Response(message.raw).text();

    // Naive extraction — production should use a proper MIME parser
    const signedBodyMatch = rawEmail.match(
      /--([\w]+)\r\n([\s\S]+?)\r\n--\1\r\n[\s\S]*?Content-Type: application\/pgp-signature[\s\S]*?\r\n\r\n([\s\S]+?)\r\n--\1--/
    );

    if (!signedBodyMatch) {
      // Not a PGP/MIME signed message; forward as-is or drop
      await message.forward('inbox@example.com');
      return;
    }

    const signedBody = signedBodyMatch[2].replace(/\n/g, '\r\n');
    const armoredSignature = signedBodyMatch[3];
    const fromEmail = message.from;

    const result = await verifyPgpSignedEmail(
      env.DB, fromEmail, signedBody, armoredSignature
    );

    if (result.valid) {
      await message.forward('trusted@example.com');
    } else {
      // Drop or quarantine unsigned/invalid messages
      console.error(`PGP verification failed for ${fromEmail}: ${result.reason}`);
    }
  },
};
```

---

## Anti-patterns

- **Trusting the `From` header without verifying the signature** – spoofed `From`
  is trivial; the signature is the only proof.
- **Fetching keys on every message** – cache in D1 and only re-fetch if the key
  is missing or a key rotation is suspected.
- **Allowing weak digest algorithms** (`pgp-md5`, `pgp-sha1`) – reject them;
  require at least `pgp-sha256`.
- **Skipping CRLF normalization of the signed body** – line-ending differences
  between transport hops will break the digest.

## Gotchas

- `openpgp` is ~1 MB after bundling; use `wrangler build --minify` and confirm
  you stay under the 10 MB Worker script size limit.
- keys.openpgp.org strips identity information (UIDs) by default unless the user
  explicitly uploads them with identity verification.
- Email Routing Workers receive a `ForwardableEmailMessage`, not a `Request`.
  `message.raw` is a `ReadableStream`.
- D1 writes inside an Email Worker use the same per-isolate limits as fetch
  Workers; batch inserts where possible.

## Verification

```bash
# Sign a test message
echo 'test body' | gpg --armor --detach-sign > sig.asc

# Upload your public key to the test keyserver
gpg --export --armor your@email.com | curl -X POST \
  https://keys.openpgp.org/vks/v1/upload \
  -H 'Content-Type: application/pgp-keys' --data-binary @-

# Check the verification log
wrangler d1 execute MY_DB --command \
  "SELECT * FROM pgp_verification_log ORDER BY checked_at DESC LIMIT 10;"
```

## Related

- `workers-email-multipart-mime-builder.md`
- `workers-email-threading-message-id.md`
- `workers-email-rate-limit-per-recipient.md`

## Sources

- RFC 3156 – MIME Security with OpenPGP
- https://openpgpjs.org/
- https://developers.cloudflare.com/email-routing/email-workers/
- https://keys.openpgp.org/about/api
