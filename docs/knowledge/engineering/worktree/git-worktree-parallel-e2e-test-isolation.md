# Git Worktree Parallel E2E Test Isolation for Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers project has a Playwright or Vitest E2E test suite that runs against `wrangler dev`. When you run two test suites simultaneously — say, a full regression run alongside a per-PR smoke test — they both bind to port 8787, use the same D1 database fixture, and write to the same `.wrangler/` state directory. Tests fail with `EADDRINUSE`, corrupt each other's database state, and produce misleading results.

You need each E2E suite to operate in complete isolation: its own local Worker server, its own D1 fixture database, its own object storage, and its own seeded test data — all without conflicting with other suites running concurrently on the same machine or in parallel CI matrix jobs.

---

## Context

`wrangler dev` in local mode (`--local`) uses Miniflare under the hood and stores all durable state (D1, KV, R2, Durable Objects) under `.wrangler/state/`. Because this path is relative to the working directory of the `wrangler dev` process, two processes launched from the same working directory share state and will conflict.

A git worktree provides each test suite with a separate working directory that:
- Has its own `.wrangler/state/` directory (isolation).
- Shares the same object database as the main repo (no extra disk space for source files).
- Can be created and destroyed programmatically within a test setup/teardown script.

This is different from the CI parallelisation pattern (which splits work across separate runner VMs) — here the isolation is within a single machine, enabling both local development parallelism and tighter control over port assignment.

---

## Worktree Creation and Teardown (Test Global Setup)

```typescript
// e2e/global-setup.ts  (Playwright or Vitest globalSetup)
import { execSync, spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

export interface WorktreeTestContext {
  worktreePath: string;
  port: number;
  baseUrl: string;
  cleanup: () => Promise<void>;
}

let portCounter = 18000; // start away from 8787 to avoid conflicts

export async function createIsolatedWorkerEnvironment(
  label: string
): Promise<WorktreeTestContext> {
  const port = portCounter++;
  const repoRoot = execSync("git rev-parse --show-toplevel", {
    encoding: "utf-8",
  }).trim();

  // Create a temporary worktree in the OS temp directory
  const worktreePath = mkdtempSync(join(tmpdir(), `e2e-${label}-`));

  execSync(
    `git worktree add --no-checkout "${worktreePath}" HEAD`,
    { cwd: repoRoot }
  );

  // Checkout the files we need for the Worker (sparse)
  execSync("git sparse-checkout init --cone", { cwd: worktreePath });
  execSync("git sparse-checkout set src wrangler.toml package.json tsconfig.json", {
    cwd: worktreePath,
  });
  execSync("git checkout HEAD", { cwd: worktreePath });

  // Install dependencies (symlink node_modules from repo root to save time)
  execSync(`ln -s "${repoRoot}/node_modules" "${worktreePath}/node_modules"`);

  // Start the isolated wrangler dev process
  const wrangler = spawn(
    "pnpm",
    [
      "wrangler",
      "dev",
      "--local",
      "--port",
      String(port),
      "--persist-to",
      `.wrangler/state-${label}`,  // explicit state dir to avoid default collision
    ],
    {
      cwd: worktreePath,
      stdio: "pipe",
      env: {
        ...process.env,
        WRANGLER_LOG: "warn",
      },
    }
  );

  // Wait until the server is ready
  await waitForPort(port, 30_000);

  const cleanup = async (): Promise<void> => {
    wrangler.kill("SIGTERM");
    await new Promise<void>((resolve) => wrangler.on("exit", resolve));
    // Remove the worktree
    execSync(`git worktree remove --force "${worktreePath}"`, { cwd: repoRoot });
    rmSync(worktreePath, { recursive: true, force: true });
  };

  return {
    worktreePath,
    port,
    baseUrl: `http://localhost:${port}`,
    cleanup,
  };
}

async function waitForPort(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://localhost:${port}/health`);
      if (response.ok) return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error(`Port ${port} did not become ready within ${timeoutMs}ms`);
}
```

---

## Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";
import { createIsolatedWorkerEnvironment, WorktreeTestContext } from "./e2e/global-setup";

// Each project gets its own worker environment
const environments: WorktreeTestContext[] = [];

export default defineConfig({
  testDir: "./e2e",
  workers: 4, // run 4 browser contexts in parallel

  globalSetup: async () => {
    // Spin up N isolated workers, one per shard if using --shard
    const ctx = await createIsolatedWorkerEnvironment("playwright");
    environments.push(ctx);
    // Make baseURL available to tests via env var
    process.env.PLAYWRIGHT_BASE_URL = ctx.baseUrl;
  },

  globalTeardown: async () => {
    await Promise.all(environments.map((e) => e.cleanup()));
  },

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8787",
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
});
```

---

## Vitest E2E with Isolated Workers

```typescript
// vitest.e2e.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globalSetup: ["./e2e/vitest-global-setup.ts"],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    // Shard-aware isolation: each shard gets a unique label
    // Pass --shard=1/4 to the CLI and use VITEST_SHARD_INDEX env var
  },
});
```

```typescript
// e2e/vitest-global-setup.ts
import { createIsolatedWorkerEnvironment, WorktreeTestContext } from "./global-setup";

let ctx: WorktreeTestContext;

export async function setup(): Promise<void> {
  const shardIndex = process.env.VITEST_POOL_ID ?? "0";
  ctx = await createIsolatedWorkerEnvironment(`vitest-${shardIndex}`);
  process.env.WORKER_BASE_URL = ctx.baseUrl;
}

export async function teardown(): Promise<void> {
  await ctx?.cleanup();
}
```

---

## D1 Database Seeding Per Worktree

Each worktree has its own `.wrangler/state-<label>/` directory, so D1 databases are fully isolated. Seed them in the global setup:

```typescript
// e2e/seed-db.ts
import { execSync } from "node:child_process";
import { join } from "node:path";

export function seedDatabase(worktreePath: string, label: string): void {
  const persistDir = join(worktreePath, `.wrangler/state-${label}`);

  // Apply migrations
  execSync(
    `wrangler d1 migrations apply my-db --local --persist-to "${persistDir}"`,
    { cwd: worktreePath }
  );

  // Seed fixture data
  execSync(
    `wrangler d1 execute my-db --local --persist-to "${persistDir}" --file ./e2e/fixtures/seed.sql`,
    { cwd: worktreePath }
  );
}
```

Call `seedDatabase(ctx.worktreePath, label)` in `createIsolatedWorkerEnvironment` after `waitForPort`.

---

## CI Matrix Strategy

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1  # shallow is fine — worktrees need only HEAD

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
      - run: pnpm playwright install chromium

      - name: Run E2E shard ${{ matrix.shard }}/4
        env:
          VITEST_SHARD_INDEX: ${{ matrix.shard }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: pnpm playwright test --shard=${{ matrix.shard }}/4

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report-shard-${{ matrix.shard }}
          path: playwright-report/
```

Because each shard runs in its own GitHub Actions runner VM, port conflicts are impossible at the CI level. The worktree isolation pattern is most valuable for local development where multiple suites share one machine.

---

## Port Allocation: Avoiding Collisions

When running multiple suites locally, naive port counters can still collide if a previous run crashed and left a port occupied. Use a port-finding utility:

```typescript
// e2e/find-free-port.ts
import { createServer } from "node:net";

export function findFreePort(start: number = 18000): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.listen(start, "127.0.0.1", () => {
      const { port } = server.address() as { port: number };
      server.close(() => resolve(port));
    });
    server.on("error", () => {
      // Port is busy, try the next one
      findFreePort(start + 1).then(resolve).catch(reject);
    });
  });
}
```

Replace `portCounter++` in `createIsolatedWorkerEnvironment` with `await findFreePort(18000 + shardIndex * 100)`.

---

## Anti-patterns

- **Sharing `.wrangler/state/` across worktrees** — The default persist path is always `.wrangler/state/` relative to `cwd`. Without `--persist-to`, two `wrangler dev` processes in different worktrees still collide if `cwd` resolves to the same directory (e.g., via symlinks). Always pass `--persist-to` with a unique label.
- **Checking out the full tree for each worktree** — A full checkout per suite wastes disk space and slows setup. Use sparse checkout (shown above) or symlink `node_modules` from the root.
- **Killing `wrangler dev` with `SIGKILL`** — This leaves `.wrangler/state/` lock files behind, causing the next run to fail with "Another instance is already running." Always use `SIGTERM` and wait for the process to exit.
- **Not waiting for readiness before running tests** — `wrangler dev` emits its ready message to stderr but the HTTP server may not be listening yet. Poll the health endpoint rather than sleeping for a fixed duration.
- **Using the same worktree for multiple sequential test runs** — Leftover state from the previous run can contaminate the next. Tear down and recreate the worktree for each run, or truncate the state directory explicitly.

---

## Gotchas

- `git worktree add --no-checkout` leaves the worktree directory empty. You must run `git checkout HEAD` (or `git sparse-checkout set` + `git checkout HEAD`) to populate it. Forgetting this step results in an empty directory and a confusing "no such file" error from `wrangler dev`.
- `git worktree remove` fails if the worktree has uncommitted changes or if the process using it is still running. Always kill the `wrangler dev` process before calling `git worktree remove`.
- Symlinked `node_modules` (the shortcut used above) can cause issues if packages use `__dirname` or `import.meta.url` to resolve their own paths, since those resolve through the symlink to the original location. Test with real installs if you see "module not found" errors in the symlinked worktree.
- On Linux, `inotify` watches are shared across worktrees. High file-watch counts can exhaust `fs.inotify.max_user_watches`. Increase it with `echo 524288 | sudo tee /proc/sys/fs/inotify/max_user_watches` if you run many parallel worktrees.
- `wrangler dev --local` with D1 stores data in SQLite files inside `.wrangler/state/`. SQLite enforces only one writer at a time. Two suites pointing at the same state directory will produce `SQLITE_BUSY` errors. The `--persist-to` flag is the fix; confirm the path is unique per suite.

---

## Verification

```bash
# 1. Confirm worktrees are listed
git worktree list

# 2. Confirm each wrangler dev process uses a distinct port and state dir
ps aux | grep 'wrangler dev' | grep -oE '\-\-port [0-9]+'
ps aux | grep 'wrangler dev' | grep -oE '\-\-persist-to [^ ]+'

# 3. Confirm no two processes share the same state directory
ps aux | grep 'wrangler dev' | grep -oE '\-\-persist-to [^ ]+' \
  | awk '{print $2}' | sort | uniq -d
# should be empty

# 4. Run the E2E suite and confirm it passes with no port conflicts
VITEST_SHARD_INDEX=1 pnpm vitest run --config vitest.e2e.config.ts
VITEST_SHARD_INDEX=2 pnpm vitest run --config vitest.e2e.config.ts &
wait
```

---

## Related

- `git-worktree-parallel-ci-patterns.md`
- `git-worktree-parallel-wrangler-environments.md`
- `cloudflare-workers-vitest-miniflare-testing.md`
- `git-worktree-lockfile-isolation.md`
- `git-sparse-checkout-cone-mode-workers-monorepo.md`
- `workers-d1-migration-ci-pipeline.md`

---

## Sources

- Cloudflare Docs — [Local development with Miniflare](https://developers.cloudflare.com/workers/testing/local-development/)
- Cloudflare Docs — [wrangler dev](https://developers.cloudflare.com/workers/wrangler/commands/#dev)
- Playwright Docs — [Global setup and teardown](https://playwright.dev/docs/test-global-setup-teardown)
- Vitest Docs — [Global setup](https://vitest.dev/config/#globalsetup)
- Git SCM — [git-worktree(1)](https://git-scm.com/docs/git-worktree)
