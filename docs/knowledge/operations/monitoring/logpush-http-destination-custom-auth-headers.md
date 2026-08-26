# Logpush HTTP Destination Custom Auth Headers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have an internal log aggregation endpoint (e.g., a custom SIEM, a self-hosted OpenTelemetry
collector, or a vector.dev HTTP sink) that requires bearer tokens, HMAC signatures, or API key
headers that Cloudflare does not natively know about. Logpush supports a generic HTTP destination
with arbitrary custom headers, but the configuration is underdocumented, headers containing secrets
are redacted in the dashboard, and misconfigured auth causes silent log loss. This article shows
how to configure, rotate, and validate custom-header auth for Logpush HTTP destinations.

## Context

Logpush's `http` destination type posts newline-delimited JSON (NDJSON) or compressed batches to
any HTTPS endpoint you control. The `destination_conf` string encodes both the URL and a `header_`
prefix query-param map for custom request headers. Secrets in headers are write-only in the
Cloudflare API — they are accepted on write but never returned on read, which means you must store
them externally (e.g., in a Cloudflare secret or your secrets manager) to support rotation.

## Configuring via the REST API

```typescript
// scripts/create-logpush-http-job.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const SINK_URL = process.env.LOG_SINK_URL!;         // https://logs.internal.example.com/ingest
const SINK_API_KEY = process.env.LOG_SINK_API_KEY!; // your SIEM bearer token

// Encode headers as `header_<Header-Name>=<value>` query params
const destUrl = new URL(SINK_URL);
destUrl.searchParams.set("header_Authorization", `Bearer ${SINK_API_KEY}`);
destUrl.searchParams.set("header_X-Source", "cloudflare-logpush");
destUrl.searchParams.set("header_X-Dataset", "workers-http");

const destinationConf = destUrl.toString();

const body = {
  name: "workers-http-to-internal-siem",
  output_options: {
    field_names: [
      "ClientIP", "ClientRequestHost", "ClientRequestMethod",
      "ClientRequestURI", "EdgeResponseStatus", "EdgeStartTimestamp",
      "WorkerScriptName", "WorkerWallTimeUs", "WorkerCPUTimeUs",
    ],
    timestamp_format: "rfc3339",
    batch_prefix: "[",
    batch_suffix: "]",
    record_delimiter: ",",
    // Use JSON array format instead of default NDJSON
  },
  destination_conf: destinationConf,
  dataset: "workers_trace_events",
  enabled: true,
  frequency: "high", // "high" = near real-time; "low" = 5-min batches
};

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/logpush/jobs`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  }
);
const job = await res.json();
console.log("Created job ID:", job.result?.id);
```

## Validating the Destination Before Job Creation

Cloudflare requires a destination ownership check — a unique token it sends in a test push that
your endpoint must echo back. Automate this check before creating the job:

```typescript
// scripts/validate-logpush-destination.ts
async function validateDestination(
  accountId: string,
  apiToken: string,
  destinationConf: string
): Promise<string> {
  // 1. Request ownership challenge
  const challenge = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/logpush/validate/destination/exists`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ destination_conf: destinationConf }),
    }
  );
  const { result } = await challenge.json();
  // result.message contains the ownership token Cloudflare just sent to your endpoint
  console.log("Ownership token delivered. Check your endpoint logs for:", result?.message);

  // 2. Your endpoint must have stored the token — retrieve it from your sink
  const ownershipToken = await fetchTokenFromSink(); // implement per your sink

  return ownershipToken;
}
```

Your HTTP sink endpoint must respond 200 to Cloudflare's test POST and record the body so you can
retrieve the ownership token:

```typescript
// Your HTTP sink worker (example) — echo ownership token
export default {
  async fetch(request: Request): Promise<Response> {
    const body = await request.text();
    // Check if it's an ownership probe (Cloudflare sends a JSON body with the token)
    await storeForValidation(body); // e.g., KV.put("logpush-token", body, { expirationTtl: 300 })
    return new Response("OK", { status: 200 });
  },
};
```

## Rotating the Auth Token

Because header values are write-only, rotation requires updating the job's `destination_conf`:

```typescript
// scripts/rotate-logpush-auth.ts
async function rotateLogpushToken(
  accountId: string,
  apiToken: string,
  jobId: number,
  newSinkToken: string,
  sinkUrl: string
): Promise<void> {
  const destUrl = new URL(sinkUrl);
  destUrl.searchParams.set("header_Authorization", `Bearer ${newSinkToken}`);
  destUrl.searchParams.set("header_X-Source", "cloudflare-logpush");

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/logpush/jobs/${jobId}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ destination_conf: destUrl.toString() }),
    }
  );
  if (!res.ok) throw new Error(`Rotation failed: ${await res.text()}`);
  console.log("Token rotated successfully");
}
```

Coordinate the rotation window: activate the new token at the sink first, then update Logpush, then
deactivate the old token. This preserves delivery continuity.

## HMAC Signature Header (Advanced)

Some internal SIEMs require per-request HMAC signatures rather than static bearer tokens. Logpush
static headers cannot compute per-request signatures. The workaround is a signing proxy Worker:

```typescript
// signing-proxy-worker/src/index.ts
const HMAC_SECRET = "your-hmac-secret"; // stored as a Workers secret

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.arrayBuffer();
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(HMAC_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sig = await crypto.subtle.sign("HMAC", key, body);
    const sigHex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");

    return fetch(env.SINK_URL, {
      method: "POST",
      headers: {
        ...Object.fromEntries(request.headers),
        "X-HMAC-Signature": sigHex,
        "X-Timestamp": Date.now().toString(),
      },
      body,
    });
  },
} satisfies ExportedHandler<Env>;
```

Point the Logpush HTTP destination to this signing proxy Worker. The proxy forwards with the HMAC
header computed over the actual batch payload.

## Anti-patterns

- **Embedding plaintext secrets in `destination_conf` without using Workers Secrets for rotation.**
  Secrets in destination_conf are write-only in the API but can appear in Terraform state or CI
  logs if not handled carefully. Use `wrangler secret put` or your secrets manager to source them.
- **Using HTTP (non-TLS) destinations.** Logpush requires HTTPS for HTTP destinations. Plaintext
  HTTP is rejected at job creation.
- **Setting `frequency: "high"` on a low-throughput account.** High-frequency mode batches every
  few seconds. If your account produces fewer than ~1,000 log lines/min, the overhead of many small
  batches can exceed your sink's connection limits. Use `"low"` for low-traffic accounts.
- **Ignoring ownership verification.** Skipping the destination validation step means jobs appear
  created but Logpush disables them automatically after initial delivery fails.

## Gotchas

- Header names in `destination_conf` query params are case-sensitive in the URL but Cloudflare
  sends them as lowercase HTTP/2 headers. Ensure your sink accepts lowercase `authorization`.
- Logpush does not retry permanently failed batches. If your sink returns 5xx, those log lines are
  lost unless you implement a fallback (e.g., also pushing to R2).
- The `destination_conf` string is URL-encoded in the API response; decode before parsing or
  updating.
- Worker-level custom domains are supported as Logpush HTTP destinations, but the Worker must
  respond within 30 seconds or Cloudflare marks the delivery as failed.

## Verification

1. Create the job with the steps above.
2. Generate 10 test log events (make 10 requests to a Workers route).
3. Within 30 seconds (`frequency: "high"`), check your sink endpoint received NDJSON with the
   expected `Authorization` header value in your sink's access log.
4. Confirm the ownership token was echoed correctly during the validation step.
5. Rotate the token and verify continued delivery using the new token within one rotation window.

## Related

- `cloudflare-logpush-setup.md`
- `logpush-datadog-workers-integration.md`
- `logpush-filter-expressions-cost-control.md`
- `logpush-bigquery-streaming-pipeline.md`
- `cloudflare-logpush-r2-partitioned-athena.md`
- `workers-logpush-observability-pipeline.md`

## Sources

- https://developers.cloudflare.com/logs/get-started/enable-destinations/http/
- https://developers.cloudflare.com/logs/logpush/ownership-challenge/
- https://developers.cloudflare.com/logs/reference/logpush-api-configuration/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
