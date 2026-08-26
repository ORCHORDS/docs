# Custom Deploy Gates with External API Checks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Standard CI gates — unit tests, lint, type checks — cannot verify deployment readiness conditions that live outside the codebase: a third-party payment provider's API degradation, a data center maintenance window published by a cloud vendor, an SLA freeze window declared by a customer, a feature flag service health check, or a security advisory feed that flags a CVE in a dependency. These are runtime conditions, not code conditions, and they need to be checked *before* a deployment is allowed to proceed.

---

## Context

External API deploy gates insert an HTTP check into the deployment pipeline between "build successful" and "deploy to production." The gate queries an external system and either approves or blocks deployment based on the response. They differ from internal smoke tests (which verify the newly deployed service itself) and from contract tests (which verify API compatibility between services you own). External API gates check the *environment* the deployment is landing in.

Common external gate categories:

| Category | Example external API |
|---|---|
| Provider health | Stripe Status API, Cloudflare Status API |
| Maintenance windows | PagerDuty Maintenance Windows API, OpsGenie |
| Change freeze | ServiceNow Change Calendar API |
| Dependency CVEs | OSV.dev API, GitHub Advisory API |
| Infrastructure readiness | Terraform Cloud plan approval API |
| Uptime budget | Your own SLO API, Datadog SLO API |

The gate pattern is: **fetch → parse → boolean decision → block or proceed**. The gate must never be the only safeguard; if the external API itself is down, the gate must fail open or closed with a deliberate policy choice, not silently succeed.

---

## Pattern 1 — GitHub Actions Composite Gate Action

A reusable composite action that wraps any external API check and emits a structured decision.

```yaml
# .github/actions/deploy-gate/action.yml
name: External Deploy Gate
description: Checks an external API for deployment readiness

inputs:
  gate-url:
    description: External API URL to check
    required: true
  gate-token:
    description: API token for the external service
    required: false
  jq-expression:
    description: jq expression that evaluates to true/false
    required: true
  fail-on-api-error:
    description: Block deploy if the external API is unreachable (true = closed gate policy)
    default: "false"
  timeout-seconds:
    description: Max seconds to wait for the API response
    default: "10"

outputs:
  gate-passed:
    description: "true" if the gate allows deployment
    value: ${{ steps.evaluate.outputs.gate-passed }}
  gate-reason:
    description: Human-readable reason for the gate decision
    value: ${{ steps.evaluate.outputs.gate-reason }}

runs:
  using: "composite"
  steps:
    - name: Query external gate API
      id: fetch
      shell: bash
      run: |
        HTTP_CODE=$(curl -s -o /tmp/gate-response.json -w "%{http_code}" \
          --max-time "${{ inputs.timeout-seconds }}" \
          -H "Authorization: Bearer ${{ inputs.gate-token }}" \
          -H "Accept: application/json" \
          "${{ inputs.gate-url }}" || echo "000")
        echo "http-code=$HTTP_CODE" >> "$GITHUB_OUTPUT"

    - name: Evaluate gate decision
      id: evaluate
      shell: bash
      run: |
        HTTP_CODE="${{ steps.fetch.outputs.http-code }}"

        # Handle unreachable API
        if [ "$HTTP_CODE" = "000" ] || [ "$HTTP_CODE" -ge 500 ]; then
          if [ "${{ inputs.fail-on-api-error }}" = "true" ]; then
            echo "gate-passed=false" >> "$GITHUB_OUTPUT"
            echo "gate-reason=Gate API unreachable (HTTP $HTTP_CODE) — closed gate policy" >> "$GITHUB_OUTPUT"
          else
            echo "gate-passed=true" >> "$GITHUB_OUTPUT"
            echo "gate-reason=Gate API unreachable (HTTP $HTTP_CODE) — open gate policy applied" >> "$GITHUB_OUTPUT"
          fi
          exit 0
        fi

        # Evaluate jq expression against response body
        RESULT=$(jq -r "${{ inputs.jq-expression }}" /tmp/gate-response.json 2>/dev/null || echo "error")
        if [ "$RESULT" = "true" ]; then
          echo "gate-passed=true" >> "$GITHUB_OUTPUT"
          echo "gate-reason=Gate passed" >> "$GITHUB_OUTPUT"
        else
          echo "gate-passed=false" >> "$GITHUB_OUTPUT"
          echo "gate-reason=Gate expression evaluated to: $RESULT" >> "$GITHUB_OUTPUT"
        fi
```

---

## Pattern 2 — Stripe Status Gate

Block deployment during Stripe API incidents to avoid shipping payment-related changes when Stripe itself is degraded.

```yaml
# .github/workflows/deploy.yml (excerpt)
jobs:
  deploy-gate-stripe:
    name: Check Stripe Status
    runs-on: ubuntu-latest
    outputs:
      gate-passed: ${{ steps.stripe-gate.outputs.gate-passed }}
    steps:
      - uses: ./.github/actions/deploy-gate
        id: stripe-gate
        with:
          gate-url: "https://www.stripestatus.com/api/v2/summary.json"
          jq-expression: >
            .components
            | map(select(.name | test("API|Checkout|Payment")))
            | all(.status == "operational")
          fail-on-api-error: "false"
          timeout-seconds: "10"

      - name: Gate result
        run: |
          echo "Stripe gate: ${{ steps.stripe-gate.outputs.gate-passed }}"
          echo "Reason: ${{ steps.stripe-gate.outputs.gate-reason }}"
          [ "${{ steps.stripe-gate.outputs.gate-passed }}" = "true" ] || exit 1

  deploy-gate-maintenance:
    name: Check PagerDuty Maintenance Windows
    runs-on: ubuntu-latest
    outputs:
      gate-passed: ${{ steps.pd-gate.outputs.gate-passed }}
    steps:
      - uses: ./.github/actions/deploy-gate
        id: pd-gate
        with:
          gate-url: >
            https://api.pagerduty.com/maintenance_windows?filter=ongoing
          gate-token: ${{ secrets.PAGERDUTY_TOKEN }}
          # Gate passes if no ongoing maintenance windows exist for our service
          jq-expression: >
            [.maintenance_windows[]
             | select(.services[].summary | test("prod|production"; "i"))]
            | length == 0
          fail-on-api-error: "false"

  deploy:
    name: Deploy to Production
    needs: [deploy-gate-stripe, deploy-gate-maintenance]
    if: >
      needs.deploy-gate-stripe.outputs.gate-passed == 'true' &&
      needs.deploy-gate-maintenance.outputs.gate-passed == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env production
```

---

## Pattern 3 — CVE Advisory Gate

Query the OSV.dev API against the project's dependency lock file to block deployment if a critical CVE was published after the last deployment.

```bash
#!/usr/bin/env bash
# scripts/cve-gate.sh
# Usage: ./scripts/cve-gate.sh package-lock.json

set -euo pipefail

LOCK_FILE="${1:-package-lock.json}"
OSV_API="https://api.osv.dev/v1/querybatch"
MAX_SEVERITY="CRITICAL"   # block on CRITICAL; skip HIGH and below

# Extract package names and versions from lock file
PACKAGES=$(jq -r '
  .packages
  | to_entries[]
  | select(.key != "" and .key != "node_modules/")
  | {
      name: (.key | ltrimstr("node_modules/")),
      version: .value.version
    }
' "$LOCK_FILE")

# Build OSV batch query
QUERY_BODY=$(echo "$PACKAGES" | jq -sc '{
  queries: map({
    version: .version,
    package: { name: .name, ecosystem: "npm" }
  })
}')

# Query OSV.dev
RESPONSE=$(curl -sf -X POST "$OSV_API" \
  -H "Content-Type: application/json" \
  -d "$QUERY_BODY")

# Find critical vulnerabilities
CRITICAL_COUNT=$(echo "$RESPONSE" | jq -r '
  [.results[]
   | .vulns[]?
   | select(
       .severity[]?
       | select(.type == "CVSS_V3")
       | .score >= 9.0
     )]
  | length
')

VULN_SUMMARY=$(echo "$RESPONSE" | jq -r '
  .results[]
  | .vulns[]?
  | select(
      .severity[]?
      | select(.type == "CVSS_V3")
      | .score >= 9.0
    )
  | "\(.id): \(.summary // "no summary") (\(.severity[]? | select(.type=="CVSS_V3") | .score))"
')

if [ "$CRITICAL_COUNT" -gt 0 ]; then
  echo "GATE BLOCKED: $CRITICAL_COUNT critical CVE(s) found:"
  echo "$VULN_SUMMARY"
  exit 1
fi

echo "CVE gate passed: no critical vulnerabilities found in $LOCK_FILE"
exit 0
```

```yaml
# In the GitHub Actions workflow
- name: Run CVE advisory gate
  run: ./scripts/cve-gate.sh package-lock.json
```

---

## Pattern 4 — Cloudflare Worker as a Centralised Gate Aggregator

Rather than each pipeline calling N external APIs independently, route all gate checks through a Worker that caches responses and implements circuit-breaker behaviour. The CI pipeline makes a single call to your gate Worker.

```typescript
// workers/deploy-gate-aggregator/src/index.ts
export interface GateEnv {
  GATE_CACHE: KVNamespace;
  GATE_AUTH: string;         // secret shared with CI
  STRIPE_STATUS_URL: string;
  PD_TOKEN: string;
}

interface GateResult {
  passed: boolean;
  reasons: string[];
  checked_at: string;
}

export default {
  async fetch(request: Request, env: GateEnv): Promise<Response> {
    if (request.headers.get("X-Gate-Secret") !== env.GATE_AUTH) {
      return new Response("Unauthorized", { status: 401 });
    }

    const cached = await env.GATE_CACHE.get("gate-result", "json") as GateResult | null;
    if (cached && Date.now() - new Date(cached.checked_at).getTime() < 60_000) {
      return Response.json({ ...cached, source: "cache" });
    }

    const results = await Promise.allSettled([
      checkStripeStatus(env.STRIPE_STATUS_URL),
      checkMaintenanceWindows(env.PD_TOKEN),
    ]);

    const failures: string[] = [];
    results.forEach((r, i) => {
      const name = ["stripe", "maintenance"][i];
      if (r.status === "rejected") {
        console.error(`Gate "${name}" errored:`, r.reason);
        // open gate policy for individual gate failures
      } else if (!r.value.passed) {
        failures.push(`${name}: ${r.value.reason}`);
      }
    });

    const result: GateResult = {
      passed: failures.length === 0,
      reasons: failures,
      checked_at: new Date().toISOString(),
    };

    await env.GATE_CACHE.put("gate-result", JSON.stringify(result), {
      expirationTtl: 120,
    });

    return Response.json(result, {
      status: result.passed ? 200 : 503,
    });
  },
};

async function checkStripeStatus(
  url: string,
): Promise<{ passed: boolean; reason: string }> {
  const resp = await fetch(url, { cf: { cacheEverything: true, cacheTtl: 60 } });
  const data = await resp.json<{ components: Array<{ name: string; status: string }> }>();
  const degraded = data.components.filter(
    (c) => /api|checkout|payment/i.test(c.name) && c.status !== "operational",
  );
  return {
    passed: degraded.length === 0,
    reason: degraded.map((c) => `${c.name}: ${c.status}`).join(", "),
  };
}

async function checkMaintenanceWindows(
  pdToken: string,
): Promise<{ passed: boolean; reason: string }> {
  const resp = await fetch(
    "https://api.pagerduty.com/maintenance_windows?filter=ongoing",
    { headers: { Authorization: `Token token=${pdToken}` } },
  );
  const data = await resp.json<{ maintenance_windows: Array<{ description: string }> }>();
  const active = data.maintenance_windows.filter((w) =>
    /prod/i.test(w.description),
  );
  return {
    passed: active.length === 0,
    reason: active.map((w) => w.description).join("; "),
  };
}
```

```bash
# CI usage — single call to the aggregator
GATE=$(curl -sf -H "X-Gate-Secret: $GATE_SECRET" \
  "https://deploy-gates.example.workers.dev")
echo "$GATE" | jq .
PASSED=$(echo "$GATE" | jq -r '.passed')
[ "$PASSED" = "true" ] || { echo "Gate blocked: $(echo "$GATE" | jq -r '.reasons[]')"; exit 1; }
```

---

## Anti-patterns

- **Treating gate failures as pipeline failures without logging reasons**: a blocked deployment with no explanation creates alert fatigue. Always log the specific gate reason as a CI annotation.
- **Calling external APIs with no timeout**: an unresponsive external API will stall the pipeline indefinitely. Always set `--max-time` in curl or `timeout` in `fetch`.
- **Closed-gate-always policy without override path**: when the external gate API itself is down, a closed-gate policy permanently blocks all deployments. Provide a manual override (e.g. a labelled commit or a repository dispatch event) that bypasses the gate with an explicit audit record.
- **One gate for all environments**: staging deployments should not be blocked by production Stripe status. Scope gates to the environment they are protecting.
- **Checking gates after a manual deployment**: if engineers can bypass CI and deploy via `wrangler deploy` directly, gates are ineffective. Restrict direct deploy access and require all production deployments through CI.

---

## Gotchas

- Many status APIs (Stripe, GitHub, Cloudflare) use Atlassian Statuspage, which has a consistent schema. A generic Statuspage gate action covers multiple providers.
- PagerDuty maintenance windows API requires a full API key (`TOKEN` type), not an OAuth token. Store it as a repository secret with minimal scope; PagerDuty read-only tokens are available in the API Access Keys section.
- OSV.dev batch API has a limit of 1000 queries per request. For monorepos with large lock files, paginate or split into multiple requests.
- Rate limits: Stripe Status returns 429 after aggressive polling. Cache responses for at least 60 seconds. The gate aggregator Worker pattern handles this automatically.
- Gate decisions are a point-in-time snapshot. A Stripe incident that starts 30 seconds after the gate passes will not be caught. Gates reduce risk; they do not eliminate it.

---

## Verification

```bash
# Simulate a Stripe degradation locally
# (Point gate URL at a mock server returning a degraded component)
npx json-server --port 3001 --routes mock/statuspage.json &
GATE_RESULT=$(GATE_URL=http://localhost:3001/summary \
  ./scripts/stripe-gate.sh)
echo "Gate decision: $GATE_RESULT"

# Verify the aggregator Worker caches correctly
curl -H "X-Gate-Secret: $TEST_SECRET" https://deploy-gates.example.workers.dev
sleep 30
# Second call should return source: "cache"
curl -H "X-Gate-Secret: $TEST_SECRET" https://deploy-gates.example.workers.dev | jq '.source'
```

---

## Related

- `deploy-gate-antipatterns.md`
- `consumer-contract-deploy-gates.md`
- `risk-based-deployment-gating.md`
- `deployment-approval-workflow.md`
- `deploy-gate-e2e-tests-playwright-pages.md`

---

## Sources

- OSV.dev API documentation (osv.dev/docs/osv_service_v1.proto)
- PagerDuty Maintenance Windows API (developer.pagerduty.com/api-reference/b3A6Mjc0ODE5Nw-list-maintenance-windows)
- Atlassian Statuspage API — component status schema (developer.statuspage.io)
- Cloudflare Workers — KV caching patterns (developers.cloudflare.com/kv)
- Google SRE Book — Chapter 17, Testing for Reliability
