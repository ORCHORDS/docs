# SLO Burn-Rate Alert Window Pairs

A single-window error-rate alert is unfixably bad at SLOs: tight windows page on noise, wide windows page too late to matter. The burn-rate method resolves the trade by pairing two windows per threshold — a short window for fast detection and a long window for confirmation — and firing only when both burn at the same rate. The SRE Workbook canonical configuration uses 14.4x over one hour plus five hours, and 6x over six hours plus three days, for a 30-day SLO with a 25 percent budget consumption per period. This article covers how those numbers arise and how to adapt the pairs to other SLOs without breaking the math.

## Scope

Covers multiwindow multi-burn-rate alerting: burn rate as a concept, the derivation of thresholds from the error budget and alerting window, the canonical window pairs and their fast/slow roles, PromQL implementation with the `for` clause, and adaptation to different SLO durations and page versus ticket severities. Excludes SLO definition and measurement design, and excludes recording-rule hygiene beyond what the alerts require.

## Workflow or implementation guidance

Derive, don't guess.

1. Compute the budget consumption rate. Burn rate is the ratio of the current error rate to the budgeted error rate. For an SLO of 99.9 percent over 30 days, the budgeted error rate is 0.001, and burn rate 1 consumes the entire budget exactly over the window. Burn rate 14.4 consumes the 30-day budget in about two hours (30 days divided by 14.4), which is why 14.4x pairs with a one-hour short window: it detects budget consumption fast enough to matter.
2. Derive thresholds from the budget fraction you are willing to spend before paging. The workbook's numbers come from choosing 2 percent of the budget for the fast page (0.02 times 720 hours equals 14.4 hours at burn 1, and burning 2 percent in one hour requires a burn rate of 14.4) and 5 percent for the slow page (5 percent of 720 hours is 36 hours; burning that in six hours is burn 6). Run this arithmetic for your own SLO duration: for a 7-day SLO the same 2 percent-in-one-hour logic yields a different divisor, and copying 14.4 from a 30-day template silently changes the semantics.
3. Build each alert as two conditions ANDed: the short window at or above the threshold and the long window at or above the same threshold. The long window prevents noise-only firing; the short window gives detection speed. The canonical pairs are 14.4x with 1h/5h windows for fast pages and 6x with 6h/3d windows for slow pages or tickets.
4. Implement in PromQL with rate over the windows and explicit clause ordering. Record the error ratio (bad events divided by total) as a recording rule so both windows reuse it, then write the alert expression as the conjunction of the two window comparisons against the burn threshold times the budgeted error rate. Set `for` to a fraction of the short window (the workbook examples use two minutes for the fast pair) to suppress single-scrape glitches.
5. Split severities deliberately. The fast pair pages; the slow pair is often a ticket, catching steady degradation that never trips the fast window. A third, lower pair (for example 1x over long windows) can drive budget reviews rather than incidents.
6. Test with synthetic series. Inject known error rates into a test metric (a constant burn at exactly 14.5x, another at exactly 14x, a burst that exceeds 14.4x for 30 minutes then stops) and assert firing behavior: the 14.5x constant fires at the expected time, the 14x constant does not, and the 30-minute burst does not survive the long-window condition. PromQL unit-test tooling makes these assertions executable.

## Controls

- Burn threshold derivation documented inline with the alert: budget fraction, SLO duration, and the arithmetic producing the number.
- Recording rules for the error ratio shared by all windows, with names encoding the SLO and window.
- `promtool test rules` fixtures covering: above-threshold sustained (fires), below-threshold sustained (does not fire), short burst above threshold (does not fire due to long window), and window-boundary behavior.
- Severity mapping reviewed per SLO: fast pair pages, slow pair tickets, budget-exhaustion alert owned by the SLO owner.
- SLO change procedure that re-derives every threshold (changing duration or target without re-deriving is the most common corruption of these alerts).
- Quarterly alert-quality review comparing firing volume with incident records to detect noisy or dead pairs.

## Validation evidence

The unit-test fixtures are the primary evidence: `promtool test rules` output showing the four canonical scenarios behaving as specified, committed with the rules. The second artifact is a live drill: artificially degrade a test service's error rate to just above the fast pair's threshold and record time-to-page, comparing it with the theoretical detection time (short window plus `for` duration); then degrade to just below and confirm silence. The third is historical: over a quarter, the ratio of fast-pair pages that corresponded to real incidents, demonstrating precision, and the absence of budget-consuming periods with no alert, demonstrating recall.

## Failure modes and correction

- Pages on every deploy blip: the short window is doing its job but the long window is too short to confirm. Lengthen the long window relative to your deploy recovery time, or gate the fast pair on an exclusion during deploys.
- Sustained slow burn never alerts: only fast pairs configured. Add the slow pair (and optionally a 1x long-horizon budget alert).
- Copied thresholds after SLO change: 14.4 imported from a 30-day template into a 7-day SLO consumes budget at the wrong rate. Re-derive from the budget fraction and fix the arithmetic comment.
- Alert never resolves: the long window keeps the condition true long after recovery. Confirm resolution requires both windows below threshold and accept the tail — or add an explicit resolution criterion.
- Recording-rule label mismatch makes the two windows compare different series: unify on shared recording rules and test the conjunction explicitly.
- Window data missing after outages: `rate` over a gap returns no data and the alert silently cannot fire. Pair burn alerts with absence-of-data alerts on the underlying metric.

## Limitations

The canonical numbers assume a 30-day SLO and specific budget fractions; other durations require re-derivation, and the resulting thresholds surprise teams that skip the arithmetic. Multiwindow alerts need the metric to have history across the longest window, so new services start unalertable for up to three days unless bootstrap windows are configured. The method addresses alerting, not SLO correctness: a mis-specified SLI produces confidently wrong burn alerts. Ticket-severity pairs depend on human follow-through that tooling cannot enforce. Window-boundary effects mean detection times are distributions, not constants, and the unit tests approximate them. Finally, the workbook itself presents the method as one proven example, not the only parameterization; treat the numbers as defaults to justify, not scripture.

## Canonical sources

- Google SRE Workbook, Alerting on SLOs (multiwindow multi-burn-rate method and canonical numbers): https://sre.google/workbook/alerting-on-slos/
- Prometheus alerting rules documentation: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Prometheus recording rules: https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/
