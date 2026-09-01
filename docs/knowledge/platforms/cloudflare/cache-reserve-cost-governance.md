# Cache Reserve Cost Governance

Cache Reserve is a persistent, R2-backed tier sitting behind Cloudflare's cache. When an object misses the in-memory and edge caches, Cache Reserve can fetch and hold it durably, so the next miss anywhere is served from storage rather than from the origin. That is an origin-offload purchase: you pay storage and operation charges for Reserve so you do not pay origin egress and origin load for the same objects over and over. Whether it saves money is a function of repeat-miss behavior, object size, and what the origin charges per retrieval. Governance means doing that arithmetic per zone before enabling, and re-checking it when traffic or content changes — because a zone of one-hit-wonder objects turns Reserve into pure added cost.

## Scope

Covers the economic governance of Cache Reserve: when enabling it reduces total cost, how to estimate origin-offload savings against Reserve charges, and the monitoring that decides whether it stays enabled. Applies to zones with meaningful cache miss volume against a billed or capacity-constrained origin. Excludes Cache Rules and Tiered Cache configuration as such (though they interact with offload), Workers Cache API governance, and R2-as-origin designs where the origin itself is already Cloudflare-billed.

## Workflow or implementation guidance

1. Gather the zone's cache profile from analytics: total requests, cache hit ratio, and miss volume in bytes over a representative period that includes normal peaks.
2. Estimate the miss-again population: of the bytes served on miss, what fraction is requested again after eviction or before expiry? Only repeat-requested objects generate Reserve savings; single-request objects generate only Reserve cost. Extract repeat-request rates from access logs by object key frequency.
3. Quantify origin cost per retrieved byte: egress charges, per-request costs, or an internal cost per origin retrieval. If the origin is capacity-constrained rather than billed, express the value as peak-shaving in requests per second.
4. Estimate Reserve charges for the same period: storage for retained objects plus read and write operation counts implied by the miss-again population and object sizes.
5. Build the comparison: savings (repeat misses served from Reserve times origin cost per byte) versus costs (storage plus operations for the retained set). State the break-even repeat-miss ratio explicitly, so the decision is a threshold, not a vibe.
6. If the zone also uses Tiered Cache, model the interaction: upper-tier hits reduce the misses that reach Reserve, which lowers both Reserve cost and Reserve benefit.
7. Enable Reserve on the zone, run for a full billing cycle, then reconcile actual charges and observed origin offload against the model.
8. Re-run the model quarterly and on material changes (new content type, traffic growth, origin renegotiation), and disable Reserve on zones where measured savings do not cover measured cost.

## Controls

- Pre-enable arithmetic gate: no zone enables Cache Reserve without the recorded break-even model and the measured repeat-miss ratio.
- Reconciliation-per-cycle rule: each billing cycle, actual Reserve charges and origin offload are compared to the model; variance beyond a set band triggers review.
- Disable criterion: zones where measured Reserve cost exceeds measured origin savings for two consecutive cycles are disabled, with the model archived.
- Object-size sensitivity note: zones dominated by very large, rarely repeated objects carry a recorded caution since storage dominates their economics.
- Interaction review with Cache Rules and Tiered Cache: offload-affecting configuration changes re-open the Reserve model.
- Quarterly model refresh with current pricing, traffic mix, and origin cost basis.

## Validation evidence

- Zone cache analytics export (requests, hit ratio, miss bytes) for the representative period used in the model.
- Repeat-miss analysis from access logs: object key frequency distribution and the derived fraction of miss bytes requested again.
- The break-even model sheet: origin cost basis, Reserve storage and operation estimates, and the computed threshold.
- Post-enable billing reconciliation: actual Reserve line items and measured origin offload versus prediction, cycle by cycle.
- Tiered Cache interaction note where applicable, with upper-tier hit rates considered.
- Disable/keep decision records per zone with the supporting measured numbers.

## Failure modes and correction

- Reserve charges exceed savings on a zone of unique objects: the repeat-miss ratio was overestimated or the content is one-hit by nature; disable Reserve for that zone and record the correction.
- Model predicted offload that never materialized: Cache Rules, short TTLs, or Tiered Cache changes altered miss flow; re-baseline and rebuild the model from current behavior before deciding.
- Origin costs dropped after renegotiation, inverting the economics: the quarterly refresh catches it; disable where the new basis shows no net saving.
- Very large objects inflate storage cost while rarely re-requested: exclude them from Reserve where configuration allows, or accept a documented exception with monitoring.
- Traffic mix shifted (more small dynamic misses, fewer repeatable static objects): re-derive the repeat-miss fraction; thresholds move with mix, not just volume.
- Zones enabled "for consistency" without the model: blocked by the pre-enable gate; run the arithmetic or leave the zone off.

## Limitations

- Savings depend on origin charging structure; internal origins with zero marginal cost show no direct financial saving, only capacity relief.
- Repeat-miss estimation from logs is approximate and depends on log completeness and sampling.
- Reserve pricing dimensions and included allowances follow current product documentation and change over time; models carry an as-of date.
- Interactions with Tiered Cache and Cache Rules make isolated attribution of Reserve benefit imperfect.
- Storage growth from long-tail retained objects accrues gradually and can lag the billing cycle in which the enabling decision was validated.

## Canonical sources

- Cloudflare Cache docs, "Cache Reserve": https://developers.cloudflare.com/cache/about/cache-reserve/
- Cloudflare Cache docs, "Concepts": https://developers.cloudflare.com/cache/about/
