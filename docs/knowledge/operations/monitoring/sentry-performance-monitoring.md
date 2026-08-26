# sentry-performance-monitoring

**Issue:** Using Sentry Performance to trace slow transactions and N+1 queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Slow API responses are reported by users but engineers cannot identify the root cause without distributed traces.

## Pattern / Solution
```typescript
Sentry.init({
  tracesSampleRate: 0.2,  // 20% of transactions
  // Or use sampler for dynamic rates
  tracesSampler: (samplingContext) => {
    const op = samplingContext.transactionContext?.op;
    if (op === "http.server") return 0.1;
    if (op === "db.query") return 0.5;
    return 0.05;
  },
});

// Manual transaction
const transaction = Sentry.startTransaction({
  name: "checkout.process",
  op: "business",
});

const span = transaction.startChild({
  op: "payment.charge",
  description: "stripe charge",
});
await chargeStripe();
span.finish();
transaction.finish();
```

N+1 detection: Sentry automatically flags repeated identical DB queries within a transaction.

## Gotchas
- High `tracesSampleRate` increases event quota consumption
- Transactions must be finished; orphaned transactions auto-expire after 30 minutes
- Use `hub.configureScope()` to attach custom data to all events in a request

## Related
- `sentry-error-tracking.md`
- `database-query-monitoring.md`
- `apm-transaction-tracing.md`
