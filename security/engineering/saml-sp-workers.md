# saml-sp-workers

**Issue:** SAML 2.0 SP implementation in Cloudflare Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom

Need to implement SAML 2.0 SP-initiated SSO in a Cloudflare Pages Functions backend.
Workers crypto API differs from Node.js; no `xmldsig`, `node-forge`, or `samlify` available.

## Root cause

Workers run in a V8 isolate — no Node.js APIs, no npm packages that use `crypto`, `fs`, or `Buffer`.
Must implement SAML signing, XML construction, and cert generation from scratch using:
- `crypto.subtle` (WebCrypto)
- `TextEncoder` / `TextDecoder`
- Custom ASN.1 DER encoding (for X.509 cert generation)

## Key design

### Endpoints

```
GET  /api/mc/saml/login       → build signed AuthnRequest, redirect to IdP
POST /api/mc/saml/acs         → parse SAMLResponse, verify signature, issue session
GET  /api/mc/saml/acs         → same (IdP-initiated GET binding)
GET  /api/mc/saml/metadata    → SP metadata XML (IdP imports this)
GET  /api/mc/saml/slo         → initiate SP-initiated logout
POST /api/mc/saml/slo         → receive IdP-initiated LogoutRequest
```

### Key storage

One RSA-2048 keypair per tenant, encrypted at rest:

```typescript
// Generate keypair (cast required — TS can't narrow from ['sign','verify'])
const keypair = await crypto.subtle.generateKey(
  { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048,
    publicExponent: new Uint8Array([1,0,1]), hash: 'SHA-256' },
  true, ['sign', 'verify']
) as CryptoKeyPair;

// Export as JWK for storage
const privateJwk = await crypto.subtle.exportKey('jwk', keypair.privateKey) as JsonWebKey;

// Encrypt before persisting to D1
const encrypted = await encryptSecret(env, JSON.stringify(privateJwk));
await env.DB!.prepare(
  `INSERT INTO saml_signing_keys (tenant_id, private_key_encrypted, public_key_pem, cert_pem, created_at)
   VALUES (?, ?, ?, ?, ?)`
).bind(tenantId, encrypted, publicKeyPem, certPem, now).run();
```

### AuthnRequest (HTTP-Redirect binding)

```typescript
// Build XML, deflate, base64url-encode, sign the query string
const authnXml = buildAuthnRequestXml(config, relayState);
const deflated = deflateRaw(new TextEncoder().encode(authnXml));
const b64 = base64Encode(deflated);
const qs = `SAMLRequest=${encodeURIComponent(b64)}&RelayState=${encodeURIComponent(relayState)}`;
const sig = await signQueryString(qs, privateKey);  // RSASSA-PKCS1-v1_5 + SHA-256
const redirectUrl = `${config.idp_sso_url}?${qs}&Signature=${encodeURIComponent(sig)}&SigAlg=...`;
```

### ACS handler

```typescript
export async function acs(request: Request, env: Env): Promise<Response> {
  // POST: form body; GET: query params
  const params = request.method === 'POST'
    ? new URLSearchParams(await request.text())
    : new URL(request.url).searchParams;

  const samlResponseB64 = params.get('SAMLResponse') ?? '';
  const relayState = params.get('RelayState') ?? '';

  // Retrieve in-flight session (relayState is the session ID)
  const session = await env.DB!.prepare(`SELECT * FROM saml_sessions WHERE id = ?`)
    .bind(relayState).first<SamlSession>();
  if (!session || session.expires_at < now()) return jsonError(400, 'expired_relay_state');

  // Decode SAMLResponse (HTTP-POST uses plain base64)
  const responseXml = new TextDecoder().decode(base64Decode(samlResponseB64));

  // Verify signature if IdP requires it
  if (config.require_signed_response) {
    const ok = await verifySamlResponse(responseXml, config.idp_cert_pem);
    if (!ok) { /* audit + return 400 */ }
  }

  // Extract NameID, attributes
  const nameId = xmlAnyTagContent(xmlAnyTagContent(responseXml, 'Subject') ?? '', 'NameID');
  const attributes = extractAttributes(responseXml);

  // Issue internal session, set cookie, redirect
}
```

### Self-signed X.509 cert (for SP metadata)

Workers don't have a cert-signing API. Build TBSCertificate DER manually:

```typescript
async function selfSignCert(keypair: CryptoKeyPair, tenantId: string): Promise<string> {
  const tbsCert = await buildTbsCertificate(keypair.publicKey, tenantId);
  const signature = await crypto.subtle.sign(
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    keypair.privateKey,
    tbsCert,
  );
  // Wrap in SEQUENCE { tbsCert, signatureAlgorithm, signatureValue }
  const cert = encodeAsn1Sequence([tbsCert, algId, encodeAsn1BitString(new Uint8Array(signature))]);
  return derToPem('CERTIFICATE', cert);
}
```

### Audit events without a user

During SAML flow no `McUser` exists yet. Use an anonymous stub:

```typescript
await writeAudit(env, {
  tenant: { id: session.tenant_id } as McTenant,  // only id is known
  user: { id: 'anonymous', tenant_id: session.tenant_id, role: 'anonymous', email: '', display_name: '' },
  request_id: relayState,
  ip: request.headers.get('cf-connecting-ip') ?? 'unknown',
  user_agent: request.headers.get('user-agent') ?? 'unknown',
}, { action: 'saml.acs.success', metadata: { name_id: nameId } });
```

## Gotchas

- **deflateRaw vs deflate**: HTTP-Redirect binding requires raw DEFLATE (no zlib header). `DecompressionStream('deflate-raw')` is available in Workers.
- **SAMLResponse timing attack**: Always verify signature before trusting NameID. Use `timingSafeEqual` for string token comparisons.
- **RelayState max length**: SAML spec limits it to 80 bytes. Use a short UUID-derived ID, not the full return URL.
- **CryptoKeyPair cast**: `crypto.subtle.generateKey` returns `CryptoKey | CryptoKeyPair`. Cast as `CryptoKeyPair` when using `['sign', 'verify']`.
- **exportKey returns `ArrayBuffer | JsonWebKey`**: Cast as `JsonWebKey` when format is `'jwk'`.
- **In-flight session TTL**: Set to 5 minutes. Clean up expired sessions opportunistically on each ACS call.
- **IdP cert refresh**: Store cert with expiry, poll/webhook for rotation. Stale cert = auth outage.

## Related

- `webauthn-passkey-flow.md`
- `workers-types-migration.md`
- `jwt-best-practices.md`
- `session-cookies-2026.md`
- `audit-without-user-context.md`
