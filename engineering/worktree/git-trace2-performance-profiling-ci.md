# git trace2 Performance Profiling for CI Pipelines

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

CI pipelines slow down over weeks without an obvious cause. `git fetch` or `git checkout` times creep from 4 s to 40 s in a monorepo with thousands of files. There is no structured data to tell you which git sub-operation is responsible, so you cannot target optimizations.

`git trace2` is git's structured telemetry system. It emits JSON events for every internal operation—pack negotiation, index updates, hook execution, fsmonitor calls—and feeds them into file targets or a Unix socket so CI can ingest them without polluting stdout.

## Context

`git trace2` replaced the older `GIT_TRACE` env vars in git 2.22. It supports three formats: `normal` (human text), `perf` (tab-delimited perf counters), and `event` (JSON Lines, one event per line). The `event` format is the only one worth ingesting in CI because it carries structured timing, thread IDs, and a session UUID that correlates parallel worktree operations.

Key environment variables:

| Variable | Purpose |
|---|---|
| `GIT_TRACE2` | human text to file or fd |
| `GIT_TRACE2_PERF` | perf counters to file or fd |
| `GIT_TRACE2_EVENT` | JSON Lines to file or fd |
| `GIT_TRACE2_MAX_FILES` | rotate after N files (default unlimited) |
| `GIT_TRACE2_BRIEF` | suppress timestamps/thread info |

## Enabling trace2 in GitHub Actions

```yaml
# .github/workflows/ci.yml
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      GIT_TRACE2_EVENT: /tmp/git-trace2-${{ github.run_id }}.jsonl
      GIT_TRACE2_MAX_FILES: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run build
        run: pnpm install && pnpm build

      - name: Upload trace2 artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: git-trace2-${{ github.run_id }}
          path: /tmp/git-trace2-*.jsonl
          retention-days: 7
```

## Parsing trace2 events in TypeScript

Each line in the `event` output is a JSON object. Important event names: `version`, `start`, `cmd_name`, `region_enter`, `region_leave`, `data`, `exit`.

```typescript
// scripts/parse-trace2.ts
import { createReadStream } from "node:fs";
import { createInterface } from "node:readline";

interface Trace2Event {
  event: string;
  sid: string;
  thread: string;
  time: string;
  file?: string;
  line?: number;
  nesting?: number;
  category?: string;
  label?: string;
  t_abs?: number;
  t_rel?: number;
  d?: unknown;
}

async function parseTrace2(filePath: string): Promise<Trace2Event[]> {
  const events: Trace2Event[] = [];
  const rl = createInterface({ input: createReadStream(filePath) });
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      events.push(JSON.parse(line) as Trace2Event);
    } catch {
      // skip malformed lines from concurrent writers
    }
  }
  return events;
}

interface RegionProfile {
  category: string;
  label: string;
  totalMs: number;
  calls: number;
}

function profileRegions(events: Trace2Event[]): RegionProfile[] {
  const stack = new Map<string, number>(); // key -> enter time
  const totals = new Map<string, RegionProfile>();

  for (const e of events) {
    const key = `${e.category ?? ""}:${e.label ?? ""}`;
    if (e.event === "region_enter") {
      stack.set(`${e.thread}:${e.nesting}`, e.t_abs ?? 0);
    } else if (e.event === "region_leave") {
      const enterTime = stack.get(`${e.thread}:${e.nesting}`);
      if (enterTime !== undefined) {
        const duration = (e.t_abs ?? 0) - enterTime;
        const existing = totals.get(key) ?? {
          category: e.category ?? "",
          label: e.label ?? "",
          totalMs: 0,
          calls: 0,
        };
        existing.totalMs += duration * 1000;
        existing.calls += 1;
        totals.set(key, existing);
        stack.delete(`${e.thread}:${e.nesting}`);
      }
    }
  }

  return [...totals.values()].sort((a, b) => b.totalMs - a.totalMs);
}

const events = await parseTrace2(process.argv[2]!);
const profile = profileRegions(events);
console.table(profile.slice(0, 20));
```

## Identifying slow operations with a Workers-deployed analysis dashboard

```typescript
// workers/trace2-dashboard/src/index.ts
import { Hono } from "hono";

const app = new Hono<{ Bindings: { TRACE2_KV: KVNamespace } }>();

app.post("/ingest", async (c) => {
  const body = await c.req.text();
  const runId = c.req.header("X-Run-Id") ?? crypto.randomUUID();

  // Store raw JSONL in KV (max 25 MB)
  await c.env.TRACE2_KV.put(`trace:${runId}`, body, {
    expirationTtl: 60 * 60 * 24 * 7, // 7 days
  });

  return c.json({ runId });
});

app.get("/slowest/:runId", async (c) => {
  const raw = await c.env.TRACE2_KV.get(`trace:${c.req.param("runId")}`);
  if (!raw) return c.json({ error: "not found" }, 404);

  const events = raw
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));

  const dataEvents = events.filter((e) => e.event === "data");
  const interesting = dataEvents
    .filter((e) => typeof e.d === "number" && e.d > 0.1)
    .map((e) => ({ category: e.category, key: e.key, value: e.d }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 30);

  return c.json(interesting);
});

export default app;
```

## Uploading trace2 to the dashboard from CI

```typescript
// scripts/upload-trace2.ts
import { readFileSync } from "node:fs";
import { globSync } from "glob";

const files = globSync("/tmp/git-trace2-*.jsonl");
const combined = files.map((f) => readFileSync(f, "utf8")).join("");

const res = await fetch(
  `https://trace2-dashboard.workers.dev/ingest`,
  {
    method: "POST",
    headers: {
      "Content-Type": "text/plain",
      "X-Run-Id": process.env.GITHUB_RUN_ID ?? "local",
      Authorization: `Bearer ${process.env.TRACE2_TOKEN}`,
    },
    body: combined,
  },
);

if (!res.ok) {
  console.error("Upload failed:", await res.text());
  process.exit(1);
}

const { runId } = (await res.json()) as { runId: string };
console.log(
  `Trace2 profile: https://trace2-dashboard.workers.dev/slowest/${runId}`,
);
```

## Anti-patterns

- **Leaving `GIT_TRACE2_EVENT` set globally** in shared CI environments: output files fill disk when thousands of jobs run; always scope to a per-run path and set `GIT_TRACE2_MAX_FILES`.
- **Parsing with regex instead of JSON**: trace2 event lines may be emitted by concurrent threads; partial lines are possible if a process is killed; always guard with try/catch.
- **Trusting `t_rel` alone**: `t_rel` is relative to the event's thread start, not wall clock. Use `t_abs` for cross-thread comparisons.
- **Enabling trace2 in production Workers**: Workers runtime is not git; trace2 only applies to git CLI invocations in CI.

## Gotchas

- On git < 2.22, `GIT_TRACE2_EVENT` is silently ignored; `GIT_TRACE` still works but is unstructured.
- The `sid` (session ID) changes for each git sub-process spawned by hooks; correlate by `parent_sid` field.
- `GIT_TRACE2_EVENT=/dev/stderr` works locally but not in Actions, where stderr is buffered per step; use a file path.
- fsmonitor hook calls appear as `region_enter` with `category=fsm-listen`; if they dominate, switch to `core.fsmonitor=false` in CI.

## Verification

```bash
# Produce a small trace locally
GIT_TRACE2_EVENT=/tmp/test.jsonl git log --oneline -10 > /dev/null
wc -l /tmp/test.jsonl        # should be > 5 lines
head -1 /tmp/test.jsonl | jq .event   # "version"

# Check for slow regions (> 100 ms)
jq 'select(.event=="data" and .d > 0.1) | {category, key, d}' /tmp/test.jsonl
```

## Related

- `git-maintenance-scheduled-background-pack-optimization.md`
- `git-shallow-clone-ci-optimization.md`
- `ci-cache-optimization-github-actions.md`
- `git-built-in-fsmonitor-correctness-and-performance.md`
- `git-commit-graph-incremental-performance.md`

## Sources

- https://git-scm.com/docs/api-trace2
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-trace2target
- https://lore.kernel.org/git/20190519195811.3042-1-git@jeffhostetler.com/
