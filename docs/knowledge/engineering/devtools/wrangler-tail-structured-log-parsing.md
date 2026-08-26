# Wrangler Tail — Structured Log Parsing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When debugging a Cloudflare Worker in production, `wrangler tail` streams live log events as JSON to stdout. Out of the box this is noisy and hard to scan. Piping the output through a small Node.js script lets you filter by log level, worker name, or request-id, format the results as a pretty-printed table, and write matching lines to a rotating file for later analysis.

---

## Context

`wrangler tail` emits one JSON object per line (newline-delimited JSON, NDJSON). Each object includes fields such as `outcome`, `scriptName`, `logs`, `exceptions`, and `event` (the incoming request). The `logs` array contains entries with `level` (`log`, `warn`, `error`) and a `message` array. By reading stdin line-by-line you can process these events in real time without any external dependency beyond Node.js and a couple of small npm packages. Rotating the output file via `rotating-file-stream` prevents unbounded disk usage during long debug sessions. The same script can be run inside a CI job pointing at a staging Worker to capture structured traces.

---

## Config / Setup

```toml
# wrangler.toml — tail consumer config (optional, for named tail workers)
[tail_consumers]
[[tail_consumers]]
service = "log-consumer"   # deploy a separate tail-consumer Worker if needed

# For local piped parsing no extra wrangler config is required.
```

```jsonc
// package.json — relevant scripts
{
  "scripts": {
    "tail": "wrangler tail --format json | node scripts/parse-tail.mjs",
    "tail:errors": "wrangler tail --format json | node scripts/parse-tail.mjs --level error",
    "tail:worker": "wrangler tail my-worker --format json | node scripts/parse-tail.mjs"
  },
  "dependencies": {
    "rotating-file-stream": "^3.2.3",
    "cli-table3": "^0.6.3"
  }
}
```

---

## Implementation — Node.js Tail Parser

```typescript
#!/usr/bin/env node
// scripts/parse-tail.mjs
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { createStream } from 'rotating-file-stream';
import Table from 'cli-table3';
import process from 'node:process';

// --- CLI args -----------------------------------------------------------
const args = process.argv.slice(2);
const filterLevel  = argValue(args, '--level')  ?? null;   // log | warn | error
const filterWorker = argValue(args, '--worker') ?? null;
const filterReqId  = argValue(args, '--req-id') ?? null;
const outDir       = argValue(args, '--out')    ?? 'logs';

function argValue(arr: string[], flag: string): string | undefined {
  const idx = arr.indexOf(flag);
  return idx !== -1 ? arr[idx + 1] : undefined;
}

// --- Rotating log file --------------------------------------------------
const rotatingLog = createStream('wrangler-tail.log', {
  interval : '1d',
  path     : outDir,
  maxFiles : 7,
  compress : 'gzip',
});

// --- Table renderer -----------------------------------------------------
function printTable(rows: string[][]): void {
  const table = new Table({
    head  : ['Time', 'Worker', 'Level', 'Request-ID', 'Message'],
    style : { head: ['cyan'] },
    colWidths: [22, 18, 7, 38, 60],
    wordWrap : true,
  });
  table.push(...rows);
  console.log(table.toString());
}

// --- NDJSON parser ------------------------------------------------------
interface TailLog {
  level   : 'log' | 'warn' | 'error';
  message : unknown[];
}

interface TailEvent {
  outcome    : string;
  scriptName : string;
  event      : { request?: { headers: Record<string, string> } };
  logs       : TailLog[];
  exceptions : { name: string; message: string }[];
  eventTimestamp: number;
}

async function main(): Promise<void> {
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });

  const buffer: string[][] = [];
  let lineCount = 0;

  for await (const raw of rl) {
    const line = raw.trim();
    if (!line) continue;

    let evt: TailEvent;
    try {
      evt = JSON.parse(line) as TailEvent;
    } catch {
      // non-JSON wrangler status lines (e.g. "Connected to …") pass through
      console.log(line);
      continue;
    }

    // Worker filter
    if (filterWorker && evt.scriptName !== filterWorker) continue;

    const ts      = new Date(evt.eventTimestamp).toISOString();
    const reqId   = (evt.event?.request?.headers?.['cf-ray'] ?? '—');
    const worker  = evt.scriptName ?? '—';

    // Request-ID filter
    if (filterReqId && !reqId.includes(filterReqId)) continue;

    for (const log of evt.logs ?? []) {
      if (filterLevel && log.level !== filterLevel) continue;

      const msg = log.message.map(String).join(' ');
      const row = [ts, worker, log.level.toUpperCase(), reqId, msg];
      buffer.push(row);

      // Write to rotating file
      rotatingLog.write(JSON.stringify({ ts, worker, level: log.level, reqId, msg }) + '\n');
    }

    for (const ex of evt.exceptions ?? []) {
      if (filterLevel && filterLevel !== 'error') continue;
      const row = [ts, worker, 'ERROR', reqId, `${ex.name}: ${ex.message}`];
      buffer.push(row);
      rotatingLog.write(JSON.stringify({ ts, worker, level: 'error', reqId, msg: `${ex.name}: ${ex.message}` }) + '\n');
    }

    // Flush table every 20 rows so output stays readable
    lineCount++;
    if (lineCount % 20 === 0 && buffer.length) {
      printTable(buffer.splice(0));
    }
  }

  // Final flush
  if (buffer.length) printTable(buffer);
  rotatingLog.end();
}

main().catch((err) => { console.error(err); process.exit(1); });
```

---

## CI Integration

```yaml
# .github/workflows/tail-smoke.yml
# Runs a 30-second tail capture against the staging Worker after deploy
name: Tail smoke test
on:
  workflow_run:
    workflows: [Deploy staging]
    types: [completed]

jobs:
  tail-smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Capture 30 s of tail output
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          timeout 30 wrangler tail staging-worker --format json \
            | node scripts/parse-tail.mjs --level error --out ci-logs \
            || true   # timeout exit code 124 is expected

      - name: Fail if errors found
        run: |
          if ls ci-logs/wrangler-tail.log 2>/dev/null; then
            COUNT=$(wc -l < ci-logs/wrangler-tail.log)
            echo "Captured $COUNT error log lines"
            if [ "$COUNT" -gt 0 ]; then
              cat ci-logs/wrangler-tail.log
              exit 1
            fi
          fi

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: tail-logs
          path: ci-logs/
```

---

## Anti-patterns

- **Parsing with `tail --format pretty`** — pretty format is human-readable but not machine-parseable; always use `--format json` when piping.
- **Blocking the event loop in the parser** — synchronous `JSON.parse` in a tight loop is fine, but avoid synchronous `fs.writeFileSync` inside the hot path; use a stream.
- **Hardcoding log file paths** — use `--out` / env var so CI and local runs write to different directories and don't stomp each other.
- **Not handling non-JSON lines** — wrangler emits plain-text status lines at startup; failing to guard against `JSON.parse` throws will crash the parser immediately.

---

## Gotchas

- `wrangler tail` requires an API token with the `Workers Tail Read` permission, not just `Workers Scripts Read`.
- The `--format json` flag must appear before any positional Worker name argument in older wrangler versions (`wrangler tail --format json my-worker`).
- `eventTimestamp` is a Unix millisecond timestamp; pass it to `new Date()` directly.
- Rotating-file-stream creates the output directory automatically, but the parent must be writable in CI.
- In GitHub Actions the step `timeout` and the shell `timeout` command interact: set the job `timeout-minutes` generously and rely on the shell `timeout` for precision.

---

## Verification

```bash
# 1. Confirm wrangler tail emits JSON
wrangler tail my-worker --format json 2>/dev/null | head -5 | python3 -m json.tool

# 2. Run parser locally for 10 s
timeout 10 wrangler tail my-worker --format json | node scripts/parse-tail.mjs || true

# 3. Verify rotating log file was created
ls -lh logs/

# 4. Filter to error level only
timeout 10 wrangler tail my-worker --format json \
  | node scripts/parse-tail.mjs --level error || true
```

---

## Related

- `workers-local-dev-d1-seed-script.md`
- `workers-multi-worker-local-dev-service-bindings.md`

---

## Sources

- Cloudflare Wrangler tail docs — https://developers.cloudflare.com/workers/wrangler/commands/#tail
- rotating-file-stream npm — https://www.npmjs.com/package/rotating-file-stream
- cli-table3 npm — https://www.npmjs.com/package/cli-table3
