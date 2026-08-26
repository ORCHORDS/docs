# opentelemetry-baggage-propagation

**Issue:** Propagating contextual data across service boundaries using OTel baggage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A tenant ID or feature flag set at the API gateway is not available in downstream microservices without being passed explicitly through every function call.

## Pattern / Solution
```typescript
import { propagation, context, baggageEntryMetadataFromString } from "@opentelemetry/api";

// Set baggage at the edge
function setTenantBaggage(tenantId: string) {
  const baggage = propagation.createBaggage({
    "tenant.id": { value: tenantId },
    "feature.flags": { value: "new-checkout=true" },
  });
  return propagation.setBaggage(context.active(), baggage);
}

// Read baggage in any downstream service
function getTenantId(): string | undefined {
  const baggage = propagation.getBaggage(context.active());
  return baggage?.getEntry("tenant.id")?.value;
}

// Baggage is automatically propagated via W3C traceparent/tracestate headers
// when using OTel HTTP instrumentation
```

## Gotchas
- Baggage is propagated to all downstream services; do not include sensitive data
- Baggage is not stored in trace backends; it is in-flight metadata only
- Total baggage size limit is 8192 bytes (W3C spec)

## Related
- `opentelemetry-custom-spans.md`
- `opentelemetry-sdk-setup.md`
- `log-correlation-ids.md`
