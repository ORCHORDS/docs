# n-plus-one-query-detection

**Issue:** Detecting and fixing N+1 query patterns in ORM code
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Loading a list of 100 orders and then fetching each order''s customer separately results in 101 queries instead of 2.

## Pattern / Solution
```typescript
// Bad: N+1 in Prisma
const orders = await prisma.order.findMany();
for (const order of orders) {
  const customer = await prisma.customer.findUnique({ where: { id: order.customerId } });
}

// Good: eager load with include
const orders = await prisma.order.findMany({
  include: { customer: true }
});

// Good: use SELECT with JOIN in raw SQL
SELECT o.id, c.email FROM orders o JOIN customers c ON c.id = o.customer_id;
```

## Gotchas
- ORMs can hide N+1 — enable query logging in development to count queries
- `include` can itself become a problem with deeply nested relations; use `select` to limit fields
- DataLoader pattern (batching) solves N+1 in GraphQL resolvers

## Related
- `join-strategies.md`
- `cte-common-table-expressions.md`
