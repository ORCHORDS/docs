# feature-cookbook-debugging

**Issue:** Debugging — techniques, tools, common bugs
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user reports a bug. You can't reproduce it. You
look at the logs. Nothing useful. You add logging.
Deploy. Wait. The user reports again. You wish you
could debug.

## Root cause
**Without proper debugging tools, bugs are
time-consuming.** Use the right techniques.

**Source:** Various debugging guides.

## The "reproduce" pattern

For reproducing, the first step:
1. **Get the exact steps:** What did the user do?
2. **Get the environment:** Browser, OS, account
3. **Get the timing:** When did it happen?
4. **Run locally:** Match the environment
5. **Use the same data:** If possible

Reproduce is 80% of the work.

## The "logs" pattern

For logs, structured + contextual:
```ts
logEvent('function.called', 'debug', {
  function: 'getUser',
  args: { id },
  user: ctx.user.id,
  requestId: ctx.requestId,
  timestamp: new Date().toISOString(),
});
```

The log has full context.

## The "log redaction" pattern

For PII, redact:
```ts
function redact(input: any): any {
  const str = JSON.stringify(input);
  return JSON.parse(str.replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '[REDACTED]'));
}

logEvent('user.queried', 'debug', redact({ userId, email }));
```

PII is redacted.

## The "breakpoint" pattern

For breakpoints, use the dev tools:
```ts
// In a Worker, you can use `console.log` + `console.error`
console.log({ msg: 'debug', userId, value });

// In a Worker with `--remote`, you can attach devtools
wrangler dev --remote

// In the browser, use the Sources tab
```

The dev tools are used.

## The "binary search" pattern

For "when did this break?":
1. **Find a known good commit:** Last deploy where it worked
2. **Find a known bad commit:** First deploy where it broke
3. **Bisect:** Try the midpoint
4. **Repeat:** Until you find the bad commit

```bash
git bisect start
git bisect bad
git bisect good <commit>
git bisect run <test>
```

The bisect finds the bad commit.

## The "rubber duck" pattern

For explaining, use a rubber duck:
1. **Explain:** Line by line, what the code does
2. **Find the gap:** The bug is where you can't explain
3. **Fix:** Address the gap

The act of explaining reveals the bug.

## The "stack trace" pattern

For stack traces, capture + log:
```ts
try {
  await doSomething();
} catch (err) {
  logEvent('error', 'error', {
    message: (err as Error).message,
    stack: (err as Error).stack,
    userId: ctx.user.id,
    requestId: ctx.requestId,
  });
  throw err;
}
```

The stack is captured.

## The "network" pattern

For network issues, log the request + response:
```ts
logEvent('http.call', 'debug', {
  url,
  method,
  headers: redact(headers),
  body: redact(body),
  responseStatus: response.status,
  responseBody: redact(await response.text()),
});
```

The network is logged.

## The "race condition" pattern

For race conditions, use locks:
```ts
class Mutex {
  private locked = false;
  private queue: Array<() => void> = [];

  async run<T>(fn: () => Promise<T>): Promise<T> {
    if (this.locked) {
      await new Promise<void>(resolve => this.queue.push(resolve));
    }
    this.locked = true;
    try {
      return await fn();
    } finally {
      this.locked = false;
      const next = this.queue.shift();
      if (next) next();
    }
  }
}

const userMutex = new Mutex();
await userMutex.run(async () => {
  await updateUser(id, updates);
});
```

The race is prevented.

## The "memory leak" pattern

For memory leaks:
- **Check:** `process.memoryUsage()` periodically
- **Profile:** Use Chrome DevTools
- **Hunt:** Look for unbounded growth

```ts
setInterval(() => {
  const usage = process.memoryUsage();
  logEvent('memory.usage', 'debug', usage);
}, 60_000);
```

The memory is monitored.

## The "performance" pattern

For performance:
- **Profile:** Chrome DevTools, wrk, autocannon
- **Find:** The hot spot
- **Fix:** Optimize
- **Measure:** Verify the fix

```ts
const start = Date.now();
const result = await expensiveOperation();
logEvent('performance.measurement', 'debug', { operation: 'expensiveOperation', durationMs: Date.now() - start });
```

The performance is measured.

## The "common bug" pattern

Common bugs to check:
- **Off-by-one:** `for (let i = 0; i <= n; i++)` should be `< n`
- **Null/undefined:** `user.email.length` (might be null)
- **Floating point:** `0.1 + 0.2 === 0.3` is false
- **Async:** `for` loop with `await` (use `for...of` or `Promise.all`)
- **Closure:** Captured loop variable
- **Equality:** `==` vs `===`
- **Type coercion:** `"0" == false` is true

The common bugs are checked.

## The "intermittent bug" pattern

For intermittent bugs:
1. **Add logging:** Every operation
2. **Run with the same data:** Multiple times
3. **Vary:** One variable at a time
4. **Find:** The pattern

```ts
// Add deterministic logging
logEvent('race.test', 'debug', { timestamp: Date.now(), requestId, userId, action });
```

The bug is found.

## The "debugging anti-pattern" anti-patterns

### 1. No logging
- **Issue:** Can't see what happened
- **Fix:** Structured logging

### 2. PII in logs
- **Issue:** GDPR violation
- **Fix:** Redact

### 3. No context
- **Issue:** Logs are useless
- **Fix:** Add user ID, request ID

### 4. Print debugging
- **Issue:** Quick, but unprofessional
- **Fix:** Structured logging

### 5. No repro
- **Issue:** Can't fix what you can't reproduce
- **Fix:** Reproduce first

### 6. Random changes
- **Issue:** Make it worse
- **Fix:** Bisect + measure

## Verification
- **Test:** Bug is reproducible
- **Test:** Bug is fixed
- **Test:** No regression
- **Live:** Monitoring catches it
- **Audit:** Quarterly debugging review

## Gotchas
- **The "no repro" anti-pattern.** Reproduce first.
- **The "no logging" anti-pattern.** Structured
  logging.
- **The "random changes" anti-pattern.** Bisect.

## Related
- `feature-cookbook-monitoring.md`
- `feature-cookbook-monitoring-detail.md`
- `feature-cookbook-testing-strategies.md`
- `profiling-and-debugging.md`
- Chrome DevTools: https://developer.chrome.com/docs/devtools/
- `git bisect`: https://git-scm.com/docs/git-bisect
