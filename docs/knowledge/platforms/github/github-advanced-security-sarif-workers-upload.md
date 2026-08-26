# GitHub Advanced Security SARIF Upload via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You run a custom security scanner (dependency audit, secret detection, DAST
probe) inside or alongside a Cloudflare Worker and want to surface findings
directly in GitHub Advanced Security's Code Scanning UI — without running a
full GitHub Actions runner for the upload step. The Worker collects findings,
formats them as SARIF 2.1.0, and posts them to the GitHub Code Scanning API.

## Context

GitHub's Code Scanning API accepts SARIF 2.1.0 JSON (gzip-compressed,
base64-encoded) via `POST /repos/{owner}/{repo}/code-scanning/sarifs`. The
endpoint requires a token with `security_events: write` scope (or a GitHub App
with the `security_events` permission). A Cloudflare Worker can hold a GitHub
App private key in a secret and generate short-lived installation tokens to
upload SARIF on behalf of the App.

## SARIF Builder

```typescript
// src/sarif-builder.ts
export interface Finding {
  ruleId: string;
  message: string;
  filePath: string;
  startLine: number;
  severity: "error" | "warning" | "note";
}

export function buildSarif(findings: Finding[], toolName: string, toolVersion: string): object {
  return {
    $schema: "https://json.schemastore.org/sarif-2.1.0.json",
    version: "2.1.0",
    runs: [
      {
        tool: {
          driver: {
            name: toolName,
            version: toolVersion,
            rules: [...new Set(findings.map((f) => f.ruleId))].map((id) => ({
              id,
              defaultConfiguration: { level: "warning" },
            })),
          },
        },
        results: findings.map((f) => ({
          ruleId: f.ruleId,
          message: { text: f.message },
          level: f.severity === "error" ? "error" : f.severity === "warning" ? "warning" : "note",
          locations: [
            {
              physicalLocation: {
                artifactLocation: { uri: f.filePath, uriBaseId: "%SRCROOT%" },
                region: { startLine: f.startLine },
              },
            },
          ],
        })),
      },
    ],
  };
}
```

## SARIF Upload to GitHub API

```typescript
// src/upload.ts
export async function uploadSarif(opts: {
  installationToken: string;
  owner: string;
  repo: string;
  commitSha: string;
  ref: string;
  sarif: object;
}): Promise<{ id: string }> {
  const sarifJson = JSON.stringify(opts.sarif);
  // Workers support CompressionStream (gzip)
  const stream = new CompressionStream("gzip");
  const writer = stream.writable.getWriter();
  writer.write(new TextEncoder().encode(sarifJson));
  writer.close();
  const compressed = await new Response(stream.readable).arrayBuffer();
  const encoded = btoa(String.fromCharCode(...new Uint8Array(compressed)));

  const res = await fetch(
    `https://api.github.com/repos/${opts.owner}/${opts.repo}/code-scanning/sarifs`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${opts.installationToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "cf-sarif-uploader/1.0",
      },
      body: JSON.stringify({
        commit_sha: opts.commitSha,
        ref: opts.ref,
        sarif: encoded,
        tool_name: "cf-scanner",
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`SARIF upload failed: ${res.status} ${body}`);
  }
  return res.json<{ id: string }>();
}
```

## GitHub App Installation Token Retrieval

```typescript
// src/gh-app-token.ts
import { SignJWT, importPKCS8 } from "jose"; // bundled via npm

export async function getInstallationToken(
  appId: string,
  privateKeyPem: string,
  installationId: string,
): Promise<string> {
  const privateKey = await importPKCS8(privateKeyPem, "RS256");
  const jwt = await new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuer(appId)
    .setIssuedAt()
    .setExpirationTime("10m")
    .sign(privateKey);

  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "cf-sarif-uploader/1.0",
      },
    },
  );
  const data = await res.json<{ token: string }>();
  return data.token;
}
```

## Worker Entry Point

```typescript
// src/index.ts
import { buildSarif, Finding } from "./sarif-builder";
import { uploadSarif } from "./upload";
import { getInstallationToken } from "./gh-app-token";

export interface Env {
  GH_APP_ID: string;
  GH_APP_PRIVATE_KEY: string;       // PEM stored as secret
  GH_INSTALLATION_ID: string;
  GH_OWNER: string;
  GH_REPO: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/scan-results") {
      return new Response("Not Found", { status: 404 });
    }
    const { findings, commitSha, ref }: { findings: Finding[]; commitSha: string; ref: string } =
      await req.json();

    const token = await getInstallationToken(
      env.GH_APP_ID,
      env.GH_APP_PRIVATE_KEY,
      env.GH_INSTALLATION_ID,
    );
    const sarif = buildSarif(findings, "cf-scanner", "1.0.0");
    const result = await uploadSarif({
      installationToken: token,
      owner: env.GH_OWNER,
      repo: env.GH_REPO,
      commitSha,
      ref,
      sarif,
    });
    return Response.json({ sarifId: result.id });
  },
};
```

## Anti-patterns

- **Using a PAT with `security_events: write`** — PATs are long-lived and bypass App installation scoping. Use a GitHub App installation token scoped to the specific repository.
- **Skipping gzip compression** — the GitHub API enforces a 10 MB compressed size limit; uncompressed SARIF for large codebases will be rejected.
- **Uploading SARIF without a valid `commit_sha`** — GitHub validates that the SHA exists on the repository. Always pass the exact commit SHA from the triggering event.
- **Storing the private key in a KV value** — KV values are readable via the dashboard. Store the PEM in a Worker secret (`wrangler secret put GH_APP_PRIVATE_KEY`).

## Gotchas

- `CompressionStream("gzip")` is available in Workers runtime but not in Node.js < 18. If you use a local test harness, ensure the Node version matches.
- GitHub Code Scanning deduplicates results by `ruleId` + location per commit; re-uploading the same SARIF for the same SHA is safe but creates a new SARIF upload record.
- SARIF uploads are asynchronous on GitHub's side — the API returns a `sarif_id` immediately but processing can take up to 60 seconds before findings appear in the Security tab.
- The GitHub App must have `security_events` (read & write) permission and be installed on the target repository.

## Verification

```bash
# Check SARIF upload status
SARIF_ID="your-sarif-id"
gh api /repos/OWNER/REPO/code-scanning/sarifs/$SARIF_ID \
  --jq '{processing_status, errors, warnings_count, rules_count}'

# List code scanning alerts to confirm findings surfaced
gh api /repos/OWNER/REPO/code-scanning/alerts \
  --jq '.[].rule.id' | sort | uniq -c
```

## Related

- `github-code-scanning-sarif-category-identity.md`
- `github-advanced-security-setup.md`
- `github-apps-installation-tokens.md`

## Sources

- https://docs.github.com/en/rest/code-scanning/code-scanning#upload-an-analysis-as-sarif-data
- https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
- https://developers.cloudflare.com/workers/runtime-apis/streams/
