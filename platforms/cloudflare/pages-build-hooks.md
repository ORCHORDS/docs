# pages-build-hooks

**Issue:** Triggering Cloudflare Pages deployments via webhook (build hooks)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Build hooks (Deploy Hooks) let you trigger a Pages deployment by sending an HTTP POST request — useful for headless CMS publish events, scheduled rebuilds, or CI/CD pipelines that don't push to Git.

## Pattern / Solution

**Creating a build hook (Dashboard):**
1. Pages → your project → Settings → Builds & Deployments.
2. Under "Build Hooks", click "Add build hook".
3. Name it (e.g. "CMS Publish") and select the branch to deploy.
4. Copy the generated webhook URL.

**Triggering a deployment:**
```bash
# Simple POST — no body required
curl -X POST "https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/<HOOK_ID>"
```

**From a Node.js CMS webhook handler:**
```typescript
import type { Request, Response } from 'express';

const PAGES_HOOK_URL = process.env.CF_PAGES_HOOK_URL!;

export async function onContentPublish(req: Request, res: Response) {
  // Validate CMS signature first
  const sig = req.headers['x-cms-signature'];
  if (!validateSignature(sig, req.body)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Trigger Pages build
  const cfRes = await fetch(PAGES_HOOK_URL, { method: 'POST' });
  const data = await cfRes.json() as { id: string; url: string };

  console.log(`Triggered Pages deploy: ${data.id}`);
  res.json({ triggered: true, deployId: data.id });
}
```

**Polling deployment status:**
```bash
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/deployments" \
  -H "Authorization: Bearer $CF_TOKEN" \
  | jq '.result[0] | {id, url, latest_stage}'
```

**GitHub Actions example:**
```yaml
- name: Trigger Pages deploy
  run: |
    curl -X POST "${{ secrets.CF_PAGES_HOOK_URL }}"
```

## Gotchas
- Build hooks bypass branch protection and deploy rules — anyone with the URL can trigger a build.
- Rotate hook URLs regularly; they are equivalent to deploy credentials.
- Concurrent builds: if a build is already running, a new hook trigger **queues** behind it (not deduplicated).
- There is no payload body — you cannot pass build variables through the hook URL itself; use environment variables set in the Pages project.
- Hook URLs are per-branch; you need separate hooks for production vs. preview branches.
- Rate limit: Cloudflare may throttle excessive hook calls (>10/minute per project).

## Related
- `pages-best-practices.md`
- `pages-functions-middleware.md`
- `wrangler-toml-reference.md`
