# n-plus-one-queries-compound-at-scale

**Issue:** N+1 query patterns that are invisible in development destroy database performance at scale
**Date:** 2026-08-11
**Status:** documented

## What happened
A product listing page worked fine in development with 50 products. In production with 4,000 products, it issued 4,001 queries per page load. Each product triggered a separate query for its category. The database CPU hit 100% during a marketing campaign, taking the site down for two hours.

## The lesson
Any loop that issues a database query per iteration is an N+1 problem. Use eager loading (JOIN or batch fetch) to load all related data in a fixed number of queries. Detect N+1 queries in development using query counting middleware or ORM debug logging before they reach production.

## Why it matters
In development, N+1 looks like 6 queries taking 30 ms. In production with real data, it is 6,000 queries taking 30 seconds, hammering the database until it falls over. The problem is invisible until it is catastrophic.

## How to apply
- [ ] Enable ORM query logging in development and review query count on every new endpoint.
- [ ] Use a query-count assertion in integration tests: any endpoint that executes more than N queries (N=10 as a starting bound) fails CI.
- [ ] Prefer eager loading (`include`, `preload`, `joinedload`) over lazy loading for list views.
- [ ] For custom queries, use `IN` clauses to batch fetch related records.
- [ ] Use a profiling tool (e.g., Bullet gem for Rails, SQLAlchemy query events) that surfaces N+1 automatically.

## Related
- `index-before-not-after-performance-problem.md`
- `cache-invalidation-is-harder-than-caching.md`
