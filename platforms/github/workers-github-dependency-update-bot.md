# Automated Dependency Update Bot via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want an automated dependency update bot — similar to Dependabot but hosted on Cloudflare Workers — that scans `package.json` files across GitHub repos on a schedule, checks npm for newer versions, creates grouped PRs (patch / minor / major), deduplicates against already-open PRs, and caches npm version lookups in KV to stay within rate limits.

## Context

Dependabot is GitHub-native but limited in customization: grouping rules, PR templates, and target branch logic are restricted. A custom Worker bot gives full control:

1. **Scheduled scan** — Cron Trigger (e.g., daily) iterates repos and reads `package.json` via Contents API.
2. **npm registry check** — `GET https://registry.npmjs.org/{package}/latest` for current version; cached in KV with 6-hour TTL.
3. **Semver classification** — patch / minor / major per `semver` rules applied inline (no npm package needed in Workers).
4. **PR deduplication** — list open PRs with label `dependencies` and skip packages already covered.
5. **PR creation** — one PR per semver tier per repo, updating `package.json` and `package-lock.json` stub via GitHub Contents API.
6. **GitHub App auth** — installation tokens, not PATs.

## Solution

```typescript
// src/index.ts
export interface Env {
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_APP_INSTALLATION_ID: string;
  GITHUB_ORG: string;
  NPM_CACHE: KVNamespace;
  TARGET_REPOS: string; // comma-separated list, or '*' for all org repos
}

interface PackageJson {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
}

interface VersionBump {
  name: string;
  currentRange: string;
  currentVersion: string;
  latestVersion: string;
  tier: 'patch' | 'minor' | 'major';
}

// --- Semver helpers (no external deps) ---
function parseSemver(v: string): [number, number, number] {
  const clean = v.replace(/^[^0-9]*/, '').split('-')[0];
  const [maj = 0, min = 0, pat = 0] = clean.split('.').map(Number);
  return [maj, min, pat];
}

function classifyBump(
  current: string,
  latest: string,
): 'patch' | 'minor' | 'major' | 'none' {
  const [cMaj, cMin, cPat] = parseSemver(current);
  const [lMaj, lMin, lPat] = parseSemver(latest);
  if (lMaj > cMaj) return 'major';
  if (lMin > cMin) return 'minor';
  if (lPat > cPat) return 'patch';
  return 'none';
}

function resolveCurrentVersion(range: string): string {
  // Strip range operators to get the pinned or approximate version
  return range.replace(/^[\^~>=<*]+/, '').trim() || '0.0.0';
}

// --- KV-cached npm version lookup ---
async function getLatestNpmVersion(pkg: string, kv: KVNamespace): Promise<string | null> {
  const cacheKey = `npm:latest:${pkg}`;
  const cached = await kv.get(cacheKey);
  if (cached) return cached;

  const res = await fetch(`https://registry.npmjs.org/${encodeURIComponent(pkg)}/latest`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) return null;
  const { version } = (await res.json()) as { version: string };
  // Cache for 6 hours
  await kv.put(cacheKey, version, { expirationTtl: 6 * 3600 });
  return version;
}

// --- GitHub App token ---
async function getInstallationToken(env: Env): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload = { iat: now - 60, exp: now + 600, iss: env.GITHUB_APP_ID };
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
  const enc = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const h = enc({ alg: 'RS256', typ: 'JWT' });
  const b = enc(payload);
  const sig = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    privateKey,
    new TextEncoder().encode(`${h}.${b}`),
  );
  const jwt =
    `${h}.${b}.` +
    btoa(String.fromCharCode(...new Uint8Array(sig)))
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_APP_INSTALLATION_ID}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'orchords-dep-bot/1.0',
      },
    },
  );
  const { token } = (await res.json()) as { token: string };
  return token;
}

function ghHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'orchords-dep-bot/1.0',
  };
}

// --- Read package.json from repo ---
async function readPackageJson(
  token: string,
  owner: string,
  repo: string,
): Promise<{ content: PackageJson; sha: string } | null> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/package.json`,
    { headers: ghHeaders(token) },
  );
  if (!res.ok) return null;
  const file = (await res.json()) as { content: string; sha: string };
  const decoded = atob(file.content.replace(/\n/g, ''));
  return { content: JSON.parse(decoded) as PackageJson, sha: file.sha };
}

// --- List open dependency PRs to deduplicate ---
async function listOpenDepPRs(
  token: string,
  owner: string,
  repo: string,
): Promise<Set<string>> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/pulls?state=open&per_page=100`,
    { headers: ghHeaders(token) },
  );
  const prs = (await res.json()) as Array<{ title: string; labels: Array<{ name: string }> }>;
  const covered = new Set<string>();
  for (const pr of prs) {
    if (!pr.labels.some((l) => l.name === 'dependencies')) continue;
    // Extract package names mentioned in the PR title (e.g. "chore(deps): bump lodash")
    const match = pr.title.match(/bump ([\w@/-]+)/);
    if (match) covered.add(match[1]);
  }
  return covered;
}

// --- Create a PR with bumped dependencies ---
async function createDepPR(
  token: string,
  owner: string,
  repo: string,
  defaultBranch: string,
  bumps: VersionBump[],
  tier: 'patch' | 'minor' | 'major',
  pkgContent: PackageJson,
  pkgSha: string,
): Promise<void> {
  const branchName = `deps/${tier}-updates-${Date.now()}`;

  // Get default branch SHA
  const refRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/git/ref/heads/${defaultBranch}`,
    { headers: ghHeaders(token) },
  );
  const { object: { sha: baseSha } } = (await refRes.json()) as { object: { sha: string } };

  // Create branch
  await fetch(`https://api.github.com/repos/${owner}/${repo}/git/refs`, {
    method: 'POST',
    headers: { ...ghHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha: baseSha }),
  });

  // Update package.json with new versions
  const updatedPkg = { ...pkgContent };
  for (const bump of bumps) {
    const prefix = bump.currentRange.match(/^[\^~>=<]+/)?.[0] ?? '^';
    if (updatedPkg.dependencies?.[bump.name]) {
      updatedPkg.dependencies[bump.name] = `${prefix}${bump.latestVersion}`;
    } else if (updatedPkg.devDependencies?.[bump.name]) {
      updatedPkg.devDependencies[bump.name] = `${prefix}${bump.latestVersion}`;
    }
  }

  const newContent = btoa(JSON.stringify(updatedPkg, null, 2) + '\n');
  await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/package.json`,
    {
      method: 'PUT',
      headers: { ...ghHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: `chore(deps): bump ${tier} dependencies\n\n${bumps.map((b) => `- ${b.name}: ${b.currentVersion} → ${b.latestVersion}`).join('\n')}`,
        content: newContent,
        sha: pkgSha,
        branch: branchName,
      }),
    },
  );

  // Create PR
  const prBody = [
    `## ${tier.charAt(0).toUpperCase() + tier.slice(1)} dependency updates`,
    '',
    '| Package | From | To |',
    '|---------|------|----|',
    ...bumps.map((b) => `| \`${b.name}\` | \`${b.currentVersion}\` | \`${b.latestVersion}\` |`),
  ].join('\n');

  await fetch(`https://api.github.com/repos/${owner}/${repo}/pulls`, {
    method: 'POST',
    headers: { ...ghHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: `chore(deps): bump ${tier} dependencies (${bumps.length} packages)`,
      body: prBody,
      head: branchName,
      base: defaultBranch,
      labels: ['dependencies', `semver:${tier}`],
    }),
  });
}

// --- Scan a single repo ---
async function scanRepo(
  token: string,
  owner: string,
  repoName: string,
  defaultBranch: string,
  kv: KVNamespace,
): Promise<void> {
  const pkg = await readPackageJson(token, owner, repoName);
  if (!pkg) return;

  const covered = await listOpenDepPRs(token, owner, repoName);
  const allDeps = {
    ...(pkg.content.dependencies ?? {}),
    ...(pkg.content.devDependencies ?? {}),
  };

  const bumps: VersionBump[] = [];
  for (const [name, range] of Object.entries(allDeps)) {
    if (covered.has(name)) continue;
    const latest = await getLatestNpmVersion(name, kv);
    if (!latest) continue;
    const current = resolveCurrentVersion(range);
    const tier = classifyBump(current, latest);
    if (tier === 'none') continue;
    bumps.push({ name, currentRange: range, currentVersion: current, latestVersion: latest, tier });
  }

  // Group by tier
  for (const tier of ['patch', 'minor', 'major'] as const) {
    const group = bumps.filter((b) => b.tier === tier);
    if (group.length === 0) continue;
    await createDepPR(token, owner, repoName, defaultBranch, group, tier, pkg.content, pkg.sha);
  }
}

// --- Scheduled entrypoint ---
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      (async () => {
        const token = await getInstallationToken(env);
        let repos: Array<{ name: string; default_branch: string; archived: boolean; fork: boolean }>;

        if (env.TARGET_REPOS === '*') {
          const res = await fetch(
            `https://api.github.com/orgs/${env.GITHUB_ORG}/repos?per_page=100`,
            { headers: ghHeaders(token) },
          );
          repos = (await res.json()) as typeof repos;
        } else {
          repos = await Promise.all(
            env.TARGET_REPOS.split(',').map(async (r) => {
              const res = await fetch(
                `https://api.github.com/repos/${env.GITHUB_ORG}/${r.trim()}`,
                { headers: ghHeaders(token) },
              );
              return res.json() as Promise<typeof repos[0]>;
            }),
          );
        }

        for (const repo of repos) {
          if (repo.archived || repo.fork) continue;
          await scanRepo(token, env.GITHUB_ORG, repo.name, repo.default_branch, env.NPM_CACHE);
        }
      })(),
    );
  },

  // Optional: manual trigger via HTTP
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/trigger') {
      return new Response('Not Found', { status: 404 });
    }
    ctx.waitUntil(
      (async () => {
        const token = await getInstallationToken(env);
        const { repo, default_branch } = (await request.json()) as {
          repo: string;
          default_branch: string;
        };
        await scanRepo(token, env.GITHUB_ORG, repo, default_branch, env.NPM_CACHE);
      })(),
    );
    return new Response('Scan triggered', { status: 202 });
  },
};
```

## Implementation Details

**wrangler.toml**:

```toml
[triggers]
crons = ["0 3 * * 1"] # Every Monday at 03:00 UTC

[[kv_namespaces]]
binding  = "NPM_CACHE"
id       = "<your-kv-id>"

[vars]
GITHUB_ORG  = "orchords"
TARGET_REPOS = "*"
```

**Label creation** — create the `dependencies`, `semver:patch`, `semver:minor`, and `semver:major` labels in each repo before the bot runs, or add label creation to the `scanRepo` function.

**Concurrency** — `for...of` with sequential `await` avoids saturating the GitHub API. For orgs with many repos, add a small delay (`await scheduler.wait(200)`) between repos or use a queue (Workers Queues).

## Anti-patterns

- Do not call `registry.npmjs.org` for every package on every run — KV caching is essential; the npm registry returns 429s at scale.
- Do not create one PR per package — group by semver tier to keep PR noise manageable.
- Do not update `package-lock.json` by committing a manually generated file — only update `package.json` and let CI regenerate the lockfile; committing a stale lockfile will break installs.
- Do not use `btoa`/`atob` on binary data from `arrayBuffer()` directly — decode via `Uint8Array` for correctness.

## Gotchas

- GitHub Contents API base64-encodes file content with embedded newlines; strip them with `.replace(/\n/g, '')` before `atob`.
- The GitHub label `name` field in a PUT /pulls request is silently ignored if the label does not exist in the repo.
- Scoped npm packages (`@org/pkg`) must be URL-encoded as `%40org%2Fpkg` in the registry URL.
- `parseSemver` above handles pre-release tags by stripping the `-` suffix; adjust if you need to compare pre-release identifiers.
- Workers KV `put` with `expirationTtl` < 60 seconds is rejected — minimum TTL is 60 seconds.

## Verification

```bash
# Trigger manually
curl -X POST https://dep-bot.orchords.workers.dev/trigger \
  -H 'Content-Type: application/json' \
  -d '{"repo":"my-repo","default_branch":"main"}'

# Inspect KV cache
wrangler kv key list --namespace-id <id> --prefix 'npm:latest:'

# Watch cron output
wrangler tail --format=pretty
```

## Related

- `documentation/categories/github/workers-github-branch-protection-enforcer.md`
- `documentation/categories/cloudflare/workers-kv-caching.md`
- `documentation/categories/cloudflare/workers-cron-triggers.md`

## Sources

- https://docs.github.com/en/rest/repos/contents
- https://docs.github.com/en/rest/pulls/pulls
- https://registry.npmjs.org/ (npm public registry)
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
