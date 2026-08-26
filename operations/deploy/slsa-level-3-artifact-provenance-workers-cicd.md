# SLSA Level 3 Artifact Provenance for Workers CI/CD

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Proving a Worker Binary Was Built by CI, Not Tampered With

Supply-chain attacks against serverless deployments are subtle: a developer's laptop is compromised, a build step is added to a fork, or a third-party action is hijacked. SLSA (Supply-chain Levels for Software Artifacts) Level 3 requires that the build platform itself generate unforgeable provenance — a signed attestation stating exactly which source commit produced which artifact, using ephemeral credentials that a human operator could not have held. For Cloudflare Workers, the artifact is the compiled `.js` bundle, and the deploy pipeline must verify provenance before activating a new version.

This article walks through a GitHub Actions pipeline that uses the official SLSA GitHub Generator action to produce an in-toto provenance attestation, uploads it alongside the Worker bundle to R2, and wires a pre-deploy verification step that fetches and validates the attestation before calling `wrangler deploy --dispatch`.

Achieving SLSA Level 3 for Workers is meaningful because Workers have no container registry or image digest that traditional SLSA tooling targets. The bundle hash stored in R2, paired with a signed provenance document, fills that gap.

## Context

- GitHub Actions as the build and deploy platform (SLSA Build Level 3 requires a GitHub-hosted runner or equivalent)
- SLSA GitHub Generator (`slsa-framework/slsa-github-generator`) for provenance generation
- Cloudflare R2 for immutable artifact + attestation storage
- `wrangler` v3 for deploy
- `slsa-verifier` CLI for pre-deploy attestation verification

## GitHub Actions: Build and Provenance Generation

The pipeline is split into two jobs. The `build` job compiles the Worker and captures the artifact hash. The `provenance` job calls the SLSA generator, which runs in an isolated reusable workflow and signs the attestation with a short-lived OIDC token — a credential the developer never touches.

```yaml
# .github/workflows/workers-slsa-deploy.yml
name: Workers SLSA L3 Deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write   # required for SLSA + Wrangler OIDC
  contents: read
  actions: read     # required by slsa-github-generator

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      artifact-digest: ${{ steps.hash.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - run: npm ci && npm run build   # outputs dist/worker.js

      - name: Compute artifact digest
        id: hash
        run: |
          DIGEST=$(sha256sum dist/worker.js | awk '{print $1}')
          echo "digest=sha256:$DIGEST" >> "$GITHUB_OUTPUT"

      - uses: actions/upload-artifact@v4
        with:
          name: worker-bundle
          path: dist/worker.js

  provenance:
    needs: [build]
    permissions:
      id-token: write
      contents: read
      actions: read
    uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.0.0
    with:
      base64-subjects: |
        ${{ needs.build.outputs.artifact-digest }}  dist/worker.js

  deploy:
    needs: [build, provenance]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: worker-bundle
          path: dist/

      - uses: actions/download-artifact@v4
        with:
          name: ${{ needs.provenance.outputs.provenance-name }}
          path: provenance/

      - name: Upload bundle + attestation to R2
        env:
          R2_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          R2_ACCESS_KEY:  ${{ secrets.R2_ACCESS_KEY_ID }}
          R2_SECRET_KEY:  ${{ secrets.R2_SECRET_ACCESS_KEY }}
          COMMIT_SHA:     ${{ github.sha }}
        run: |
          aws s3 cp dist/worker.js \
            s3://workers-artifacts/${COMMIT_SHA}/worker.js \
            --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
          aws s3 cp provenance/*.intoto.jsonl \
            s3://workers-artifacts/${COMMIT_SHA}/provenance.intoto.jsonl \
            --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

      - name: Verify provenance before deploy
        run: |
          curl -Lo slsa-verifier https://github.com/slsa-framework/slsa-verifier/releases/latest/download/slsa-verifier-linux-amd64
          chmod +x slsa-verifier
          ./slsa-verifier verify-artifact dist/worker.js \
            --provenance-path provenance/*.intoto.jsonl \
            --source-uri github.com/${{ github.repository }} \
            --source-tag "" \
            --builder-id "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml"

      - name: Deploy Worker
        run: npx wrangler deploy dist/worker.js --name my-worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Attestation Verification in a Pre-Deploy Workers Script

For pipelines where the deploy step is itself a Worker (e.g., a deploy orchestrator), verification can happen inside the Worker by fetching the attestation from R2 and validating the signature chain.

```ts
// src/deploy-verifier.ts — runs as a pre-deploy gate Worker
interface Env {
  ARTIFACTS: R2Bucket;
  TRUSTED_BUILDER: string; // e.g. "https://github.com/slsa-framework/..."
}

interface ProvenanceStatement {
  _type: string;
  subject: Array<{ name: string; digest: { sha256: string } }>;
  predicate: {
    builder: { id: string };
    buildType: string;
    invocation: { configSource: { uri: string; digest: { sha1: string } } };
  };
}

async function fetchAttestation(env: Env, commitSha: string): Promise<ProvenanceStatement> {
  const obj = await env.ARTIFACTS.get(`${commitSha}/provenance.intoto.jsonl`);
  if (!obj) throw new Error(`No attestation found for ${commitSha}`);
  const lines = (await obj.text()).trim().split('\n');
  // DSSE envelope — decode the payload
  const envelope = JSON.parse(lines[0]);
  const payload = atob(envelope.payload);
  return JSON.parse(payload) as ProvenanceStatement;
}

export async function verifyBeforeDeploy(env: Env, commitSha: string, expectedDigest: string): Promise<void> {
  const stmt = await fetchAttestation(env, commitSha);

  // Check builder identity
  if (!stmt.predicate.builder.id.startsWith(env.TRUSTED_BUILDER)) {
    throw new Error(`Untrusted builder: ${stmt.predicate.builder.id}`);
  }

  // Check subject digest matches the bundle we're about to deploy
  const match = stmt.subject.find(s => s.digest.sha256 === expectedDigest);
  if (!match) throw new Error(`Digest mismatch: ${expectedDigest} not in provenance`);

  // Check source commit
  const srcUri = stmt.predicate.invocation.configSource.uri;
  if (!srcUri.includes(commitSha) && stmt.predicate.invocation.configSource.digest.sha1 !== commitSha) {
    throw new Error(`Source commit mismatch in provenance`);
  }
}
```

## Storing Attestation Metadata in D1

For audit queries ("which deploys in the last 90 days had verified provenance?"), write attestation metadata to D1 after each successful verification.

```ts
// Extend the deploy-recorder Worker to also write provenance records
interface ProvenanceRecord {
  deploy_id: string;
  commit_sha: string;
  builder_id: string;
  artifact_digest: string;
  verified_at: number;
}

async function recordProvenance(db: D1Database, rec: ProvenanceRecord) {
  await db.prepare(`
    INSERT OR REPLACE INTO provenance_records
      (deploy_id, commit_sha, builder_id, artifact_digest, verified_at)
    VALUES (?, ?, ?, ?, ?)
  `).bind(rec.deploy_id, rec.commit_sha, rec.builder_id,
           rec.artifact_digest, rec.verified_at).run();
}
```

## Anti-patterns

- Generating provenance in the same job that builds the artifact — SLSA L3 requires the generator to run in a separate, isolated job with its own OIDC token
- Storing the attestation only in the GitHub Actions run artifacts — these expire; push to R2 for durable audit trails
- Skipping the `--builder-id` check in `slsa-verifier` — without it, any SLSA generator can produce a "valid" attestation
- Using a long-lived API token for the build job instead of OIDC federated credentials — defeats the non-repudiation guarantee

## Gotchas

- `slsa-github-generator` v2+ requires `actions: read` permission on the calling workflow and the reusable workflow — missing this causes an opaque 403
- The DSSE envelope produced by the generator wraps the in-toto statement in base64; you must decode `envelope.payload` before parsing the JSON
- R2 object keys are case-sensitive; use a consistent convention (lowercase commit SHA)
- `wrangler deploy` does not natively consume provenance — the verification step must be a pre-flight script that blocks deploy on failure

## Verification

```ts
// Confirm the provenance record exists in D1 for the latest deploy
const row = await env.DB.prepare(
  `SELECT * FROM provenance_records ORDER BY verified_at DESC LIMIT 1`
).first<{ commit_sha: string; builder_id: string }>();
console.assert(row?.builder_id?.includes('slsa-framework'), 'Latest deploy lacks SLSA L3 provenance');
```

## Related

- [deployment-audit-trail-provenance.md](deployment-audit-trail-provenance.md)
- [oidc-federated-deploy-credentials.md](oidc-federated-deploy-credentials.md)
- [build-reproducibility-verification.md](build-reproducibility-verification.md)
- [docker-security-scanning.md](docker-security-scanning.md)
- [gitops-secrets-management.md](gitops-secrets-management.md)

## Sources

- https://slsa.dev/spec/v1.0/levels
- https://github.com/slsa-framework/slsa-github-generator
- https://github.com/slsa-framework/slsa-verifier
- https://developers.cloudflare.com/r2/
- https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds
