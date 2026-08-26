# GitHub Actions OIDC Multi-Cloud Federation with Workers Orchestration

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Production deployments often span multiple clouds simultaneously: secrets pulled from
AWS Secrets Manager, artifacts pushed to GCP Artifact Registry, and the runtime deployed
to Cloudflare Workers. Managing long-lived credentials for each provider in GitHub
Secrets is fragile and violates least-privilege. GitHub Actions OIDC eliminates
static credentials by exchanging a short-lived OIDC token for temporary credentials at
each provider. This article covers the cross-provider federation pattern and how a
Cloudflare Worker can act as an audit/coordination layer.

---

## Context

GitHub Actions issues a signed OIDC JWT per job via the `id-token: write` permission.
Each cloud provider verifies this JWT against GitHub's JWKS endpoint
(`https://token.actions.githubusercontent.com/.well-known/jwks`) and returns
short-lived credentials when the subject claim matches a configured trust policy.

Provider-specific exchange:
- **AWS** – `aws-actions/configure-aws-credentials` calls STS `AssumeRoleWithWebIdentity`
- **GCP** – `google-github-actions/auth` calls Workload Identity Federation token exchange
- **Cloudflare** – direct JWT assertion; Worker validates subject claim via KV allow-list

The three exchanges can run in parallel jobs, feeding downstream deployment jobs via
`needs` + `outputs`.

---

## 1. Workflow Structure – Parallel Token Exchange

```yaml
# .github/workflows/multi-cloud-deploy.yml
name: Multi-cloud deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  # ── Exchange tokens in parallel ──────────────────────────────────────────
  aws-auth:
    runs-on: ubuntu-latest
    outputs:
      role-arn: ${{ steps.sts.outputs.aws-account-id }}
    steps:
      - id: sts
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - run: aws secretsmanager get-secret-value --secret-id prod/db-url --query SecretString --output text > /tmp/db_url.txt
      - uses: actions/upload-artifact@v4
        with:
          name: aws-secrets
          path: /tmp/db_url.txt

  gcp-auth:
    runs-on: ubuntu-latest
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ vars.GCP_WIF_PROVIDER }}
          service_account: ${{ vars.GCP_SERVICE_ACCOUNT }}
      - run: gcloud artifacts docker images list ${{ vars.GCP_ARTIFACT_REGISTRY }}

  cf-notify:
    runs-on: ubuntu-latest
    steps:
      - name: Notify Workers audit endpoint
        env:
          ACTIONS_ID_TOKEN_REQUEST_URL: ${{ env.ACTIONS_ID_TOKEN_REQUEST_URL }}
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: ${{ env.ACTIONS_ID_TOKEN_REQUEST_TOKEN }}
        run: |
          OIDC_TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://deploy.example.workers.dev" \
            | jq -r .value)
          curl -X POST https://deploy.example.workers.dev/audit \
            -H "Authorization: Bearer $OIDC_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"event":"deploy_started","ref":"${{ github.ref }}","sha":"${{ github.sha }}"}'

  # ── Deploy after all auth jobs pass ──────────────────────────────────────
  deploy:
    needs: [aws-auth, gcp-auth, cf-notify]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: aws-secrets
      - name: Deploy to Workers
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 2. Workers OIDC Audit Endpoint

```typescript
// workers/deploy-audit/src/index.ts
export interface Env {
  ALLOWED_REPOS: string;   // comma-separated: "org/repo1,org/repo2"
  AUDIT_LOG: D1Database;
}

interface GitHubOIDCClaims {
  sub: string;            // "repo:org/repo:ref:refs/heads/main"
  repository: string;
  ref: string;
  sha: string;
  workflow: string;
  iss: string;
  aud: string;
  exp: number;
  iat: number;
}

async function verifyGitHubOIDC(token: string, audience: string): Promise<GitHubOIDCClaims> {
  // Fetch JWKS and verify – production code should cache JWKS in KV
  const jwksRes = await fetch("https://token.actions.githubusercontent.com/.well-known/jwks");
  const { keys } = await jwksRes.json<{ keys: JsonWebKey[] }>();

  const [header] = token.split(".").map((p) => JSON.parse(atob(p.replace(/-/g, "+").replace(/_/g, "/"))));
  const jwk = keys.find((k: { kid?: string }) => k.kid === header.kid);
  if (!jwk) throw new Error("Unknown key ID");

  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);

  const [encodedHeader, encodedPayload, encodedSig] = token.split(".");
  const signingInput = new TextEncoder().encode(`${encodedHeader}.${encodedPayload}`);
  const sig = Uint8Array.from(atob(encodedSig.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

  const valid = await crypto.subtle.verify({ name: "RSASSA-PKCS1-v1_5" }, key, sig, signingInput);
  if (!valid) throw new Error("Invalid OIDC token signature");

  const claims = JSON.parse(atob(encodedPayload.replace(/-/g, "+").replace(/_/g, "/")
  )) as GitHubOIDCClaims;

  if (claims.exp < Math.floor(Date.now() / 1000)) throw new Error("Token expired");
  if (!claims.aud.includes(audience)) throw new Error("Audience mismatch");

  return claims;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/audit") {
      return new Response("Not found", { status: 404 });
    }

    const authHeader = request.headers.get("Authorization") ?? "";
    const token = authHeader.replace(/^Bearer\s+/, "");
    const audience = new URL(request.url).origin;

    let claims: GitHubOIDCClaims;
    try {
      claims = await verifyGitHubOIDC(token, audience);
    } catch (e) {
      return new Response(`Unauthorized: ${(e as Error).message}`, { status: 401 });
    }

    const allowed = (env.ALLOWED_REPOS ?? "").split(",").map((r) => r.trim());
    if (!allowed.includes(claims.repository)) {
      return new Response("Forbidden: repository not in allow-list", { status: 403 });
    }

    const body = await request.json<{ event: string; ref: string; sha: string }>();

    await env.AUDIT_LOG.prepare(
      `INSERT INTO deploy_audit (repository, ref, sha, workflow, event, recorded_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    )
      .bind(claims.repository, claims.ref, body.sha, claims.workflow, body.event)
      .run();

    return Response.json({ ok: true, subject: claims.sub });
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. AWS Trust Policy (Terraform)

```hcl
# infra/iam.tf
data "aws_iam_policy_document" "github_oidc_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:my-org/my-repo:ref:refs/heads/main"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}
```

---

## 4. GCP Workload Identity Federation (gcloud)

```bash
# One-time setup (not in CI)
gcloud iam workload-identity-pools create "github-pool" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub OIDC Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='my-org/my-repo'"
```

---

## 5. JWKS Cache in Workers KV

```typescript
// workers/deploy-audit/src/jwks-cache.ts
const JWKS_KEY = "github-oidc-jwks";
const JWKS_TTL = 3600; // 1 hour

export async function getCachedJWKS(kv: KVNamespace): Promise<JsonWebKey[]> {
  const cached = await kv.get(JWKS_KEY, "json");
  if (cached) return cached as JsonWebKey[];

  const res = await fetch("https://token.actions.githubusercontent.com/.well-known/jwks");
  const { keys } = await res.json<{ keys: JsonWebKey[] }>();
  await kv.put(JWKS_KEY, JSON.stringify(keys), { expirationTtl: JWKS_TTL });
  return keys;
}
```

Cache JWKS to avoid hammering GitHub's discovery endpoint on every request.

---

## Anti-patterns

- **Sharing one OIDC subject claim across all branches** – use `ref:refs/heads/main`
  constraints in trust policies; `*` allows any branch including attacker-controlled
  forks on `pull_request_target` workflows.
- **Requesting `id-token: write` at workflow level** – scope it to only the jobs that
  actually need the OIDC token; unused jobs inherit the permission unnecessarily.
- **Not validating `aud` in Workers** – GitHub OIDC tokens with a custom `audience`
  parameter are scoped to that audience; skipping audience validation allows token
  replay across services.
- **Caching cloud credentials across jobs** – STS and GCP tokens are scoped to a
  single job; artifacts containing credential files must be treated as sensitive and
  deleted after use.

---

## Gotchas

- AWS OIDC provider thumbprint must be updated if the GitHub OIDC CA certificate
  rotates; Terraform `thumbprint_list` is not auto-managed.
- GCP Workload Identity Federation requires the service account to have
  `roles/iam.workloadIdentityUser` binding to the Workload Identity Pool principal.
- The GitHub OIDC token is issued per-job, not per-step; a single token request covers
  all steps in one job, so parallel jobs each get their own token.
- `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` environment
  variables are only populated when `id-token: write` is set on the job or workflow.
- Cloudflare does not have a native OIDC provider trust mechanism like AWS/GCP; the
  Worker must verify the JWT signature itself using the GitHub JWKS endpoint.

---

## Verification

```bash
# Confirm AWS credential exchange worked
aws sts get-caller-identity --output json

# Confirm GCP exchange
gcloud auth print-access-token

# Confirm Workers audit record
npx wrangler d1 execute audit-db \
  --command "SELECT * FROM deploy_audit ORDER BY recorded_at DESC LIMIT 5"

# Inspect OIDC token claims (decode without verifying)
echo $OIDC_TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

---

## Related

- `github-actions-oidc-cloudflare.md`
- `github-actions-oidc-aws.md`
- `github-actions-oidc-gcp.md`
- `github-actions-immutable-oidc-subject-claims.md`
- `github-actions-security-hardening.md`

---

## Sources

- GitHub OIDC documentation: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- AWS IAM OIDC federation: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html
- GCP Workload Identity Federation: https://cloud.google.com/iam/docs/workload-identity-federation
- RFC 7517 – JSON Web Key: https://datatracker.ietf.org/doc/html/rfc7517
- Cloudflare Workers WebCrypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
