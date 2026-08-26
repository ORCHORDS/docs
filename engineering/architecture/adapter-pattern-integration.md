# adapter-pattern-integration

**Issue:** Integrating incompatible interfaces without modifying existing code
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A new payment provider has a completely different API from the old one; business logic must not change.

## Pattern / Solution
The adapter wraps the incompatible interface and exposes the expected one.

```python
# Expected interface (port)
class PaymentGateway(ABC):
    def charge(self, amount: Decimal, currency: str, token: str) -> PaymentResult: ...

# Old provider (incompatible interface)
class StripeClient:
    def create_charge(self, amount_cents, currency, source): ...

# Adapter
class StripeAdapter(PaymentGateway):
    def __init__(self, stripe: StripeClient):
        self.stripe = stripe

    def charge(self, amount, currency, token):
        cents = int(amount * 100)
        result = self.stripe.create_charge(cents, currency, token)
        return PaymentResult(success=result.status == "succeeded", id=result.id)
```

## Gotchas
- Adapters that become too thick are a smell; the underlying API should be wrapped, not re-designed
- Each adapter must handle error translation — provider-specific errors → domain errors
- Test adapters against real/sandboxed APIs, not just unit tests

## Related
- `anti-corruption-layer.md`
- `hexagonal-architecture.md`
- `bounded-context-design.md`
