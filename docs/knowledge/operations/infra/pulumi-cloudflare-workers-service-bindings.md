# Pulumi Cloudflare Workers Service Bindings

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project (example.com) is decomposed into several Workers: an authentication gateway, a feed
aggregator, a content moderation worker, and a notification dispatcher. These Workers need
to call each other directly at the edge without traversing the public internet, incurring
extra latency, or requiring mTLS certificate management. Service bindings solve this but
wiring them manually via the dashboard is error-prone and not reproducible across environments.

## Context

Cloudflare Workers service bindings allow one Worker script to invoke another as if it were
a local function — no HTTP round-trip, same data-centre execution. The Pulumi Cloudflare
provider (`@pulumi/cloudflare` ≥ 5.x) models this through the `serviceBinding` property on
`cloudflare.WorkerScript`. Because Pulumi tracks resource dependencies, it can automatically
sequence script uploads before binding registration, something wrangler multi-deploy cannot
guarantee in CI.

## Resource Definition — WorkerScript with serviceBinding

The `serviceBinding` block on the calling Worker names the target script. The `name` field
is the JavaScript identifier exposed inside the calling Worker's `env` object.

```typescript
// infra/workers/index.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import * as fs from "fs";

const config = new pulumi.Config();
const accountId = config.requireSecret("cloudflareAccountId");
const zoneId   = config.require("cloudflareZoneId");

// 1. Upload the callee (moderation worker) first
const moderationWorker = new cloudflare.WorkerScript("moderation", {
  accountId,
  name: "example project-moderation",
  content: fs.readFileSync("../../dist/moderation.js", "utf8"),
  compatibilityDate: "2025-09-01",
});

// 2. Upload the caller (feed worker) with a service binding to moderation
const feedWorker = new cloudflare.WorkerScript("feed", {
  accountId,
  name: "example project-feed",
  content: fs.readFileSync("../../dist/feed.js", "utf8"),
  compatibilityDate: "2025-09-01",
  serviceBindings: [
    {
      name:    "MODERATION",      // env.MODERATION inside feed worker
      service: moderationWorker.name,
      environment: "production",  // optional: target environment
    },
  ],
}, { dependsOn: [moderationWorker] });
```

Inside `feed.js` the binding is a standard `fetch`-compatible interface:

```javascript
export default {
  async fetch(request, env) {
    const result = await env.MODERATION.fetch(
      new Request("https://internal/moderate", {
        method: "POST",
        body: request.body,
      })
    );
    const { safe } = await result.json();
    if (!safe) return new Response("Content blocked", { status: 403 });
    // ... continue feed logic
  }
};
```

## Configuration — Multi-Worker Topology

For example project the full service mesh is defined in a single Pulumi stack to guarantee ordering.
A helper function keeps the pattern DRY.

```typescript
function makeWorker(
  name: string,
  bundlePath: string,
  bindings: cloudflare.types.input.WorkerScriptServiceBinding[],
  deps: pulumi.Resource[]
): cloudflare.WorkerScript {
  return new cloudflare.WorkerScript(name, {
    accountId,
    name: `example project-${name}`,
    content: fs.readFileSync(bundlePath, "utf8"),
    compatibilityDate: "2025-09-01",
    serviceBindings: bindings,
  }, { dependsOn: deps });
}

const authWorker         = makeWorker("auth",         "../../dist/auth.js",         [], []);
const notificationWorker = makeWorker("notification", "../../dist/notification.js", [], []);

const moderationWorker = makeWorker("moderation", "../../dist/moderation.js",
  [{ name: "NOTIFY", service: notificationWorker.name }],
  [notificationWorker]
);

const feedWorker = makeWorker("feed", "../../dist/feed.js",
  [
    { name: "AUTH",       service: authWorker.name },
    { name: "MODERATION", service: moderationWorker.name },
  ],
  [authWorker, moderationWorker]
);

export const feedWorkerName = feedWorker.name;
```

## CI Integration — Pulumi Preview and Up

```yaml
# .github/workflows/workers-service-bindings.yml
name: Deploy Workers Service Bindings

on:
  push:
    branches: [main]
    paths:
      - "infra/workers/**"
      - "dist/**"

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build all worker bundles
        run: npm run build:all

      - uses: pulumi/actions@v5
        with:
          command: preview
          stack-name: org/example project/production
          work-dir: infra/workers
        env:
          PULUMI_ACCESS_TOKEN:        ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN:       ${{ secrets.CF_API_TOKEN }}
          PULUMI_CONFIG_PASSPHRASE:   ${{ secrets.PULUMI_PASSPHRASE }}

  deploy:
    needs: preview
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Build all worker bundles
        run: npm run build:all

      - uses: pulumi/actions@v5
        with:
          command: up
          stack-name: org/example project/production
          work-dir: infra/workers
        env:
          PULUMI_ACCESS_TOKEN:        ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN:       ${{ secrets.CF_API_TOKEN }}
          PULUMI_CONFIG_PASSPHRASE:   ${{ secrets.PULUMI_PASSPHRASE }}
```

## Stack Outputs and Cross-Stack References

When the Workers stack is separate from the DNS/routing stack, export binding metadata so
downstream stacks can reference worker names without hardcoding.

```typescript
// Export names for use by the routing stack
export const workerNames = {
  auth:         authWorker.name,
  feed:         feedWorker.name,
  moderation:   moderationWorker.name,
  notification: notificationWorker.name,
};

// In the routing stack:
// const workerStack = new pulumi.StackReference("org/example project-workers/production");
// const feedName = workerStack.getOutput("workerNames").apply(n => n.feed);
```

## Anti-patterns

- Defining service bindings before the callee script is uploaded — Cloudflare rejects bindings
  that reference non-existent scripts; use `dependsOn` to enforce order.
- Binding to a script by hardcoded string name — reference `worker.name` output so renames
  propagate automatically through Pulumi's dependency graph.
- Using service bindings for cross-account calls — service bindings only work within the same
  Cloudflare account; use `fetch` with an API token for cross-account needs.
- Circular service bindings (A → B → A) — Cloudflare will accept the configuration but
  recursive invocations will hit the subrequest depth limit (≈ 32 hops) and return errors.
- Deploying all Workers in a single `WorkerScript` to avoid binding complexity — monolithic
  Workers hit CPU time limits faster and cannot be updated independently.

## Gotchas

- Service binding `environment` defaults to `production`; staging environments must explicitly
  set it to `"staging"` or omit it and deploy both scripts under the same script name in a
  Wrangler-style environment — Pulumi stacks map 1:1 to Cloudflare script names.
- The callee Worker must have a valid route or be a named script; an unrouted script is still
  reachable via service binding without a public URL.
- Pulumi diffs `content` by value; rebuilding the bundle with no source changes (e.g., a
  timestamp injected by the bundler) will trigger an unnecessary Worker re-upload every run.
- Renaming a Worker script (`name` field) causes Pulumi to destroy and recreate the resource,
  briefly breaking any service bindings that reference the old name during the transition.
- `pulumi preview` cannot validate that the referenced service script actually handles the
  request protocol your calling Worker sends — test locally with `workerd`.

## Verification

```bash
# List service bindings on the feed worker
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/example project-feed/bindings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | select(.type=="service")'

# Expected output includes entries like:
# { "type": "service", "name": "MODERATION", "service": "example project-moderation", "environment": "production" }

# End-to-end test via the public feed endpoint
curl -s -X POST https://example.com/api/feed \
  -H "Content-Type: application/json" \
  -d '{"post": "hello world"}' | jq .
```

## Related

- `pulumi-cloudflare-workers-infrastructure-as-code.md` — base Workers IaC patterns with Pulumi
- `terraform-cloudflare-workers-ai-binding-config.md` — adding AI bindings alongside service bindings
- `cloudflare-workers-kv-namespace-terraform.md` — KV bindings for shared state across Workers
- `workers-subrequest-budget-management.md` — managing subrequest limits from service binding chains

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/workerscript/
- https://developers.cloudflare.com/workers/configuration/environments/
- https://developers.cloudflare.com/workers/observability/dev-tools/workerd/
