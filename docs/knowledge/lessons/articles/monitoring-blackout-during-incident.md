# monitoring-blackout-during-incident

**Issue:** The worst time to lose your monitoring is during the incident it was supposed to explain, and that is precisely when it fails most often, because the observability stack shares infrastructure, dependencies, or fate with the production system it watches. When dashboards, alerts, and logs go dark, responders are flying blind exactly when they need instrument landings, and MTTR multiplies. This is not hypothetical: Datadog's own March 8, 2023 incident took out large parts of their service, and their post-incident writeup explicitly credits basic out-of-band monitoring that runs completely outside their own infrastructure as what kept them oriented. The Pragmatic Engineer's analysis of that outage added a second lesson: status pages and customer communication degraded alongside the product, compounding the blackout into a trust failure.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **A storage event hit production and the monitoring stack at once.** Both the API tier and the metrics pipeline ran on the same cloud account and shared the same object store backend. When the store degraded, telemetry ingestion stopped minutes before the product symptoms became visible.

2. **The last graph froze, and it lied.** Dashboards rendered stale data with no prominent staleness indicator. For ten minutes the team believed traffic had simply stopped, and initial actions were aimed at "restoring traffic" rather than the actual failure.

3. **Alerts never fired.** Every symptom-based alert was evaluated by the dead pipeline. The incident was detected by a customer support tweet, not by any internal signal, adding 12 minutes to detection.

4. **Debugging was blind.** Log aggregation shared the same backend, so engineers could not query recent logs. They resorted to manually SSHing into boxes and reading local files with grep, at one-tenth the speed and none of the correlation.

5. **The status page was hosted with the product.** Updating it required the same degraded auth infrastructure, so the first public acknowledgment came 40 minutes in, from a personal account. Customers concluded the company did not know it was down.

## Why monitoring shares fate with production

1. **Same account, same quota, same blast radius.** When observability runs as workloads in the same cloud account, an account-level event, quota exhaustion, or IAM misconfiguration silences the witnesses along with the victims.

2. **Critical-path dependencies are shared.** The metrics pipeline often depends on the same load balancers, DNS zones, message buses, or databases as production. Any of those failing takes both down together, converting a partial outage into an unobservable one.

3. **Agents sample from the system they watch.** During overload, the metrics agent competes for CPU and network with the overloaded service, drops data first under backpressure, and reports the outage least reliably precisely when sampling matters most.

4. **Vendor observability fails too.** SaaS monitoring has its own outages, as Datadog's 2023 incident demonstrated from the inside. Treating the vendor's uptime as a constant leaves no plan for the day their status page is red at the same moment yours should be.

## Out-of-band design

1. **Run minimal watchdogs on separate infrastructure.** A cheap external prober on a different cloud and account, checking can-you-log-in and can-you-serve-traffic, with alerts via a different channel, is the floor. Datadog's postmortem credits exactly this kind of basic out-of-band monitoring for keeping them oriented during their worst incident.

2. **Make staleness loud.** Every dashboard must display last-ingestion age prominently, and alert when telemetry stops arriving. No data is a signal, not a reassurance; a metrics pipeline that goes quiet is itself an alert-worthy incident.

3. **Host the status page on infrastructure that cannot fail with the product.** Separate provider, separate auth, with pre-authorized operators who can post during an identity-provider outage. The status page is the one system whose availability requirement is highest during your worst day.

4. **Keep local logs readable without the aggregator.** Retain a few days of logs on the host or on independent storage, with a documented grep-based triage procedure. Slow and primitive beats nonexistent during a blackout.

5. **Rehearse blind operations.** Include a scenario in game days where the monitoring is deliberately turned off, and the team must diagnose from out-of-band checks and local logs alone. The first run always fails; that is the point of running it.

## Incident comms fallback

1. **Pre-draft the first status post.** A template acknowledging investigation, with placeholders for symptoms, turns a 40-minute silence into a 5-minute acknowledgment when the tools are degraded.

2. **Separate the comms channel from the incident.** Customer-facing updates must not depend on the same chat, auth, or CMS as internal response. A simple static page with a manual deploy path suffices.

3. **Watch the vendor's status page skeptically.** Datadog's own guidance on third-party outages notes vendor status pages lag actual detection. Correlate vendor status with your own out-of-band signals before accepting "all clear."
