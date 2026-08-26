# anti-corruption-layer

**Issue:** Protecting a domain model from being corrupted by integration with legacy or external systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Integrating with a legacy CRM requires adopting its anemic, messy model throughout the new system.

## Pattern / Solution
ACL translates between the external model and the local domain model, preventing the external model from leaking in.

```
[Legacy CRM Model]        [ACL]              [Domain Model]
  CustomerRecord    →   translate()   →    Customer aggregate
  {account_no,           maps fields         {id, email,
   acct_status,          validates            status: AccountStatus}
   contact_email}        enriches
```

```python
class CrmAntiCorruptionLayer:
    def __init__(self, crm_client):
        self.crm = crm_client

    def get_customer(self, customer_id: str) -> Customer:
        raw = self.crm.fetch_account(customer_id)  # external call
        return Customer(
            id=CustomerId(raw['account_no']),
            email=Email(raw['contact_email']),
            status=self._map_status(raw['acct_status'])
        )

    def _map_status(self, raw_status):
        mapping = {'A': AccountStatus.ACTIVE, 'I': AccountStatus.INACTIVE}
        return mapping.get(raw_status, AccountStatus.UNKNOWN)
```

## Gotchas
- ACL can become a maintenance burden if the external API changes frequently
- Do not put business logic in ACL — only translation
- ACL can be a facade, adapter, or full service depending on complexity

## Related
- `bounded-context-design.md`
- `adapter-pattern-integration.md`
- `strangler-fig-migration.md`
