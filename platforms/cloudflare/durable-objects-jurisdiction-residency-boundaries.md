# Durable Objects Jurisdiction and Residency Boundaries

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Documented

## Problem

A Durable Object jurisdiction constrains where that object runs and persists data. It does not automatically constrain where requests are processed, where identifiers are logged, or where related systems store data. Treating it as a complete residency guarantee creates false compliance claims.

## Current contract

Cloudflare documents `eu`, `us`, and `fedramp` jurisdictions. Create IDs and stubs from a jurisdiction-scoped subnamespace. The same name in the default namespace and a jurisdiction-scoped namespace produces different IDs.

Inside the object, `ctx.id.jurisdiction` exposes the jurisdiction. It is preserved through ID string round trips. It can be undefined for unrestricted objects and for older alarms that predate documented jurisdiction persistence unless those alarms are rescheduled.

## Controls

- Select jurisdiction from an authoritative tenant/data policy, never from an untrusted request header.
- Include jurisdiction in the application's durable routing key and audit evidence.
- Construct every ID through the required scoped namespace.
- Reject a mismatch between tenant policy, requested jurisdiction, and `ctx.id.jurisdiction`.
- Test alarms, migrations, backups, analytics, and external dependencies separately.
- Combine with Regional Services when request-processing geography is also required.
- Do not place personal or secret data in Durable Object IDs; Cloudflare documents that IDs can be logged outside the jurisdiction.
- Treat location hints as best-effort latency hints, not residency controls.

## Verification

1. Create objects with the same logical name in default, EU, US, and applicable FedRAMP namespaces.
2. Assert their IDs differ and each object reports the intended jurisdiction.
3. Attempt cross-jurisdiction namespace/ID combinations and confirm failure.
4. Exercise ID serialization and alarm handlers.
5. Verify routing cannot silently fall back to an unrestricted namespace.
6. Inventory where logs, request handling, storage dependencies, and support access occur.
7. Test termination and re-creation without changing the tenant's jurisdiction mapping.

## Gotchas

- Workers can access jurisdiction-constrained objects from anywhere.
- Jurisdiction and location hint solve different problems.
- Dynamic relocation of an existing object is not implied.
- Regulatory applicability still requires legal and architectural analysis beyond a platform setting.

## Official sources

- [Durable Objects data location](https://developers.cloudflare.com/durable-objects/reference/data-location/)
- [Durable Object ID API](https://developers.cloudflare.com/durable-objects/api/id/)
- [Durable Object namespace API](https://developers.cloudflare.com/durable-objects/api/namespace/)
- [New US jurisdiction changelog](https://developers.cloudflare.com/changelog/post/2026-06-26-durable-objects-us-jurisdiction/)
