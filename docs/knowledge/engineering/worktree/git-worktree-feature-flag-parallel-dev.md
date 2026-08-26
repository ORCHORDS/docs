# Developing Feature-Flagged Code in Parallel Worktrees

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are rolling out a significant feature behind a feature flag (e.g., a new payments flow, a redesigned UI component) and need to:

- Keep the **flag-off** (stable) path green on `main`
- Actively develop the **flag-on** (new) path on a feature branch
- Run both paths simultaneously to compare behaviour, performance, or visual output side-by-side
- Toggle the KV/config flag value without restarting both dev servers

Without worktrees you end up switching branches constantly, losing editor state, or running two separate clones that drift out of sync.

---

## Context

A git worktree lets multiple working trees share the same `.git` directory. Each worktree checks out a different branch (or commit) independently. Both share object storage, so no extra disk usage for the object database.

This pattern pairs naturally with:
- Cloudflare Workers / KV feature flags
- LaunchDarkly / Unleash SDK flags checked at runtime
- Environment-variable-toggled flags (`NEXT_PUBLIC_FLAG=true`)

---

## Section 1: Setting Up the Parallel Worktrees

```bash
# From the main repo root (flag-off path lives here on main)
git worktree add ../myapp-flag-on feature/new-payments-flow

# Confirm both worktrees exist
git worktree list
# /path/to/project           abc1234 [main]
# /path/to/project  def5678 [feature/new-payments-flow]
```

```bash
# Start the flag-OFF dev server in the primary worktree
cd /path/to/project
FEATURE_NEW_PAYMENTS=false npm run dev -- --port 3000

# In a second terminal, start the flag-ON dev server
cd /path/to/project
FEATURE_NEW_PAYMENTS=true npm run dev -- --port 3001
```

Both servers are now live. Open `localhost:3000` and `localhost:3001` side by side.

---

## Section 2: KV Flag Toggle Testing (Cloudflare Workers)

When the flag is stored in Cloudflare KV rather than an env var, use Miniflare or Wrangler's local KV to simulate both states.

```bash
# myapp (flag-off worktree) – wrangler.toml points to KV namespace FLAG_NS
cd /path/to/project
wrangler dev --local --persist-to .wrangler/state

# myapp-flag-on – use a separate persist directory so KV state is isolated
cd /path/to/project
wrangler dev --local --persist-to .wrangler/state-flag-on --port 8788
```

```bash
# Seed flag-off KV state
wrangler kv key put --binding FLAG_NS "feature:new-payments" "false" \
  --local --persist-to /path/to/project

# Seed flag-on KV state
wrangler kv key put --binding FLAG_NS "feature:new-payments" "true" \
  --local --persist-to /path/to/project
```

```typescript
// src/flags.ts – shared across both worktrees via the same file on their branch
export async function isEnabled(
  key: string,
  kv: KVNamespace,
): Promise<boolean> {
  const val = await kv.get(key);
  return val === "true";
}

// src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const newPayments = await isEnabled("feature:new-payments", env.FLAG_NS);
    if (newPayments) {
      return handleNewPayments(req, env);
    }
    return handleLegacyPayments(req, env);
  },
};
```

---

## Section 3: Side-by-Side Visual Comparison Script

```typescript
// scripts/compare-screenshots.ts
// Run with: npx tsx scripts/compare-screenshots.ts
import { chromium } from "playwright";
import { writeFileSync } from "fs";

const PATHS = ["/checkout", "/checkout/review", "/checkout/confirm"];
const SERVERS = [
  { label: "flag-off", base: "http://localhost:3000" },
  { label: "flag-on", base: "http://localhost:3001" },
];

async function main() {
  const browser = await chromium.launch();
  for (const path of PATHS) {
    for (const server of SERVERS) {
      const page = await browser.newPage();
      await page.goto(`${server.base}${path}`);
      const slug = path.replace(/\//g, "-").replace(/^-/, "");
      const file = `screenshots/${server.label}-${slug}.png`;
      await page.screenshot({ path: file, fullPage: true });
      console.log(`Saved ${file}`);
      await page.close();
    }
  }
  await browser.close();
}

main().catch(console.error);
```

```bash
mkdir -p screenshots
npx tsx scripts/compare-screenshots.ts
# Open both screenshots for each path and diff visually or with pixelmatch
npx pixelmatch screenshots/flag-off-checkout.png \
                  screenshots/flag-on-checkout.png \
                  screenshots/diff-checkout.png 0.1
```

---

## Section 4: Merging the Feature Branch

Once the flag-on path is approved:

```bash
# Remove the feature worktree first
git worktree remove /path/to/project

# Merge into main
git checkout main
git merge --no-ff feature/new-payments-flow -m "feat: new payments flow (flag graduated)"

# Delete the feature branch
git branch -d feature/new-payments-flow

# Flip the production flag
wrangler kv key put --binding FLAG_NS "feature:new-payments" "true"
```

---

## Anti-patterns

- **Sharing the same port across worktrees** — each dev server must use a distinct port or Unix socket; otherwise the second process fails to bind.
- **Editing the same file in both worktrees expecting it to sync** — changes in `myapp-flag-on` live only on the feature branch; cherry-pick or merge deliberately.
- **Running `npm install` in both worktrees independently** — see the shared `node_modules` article; duplicate installs waste time and disk.
- **Using the same Wrangler persist directory** — KV and DO state collide; always use `--persist-to` with distinct paths.

---

## Gotchas

- `git worktree add` requires the target branch to not be checked out in any other worktree already.
- If you use `husky` or `lefthook`, hooks fire from `.git/hooks` of the main repo for both worktrees (see the hooks isolation article).
- TypeScript `paths` aliases in `tsconfig.json` that are absolute (`/src/...`) may resolve differently depending on CWD — prefer relative or `baseUrl`-relative paths.
- Vite HMR web-socket ports default to the same value; set `server.hmrPort` explicitly per worktree:

```typescript
// vite.config.ts in the flag-on worktree
export default {
  server: { port: 3001, hmr: { port: 3001 } },
};
```

---

## Verification

```bash
# Both servers respond
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/checkout  # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/checkout  # 200

# Confirm each path hits the correct code branch
curl -s http://localhost:3000/api/debug-flag | jq .newPayments  # false
curl -s http://localhost:3001/api/debug-flag | jq .newPayments  # true

# Worktree list sanity check
git worktree list
```

---

## Related

- `documentation/docs/policies/worktree/git-worktree-shared-node-modules-symlink.md`
- `documentation/docs/policies/worktree/git-worktree-git-hooks-isolation.md`
- `documentation/docs/policies/worktree/git-worktree-vscode-multi-root-workspace.md`

---

## Sources

- https://git-scm.com/docs/git-worktree
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/kv/api/
- https://playwright.dev/docs/screenshots
