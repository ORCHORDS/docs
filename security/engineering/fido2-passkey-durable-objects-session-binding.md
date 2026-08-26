# FIDO2 Passkey Authentication with Durable Objects Session Binding

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have implemented WebAuthn passkey registration and authentication but session state is stored in KV, causing race conditions during concurrent requests and making it impossible to safely bind a challenge to a single in-flight authentication ceremony. You need per-user, strongly consistent session and challenge storage so that replay attacks are categorically impossible and challenge expiry is enforced atomically.

## Context

FIDO2 passkey ceremonies require a server-generated challenge that must be single-use. Cloudflare KV is eventually consistent and unsuitable for this; Durable Objects (DOs) provide per-object strong consistency with local storage, making them ideal for binding a challenge to exactly one active ceremony. Each DO instance holds one user's authentication state: pending challenge, bound device credentials, and active session tokens.

## 1. Durable Object: Per-User Auth State

```typescript
// src/auth-do.ts
import { DurableObject } from "cloudflare:workers";

interface Credential {
  credentialId: string;       // base64url
  publicKey: string;          // COSE CBOR, base64url
  signCount: number;
  transports: string[];
  backedUp: boolean;
  createdAt: string;
}

interface PendingChallenge {
  challenge: string; // base64url, 32 random bytes
  type: "registration" | "authentication";
  expiresAt: number; // unix ms
}

interface SessionToken {
  token: string;
  credentialId: string;
  expiresAt: number;
}

export class UserAuthDO extends DurableObject {
  private storage: DurableObjectStorage;

  constructor(ctx: DurableObjectState, _env: unknown) {
    super(ctx, _env);
    this.storage = ctx.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.split("/").pop();

    switch (action) {
      case "begin-registration": return this.beginRegistration();
      case "complete-registration": return this.completeRegistration(request);
      case "begin-authentication": return this.beginAuthentication();
      case "complete-authentication": return this.completeAuthentication(request);
      case "verify-session": return this.verifySession(request);
      case "logout": return this.logout(request);
      default: return new Response("Not Found", { status: 404 });
    }
  }

  private async beginRegistration(): Promise<Response> {
    const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
    const challenge = btoa(String.fromCharCode(...challengeBytes))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

    const pending: PendingChallenge = {
      challenge,
      type: "registration",
      expiresAt: Date.now() + 5 * 60 * 1000, // 5-minute window
    };
    await this.storage.put("pending_challenge", pending);
    return Response.json({ challenge });
  }

  private async completeRegistration(request: Request): Promise<Response> {
    const pending = await this.storage.get<PendingChallenge>("pending_challenge");
    if (!pending || pending.type !== "registration") {
      return new Response("No pending challenge", { status: 400 });
    }
    if (Date.now() > pending.expiresAt) {
      await this.storage.delete("pending_challenge");
      return new Response("Challenge expired", { status: 400 });
    }

    // Atomically consume the challenge—no replay possible
    await this.storage.delete("pending_challenge");

    const { attestation, credentialId, publicKey, transports, backedUp } =
      await request.json<{
        attestation: string;
        credentialId: string;
        publicKey: string;
        transports: string[];
        backedUp: boolean;
      }>();

    // In production: verify attestation and challenge binding using a WebAuthn library
    // Here we trust the client has verified locally (illustrative)
    const credential: Credential = {
      credentialId,
      publicKey,
      signCount: 0,
      transports,
      backedUp,
      createdAt: new Date().toISOString(),
    };

    const credentials = (await this.storage.get<Credential[]>("credentials")) ?? [];
    credentials.push(credential);
    await this.storage.put("credentials", credentials);

    return Response.json({ registered: true });
  }

  private async beginAuthentication(): Promise<Response> {
    const credentials = await this.storage.get<Credential[]>("credentials");
    if (!credentials?.length) {
      return new Response("No credentials registered", { status: 400 });
    }

    const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
    const challenge = btoa(String.fromCharCode(...challengeBytes))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

    const pending: PendingChallenge = {
      challenge,
      type: "authentication",
      expiresAt: Date.now() + 5 * 60 * 1000,
    };
    await this.storage.put("pending_challenge", pending);

    return Response.json({
      challenge,
      allowCredentials: credentials.map((c) => ({
        id: c.credentialId,
        type: "public-key",
        transports: c.transports,
      })),
    });
  }

  private async completeAuthentication(request: Request): Promise<Response> {
    const pending = await this.storage.get<PendingChallenge>("pending_challenge");
    if (!pending || pending.type !== "authentication") {
      return new Response("No pending challenge", { status: 400 });
    }
    if (Date.now() > pending.expiresAt) {
      await this.storage.delete("pending_challenge");
      return new Response("Challenge expired", { status: 400 });
    }

    // Consume challenge atomically
    await this.storage.delete("pending_challenge");

    const { credentialId, signCount } = await request.json<{
      credentialId: string;
      signCount: number;
    }>();

    const credentials = await this.storage.get<Credential[]>("credentials");
    const cred = credentials?.find((c) => c.credentialId === credentialId);
    if (!cred) return new Response("Unknown credential", { status: 401 });

    // Enforce sign count monotonicity (clone detection)
    if (signCount !== 0 && signCount <= cred.signCount) {
      return new Response("Sign count regression — possible cloned authenticator", {
        status: 401,
      });
    }
    cred.signCount = signCount;
    await this.storage.put("credentials", credentials!);

    // Issue a session token
    const tokenBytes = crypto.getRandomValues(new Uint8Array(32));
    const token = btoa(String.fromCharCode(...tokenBytes))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

    const session: SessionToken = {
      token,
      credentialId,
      expiresAt: Date.now() + 24 * 60 * 60 * 1000, // 24 hours
    };
    await this.storage.put(`session:${token}`, session);

    return Response.json({ sessionToken: token });
  }

  private async verifySession(request: Request): Promise<Response> {
    const { token } = await request.json<{ token: string }>();
    const session = await this.storage.get<SessionToken>(`session:${token}`);
    if (!session || Date.now() > session.expiresAt) {
      if (session) await this.storage.delete(`session:${token}`);
      return Response.json({ valid: false }, { status: 401 });
    }
    return Response.json({ valid: true, credentialId: session.credentialId });
  }

  private async logout(request: Request): Promise<Response> {
    const { token } = await request.json<{ token: string }>();
    await this.storage.delete(`session:${token}`);
    return Response.json({ loggedOut: true });
  }
}
```

## 2. Worker Router: Routing Auth Requests to the DO

```typescript
// src/index.ts
export { UserAuthDO } from "./auth-do";

interface Env {
  USER_AUTH: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/auth\/([^/]+)\/(.+)$/);
    if (!match) return new Response("Not Found", { status: 404 });

    const userId = match[1];
    const action = match[2];

    // Route to the DO for this user; strong consistency guaranteed per user
    const stub = env.USER_AUTH.get(env.USER_AUTH.idFromName(userId));
    return stub.fetch(`https://do/${action}`, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
  },
};
```

## Anti-patterns

- **Storing challenges in KV.** KV eventual consistency allows a race where the same challenge passes two concurrent verification requests; DOs are the correct store.
- **Not deleting the challenge atomically before verifying.** If you verify then delete, a concurrent request can replay the same challenge in the window between.
- **Ignoring sign count.** Setting `signCount` updates to 0 to "support cloud backups" disables clone detection; use the `backedUp` flag to decide policy instead.
- **Session tokens in DO without expiry.** An unbounded number of session keys accumulates; always set `expiresAt` and clean up on verification.
- **Using DO name derived from a user-controlled string without normalisation.** Always lowercase and validate the `userId` segment before calling `idFromName`.

## Gotchas

- DO storage is billed per read/write operation; keep session keys compact and avoid `list()` on large key sets during hot paths.
- `DurableObjectState.storage.put()` and `delete()` within the same event loop tick are automatically batched into one atomic write; split across awaits breaks this.
- Chrome sends `transports` only when the authenticator was registered with that information; do not require it for existing credentials.
- `backedUp=true` means the private key may exist on multiple devices (iCloud Keychain, Google Password Manager); sign count monotonicity is not guaranteed for backed-up passkeys—do not treat count regression as certain cloning when `backedUp=true`.
- The DO instance lives in a single Cloudflare region determined by the first request; for global users, latency to DO can add 50–200 ms. Accept this trade-off for ceremony requests or use Smart Placement.

## Verification

```bash
# Begin registration
curl -X POST https://api.example.com/auth/user123/begin-registration

# Complete authentication and receive session token
curl -X POST https://api.example.com/auth/user123/complete-authentication \
  -H "Content-Type: application/json" \
  -d '{"credentialId":"abc123","signCount":1}'

# Verify session token
curl -X POST https://api.example.com/auth/user123/verify-session \
  -H "Content-Type: application/json" \
  -d '{"token":"SESSION_TOKEN_HERE"}'
```

## Related

- `webauthn-passkey-workers-d1-implementation.md`
- `webauthn-passkey-flow.md`
- `durable-objects-auth-patterns.md`
- `jwt-refresh-token-rotation-durable-objects.md`
- `session-fixation-workers-d1-rotation.md`

## Sources

- FIDO2 / W3C WebAuthn Level 3 — https://www.w3.org/TR/webauthn-3/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- FIDO Alliance Passkey Overview — https://fidoalliance.org/passkeys/
- WebAuthn sign count guidance — https://www.w3.org/TR/webauthn-3/#sign-counter
- Cloudflare Durable Objects Smart Placement — https://developers.cloudflare.com/durable-objects/reference/smart-placement/
