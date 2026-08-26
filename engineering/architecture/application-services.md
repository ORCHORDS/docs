# application-services

**Issue:** Coordinating domain operations without polluting domain logic with infrastructure concerns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Business logic leaks into controllers and HTTP handlers, making it untestable and non-reusable.

## Pattern / Solution
Application Services orchestrate domain objects and infrastructure. They are transaction boundaries.

```python
class TransferMoneyService:
    def __init__(self, account_repo, event_bus, unit_of_work):
        self.account_repo = account_repo
        self.event_bus = event_bus
        self.uow = unit_of_work

    def execute(self, cmd: TransferMoneyCommand):
        with self.uow:
            source = self.account_repo.get(cmd.source_id)
            target = self.account_repo.get(cmd.target_id)
            source.debit(cmd.amount)     # domain logic
            target.credit(cmd.amount)    # domain logic
            self.account_repo.save(source)
            self.account_repo.save(target)
            # domain events published after commit
        for event in [...]:
            self.event_bus.publish(event)
```

Application services: no business rules, only orchestration. Domain objects: all business rules.

## Gotchas
- Anemic domain model: all logic in application service, domain objects are just data bags
- Application services should not call other application services directly — compose at a higher level
- Keep application services thin; if growing large, extract domain logic into domain objects

## Related
- `hexagonal-architecture.md`
- `cqrs-pattern.md`
- `domain-events.md`
