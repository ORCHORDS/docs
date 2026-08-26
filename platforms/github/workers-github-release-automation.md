# Automated GitHub Release Creation from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a zero-server release pipeline: when a tag is pushed to GitHub, a Cloudflare Worker receives the `push` webhook event, generates a changelog from commits since the previous tag, creates a GitHub Release via the Releases API, uploads build artifacts to R2, attaches them as release assets, and posts a Slack notification — all in a single serverless function.

## Context

Traditional CI release jobs run on GitHub Actions VMs, which adds billing minutes and cold-start latency. A Worker webhook handler can orchestrate the same steps in under 5 seconds:

1. Verify the `X-Hub-Signature-256` HMAC from GitHub.
2. Filter for `refs/tags/*` push events.
3. Call GitHub API to list commits between the new tag and the previous one.
4. Format commit messages into a markdown changelog (grouped by conventional-commit type).
5. POST to `POST /repos/{owner}/{repo}/releases` to create the release.
6. Fetch build artifacts from a pre-signed R2 URL (uploaded by CI), then attach them to the release with `POST /repos/{owner}/{repo}/releases/{release_id}/assets`.
7. Send a Slack webhook with release summary.

The Worker uses the GitHub App installation token (not a PAT) to call the API, which grants fine-grained permissions without long-lived secrets.

## Solution

```typescript
// src/index.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string; // PEM, stored as a secret
  GITHUB_APP_INSTALLATION_ID: string;
  ARTIFACTS_BUCKET: R2Bucket;
  SLACK_WEBHOOK_URL: string;
}

interface PushEvent {
  ref: string;
  before: string;
  after: string;
  repository: { full_name: string; owner: { login: string }; name: string };
  head_commit: { message: string };
}

interface GitHubCommit {
  sha: string;
  commit: { message: string };
}

// --- HMAC verification ---
async function verifySignature(
  secret: string,
  signature: string,
  body: ArrayBuffer,
): Promise<void> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, body);
  const expected =
    'sha256=' +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  if (expected !== signature) throw new Error('Signature mismatch');
}

// --- GitHub App installation token via JWT ---
async function getInstallationToken(env: Env): Promise<string> {
  // Build JWT for GitHub App
  const now = Math.floor(Date.now() / 1000);
  const payload = { iat: now - 60, exp: now + 600, iss: env.GITHUB_APP_ID };

  // Import RSA private key
  const pemContents = env.GITHUB_APP_PRIVATE_KEY.replace(
    /-----(?:BEGIN|END) RSA PRIVATE KEY-----/g,
    '',
  ).replace(/\s/g, '');
  const keyData = Uint8Array.from(atob(pemContents), (c) => c.charCodeAt(0));
  const privateKey = await crypto.subtle.importKey(
    'pkcs8',
    keyData,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const encode = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');

  const header = encode({ alg: 'RS256', typ: 'JWT' });
  const body = encode(payload);
  const signing = new TextEncoder().encode(`${header}.${body}`);
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', privateKey, signing);
  const jwt =
    `${header}.${body}.` +
    btoa(String.fromCharCode(...new Uint8Array(sig)))
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');

  // Exchange JWT for installation token
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_APP_INSTALLATION_ID}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'orchords-release-bot/1.0',
      },
    },
  );
  const { token } = (await res.json()) as { token: string };
  return token;
}

// --- Changelog generation ---
function groupCommits(commits: GitHubCommit[]): string {
  const groups: Record<string, string[]> = {
    feat: [],
    fix: [],
    perf: [],
    refactor: [],
    docs: [],
    chore: [],
    other: [],
  };

  const typeLabel: Record<string, string> = {
    feat: '### Features',
    fix: '### Bug Fixes',
    perf: '### Performance',
    refactor: '### Refactoring',
    docs: '### Documentation',
    chore: '### Chores',
    other: '### Other',
  };

  for (const c of commits) {
    const firstLine = c.commit.message.split('\n')[0];
    const match = firstLine.match(/^(\w+)(?:\([^)]+\))?!?:\s*(.+)/);
    if (match) {
      const type = match[1] in groups ? match[1] : 'other';
      groups[type].push(`- ${match[2]} (${c.sha.slice(0, 7)})`);
    } else {
      groups['other'].push(`- ${firstLine} (${c.sha.slice(0, 7)})`);
    }
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([type, items]) => `${typeLabel[type]}\n${items.join('\n')}`)
    .join('\n\n');
}

// --- R2 artifact upload + GitHub asset attachment ---
async function attachArtifacts(
  ghToken: string,
  owner: string,
  repo: string,
  releaseId: number,
  tag: string,
  bucket: R2Bucket,
): Promise<string[]> {
  const attached: string[] = [];
  // Convention: artifacts uploaded by CI to R2 under `releases/{tag}/`
  const listed = await bucket.list({ prefix: `releases/${tag}/` });

  for (const obj of listed.objects) {
    const r2Object = await bucket.get(obj.key);
    if (!r2Object) continue;

    const filename = obj.key.split('/').pop() ?? obj.key;
    const assetBlob = await r2Object.arrayBuffer();

    const uploadRes = await fetch(
      `https://uploads.github.com/repos/${owner}/${repo}/releases/${releaseId}/assets?name=${encodeURIComponent(filename)}`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${ghToken}`,
          'Content-Type': r2Object.httpMetadata?.contentType ?? 'application/octet-stream',
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'orchords-release-bot/1.0',
        },
        body: assetBlob,
      },
    );
    if (uploadRes.ok) attached.push(filename);
  }
  return attached;
}

// --- Main handler ---
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const rawBody = await request.arrayBuffer();
    const signature = request.headers.get('X-Hub-Signature-256') ?? '';

    try {
      await verifySignature(env.GITHUB_WEBHOOK_SECRET, signature, rawBody);
    } catch {
      return new Response('Unauthorized', { status: 401 });
    }

    const event = request.headers.get('X-GitHub-Event');
    if (event !== 'push') return new Response('Ignored', { status: 200 });

    const payload = JSON.parse(new TextDecoder().decode(rawBody)) as PushEvent;
    const { ref, before, after, repository } = payload;

    if (!ref.startsWith('refs/tags/')) return new Response('Not a tag push', { status: 200 });

    const tag = ref.replace('refs/tags/', '');
    const { owner: { login: owner }, name: repo } = repository;

    ctx.waitUntil(
      (async () => {
        const ghToken = await getInstallationToken(env);
        const headers = {
          Authorization: `Bearer ${ghToken}`,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'orchords-release-bot/1.0',
        };

        // Get commits between before and after SHAs
        const compareRes = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/compare/${before}...${after}`,
          { headers },
        );
        const { commits } = (await compareRes.json()) as { commits: GitHubCommit[] };
        const changelog = groupCommits(commits);

        // Create GitHub release
        const releaseRes = await fetch(
          `https://api.github.com/repos/${owner}/${repo}/releases`,
          {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({
              tag_name: tag,
              name: `Release ${tag}`,
              body: changelog,
              draft: false,
              prerelease: tag.includes('-'),
            }),
          },
        );
        const release = (await releaseRes.json()) as { id: number; html_url: string };

        // Attach R2 artifacts
        const attached = await attachArtifacts(
          ghToken,
          owner,
          repo,
          release.id,
          tag,
          env.ARTIFACTS_BUCKET,
        );

        // Slack notification
        await fetch(env.SLACK_WEBHOOK_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `*${repo} ${tag} released* <${release.html_url}|View Release>`,
            attachments: [
              {
                color: '#36a64f',
                text:
                  changelog.slice(0, 500) +
                  (attached.length ? `\n\n*Assets:* ${attached.join(', ')}` : ''),
              },
            ],
          }),
        });
      })(),
    );

    return new Response('Release queued', { status: 202 });
  },
};
```

## Implementation Details

**R2 artifact convention** — CI jobs (e.g., GitHub Actions) upload build outputs to the R2 bucket under `releases/{tag}/` before or in parallel with tag push. The Worker reads them asynchronously via `waitUntil`.

**Installation token TTL** — installation tokens expire after 1 hour. Cache them in Workers KV with a 55-minute TTL to avoid extra API calls on rapid tag pushes.

**Prerelease detection** — tags containing a hyphen (`v1.2.0-beta.1`) are automatically marked prerelease. Adjust the regex to match your versioning scheme.

**wrangler.toml**:

```toml
[[r2_buckets]]
binding        = "ARTIFACTS_BUCKET"
bucket_name    = "orchords-artifacts"

[vars]
GITHUB_APP_ID             = "123456"
GITHUB_APP_INSTALLATION_ID = "78901234"
```

## Anti-patterns

- Do not use a long-lived PAT — use GitHub App installation tokens for least-privilege access and auditability.
- Do not generate the changelog inside the synchronous response path — do it inside `waitUntil` and return 202 immediately so GitHub's webhook delivery does not time out.
- Do not concatenate untrusted commit messages directly into Slack `text` fields without escaping `&`, `<`, `>`.
- Do not store the PEM private key as a `[vars]` entry — always use `wrangler secret put GITHUB_APP_PRIVATE_KEY`.

## Gotchas

- The GitHub release assets upload endpoint is `uploads.github.com`, not `api.github.com` — different hostname.
- `R2Bucket.list()` returns at most 1 000 objects per call; paginate with `cursor` for large artifact sets.
- When `before` is the zero SHA (`0000000000000000000000000000000000000000`) the tag is new with no prior history — handle this case by comparing against the previous tag instead.
- GitHub's webhook delivery timeout is 10 seconds; `waitUntil` lets the Worker finish after the 202 is sent.

## Verification

```bash
# Trigger a test release
git tag v0.0.1-test && git push origin v0.0.1-test

# Check Worker logs
wrangler tail --format=pretty

# Confirm release was created
gh release view v0.0.1-test --repo example-org/example-repo
```

## Related

- `documentation/categories/github/workers-github-branch-protection-enforcer.md`
- `documentation/categories/cloudflare/workers-r2-presigned-urls.md`
- `documentation/categories/cloudflare/workers-github-app-jwt.md`

## Sources

- https://docs.github.com/en/rest/releases/releases
- https://docs.github.com/en/rest/releases/assets
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
