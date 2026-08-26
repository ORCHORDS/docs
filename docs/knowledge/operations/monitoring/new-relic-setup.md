# new-relic-setup

**Issue:** Instrumenting a Node.js application with New Relic APM
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams using New Relic need APM, infrastructure, and log management in one platform.

## Pattern / Solution
```bash
npm install newrelic
```

```javascript
// newrelic.js — must be first require
'use strict';
exports.config = {
  app_name: ['My Application'],
  license_key: process.env.NEW_RELIC_LICENSE_KEY,
  distributed_tracing: { enabled: true },
  logging: { level: 'info' },
  application_logging: {
    enabled: true,
    forwarding: { enabled: true },
    local_decorating: { enabled: false },
  },
  transaction_tracer: {
    enabled: true,
    transaction_threshold: 'apdex_f',
    record_sql: 'obfuscated',
  },
};
```

Start: `node -r newrelic server.js`

Infrastructure agent (Linux):
```bash
curl -Ls https://download.newrelic.com/install/newrelic-cli/scripts/install.sh | bash
NEW_RELIC_API_KEY=$KEY NEW_RELIC_ACCOUNT_ID=$ACCOUNT newrelic install
```

## Gotchas
- `newrelic.js` must be required before any other module
- `record_sql: 'obfuscated'` required to avoid logging sensitive query parameters
- New Relic uses Apdex T for thresholds; configure it per application

## Related
- `datadog-apm-setup.md`
- `opentelemetry-sdk-setup.md`
