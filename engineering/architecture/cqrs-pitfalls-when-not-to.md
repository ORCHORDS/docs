# cqrs-pitfalls-when-not-to

**Issue:** A team reads about CQRS and event sourcing, adopts it wholesale for a domain that is essentially CRUD (users, profiles, settings, simple catalogs), and eighteen months later is spending more time maintaining projections, chasing read-model drift, and explaining "why did the screen show stale data" than shipping product. Microsoft's own Azure Architecture Center guidance says event-sourced CQRS is not suitable for systems with straightforward CRUD operations that do not need auditability, replay, or historical state — yet the pattern keeps being applied by default. This article is the decision record for when NOT to reach for CQRS, what it actually costs, and what the fallback options are; it complements `cqrs.md` (mechanics) and `cqrs-pattern.md` (the happy-path writeup) in this knowledge base.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Failure modes nobody demos in the conference talk

1. **Read-after-write inconsistency.** The moment the write model and read model are separate stores, a user who saves a form and immediately reloads the page can see their old data, because the projection has not caught up. Teams end up bolting on workarounds — version pinning, client-side optimistic echoes of the mutation, "we saved your changes" intermediate states — none of which exist in a single-model CRUD app.
2. **Projection rebuild debt.** Every schema change to a read model means rebuilding projections by replaying the event log, which takes hours on real datasets, must be rehearsed, and must not lose events mid-replay. Teams that skip rehearsal discover mid-incident that their event log has gaps or that old event versions can no longer be deserialized.
3. **Event schema evolution.** Old events live forever, so renaming a field or changing a payload shape requires upcasting functions, versioned event types, or a painful migration of history. In CRUD, an `ALTER TABLE` plus a deploy finishes the job; in event-sourced CQRS, the same logical change touches the event store, every consumer, and every projection.
4. **Operational surface area.** You now run (at minimum) an event store, one or more read stores, projection processes, and a replay tool, each with its own monitoring, backups, and failure modes. The Stack Overflow and blog consensus (RisingStack, SystemsArchitect.io, the 2025 JavaCode Geeks retrospective) is blunt: most of this machinery buys nothing for domains without temporal queries or audit mandates.
5. **Debugging cost triples.** Answering "why is this value wrong" requires tracing a command through the event store, then the projection, then the read store, across possibly different databases. In CRUD it is one query against one table.

## When CQRS genuinely pays for itself

1. **Massive read/write asymmetry.** Tens of thousands of reads per write with genuinely different query shapes (search, aggregation, denormalized feeds) where a single relational model cannot serve both without pathological indexes.
2. **Audit and temporal requirements.** Domains that legally or contractually need "the state as it was on date X" — ledgers, betting, insurance claims, medical records — get audit, replay, and time travel essentially for free from an event log.
3. **Independent scaling of sides.** Read traffic spiking 100x during business hours while writes stay flat is the textbook case for scaling projections horizontally without touching the write path.
4. **Multiple heterogeneous read models.** When the same write stream must feed a search index, a reporting warehouse, and a cache with different shapes, projections are a real solution rather than an incidental one.
5. **Team boundary alignment.** Distinct write-side and read-side teams that need to deploy independently can be served by the model split, though this alone rarely justifies full CQRS with separate stores.

## The boring-CRUD-is-fine line

1. **Default to one model until proven otherwise.** A normalized relational schema plus indexes plus a cache in front of hot queries serves the overwhelming majority of line-of-business applications; the Reddit/Medium consensus ("most of a web developer's work is still CRUD on databases") reflects what actually ships.
2. **Ask the audit question first.** If nobody can name a concrete feature that needs event replay or point-in-time state, event sourcing is dead on arrival — that is the Azure Architecture Center's own suitability test.
3. **Try CQRS-lite before full CQRS.** Separate command and query services over the same database keeps the modeling benefits (distinct DTOs, validation, and handlers per side) with zero consistency lag and zero rebuild burden; this is what `cqrs-pattern.md` calls "simple CQRS" and it covers a surprising share of claimed use cases.
4. **Scope it per bounded context.** CQRS applied to the ledger context of an otherwise-CRUD application is reasonable; CQRS applied to the whole application because one context needed it is the classic overreach.
5. **Price the exit before entering.** Ask the sponsor: who rebuilds projections at 3am, how long is replay on production data, and what is the rollback plan for a bad event schema? No answers means no adoption.

## Damage control when already committed

1. **Freeze the blast radius.** Stop new contexts from adopting the pattern until the existing ones have tested replay tooling, a projection lag dashboard, and an on-runbook for read-model drift.
2. **Add read-your-own-writes where users feel it.** Return the mutated state from the command response and have the UI render it optimistically, keeping eventual consistency invisible for the 95% case.
3. **Invest in replay before you need it.** A projection rebuild that has never been executed on a production-size copy of the event log does not count as a capability; schedule quarterly rebuild drills.
4. **Collapse back where it never paid.** Contexts that turned out to be pure CRUD can be migrated off the event store with a one-time state snapshot into ordinary tables — the event log stays as an archive if retention requires it.
5. **Track the cost line.** Measure engineering hours per quarter spent on projections, upcasters, and consistency bugs versus feature delivery; make that number visible in the decision to expand or shrink the pattern's footprint.

## Related articles in this knowledge base

1. **`cqrs.md` and `cqrs-pattern.md`.** The mechanics and the pattern writeup this article constrains; read them second, not first.
2. **`event-sourcing-pattern.md` and `event-sourcing-strategy.md`.** Event store mechanics, upcasting, and snapshotting details for the cases that do pass the audit test.
3. **`microservices-vs-monolith.md`.** The same "distributed by default" overreach pattern at the deployment level.
4. **`consistency-patterns.md` and `at-least-once-delivery.md`.** The consistency-lag and delivery guarantees that projections inherit.
