# performance-testing-artillery

**Issue:** Load testing HTTP APIs and WebSocket services with Artillery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
k6 requires scripting in JavaScript. Artillery uses YAML config for common load patterns and supports WebSocket and Socket.io natively.

## Pattern / Solution
`load-test.yml`:
```yaml
config:
  target: "https://api.example.com"
  phases:
    - duration: 60
      arrivalRate: 10
      name: Warm up
    - duration: 120
      arrivalRate: 50
      name: Ramp up
    - duration: 60
      arrivalRate: 100
      name: Peak load
  defaults:
    headers:
      Authorization: "Bearer {{ $processEnvironment.API_TOKEN }}"

scenarios:
  - name: "Create and fetch user"
    weight: 70
    flow:
      - post:
          url: "/users"
          json: { name: "Test User", email: "{{ $randomString() }}@example.com" }
          capture:
            - json: "$.id"
              as: "userId"
      - get:
          url: "/users/{{ userId }}"
          expect:
            - statusCode: 200
```

Run: `artillery run load-test.yml --output report.json`
Report: `artillery report report.json`

## Gotchas
- `arrivalRate` is new virtual users per second, not concurrent users
- Use `maxVusers` to cap concurrent connections
- WebSocket tests use `engine: ws` in config

## Related
- `performance-testing-k6.md`
- `load-test-scenarios.md`
