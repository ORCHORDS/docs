# Prometheus Scrape ODR Reduction

On-demand read (ODR) pressure is what a scrape creates: every interval, Prometheus opens a connection, the target materializes its full metric set, and the target pays CPU to serve it. At small scale this is noise; at thousands of targets with heavyweight exposition endpoints, scrape traffic becomes a visible tax on the production path — memory allocations, lock contention, GC pauses on the scraped process itself. Reducing ODR pressure means trading freshness, fan-out architecture, or storage granularity, and this article sets out those trades explicitly.

## Scope

Covers techniques for reducing the read pressure Prometheus scraping imposes on targets: interval and timeout math, scrape body size limits and metric filtering at the target, scrape configuration consolidation, staleness semantics under longer intervals, and alternatives that push data instead of pulling it. Focused on the scraped side's cost, not on Prometheus's own ingestion cost. Assumes standard pull-mode Prometheus; push-gateway and OTLP-push patterns appear only as alternatives.

## Workflow or implementation guidance

Reduce pressure in order of leverage.

The highest-leverage lever is not the interval — it is cutting what the target must produce per scrape. Many exposition endpoints render thousands of series that nobody queries: runtime internals, per-connection counters, debug gauges. Enable server-side filtering where the client library or exporter supports it (allow-lists of metric families), or apply Prometheus-side metric relabelling to drop series after scrape — recognizing that relabelling drops storage cost, not target-side render cost. Target-side filtering is the only lever that reduces the ODR work itself.

The second lever is the interval. Doubling the scrape interval halves scrape frequency and halves per-target ODR work, at the cost of resolution: alert detection latency grows by up to one interval, and rate calculations span wider windows, which smooths spikes. Set intervals per job rather than globally: user-facing latency metrics may warrant 15 seconds, while batch-job or capacity metrics tolerate 60 or 300 seconds. A common three-tier scheme (15s / 60s / 300s) maps naturally to alerting needs versus trend needs.

Third, apply the timeout rule: `scrape_timeout` must be strictly less than `scrape_interval`, or overlapping scrapes pile up. For slow, heavy targets, a long timeout with a long interval is kinder than a short timeout that fails and retries immediately. Track `up == 0` causes to distinguish timeout failures from target crashes — frequent timeouts mean the target cannot keep up with the read pressure and the interval should grow.

Fourth, consider scrape consolidation for chatty low-value targets: a lightweight exporter or textfile collector that aggregates several sources into one endpoint reduces connection and exposition overhead per host.

Fifth, evaluate pull-to-push alternatives for targets where even an infrequent pull hurts: OTLP push from an SDK into a Collector removes the per-scrape render entirely, moving cost to the application's own export schedule with batching. This changes the staleness model (pushed series go stale if the pusher dies, just as pulled series do, but detection depends on export interval rather than scrape interval) and belongs in an architectural review, not a config tweak.

Throughout, quantify before changing: measure target-side allocations and latency of the metrics endpoint under scrape load, and re-measure after. A metrics endpoint that takes tens of milliseconds and allocates heavily per scrape is a real ODR problem; one that takes a millisecond is not worth optimizing.

## Controls

- Per-job scrape interval policy documented in a table (job class to interval to rationale), reviewed when new jobs are added.
- `scrape_timeout` configured strictly below `scrape_interval` per job, with a CI check over the configuration file enforcing the inequality.
- Target-side metric allow-lists (or exporter filter flags) declared alongside deployment configuration, so filtering survives redeployments.
- Scrape body size limit (`body_size_limit`) set per job to bound worst-case exposition memory on the Prometheus side.
- Alert on scrape duration approaching the timeout, as an early warning that the target cannot sustain the interval.
- Quarterly ODR review: total scrapes per second fleet-wide, top ten targets by scrape duration, and a disposition (filter, slow down, or leave) for each.

## Validation evidence

Evidence for an ODR reduction is a paired measurement: target-side cost of serving the metrics endpoint (CPU time and allocated bytes per scrape, from a profiling or runtime metric captured before and after the change) and Prometheus-side freshness (scrape duration and `up` stability). A second artifact is the alert-latency delta: for each alert fed by the slowed job, the measured detection delay under a fault-injection drill before and after, showing the increase stays within the alert's declared tolerance. File both alongside the interval change record.

## Failure modes and correction

- Alerts fire late after interval extension: detection latency grew past the page-worthy threshold. Either restore the faster interval for the alerting job only, or split the metric into a fast-scraped minimal endpoint and a slow full endpoint.
- Missed brief spikes: rate windows spanning wider intervals smooth transients. Where spike visibility matters, record the relevant fast counter on a fast interval even in an otherwise slow job.
- Timeout misconfiguration after interval change: `scrape_timeout` left equal to or above the new interval, causing overlapping scrapes and target thrash. The CI inequality check catches this; fix by scaling both together.
- Series gaps misread as outages: longer intervals interact with staleness markers so a single failed scrape leaves a longer hole. Adjust `up`-based alert `for` clauses to require multiple failures proportional to the interval.
- Filtering removes a series an alert silently depends on: relabel or allow-list changes orphan alerts. Run `promtool check rules` plus a test fixture suite as part of every filter change.

## Limitations

ODR cost is target-specific: the same interval change that saves one service nothing can rescue another, so measurements must be per-target. Prometheus staleness and lookback semantics bound how far intervals can stretch before queries return gaps (five minutes of lookback against a five-minute interval leaves no slack). Push-based alternatives restructure the deployment and interact differently with entity monitoring of `up`. Body size limits protect the scraper but can truncate exposition, trading ODR relief for silent data loss if set below real payload sizes. Finally, interval math only reduces linear load; targets whose endpoint render is inherently expensive need target-side fixes, not scheduling ones.

## Canonical sources

- Prometheus configuration reference (scrape configs, intervals, timeouts, body_size_limit): https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- Prometheus remote write tuning practices (exposition cost context and alternatives): https://prometheus.io/docs/practices/remote_write/
