# value-objects

**Issue:** Modeling domain concepts that have no identity, only their attributes matter
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Primitive obsession: `string email`, `decimal amount`, `string currency` passed around without validation or meaning.

## Pattern / Solution
Value Objects are immutable, equality is by value, and they encapsulate domain rules.

```python
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
        if self.currency not in VALID_CURRENCIES:
            raise ValueError(f"Unknown currency: {self.currency}")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

@dataclass(frozen=True)
class Email:
    value: str
    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError("Invalid email")
```

## Gotchas
- Immutability means replace, not mutate; `money = money.add(other)` not `money.amount += ...`
- Do not use value objects as DB primary keys — entities need identity
- Collections of value objects are fine inside aggregates

## Related
- `aggregate-root-pattern.md`
- `domain-driven-design-basics.md`
