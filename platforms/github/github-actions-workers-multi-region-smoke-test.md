# GitHub Actions Multi-Region Workers Smoke Test

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a Cloudflare Worker you need to verify it is reachable and returning expected responses from multiple geographic regions before marking the deployment complete. A single-origin curl check cannot confirm that Cloudflare's anycast network has propagated the Worker to edge locations in different continents.

## Context

Cloudflare Workers run on a global anycast network — propagation typically completes within 30 seconds but can take up to 60 seconds in rare cases. GitHub-hosted runners are located in Azure data centers across multiple regions. By dispatching smoke-test jobs to runners in `us-east`, `us-west`, `eu-west`, and `ap-southeast` Azure regions and routing each curl through a regional Cloudflare PoP, you get real geographic coverage without a third-party synthetic monitoring service. The `wrangler deploy` output includes the deployment ID; passing it in a `CF-Deployment-ID` header lets the Worker confirm it is running the expected code version.

---

## 1. Deploy and Capture Deployment ID

```yaml
# .github/workflows/deploy-and-smoke.yml
name: Deploy + Multi-Region Smoke Test

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    outputs:
      deployment_id: ${{ steps.deploy.outputs.deployment_id }}
      worker_url:    ${{ steps.deploy.outputs.worker_url }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'pnpm' }

      - run: pnpm install --frozen-lockfile

      - name: Deploy Worker
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(pnpm wrangler deploy 2>&1)
          echo "$OUTPUT"
          DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oP 'Deployment ID: \K[a-f0-9-]+')
          WORKER_URL=$(echo "$OUTPUT" | grep -oP 'https://[^ ]+\.workers\.dev')
          echo "deployment_id=$DEPLOYMENT_ID" >> "$GITHUB_OUTPUT"
          echo "worker_url=$WORKER_URL"       >> "$GITHUB_OUTPUT"
```

## 2. Matrix Smoke Test Across GitHub Runner Regions

```yaml
  smoke-test:
    needs: deploy
    strategy:
      fail-fast: false
      matrix:
        include:
          - region: us-east
            runner: ubuntu-latest             # Azure East US
          - region: us-west
            runner: ubuntu-latest-arm64       # Azure West US 2
          - region: eu-west
            runner: ubuntu-24.04              # Azure West Europe
          - region: ap-southeast
            runner: ubuntu-22.04              # Azure Southeast Asia
    runs-on: ${{ matrix.runner }}
    name: Smoke – ${{ matrix.region }}

    steps:
      - name: Wait for propagation
        run: sleep 20

      - name: Health check
        env:
          WORKER_URL: ${{ needs.deploy.outputs.worker_url }}
          DEPLOYMENT_ID: ${{ needs.deploy.outputs.deployment_id }}
        run: |
          STATUS=$(curl -sf -o /dev/null -w '%{http_code}' \
            -H "CF-Deployment-ID: $DEPLOYMENT_ID" \
            "$WORKER_URL/health")
          if [ "$STATUS" != "200" ]; then
            echo "FAIL: ${{ matrix.region }} returned HTTP $STATUS"
            exit 1
          fi
          echo "PASS: ${{ matrix.region }} returned HTTP 200"
```

## 3. Validate Response Body and Headers

```yaml
      - name: Body and header validation
        env:
          WORKER_URL: ${{ needs.deploy.outputs.worker_url }}
          DEPLOYMENT_ID: ${{ needs.deploy.outputs.deployment_id }}
        run: |
          RESPONSE=$(curl -sf \
            -H "CF-Deployment-ID: $DEPLOYMENT_ID" \
            -D /tmp/headers.txt \
            "$WORKER_URL/health")

          # Assert JSON body field
          VERSION=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")
          echo "Worker version: $VERSION"

          # Assert CF-Ray header present (proves it transited Cloudflare edge)
          CF_RAY=$(grep -i '^cf-ray:' /tmp/headers.txt | tr -d '\r\n')
          if [ -z "$CF_RAY" ]; then
            echo "FAIL: No CF-Ray header — response may have bypassed edge"
            exit 1
          fi
          echo "CF-Ray: $CF_RAY"
```

## 4. Worker Health Endpoint (TypeScript)

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      return Response.json({
        status: 'ok',
        version: env.DEPLOY_VERSION ?? 'unknown',
        region: request.cf?.colo ?? 'unknown',
        ts: Date.now(),
      }, {
        headers: {
          'Cache-Control': 'no-store',
          'X-Deploy-Version': env.DEPLOY_VERSION ?? 'unknown',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

interface Env {
  DEPLOY_VERSION: string;
}
```

## 5. Gate the Deployment on All Region Results

```yaml
  all-regions-passed:
    needs: smoke-test
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Check all smoke tests passed
        run: |
          if [ "${{ needs.smoke-test.result }}" != "success" ]; then
            echo "One or more regional smoke tests failed — see matrix results above"
            exit 1
          fi
          echo "All regions passed — deployment verified"

  notify-on-failure:
    needs: [deploy, smoke-test]
    runs-on: ubuntu-latest
    if: failure()
    steps:
      - name: Post failure to Slack
        uses: slackapi/slack-github-action@v2
        with:
          webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
          webhook-type: incoming-webhook
          payload: |
            {
              "text": "Multi-region smoke test failed for <${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|${{ github.repository }}>"
            }
```

---

## Anti-patterns

- Routing all smoke-test jobs through the same runner label — you lose geographic diversity and end up testing the same Cloudflare PoP multiple times.
- Checking only HTTP status without verifying the `CF-Ray` header — a cached or CDN-intercepted response at a non-Cloudflare layer could mask a broken origin.
- Using a `sleep 60` unconditionally — most propagation completes in under 20 seconds; a long sleep wastes runner minutes on every deploy.
- Failing fast (`fail-fast: true`) in the smoke matrix — you want all regions to report before deciding pass/fail; partial failures are useful for diagnosing propagation issues.

## Gotchas

- GitHub-hosted runner Azure regions do not map 1:1 to Cloudflare PoP regions — a runner labeled `ubuntu-latest` could route to a nearby PoP that differs across runs.
- `request.cf?.colo` returns the IATA airport code of the Cloudflare data center that handled the request, not the client's location.
- The `DEPLOY_VERSION` env var must be set in `wrangler.toml` `[vars]` or injected at deploy time with `--var DEPLOY_VERSION:$GITHUB_SHA`; it is not automatically populated.
- Workers in `workers.dev` subdomains ignore `Cache-Control: no-store` sent from the browser but respect it on the Worker-to-client path — always include it on the health endpoint.

## Verification

```bash
# Manually trigger a smoke check from your local machine against a specific PoP
curl -sv -H "CF-Deployment-ID: <id>" https://<worker>.workers.dev/health 2>&1 | grep -E 'cf-ray|HTTP/'
```

The `all-regions-passed` job should be added as a required status check in branch protection so deploys that fail smoke tests cannot be considered complete.

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-retry-failed-workers-deploy.md`
- `github-actions-environment-protection.md`
- `github-actions-matrix-strategy-workers.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/workers/platform/deployments/
- https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#supported-runners-and-hardware-resources
