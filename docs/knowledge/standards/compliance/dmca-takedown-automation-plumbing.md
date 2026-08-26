# dmca-takedown-automation-plumbing

**Issue:** example project (PR #<number>) implemented the full DMCA takedown pipeline: intake of takedown requests, flagging the content, removing it from the public projection, purging CDN caches (a stale edge cache would keep serving the removed content publicly), incrementing a repeat-infringer counter per uploader, and exposing agent-visible status for every request. The engineering lesson is that "remove the content" is not one write — it is a projection write plus cache invalidation plus bookkeeping, and skipping any stage either re-serves infringing content or forfeits 17 U.S.C. § 512 safe harbor.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## What the law actually requires

1. **Expeditious removal (§ 512(c)(1)(C)).** On receiving a [compliant notification](https://www.law.cornell.edu/uscode/text/17/512) (§ 512(c)(3) elements: signature, identification of the work, contact info, good-faith and accuracy statements), the provider must "respond expeditiously to remove, or disable access to, the material" to keep safe harbor. The statute never defines "expeditious" — the [U.S. Copyright Office § 512 resources](https://www.copyright.gov/512/) frame it as prompt action on compliant notices, which is exactly what an automated pipeline demonstrates.
2. **A registered designated agent (§ 512(c)(2)).** Safe harbor requires designating an agent with the Copyright Office, keeping the DMCA.com-style agent info current, and publishing it — otherwise there is no valid "intake" endpoint and every downstream stage is moot.
3. **Repeat-infringer policy, reasonably implemented (§ 512(i)(1)(A)).** The provider must "reasonably implement" a policy terminating repeat infringers. The 2020 Copyright Office § 512 report (via [Venable's summary](https://www.venable.com/insights/publications/2020/07/dmca-512-report-key-findings)) confirmed a policy can even be unwritten if actually implemented, and *Perfect 10 v. CCBill* (per [Finnegan's roundup](https://www.finnegan.com/en/insights/articles/recent-safe-harbor-rulings-in-the-united-states.html)) treats a working notification system plus a termination procedure as implementation. A per-uploader strike counter in the database is the evidence of implementation.
4. **Counter-notification path (§ 512(g)).** A valid counter-notice (signature, identification of removed material, penalty-of-perjury good-faith statement, consent to jurisdiction) obliges the provider to restore access after no fewer than 10 and no more than 14 business days unless the complainant files a court action. The pipeline needs a `counter_noticed` state with a restore-by date, not just removal states.

## Pipeline stages (as implemented)

1. **Intake and validation.** Each takedown request is a database record capturing the notice contents, the complainant, the targeted content IDs, and receipt timestamp. Validate against § 512(c)(3) elements at intake — acting on a facially invalid notice is voluntary, not required, so validation determines the compliance clock.
2. **Flag before remove.** Content moves to a `flagged`/`under_review` state first (agent-visible), then to removed status. The status field is the single source of truth for every downstream consumer — the public projection, the CDN purge job, and the repeat-infringer counter all read it.
3. **Remove from the public projection only.** The content row is not deleted; it is excluded from every public read path (feed, detail endpoint, embeds) by the status filter. Deletion would destroy the evidence trail needed for counter-notices, repeat-infringer accounting, and legal hold.
4. **Purge CDN caches as part of removal.** A cached copy served from the edge is still public "access" to the material — from a safe-harbor standpoint, "disable access" is not done while a stale cache keeps serving it. Cache purge is therefore a hard dependency of the removal transaction, not a cleanup step: emit the purge (by URL / cache tag / everything-that-touches-the-row) in the same job that flips status.
5. **Increment the repeat-infringer counter.** Each upheld takedown increments a per-uploader strike count; reaching the policy threshold triggers the termination workflow (account ban). Because § 512(i) asks whether the policy is *reasonably implemented*, the counter and its threshold must be enforced, not just configured.
6. **Agent-visible status end-to-end.** Support agents see request state (`received` → `flagged` → `removed` / `rejected` → `counter_noticed` → `restored`), so "when did we act on this notice" is answerable in seconds — which is what "expeditious" looks like when a plaintiff asks.

## Cache purging — the stage everyone forgets

1. **Stale cache silently re-serves removed content.** If the CDN TTL for content pages is hours, a takedown executed only against the origin leaves the infringing copy publicly reachable until TTL expiry. That gap is the delta between "we removed it" and "access is disabled."
2. **Purge by exact public URL set.** Compute every public URL that can render the content (page URL, API projection URL, thumbnail/media asset URLs) and purge all of them in the same operation; a purge that misses the asset URL leaves the file itself fetchable.
3. **Purge is asynchronous — verify it.** CDN purge APIs return before propagation completes, so the pipeline should re-fetch the public URLs (or check cache status) and only mark the request fully `removed` when the edge actually stops serving the content. On Cloudflare, the [cache purge API](https://developers.cloudflare.com/cache/how-to/purge-cache/) supports purge-by-URL, by tag, and purge-everything.

## Automation and evidence

1. **Automated intake is now the norm.** The 2020 Copyright Office report documented that automated/bot-generated notices dominate the ecosystem ([report background](https://www.federalregister.gov/documents/2015/12/31/2015-32973/section-512-study-notice-and-request-for-public-comment)); a platform without structured intake will drown in email-pasted notices with no audit trail.
2. **Timestamps are the safe-harbor defense.** Store receipt time, validation time, removal time, and purge-verified time per request. If "expeditious" is ever litigated, these timestamps are the entire argument — see the [CRS safe-harbor overview](https://www.everycrsreport.com/reports/R43436.html) for how the requirement is framed.
3. **Counter-notice restore must also purge/invalidate caches.** Restoration after the 10–14 business day window has the mirror-image cache problem: caches keyed on the removed state must be invalidated so restored content actually reappears, and any "this content was removed" interstitials are cleared.
4. **Distinct from GDPR erasure.** DMCA removal is a status/projection change with retention; [GDPR Art. 17 erasure](gdpr-article-17-erasure.md) is data destruction. Keep them separate code paths — conflating them either destroys DMCA evidence or under-delivers GDPR rights.
