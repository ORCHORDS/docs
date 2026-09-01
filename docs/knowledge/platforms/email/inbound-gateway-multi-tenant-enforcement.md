# Inbound Gateway Multi-Tenant Enforcement

An inbound email gateway that accepts mail for many tenant domains is not a router with extra steps; it is a security boundary that must decide, for every message, which tenant it belongs to and whether that tenant's policy admits it. The MX record is the boundary's public face - each tenant domain points MX at the gateway - but the enforcement obligation begins well before the first RCPT TO is answered. Get tenant resolution wrong and one customer's reject policy silently governs another's mail. Get the rejection model wrong - accepting everything and bouncing later - and the gateway becomes a backscatter factory. The discipline is to enforce at the earliest point where the tenant and its policy are both known, and to reject synchronously at that point rather than generate asynchronous bounces for policy failures.

## Scope

This article covers tenant boundary enforcement on shared inbound MX infrastructure: tenant resolution from connection data through RCPT, per-tenant policy application, routing handoff to tenant backends, and the choice between synchronous rejection and asynchronous bounce. It applies to hosting platforms, alias/forwarding providers, and enterprise gateways fronting multiple subsidiary domains. It does not cover outbound sending architecture, per-tenant spam-filter tuning, provisioning systems, or ARC sealing, though each intersects with the boundary decisions here.

## Workflow or implementation guidance

Tenant resolution and enforcement proceed through six ordered checks. The ordering principle: fail as early as the information exists, and never let an unidentified tenant's mail proceed on default permissive assumptions.

1. **Classify the connection at EHLO.** The HELO/EHLO name and source address feed reputation and rate controls, but cannot yet identify the tenant - the gateway multiplexes tenants on the same listener. Apply gateway-global connection limits here, not tenant-specific ones.
2. **Resolve tenant at MAIL FROM / first RCPT.** The tenant is determined by the recipient domain: RCPT TO maps to the tenant account owning that domain. Cache the mapping. When the domain is unknown to the platform - unregistered, expired, or provisioned but still pointing at the gateway - the correct behavior at the first such RCPT is rejection, not acceptance with later bounce, because no tenant policy can be attributed.
3. **Load and apply tenant policy.** Fetch the tenant's admission policy: volume limits, per-tenant rate ceilings, size caps, allowlists and blocklists, required authentication outcomes (some tenants mandate DMARC pass), attachment rules. Every subsequent decision consults this policy; no decision may consult a default once the tenant is known.
4. **Evaluate every RCPT against the same tenant.** Multi-recipient messages crossing tenant lines - possible when one message addresses two hosted domains - must be split or rejected, not evaluated against whichever tenant resolved first. This is the classic multi-tenant boundary failure.
5. **Reject synchronously at the SMTP layer.** Policy violations - unknown recipient, over-limit, authentication failure under an enforcing tenant - produce a 5xx reply within the transaction. The sending MTA owns generating the bounce to its own sender; the gateway does not accept-then-bounce, which prevents both backscatter to forged senders and the gateway's IPs appearing as bounce originators.
6. **Route by tenant, isolated.** Accepted mail enters a per-tenant queue lane and is delivered to the tenant's backend over tenant-scoped credentials and paths. Routing metadata travels with the message internally, and cross-tenant access to queue contents is denied by construction.

The general rule for rejection versus bounce: reject in-transaction whenever the decision is knowable in-transaction; reserve asynchronous notification for post-acceptance content analysis the design genuinely requires, and then notify the envelope sender only after authenticating the original message's provenance.

## Controls

- Tenant lookup table with positive and negative caching: unknown domains fail fast at first RCPT, negative-cache TTL tuned to provisioning latency.
- Per-tenant policy schema, versioned and defaulted-closed: a policy load failure defers rather than admits.
- Transaction-scoped tenant pinning: all checks use the resolved tenant's policy; cross-tenant recipient splits are mandatory, not best-effort.
- Synchronous rejection discipline: SMTP-layer 5xx for every decision available in-transaction; no accept-then-bounce path for policy failures.
- Per-tenant rate and concurrency ceilings enforced at RCPT time, keyed on tenant identity rather than source IP alone.
- Routing isolation: per-tenant queue lanes, tenant-scoped delivery credentials, internal authorization requiring tenant context on every access.
- Audit logging of tenant resolution path, policy version applied, and rejection code per message.
- Provisioning hooks publishing domain-to-tenant mappings atomically with policy activation.

## Validation evidence

- Message-injection tests for each rejection class (unknown domain, unknown mailbox, rate limit, authentication failure) showing SMTP-layer 5xx with intended enhanced status codes, not queued bounces.
- A cross-tenant multi-RCPT test demonstrating split handling or rejection with no policy bleed from the first-resolved tenant.
- Backscatter audit: gateway-originated asynchronous bounces measured at zero across a spoofed-sender corpus.
- Tenant resolution latency and cache-hit metrics under load, showing no per-transaction backend lookup on the hot path.
- Policy version pinning: audit rows before and after a policy change showing the version identifier change.
- Isolation test: an internal access attempt against another tenant's queued message denied and logged.

## Failure modes and correction

Mail for a newly registered tenant bouncing as unknown domain means the negative cache is serving stale absence - shorten negative TTLs or invalidate on provisioning events. One tenant's enforcement applying to another's mail appears as inexplicable rejections clustered at shared sending networks; the root cause is tenant resolution running once per message instead of per recipient, and the correction is the mandatory split. Backscatter complaints with the gateway's address in bounce paths mean an accept-then-bounce path survived - usually a content filter acting post-acceptance without provenance authentication; route those decisions back into the transaction or suppress the notification. Deferred mail accumulating under policy-load failure is fail-closed working; restore the policy service and never relax the control to admit on failure. Queue cross-talk after a routing refactor - tenant-visible message misdirection, the most serious failure class - is detected via audit sampling and remediated by restoring tenant-scoped authorization on the internal API. Rate-limit evasion via distributed senders points at IP-keyed limits; re-key ceilings on tenant identity. Expired-tenant domains still resolving to the gateway generate steady rejection noise, which is correct; the cleanup is DNS decommissioning on the tenant's side.

## Limitations

The boundary is only as accurate as the domain-to-tenant mapping provisioned behind it; DNS pointing at the gateway without a tenant record forces rejection, safe but unhelpful for misconfigured customers. SMTP-layer rejection cannot express post-acceptance content decisions, so platforms performing deep content analysis must retain an asynchronous path and manage its abuse surface. Per-tenant policy richness trades against transaction latency - every RCPT-path check costs every sender. The model assumes the platform controls the MX; tenants redirecting through third parties before arrival weaken the boundary's authentication evidence. Cross-tenant messages are rare but structurally awkward, and split handling multiplies partial-failure states. Synchronous rejection shifts bounce generation to senders - correct for abuse, but tenants see rejection data only through platform logs, not their own inboxes.

## Canonical sources

- [RFC 5321: Simple Mail Transfer Protocol (rejection semantics, null reverse-path)](https://www.rfc-editor.org/rfc/rfc5321.html)
- [RFC 3464: Delivery Status Notifications](https://www.rfc-editor.org/rfc/rfc3464.html)
- [RFC 5598: Internet Mail Architecture (boundary and ADMD model)](https://www.rfc-editor.org/rfc/rfc5598.html)
- [M3AAWG best practices and published documents](https://www.m3aawg.org/published-documents/)
- [RFC 5321 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc5321/)
