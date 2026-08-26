# sli-selection-user-journeys

**Issue:** Teams adopting SLOs routinely pick SLIs from whatever metrics already exist — CPU, request counts, 500s on one internal hop — and end up with objectives that stay green while users are angry, or burn budgets on signals no user can perceive. The definitions of SLI, SLO, and error budget are easy; the craft is selecting indicators that actually track user happiness. This article covers a repeatable selection method: enumerate critical user journeys, define good events as ratios, measure from the user's vantage point, keep the set small, and validate against reality.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Start from critical user journeys

1. **List the journeys, not the systems.** A journey is a complete path a user takes that delivers value — "customer signs up and receives a verification email", "developer deploys a function and sees it serve traffic". Systems exist to serve journeys; instrumenting systems first is how you get green dashboards during outages.
2. **Rank journeys by business impact.** Google's practical SLO guidance is to enumerate critical user journeys and order them by revenue, user count, and reputational damage; the top of that list defines where SLIs are mandatory, and the long tail defines where they are optional.
3. **Define what "good" means per journey.** For each journey, ask the user-experience questions: did it complete, was it fast enough, was the answer correct, was it complete? Each dimension that a user can perceive failing is a candidate indicator; anything invisible to users is an internal cause, not a candidate.
4. **Limit to a handful of SLI types.** The SRE Workbook recommends five or fewer SLI types representing the most critical functionality, and the Art of SLOs workshop suggests roughly 3-5 indicators per journey — beyond that, the signal-to-noise ratio collapses and error budgets multiply into unmanageable policy.

## Construct indicators as good-event ratios

1. **Express every SLI as good events divided by valid events.** "Fraction of requests served under 300ms" and "fraction of checkouts that reached the confirmation state" are ratios; ratios are window-stable, threshold-explicit, and drop directly into error-budget arithmetic, unlike raw counts or averages.
2. **State the threshold inside the indicator.** "Latency is fine" is not an SLI; "p-fraction of requests complete in under 400ms" is. The threshold is the product decision, and hiding it inside a dashboard default makes it invisible to the people who own it.
3. **Include correctness and completeness, not just speed.** Availability and latency are the easy two dimensions; for data systems, freshness ("results no older than X") and correctness ("order total matches the sum of line items") are often the dimensions users actually care about.
4. **Decide how partial failures count.** A journey that completes after one retry is not the same as a clean success; defining whether retried, degraded, or fallback-path completions count as good is part of the indicator, and ambiguity here shows up later as unexplainable budget burn.

## Measure from the user's vantage point

1. **Prefer the client side or the closest proxy to the user.** Server-side metrics at the innermost hop miss CDN faults, regional degradation, and client rendering problems; RUM or edge-observed measurements align with what users experience.
2. **When you must measure server-side, measure the whole journey, not one hop.** Instrument at the gateway or edge where the full request path is behind you; a 99.9% SLI on the auth service can coexist with 95% journey success if every journey crosses five such services.
3. **Watch for observer bias in synthetic-only setups.** Synthetics measure from your chosen locations with your chosen payloads; they catch availability loss but underrepresent long-tail user conditions, so pair them with RUM-derived ratios where possible.

## Keep the set small and the owners named

1. **Three to five indicators per journey, three-ish journeys per service tier.** Beyond that, error budgets fragment into noise and nobody can say which budget governs the roadmap freeze; if everything is an SLO, nothing is.
2. **Name an owner per indicator.** Every SLI needs a person accountable for its health and its threshold; ownerless SLIs rot into dashboard wallpaper.
3. **Record the selection rationale.** A one-paragraph note per indicator — journey, dimension, vantage point, threshold reasoning — turns the selection into a reviewable artifact instead of folklore that gets re-litigated every quarter.

## Validate against reality

1. **Backtest against past incidents.** Replay the last six months of incidents and ask whether each candidate SLI would have burned budget; an indicator that stayed flat through a user-visible outage is measuring the wrong thing, and one that burns through invisible incidents will train people to ignore it.
2. **Compare with support and revenue signals.** Correlate SLI dips with ticket volume and conversion data; the entire point of the exercise is that these move together.
3. **Instrument before committing targets.** Collect the ratio for a few weeks before setting the SLO target; targets set on day one are guesses that either never burn (too lax) or burn constantly (too strict), and both outcomes discredit the program.
4. **Revisit thresholds as the product changes.** New client types, new regions, and new features shift what good means; schedule indicator review with roadmap planning so the SLI set tracks the product rather than the product's history.
