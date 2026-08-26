# Multi-Cloud Workers Federation Deployment

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Identical Edge Logic Across Three Platforms

Regulatory requirements, latency SLAs, or vendor risk policies sometimes demand that critical edge logic run on multiple cloud providers simultaneously. A payment gateway, an A/B testing layer, or a rate-limiter must behave identically whether the request hits Cloudflare, AWS CloudFront/Lambda@Edge, or Vercel's Edge Network — but each platform has a different deploy API, different bundle format requirements, and different environment variable injection patterns.

Maintaining three separate CI pipelines with three diverging codebases is a maintenance trap. This article describes a single TypeScript codebase with a thin platform abstraction layer, a unified CI pipeline that builds and deploys to all three targets from one push, and a traffic-steering mechanism that shifts load between providers based on latency probes.

The abstraction does not try to normalize runtime APIs (each platform's runtime has genuine differences). Instead it isolates platform-specific glue in adapter modules while keeping the business logic in a shared core that compiles to each target's bundle format.

## Context

- TypeScript source compiled with `esbuild` for all three targets
- Cloudflare Workers via `wrangler deploy`
- AWS Lambda@Edge via `aws lambda update-function-code` + CloudFront invalidation
- Vercel Edge Functions via `vercel deploy --prebuilt`
- GitHub Actions for the unified CI pipeline
- Cloudflare DNS + Load Balancer for traffic steering between origins

## Project Layout and Config Abstraction

```
edge-federation/
  src/
    core/          # shared business logic — no platform imports
      handler.ts
      auth.ts
      ratelimit.ts
    adapters/
      cloudflare.ts   # Workers entry point
      lambda-edge.ts  # Lambda@Edge handler wrapper
      vercel.ts       # Vercel Edge Function wrapper
  build/
    build-cf.ts
    build-lambda.ts
    build-vercel.ts
  wrangler.toml
  vercel.json
```

```ts
// src/core/handler.ts — platform-agnostic request handler
export interface PlatformEnv {
  RATE_LIMIT_NAMESPACE: { get(k: string): Promise<string | null>; put(k: string, v: string): Promise<void> };
  FEATURE_FLAGS: Record<string, boolean>;
  ORIGIN_URL: string;
}

export async function handleRequest(req: Request, env: PlatformEnv): Promise<Response> {
  const ip = req.headers.get('CF-Connecting-IP')
           ?? req.headers.get('X-Forwarded-For')?.split(',')[0].trim()
           ?? 'unknown';

  const count = parseInt(await env.RATE_LIMIT_NAMESPACE.get(ip) ?? '0', 10);
  if (count > 100) return new Response('Rate limited', { status: 429 });
  await env.RATE_LIMIT_NAMESPACE.put(ip, String(count + 1));

  const upstream = await fetch(new Request(env.ORIGIN_URL + new URL(req.url).pathname, req));
  return upstream;
}
```

## Platform Adapters

```ts
// src/adapters/cloudflare.ts
import { handleRequest, PlatformEnv } from '../core/handler';

interface CFEnv {
  RATE_LIMITER: KVNamespace;
  ORIGIN_URL: string;
}

export default {
  async fetch(req: Request, env: CFEnv): Promise<Response> {
    const platformEnv: PlatformEnv = {
      RATE_LIMIT_NAMESPACE: {
        get: (k) => env.RATE_LIMITER.get(k),
        put: (k, v) => env.RATE_LIMITER.put(k, v, { expirationTtl: 60 }),
      },
      FEATURE_FLAGS: {},
      ORIGIN_URL: env.ORIGIN_URL,
    };
    return handleRequest(req, platformEnv);
  },
};

// src/adapters/lambda-edge.ts
import { CloudFrontRequestEvent, CloudFrontRequestResult, Context, Callback } from 'aws-lambda';
import { handleRequest, PlatformEnv } from '../core/handler';

const store = new Map<string, string>(); // in-memory; replace with ElastiCache for production

export const handler = async (
  event: CloudFrontRequestEvent, _ctx: Context, cb: Callback<CloudFrontRequestResult>
) => {
  const cf = event.Records[0].cf;
  const req = new Request(`https://${cf.request.headers.host[0].value}${cf.request.uri}`, {
    method: cf.request.method,
    headers: Object.fromEntries(Object.entries(cf.request.headers).map(([k, v]) => [k, v[0].value])),
  });

  const platformEnv: PlatformEnv = {
    RATE_LIMIT_NAMESPACE: {
      get: async (k) => store.get(k) ?? null,
      put: async (k, v) => { store.set(k, v); },
    },
    FEATURE_FLAGS: {},
    ORIGIN_URL: process.env.ORIGIN_URL ?? '',
  };

  const res = await handleRequest(req, platformEnv);
  cb(null, {
    status: String(res.status),
    statusDescription: res.statusText,
    body: await res.text(),
    headers: Object.fromEntries([...res.headers.entries()].map(([k, v]) => [k, [{ key: k, value: v }]])),
  });
};

// src/adapters/vercel.ts
import { handleRequest, PlatformEnv } from '../core/handler';
export const config = { runtime: 'edge' };
const store = new Map<string, string>();
export default async function handler(req: Request): Promise<Response> {
  const platformEnv: PlatformEnv = {
    RATE_LIMIT_NAMESPACE: { get: async (k) => store.get(k) ?? null, put: async (k, v) => { store.set(k, v); } },
    FEATURE_FLAGS: {},
    ORIGIN_URL: process.env.ORIGIN_URL ?? '',
  };
  return handleRequest(req, platformEnv);
}
```

## Unified CI Pipeline

```yaml
# .github/workflows/federation-deploy.yml
name: Multi-Cloud Federation Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npm run build:cf && npm run build:lambda && npm run build:vercel
      - uses: actions/upload-artifact@v4
        with: { name: bundles, path: dist/ }

  deploy-cloudflare:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: bundles, path: dist/ }
      - run: npx wrangler deploy dist/cf/worker.js --name edge-federation
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  deploy-lambda-edge:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with: { name: bundles, path: dist/ }
      - name: Package for Lambda
        run: cd dist/lambda && zip -r ../lambda.zip .
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - run: |
          aws lambda update-function-code \
            --function-name edge-federation \
            --zip-file fileb://dist/lambda.zip
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CF_DIST_ID }} --paths "/*"

  deploy-vercel:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: bundles, path: dist/ }
      - run: npx vercel deploy --prebuilt --prod dist/vercel/
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}

  steer-traffic:
    needs: [deploy-cloudflare, deploy-lambda-edge, deploy-vercel]
    runs-on: ubuntu-latest
    steps:
      - name: Update Cloudflare Load Balancer weights
        run: |
          curl -X PATCH \
            "https://api.cloudflare.com/client/v4/accounts/${{ secrets.CF_ACCOUNT_ID }}/load_balancers/pools/${{ secrets.LB_POOL_ID }}" \
            -H "Authorization: Bearer ${{ secrets.CF_API_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d '{"origins":[{"name":"cloudflare","address":"cf.edge.example.com","weight":0.6},{"name":"lambda","address":"aws.edge.example.com","weight":0.3},{"name":"vercel","address":"vercel.edge.example.com","weight":0.1}]}'
```

## Anti-patterns

- Sharing mutable in-process state between requests in Lambda@Edge — Lambda@Edge containers are reused but not guaranteed persistent; use ElastiCache or DynamoDB for rate-limit counters
- Using platform-specific APIs (Durable Objects, KV) in the shared core — this forces a shim in every adapter and usually leaks abstractions
- Deploying all three platforms in series — run them in parallel CI jobs to cut total deploy time
- Keeping a single `package.json` entry point that branches on `process.env.PLATFORM` — esbuild tree-shaking works better when adapters are separate entry files

## Gotchas

- Lambda@Edge functions must be deployed to `us-east-1` regardless of where CloudFront distributes them; `aws-region` in the CI step must be `us-east-1`
- Vercel `--prebuilt` requires a `.vercel/output` directory structure, not a raw JS file; run `vercel build` locally once to understand the expected layout
- Cloudflare's load balancer requires a paid plan for origin weights; on free plans all origins get equal weight
- In-memory maps in Lambda@Edge and Vercel adapters are not shared across invocations or regions — they're only appropriate for local request coalescing, not global rate limiting

## Verification

```ts
// Smoke test: hit the public endpoint and confirm the X-Provider header is present
const res = await fetch('https://edge.example.com/health');
const provider = res.headers.get('X-Edge-Provider'); // set by each adapter
console.assert(['cloudflare', 'lambda', 'vercel'].includes(provider ?? ''), `Unexpected provider: ${provider}`);
```

## Related

- [blue-green-traffic-switch.md](blue-green-traffic-switch.md)
- [canary-deployments.md](canary-deployments.md)
- [progressive-delivery-2026.md](progressive-delivery-2026.md)
- [lambda-deploy-package-optimization.md](lambda-deploy-package-optimization.md)
- [feature-rollout-strategies.md](feature-rollout-strategies.md)

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/load-balancing/
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-edge.html
- https://vercel.com/docs/functions/edge-functions
- https://esbuild.github.io/api/#entry-points
