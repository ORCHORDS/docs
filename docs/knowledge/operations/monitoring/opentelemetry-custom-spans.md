# opentelemetry-custom-spans

**Issue:** Adding custom spans and attributes to traces for business-level visibility
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Auto-instrumentation captures infrastructure calls but misses business logic like payment processing or recommendation engine execution.

## Pattern / Solution
```typescript
import { trace, SpanStatusCode, context } from "@opentelemetry/api";

const tracer = trace.getTracer("payments-service", "1.0.0");

async function processPayment(orderId: string, amount: number) {
  return tracer.startActiveSpan("payment.process", async (span) => {
    span.setAttributes({
      "payment.order_id": orderId,
      "payment.amount_cents": Math.round(amount * 100),
      "payment.currency": "USD",
    });

    try {
      const result = await chargeCard(orderId, amount);
      span.setStatus({ code: SpanStatusCode.OK });
      span.setAttribute("payment.transaction_id", result.txId);
      return result;
    } catch (err) {
      span.recordException(err as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      throw err;
    } finally {
      span.end();
    }
  });
}
```

## Gotchas
- Always call `span.end()` in a finally block to avoid span leaks
- Do not set PII (email, card numbers) as span attributes
- Use semantic conventions for attribute names when they exist

## Related
- `opentelemetry-sdk-setup.md`
- `opentelemetry-baggage-propagation.md`
- `apm-transaction-tracing.md`
