# Customer Success Cross-Tenant Baseline Comparison

Telling a customer where they stand requires knowing where others stand. Cross-tenant baseline comparison pools adoption measurements across customer tenants so an individual tenant's telemetry can be read as a percentile or band rather than an uncontextualized number. The same pooling that creates context creates exposure: tenant data moves outside its original boundary, small cohorts become re-identifiable, and contracts sometimes prohibit pooling outright. This article governs how comparisons are designed, what leaves the warehouse, and which disclosure floors must hold before any peer-referenced figure is produced.

## Scope

Applies to any analysis, report, or customer-facing artifact that derives an adoption baseline, benchmark, or percentile from data belonging to more than one tenant, including health-score calibration, adoption-gap reviews, and "customers like you" statements. Covers comparison design, aggregation and suppression rules, contractual screening, and output review. Does not cover single-tenant trend analysis against its own history, financial benchmarking against external published indices, or cross-entity analytics performed under a separate data-processing agreement with distinct obligations. Where a tenant contract restricts use of its data beyond service delivery, that restriction is a hard input to this process, not a consideration to weigh.

## Workflow or implementation guidance

1. **Register the purpose before extraction.** The requesting owner states the decision the comparison informs, the tenants in scope, the metrics, and the output audience. Analyses without a registered purpose are refused at the data-access layer, which keeps exploratory curiosity from quietly becoming an exposure event.
2. **Fix the shared measurement contract.** Every pooled metric uses the authoritative telemetry source with its definition version pinned: activation, depth, and breadth carry the same meaning for every tenant in the pool, measured over a stated window. A benchmark built from differently-defined inputs is a comparison of measurement artifacts, not of tenants.
3. **Stratify before averaging.** Pool only within pre-declared strata — size band, tier, industry where available, and tenure cohort — so the comparison remains like-for-like. Strata are chosen and frozen in the registration step; discovering a convenient stratum after seeing results is post-hoc and is not permitted.
4. **Apply disclosure floors to every cell.** Any published figure rests on a minimum number of contributing tenants (the standing floor is five; owners may raise it for sensitive strata). Cells below the floor are suppressed, and neighboring cells that would allow the suppressed value to be recovered by subtraction are suppressed with them.
5. **Limit what the output can reveal.** Artifacts present a tenant's position as a band or percentile against the stratum, with the stratum size rounded, the window, and the definition versions cited. Raw peer values, peer identities, and per-tenant lists never appear in any artifact, internal or external. Underlying record-level access stays with named analysts under the registered purpose.
6. **Screen contracts and review output before release.** A contractual check confirms no in-scope tenant prohibits pooling; where one does, it is excluded and the stratum size adjusted before floors are tested. A second reviewer confirms suppression integrity and absence of identifying detail before the artifact leaves the team.

## Controls

- Minimum cohort floor with complementary suppression on every published cell, verified at review rather than asserted by the query author.
- Registered-purpose access: record-level cross-tenant joins are available only to named analysts for the registered analysis, with access expiring at its close.
- No peer identity, peer name, or tenant-count exact value below the rounding threshold appears in any artifact, internal or customer-facing.
- Contractual pooling restrictions are screened at registration, and any tenant flagged late triggers removal from the pool and a reassessment of artifacts already produced.
- Query logs on the pooled dataset are retained so differencing attempts across repeated narrow queries can be detected after the fact.

## Validation evidence

A defensible comparison cycle shows: the purpose registration with strata declared before extraction; the measurement contract with definition versions and window; the contract-screening result naming exclusions; a suppression audit confirming every published cell meets the floor and that complementary suppression closed residual channels; the query log for the pooled dataset covering the analysis period; reviewer sign-off on each released artifact; and reproduction of one published percentile from the underlying pool. The audit trail should allow an independent reader to confirm not just that the number is right, but that nothing beyond the number got out.

## Failure modes and correction

- **Small-cell disclosure** (a band quietly rests on three tenants): suppress the cell, apply complementary suppression, and re-run the review checklist to find why the floor check was skipped rather than trusting the query.
- **Differencing reconstruction** (an analyst runs several narrow slices whose union isolates one tenant): treat as an exposure event — log it, revoke the pattern, assess what was inferable, and narrow the analyst's standing access.
- **Late-discovered pooling prohibition**: pull the tenant from the pool, purge or re-issue affected artifacts without it, and record the incident for the contract-screening review; if the tenant was already identifiable in a released artifact, notify per the disclosure procedure.
- **Stratum drift** (the benchmark is recomputed on a shifting pool until the story improves): freeze strata and window at registration; changes require a new registration, and both versions are retained side by side.

## Limitations

Percentile bands are coarse instruments; they collapse distributional shape and cannot say why a tenant trails its stratum. Very small or unusual tenants may never clear the cohort floor and therefore never receive a peer comparison at all — the honest output is a self-history comparison, not a loosened floor. Stratification variables are imperfect proxies for comparability, and pooled baselines inherit the coverage gaps and definition drift of the telemetry source beneath them. None of this supports causal claims about why peers differ, and customer-facing use of peer figures remains subject to substantiation discipline on top of the exposure limits here.

## Canonical sources

- [NIST Privacy Framework](https://www.nist.gov/privacy-framework) — privacy risk management, data minimization, and limiting collection and disclosure to stated purposes.
- [RFC 6973, Privacy Considerations for Internet Protocols](https://www.rfc-editor.org/rfc/rfc6973) — privacy threat taxonomy including correlation and re-identification from combined data sources.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
