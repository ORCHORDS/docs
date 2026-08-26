# containers-best-practices

**Issue:** Cloudflare Containers — Docker at the edge
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a complex backend (e.g. video transcoding,
ML inference, headless browser). You need Docker.
Cloudflare Workers has a 128MB memory limit + 30s
CPU. Your job doesn't fit.

## Root cause
**Some workloads need real containers.** Use CF
Containers.

**Source:** CF Containers:
https://developers.cloudflare.com/containers/

## The "Containers" concept

Cloudflare Containers (GA 2026):
- **Docker support:** Any OCI image
- **Region:Earth:** Global deploy
- **Worker-orchestrated:** Container is bound
- **Durable Object wrapping:** Per-instance isolation
- **Auto-scaling:** Per-region, per-concurrency
- **Workers Paid plan:** $5/mo

The container runs at the edge.

## The "create" pattern

For a new project:
```bash
npm create cloudflare@latest -- --template=cloudflare/templates/containers-template
```

The project is created.

## The "wrangler.jsonc" pattern

For the wrangler config:
```jsonc
{
  "name": "image-edge-api",
  "main": "worker/src/index.ts",
  "containers": [
    {
      "name": "image-container",
      "class_name": "ImageContainer",
      "image": "./container/Dockerfile",
      "max_instances": 25,
      "instance_type": "standard",  // dev, basic, standard, enhanced
    },
  ],
  "durable_objects": {
    "bindings": [
      { "name": "IMAGE_CONTAINER", "class_name": "ImageContainer" },
    ],
  },
  "migrations": {
    "new_sqlite_classes": ["ImageContainer"],
  },
  "observability": { "enabled": true },
}
```

The container is configured.

## The "Worker orchestrator" pattern

For the Worker that routes to the container:
```ts
import { getContainer } from '@cloudflare/containers';

export class ImageContainer extends Container {
  defaultPort = 8080;
  sleepAfter = '5m';  // Spin down after 5 min idle
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Get a container instance (sticky by name)
    const container = getContainer(env.IMAGE_CONTAINER, 'main');
    return container.fetch(request);
  },
};
```

The Worker routes to the container.

## The "Dockerfile" pattern

For the Dockerfile:
```dockerfile
# Multi-stage build
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 8080
CMD ["node", "dist/index.js"]
```

The image is built.

**Note:** Cloudflare requires `linux/amd64` images. Build
with `--platform=linux/amd64` on Apple Silicon.

## The "sticky vs random" pattern

For routing:
- **Sticky:** Same name = same container (session-bound)
- **Random:** New name each time (parallel jobs)

```ts
// Sticky (session-bound)
const container = getContainer(env.IMAGE_CONTAINER, sessionId);

// Random (parallel)
const container = getContainer(env.IMAGE_CONTAINER, crypto.randomUUID());
```

The routing is per use case.

## The "auto-scaling" pattern

For auto-scaling, configure in `wrangler.jsonc`:
```jsonc
{
  "containers": [{
    "name": "image-container",
    "max_instances": 25,
    "scaling": {
      "min_instances": 1,  // Always-on
      "max_instances": 25, // Max per region
    },
  }],
  "regions": ["weur", "enam", "apac"],  // Restrict regions
}
```

The container auto-scales.

## The "sleepAfter" pattern

For sleep after idle:
```ts
export class ImageContainer extends Container {
  sleepAfter = '5m';  // Spin down after 5 min idle
}
```

The container sleeps when idle.

## The "health check" pattern

For health check:
```ts
export class ImageContainer extends Container {
  defaultPort = 8080;

  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`http://localhost:8080/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}
```

The container is health-checked.

## The "region" pattern

For data residency:
```jsonc
{
  "regions": ["EU"],  // Only EU regions
}
```

The container is region-restricted.

## The "secret" pattern

For secrets, use `wrangler secret`:
```bash
wrangler secret put MY_SECRET
```

Inside the container:
```ts
const secret = process.env.MY_SECRET;
```

The secret is encrypted.

## The "observability" pattern

For observability, enable:
```jsonc
{
  "observability": { "enabled": true },
}
```

The logs stream to the dashboard.

```bash
wrangler tail
```

Logs are real-time.

## The "Container limits" pattern

For limits:
- **Memory:** 128MB-8GB (per instance type)
- **CPU:** 0.5-4 vCPU
- **Concurrent:** 25-100+ per region
- **Cold start:** ~600ms
- **Warm start:** < 50ms

The limits are checked.

## The "Container cost" pattern

For cost:
- **Workers Paid plan:** $5/mo
- **Container instance hours:** $0.000020/vCPU-second
- **Sleep when idle:** No charge

The cost is per usage.

## The "Container + Worker pattern"

For hybrid (container for heavy, Worker for light):
```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/heavy') {
      // Heavy: container
      const container = getContainer(env.IMAGE_CONTAINER, 'main');
      return container.fetch(request);
    } else {
      // Light: Worker
      return new Response('OK');
    }
  },
};
```

The hybrid uses the right tool.

## The "Container anti-pattern" anti-patterns

### 1. Container for everything
- **Issue:** Expensive
- **Fix:** Use Worker for simple

### 2. No auto-scaling
- **Issue:** One container = one user
- **Fix:** Auto-scale

### 3. No sleep
- **Issue:** Idle cost
- **Fix:** sleepAfter

### 4. No health check
- **Issue:** Stale container
- **Fix:** Health check

### 5. Secrets in image
- **Issue:** Leak
- **Fix:** wrangler secret

### 6. No region restriction
- **Issue:** GDPR violation
- **Fix:** Restrict regions

## Verification
- **Test:** Container deploys
- **Test:** Cold start is fast
- **Test:** Auto-scale works
- **Test:** Health check works
- **Live:** Container metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "container for everything" anti-pattern.** Use
  Worker for simple.
- **The "no sleep" anti-pattern.** Sleep when idle.
- **The "secrets in image" anti-pattern.** Use secrets.

## Related
- `cloudflare/workflows-best-practices.md`
- `cloudflare/durable-objects-best-practices.md`
- `cloudflare/workers-best-practices.md`
- `feature-cookbook-batch-processing.md`
- CF Containers: https://developers.cloudflare.com/containers/
- @cloudflare/containers: https://www.npmjs.com/package/@cloudflare/containers
