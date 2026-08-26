# performance-testing-k6

**Issue:** Load testing APIs with k6 to validate performance under load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APIs perform well with 1 user but degrade with 100 concurrent users. k6 simulates realistic load.

## Pattern / Solution
```js
// load-test.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {
  stages: [
    { duration: "1m", target: 50 },   // ramp up
    { duration: "3m", target: 50 },   // steady state
    { duration: "1m", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],  // 95th percentile < 500ms
    errors: ["rate<0.01"],             // error rate < 1%
  },
};

export default function () {
  const res = http.get("https://api.example.com/users");
  check(res, { "status is 200": (r) => r.status === 200 });
  errorRate.add(res.status !== 200);
  sleep(1);
}
```

Run: `k6 run load-test.js`
Cloud run: `k6 cloud load-test.js`

## Gotchas
- k6 scripts are JavaScript but run in a Go runtime — no Node.js APIs
- Use `k6/html` for response parsing, not DOM APIs
- Baseline before optimizing — always establish current p95 first

## Related
- `performance-testing-artillery.md`
- `stress-testing-patterns.md`
- `load-test-scenarios.md`
