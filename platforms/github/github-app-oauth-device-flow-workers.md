# GitHub App OAuth Device Flow in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

CLI tools and headless environments cannot open a browser redirect for a standard OAuth
web application flow. GitHub's OAuth Device Flow lets a user authenticate on a secondary
device (phone or browser tab) while a CLI or Workers-based service polls for the access
token. This pattern is required when building internal tools, GitHub Apps that provision
tokens for scripts, or "log in with GitHub" flows in edge-deployed apps where the
redirect URI cannot be a localhost URL.

---

## Context

GitHub's Device Flow (RFC 8628) works in three phases:

1. **Request** – POST to `/login/device/code` with `client_id` and `scope`.
2. **Display** – show `user_code` and `verification_uri` to the user.
3. **Poll** – POST to `/login/oauth/access_token` with `device_code` until the user
   approves or the code expires.

In a Workers context the polling loop runs inside a Durable Object (DO) or a KV-backed
queue to avoid holding a CPU thread. The resulting `access_token` is a user-level OAuth
token (not a GitHub App installation token), so scopes must be explicitly requested.

Required environment variables:

- `GITHUB_CLIENT_ID` – the GitHub App or OAuth App client ID
- `GITHUB_CLIENT_SECRET` – client secret (store in Workers Secrets)
- `TOKEN_KV` – KV namespace binding for token storage

---

## 1. Initiate Device Flow

```typescript
// workers/gh-device-flow/src/initiate.ts
interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
}

export async function requestDeviceCode(
  clientId: string,
  scope = "repo read:org"
): Promise<DeviceCodeResponse> {
  const response = await fetch("https://github.com/login/device/code", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ client_id: clientId, scope }),
  });

  if (!response.ok) {
    throw new Error(`Device code request failed: ${response.status}`);
  }

  return response.json<DeviceCodeResponse>();
}
```

---

## 2. Poll for Token (Durable Object)

```typescript
// workers/gh-device-flow/src/DeviceFlowPoller.ts
import { DurableObject } from "cloudflare:workers";

export interface Env {
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  TOKEN_KV: KVNamespace;
}

interface PollResult {
  access_token?: string;
  token_type?: string;
  scope?: string;
  error?: string;
  error_description?: string;
}

export class DeviceFlowPoller extends DurableObject<Env> {
  async poll(deviceCode: string, interval: number, sessionId: string): Promise<string> {
    const pollUrl = "https://github.com/login/oauth/access_token";

    while (true) {
      await scheduler.wait(interval * 1000);

      const res = await fetch(pollUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          client_id: this.env.GITHUB_CLIENT_ID,
          client_secret: <redacted-secret>
          device_code: deviceCode,
          grant_type: "urn:ietf:params:oauth:grant-type:device_code",
        }),
      });

      const result = await res.json<PollResult>();

      if (result.access_token) {
        // Store token encrypted in KV, TTL 8 hours
        await this.env.TOKEN_KV.put(
          `session:${sessionId}:token`,
          result.access_token,
          { expirationTtl: 28_800 }
        );
        return result.access_token;
      }

      if (result.error === "authorization_pending") continue;
      if (result.error === "slow_down") {
        interval += 5; // back off as required by spec
        continue;
      }
      throw new Error(`Device flow error: ${result.error} – ${result.error_description}`);
    }
  }
}
```

---

## 3. Workers Fetch Handler (Entry Point)

```typescript
// workers/gh-device-flow/src/index.ts
import { requestDeviceCode } from "./initiate";
import type { DeviceFlowPoller, Env } from "./DeviceFlowPoller";

export { DeviceFlowPoller };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Step 1: client calls /start to get user_code
    if (url.pathname === "/start") {
      const sessionId = crypto.randomUUID();
      const dc = await requestDeviceCode(env.GITHUB_CLIENT_ID);

      // Store device_code keyed by session
      await env.TOKEN_KV.put(
        `session:${sessionId}:device`,
        JSON.stringify(dc),
        { expirationTtl: dc.expires_in }
      );

      // Kick off async polling in a DO
      const stub = env.DEVICE_FLOW_DO.get(
        env.DEVICE_FLOW_DO.idFromName(sessionId)
      );
      // Fire-and-forget: DO will write token to KV when done
      stub.poll(dc.device_code, dc.interval, sessionId).catch(() => {});

      return Response.json({
        session_id: sessionId,
        user_code: dc.user_code,
        verification_uri: dc.verification_uri,
        expires_in: dc.expires_in,
      });
    }

    // Step 2: client polls /token?session_id=<id>
    if (url.pathname === "/token") {
      const sessionId = url.searchParams.get("session_id");
      if (!sessionId) return new Response("Missing session_id", { status: 400 });

      const token = await env.TOKEN_KV.get(`session:${sessionId}:token`);
      if (!token) {
        return Response.json({ status: "pending" }, { status: 202 });
      }
      return Response.json({ status: "complete", access_token: token });
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. wrangler.toml Configuration

```toml
# wrangler.toml
name = "gh-device-flow"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "TOKEN_KV"
id = "YOUR_KV_NAMESPACE_ID"

[[durable_objects.bindings]]
name = "DEVICE_FLOW_DO"
class_name = "DeviceFlowPoller"

[[migrations]]
tag = "v1"
new_classes = ["DeviceFlowPoller"]

[vars]
GITHUB_CLIENT_ID = "Iv1.xxxxxxxxxxxx"

# Store secret via: npx wrangler secret put GITHUB_CLIENT_SECRET
```

---

## 5. Revoking Tokens on Logout

```typescript
// workers/gh-device-flow/src/revoke.ts
export async function revokeToken(
  clientId: string,
  clientSecret: string,
  accessToken: string
): Promise<void> {
  const res = await fetch(
    `https://api.github.com/applications/${clientId}/token`,
    {
      method: "DELETE",
      headers: {
        Authorization: `Basic ${btoa(`${clientId}:${clientSecret}`)}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ access_token: accessToken }),
    }
  );

  if (res.status !== 204) {
    throw new Error(`Token revocation failed: ${res.status}`);
  }
}
```

Call this from the `/logout` endpoint and delete the KV key in the same handler.

---

## Anti-patterns

- **Polling from the main Worker isolate** – holding the event loop in a `while(true)`
  burns CPU time and hits Worker CPU limits; always offload to a Durable Object or KV
  poller.
- **Storing access tokens in plain KV without TTL** – tokens that are never revoked or
  expired linger indefinitely; always set `expirationTtl`.
- **Requesting broad scopes** – `repo` grants full read/write; prefer `repo:status`,
  `read:user`, etc. and request only what the app needs.
- **Ignoring `slow_down` error** – GitHub will return HTTP 429 if you ignore this; you
  must increase the polling interval by 5 seconds on each occurrence.

---

## Gotchas

- The `device_code` is distinct from the `user_code`; the `user_code` is what the user
  types at `verification_uri`, while `device_code` is what your app uses to poll.
- `expires_in` for device codes is typically 900 seconds (15 minutes); if the user does
  not authenticate in time, the `device_code` is invalidated and you must start over.
- GitHub Apps must have "User authorization callback URL" set even for device flow if
  you later want to call `/login/oauth/authorize` for web flow; the Device Flow itself
  does not use the redirect URL.
- Tokens obtained via device flow are user OAuth tokens, not installation tokens – they
  count against the user's rate limit (5,000 req/hr), not the App's installation limit.
- Durable Objects in the polling loop must handle `scheduler.wait()` interruptions if
  the DO hibernates; consider persisting `device_code` and `interval` to DO storage.

---

## Verification

```bash
# Start a device flow session
curl -X POST https://gh-device-flow.<account>.workers.dev/start | jq .

# Authenticate in browser at the returned verification_uri with the user_code

# Poll for completion
SESSION=<session_id_from_above>
curl "https://gh-device-flow.<account>.workers.dev/token?session_id=$SESSION" | jq .

# Confirm token works
curl -H "Authorization: Bearer <access_token>" https://api.github.com/user | jq .login
```

---

## Related

- `github-apps-jwt-webcrypto-workers-auth.md`
- `github-apps-installation-tokens.md`
- `github-apps-vs-pat.md`
- `github-fine-grained-personal-access-tokens.md`

---

## Sources

- GitHub Device Flow documentation: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow
- RFC 8628 – OAuth 2.0 Device Authorization Grant: https://datatracker.ietf.org/doc/html/rfc8628
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- GitHub token revocation API: https://docs.github.com/en/rest/apps/oauth-applications#delete-an-app-token
