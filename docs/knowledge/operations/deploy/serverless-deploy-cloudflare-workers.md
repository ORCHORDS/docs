# Serverless Deploy: Cloudflare Workers

## Overview

Cloudflare Workers provide a serverless computing platform that allows developers to deploy JavaScript/TypeScript functions at the edge, enabling fast global execution with minimal latency. This guide covers essential deployment practices including configuration management, environment handling, and production-ready workflows.

## wrangler.toml Configuration

The `wrangler.toml` file serves as your Workers' primary configuration manifest. Here's a comprehensive example:

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2023-12-01"

[vars]
API_KEY = "your-api-key"
ENVIRONMENT = "production"

[triggers]
crons = ["*/5 * * * *"]

[[kv_namespaces]]
binding = "MY_KV"
id = "kv-namespace-id"

[[durable_objects.bindings]]
name = "MY_DO"
class_name = "MyDurableObject"

[[r2_buckets]]
binding = "MY_BUCKET"
bucket_name = "my-bucket-name"
```

## Environments

Workers support multiple environments through wrangler configuration profiles:

```toml
# wrangler.toml
[env.production]
name = "my-worker-production"
route = "example.com/*"
vars = { ENV = "production" }

[env.staging]
name = "my-worker-staging"
route = "staging.example.com/*"
vars = { ENV = "staging" }
```

Deploy specific environments using:
```bash
wrangler deploy --env production
wrangler deploy --env staging
```

## Secrets Management

Store sensitive data through Cloudflare Dashboard or API:

```javascript
// Access secrets in your worker
export default {
  async fetch(request, env) {
    const apiKey = env.API_KEY;
    const secretValue = env.SECRET_VALUE;

    return new Response(`API Key: ${apiKey}`);
  }
};
```

Set via dashboard:
1. Navigate to Workers & Pages → Your Worker
2. Go to Settings → Variables → Secrets
3. Add key-value pairs

Via API:
```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}/secrets" \
  -H "Authorization: Bearer {api_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API_KEY",
    "value": "your-secret-value"
  }'
```

## Rolling Deploys

Implement safe rolling updates with versioned deployments:

```bash
# Deploy to staging first
wrangler deploy --env staging

# Test staging environment
curl https://staging.example.com/health

# Deploy to production
wrangler deploy --env production

# Monitor deployment status
wrangler deployments list
```

## Version Rollback

Rollback to previous versions using deployment history:
