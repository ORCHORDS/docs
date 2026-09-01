# TLSRPT Aggregate Report Cadence

TLSRPT's value is cumulative. A single aggregate report tells you what one sender saw during one interval; the interesting signal - a destination quietly regressing from validated TLS to handshake failure, a certificate chain falling out of favor across many senders, a policy ID churning too aggressively - only becomes visible when reports arrive on a dependable cadence and are compared across intervals. The specification pins the reporting period to a full UTC day, with delivery deliberately jittered, but everything else about cadence - aggregation granularity, retention, baselines - is an operator's design decision. Treating reports as alerts rather than as a time series wastes them: most failure signatures that matter appear first as drift, not a spike.

## Scope

This article covers the timing and aggregation layer of TLSRPT operation: what the specification fixes about report intervals, how receiving operators should structure ingestion cadence and retention for trending, how to build baselines that surface failure trends, and how to reconcile incomplete or late reports. It does not cover TLSRPT policy record syntax, the failure taxonomy in depth, or sending-side obligations beyond the cadence-relevant ones.

## Workflow or implementation guidance

Four practices convert a report stream into a usable time series.

**Anchor to the UTC day.** The specification calls for each report to cover a full day, 00:00 to 24:00 UTC, so failures reported by different senders for the same incident window can be correlated without clock gymnastics. Design storage around (report date, policy domain, report sender) as the natural key, and flag partial-interval reports rather than silently co-mingling them with full-day ones - partial coverage is legitimate, but it must be distinguishable or your denominators will mislead you.

**Model delivery jitter.** Reports are intentionally delayed, with randomized delivery spread of up to a few hours, so report-processing systems are not synchronized into thundering herds at midnight. A report "for" a given day may arrive any time during the following day. Do not alert on non-arrival until the jitter window plus a margin has elapsed, and build completeness views on report date plus arrival time, not arrival time alone.

**Aggregate, then trend.** Two aggregation levels earn their keep. Per-day-per-sender gives attribution - which sender saw the failure and how many sessions. Per-day-all-senders gives signal - whether the failure is universal (your infrastructure) or idiosyncratic (their path). Maintain both and compute week-over-week deltas per policy domain and failure result type. The failures that trend rather than spike are the ones this layer catches: a slow rise in certificate-not-trusted counts across several senders over two weeks is a CA chain problem forming; a one-day spike from one sender is usually their side.

**Reconcile gaps.** Maintain an expected-senders register - the distinct report sources observed per policy domain over trailing windows - and track when an expected sender's report fails to arrive, including the redelivery attempts senders are expected to make over the following day. A sender that disappears from the stream entirely has stopped reporting or stopped sending; distinguishing the two requires correlating with your own traffic logs, worth building because a vanished reporter is indistinguishable from a vanished problem.

## Controls

- Schema constraint mapping one stored record set to one (report date, policy domain, sender) triple, with late arrivals merged by replacement rather than duplication.
- Completeness dashboard keyed on expected senders per domain, with jitter-aware non-arrival thresholds.
- Retention sufficient for seasonal baselines - at minimum 90 days, ideally a year of aggregates, with raw payloads retained on a shorter window and summarized after.
- Automated flagging of partial-interval reports at ingestion.
- Trend alerting on week-over-week growth per result type, in addition to absolute-threshold alerts.
- Idempotent ingestion by report identifier, with data-quality checks for duplicates and malformed intervals.
- Access controls and retention limits on the sending-IP telemetry inside reports.
- Runbook naming the escalation path per result type: certificate owner, DNS owner, policy record owner.

## Validation evidence

- A synthetic report generator submitting known-content reports on varied delay schedules, reflected correctly at expected-arrival boundaries on the completeness dashboard.
- Idempotency test: the same report submitted twice produces one stored aggregate, verified by row counts.
- A partial-interval report flagged at ingestion with its true coverage window recorded.
- A retro-injected week of synthetic rising certificate failures that trend alerting detects at the configured threshold.
- Late-arrival merge test: a full-day report arriving after a partial one replaces it without double counting.
- Retention expiry test confirming raw payloads age out on schedule while aggregates persist.

## Failure modes and correction

Two reports for the same day and sender arriving with different content is usually redelivery after a processing failure - the later one supersedes, and idempotency keys prevent double counting; if both persist, the merge logic is keyed wrongly. A completeness dashboard crying wolf every morning ignores the jitter window; widen the threshold before people learn to ignore it. Trends firing on sender churn rather than real failures mean the week-over-week computation is not normalized by session volume; normalize by success counts, not absolute failures. Baselines skewed by a sender reporting only failures indicate degenerate reports - the format permits success counts, and senders omitting them should be flagged or down-weighted. Reports continuing for a day or so after record removal are cache and cadence lag, not a problem. Aggregates drifting from raw payloads after a summarizer change point at unversioned transformations; version them so recomputation is possible. A vanished-reporter investigation that stalls is usually sender-side change - verify the record still resolves and engage the postmaster contact with the last report identifier processed.

## Limitations

The cadence is sender-controlled: nothing a receiving operator does can compel daily, full-coverage reporting, and implementations vary in interval discipline and redelivery effort. Daily granularity means sub-day incidents appear as diluted counts, not incidents; correlation with your own logs is the only finer-grained signal. Aggregation across senders mixes populations with different volumes and paths, so normalization is approximate. Privacy constraints on retaining sender-IP telemetry legitimately limit how long raw evidence stays available. Reports describe sender observations, so sender behavior changes are confounded with infrastructure changes, and no cadence discipline fully separates them. The delay recommendation is a recommendation - some senders deliver at midnight UTC regardless, and dashboards must tolerate both populations.

## Canonical sources

- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
- [RFC 8461: SMTP MTA Strict Transport Security (MTA-STS)](https://www.rfc-editor.org/rfc/rfc8461.html)
- [RFC 8460 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc8460/)
- [M3AAWG: TLS for Mail baseline recommendations](https://www.m3aawg.org/published-documents/)
- [Postfix TLS Support](https://www.postfix.org/TLS_README.html)
