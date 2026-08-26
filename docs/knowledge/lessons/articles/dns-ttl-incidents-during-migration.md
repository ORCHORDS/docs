# dns-ttl-incidents-during-migration

**Issue:** DNS migrations fail because teams treat TTL (time-to-live) as a propagation-speed knob instead of a caching contract. The classic incident: a cutover is planned, the record is flipped, and a large fraction of traffic keeps hitting the old destination for hours because resolvers worldwide hold the old answer for the *old* TTL — which was set to 24 or 48 hours years ago and never revisited. The equal-and-opposite incident: someone "prepares" for a migration by setting TTL to 60 seconds, but does it at the same moment as the change (too late — resolvers already cached the old value), or leaves the low TTL in place permanently, adding resolver load and fragility for no benefit. A third variant bites during DNS *provider* migrations, where stale cached NS records keep answering from the dead zone. 2025-era discussion (including the "stop using low DNS TTLs" thread) crystallized the misunderstanding: a low TTL on a *new* record does not speed anything up — a resolver either has the record cached or it doesn't — and the "24–48 hour propagation" number is folklore covering a few badly behaved resolvers.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The mental model teams get wrong

1. **TTL is a promise you make to resolvers, not a switch you flip.** When a resolver caches your A/CNAME record, the copy it holds expires after the TTL *that was in effect at cache time*. Lowering TTL now does not affect copies already cached — which is why the reduction must happen one full old-TTL before the cutover, not during it.
2. **Low TTL on a new record is worthless.** There is nothing cached for a name nobody has resolved before, so a 60-second TTL speeds up nothing; and for a *changed* record, only the previously cached value matters. Teams burn permanent resolver-load increases for zero migration benefit this way.
3. **"Propagation" is a misleading frame.** Records do not propagate outward; caches simply expire. Most traffic follows a change within the old TTL; a long tail of misbehaving resolvers ignores TTL entirely (clamping it up or holding records indefinitely), which is where real multi-hour tails come from — and no TTL setting fixes those.
4. **Negative answers are cached too.** NXDOMAIN and SERVFAIL responses carry their own TTL (negative caching). A migration that briefly points at a missing record can poison resolvers with cached failures that outlive the fix.

## The migration procedure that works

1. **Lower TTL early: one full old-TTL (ideally 24–48h) before the change.** Example: with a live 86400-second TTL, drop to 300 seconds, then wait at least 24 hours before cutting over. This guarantees essentially all cached copies carry the 300-second expiry.
2. **Cut over, then *verify from the outside*.** After the change, check resolution from multiple vantage points (public resolvers, `dig` against 8.8.8.8/1.1.1.1, a few regional VMs) rather than trusting the authoritative server's answer — your authoritative answer was always correct; the question is what caches hold.
3. **Keep the old destination warm through the tail.** Because a residual of TTL-ignoring resolvers will keep sending traffic to the old IP for hours or days, plan for old-destination overlap (serving or redirecting) rather than decommissioning it the moment the migration "completes."
4. **Raise the TTL back afterward.** A migration-tactical 300-second TTL left behind forever means every resolver re-queries you constantly — more load on your DNS, more coupling to your provider's availability, and a settings surface that drifts. The cleanup step belongs in the runbook, with a checklist line and an owner.
5. **For provider migrations, mind the NS records — they are the real trap.** Moving a zone to a new DNS provider means the parent's NS delegation changes, and NS TTLs at registries are commonly 48 hours. Stale cached NS records keep resolving against the old provider; the standard play is to run both providers in parallel (same zone content) for the full NS TTL window before anything gets shut off at the old one.

## Incident dynamics when it goes wrong

1. **The rollback that can't roll back.** High-TTL records mean an emergency revert also takes the full TTL to reach users — the outage window doubles. Teams that discovered this mid-incident learned that TTL decisions made in calm times determine recovery speed in bad times (low TTL's genuine value is fast *failback*, not fast rollout).
2. **DNS steering during attacks backfires at low TTL.** The 2016 Dyn DDoS context: providers use low TTLs for geographic steering, which concentrates enormous query volume on the provider — exactly the component under attack. Your low TTL increases your dependence on your DNS provider's continued health; treat TTL as a resilience tradeoff, not just a speed one.
3. **Traffic splits confuse debugging.** During the TTL window, some users hit old, some hit new. Symptoms appear "intermittent" and region-random, sending responders hunting for load balancer or network causes while the real answer is split-brain DNS. The first diagnostic of any post-migration "intermittent" issue is: which version is the affected user actually reaching?
4. **Application-level caches outlive DNS TTLs.** Long-lived connection pools, app-level IP caches, and SDKs that resolve once at startup ignore DNS changes regardless of TTL. If your failover plan is "flip DNS," your clients must also re-resolve on connection failure, or the plan doesn't work for the clients that need it most.

## Guardrails to install

1. **Track TTLs as configuration with policy.** Alert on records whose TTL deviates from policy (e.g., anything below 300s or above 86400s outside an approved change window). TTL drift is config drift, and it compounds silently because nobody looks at TTLs until a migration.
2. **Script the lower-wait-cut-verify-raise sequence.** The procedure is mechanical; making it a script (or runbook with explicit timings and verification commands) prevents the two human errors: cutting before the old TTL expires, and forgetting to restore the TTL.
3. **Rehearse on a low-stakes record first.** A dry run on a staging hostname surfaces resolver behaviour, tooling gaps, and the real length of the tail before the production hostname is on the line.
4. **Pair DNS changes with origin-side overlap.** The durable lesson from every TTL incident: DNS is not atomic and never will be. Design migrations so both sides serve correctly during the overlap window, and TTL behaviour becomes a latency detail instead of the outage.
