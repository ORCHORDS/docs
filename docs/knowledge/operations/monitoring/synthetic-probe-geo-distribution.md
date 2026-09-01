# Synthetic Probe Geographic Distribution

A synthetic check answers "is the service up," but from where is as consequential as what it tests. A probe in the same region as the origin measures almost nothing a user in another continent would experience; a probe fleet that mirrors your office locations rather than your user base systematically misreports availability. Designing probe geography is an exercise in matching measurement vantage points to the population you claim to speak for, then controlling the noise that geographic distance introduces.

## Scope

Covers placement strategy for synthetic probes (managed probe fleets and self-hosted private probes alike): aligning probe distribution with user distribution, choosing check frequency and jitter to separate real latency from probe scheduling noise, interpreting per-probe variance, and alert design over geographically distributed results. Applies to uptime and multi-step HTTP/browser checks in any synthetic monitoring system, including Grafana Cloud Synthetic Monitoring's probe model. Excludes browser check scripting internals and third-party SLO accounting.

## Workflow or implementation guidance

Anchor placement to user truth, then tune the measurement.

Start with the user distribution you are defending. Traffic analytics — the geographic breakdown of real requests — is the input. If half your traffic originates in two countries, at least half your probes should sit in or near those regions. Common failure pattern: probes concentrated where the engineering team lives, because that region is cheap and familiar; dashboards then show excellent latency that no actual user enjoys. Managed probe fleets publish their locations; select the subset that matches your user map, and where no managed probe is near a major user cluster, deploy a private probe in that region instead of accepting the gap.

Next, decide what each check is for, because purpose dictates placement density. Availability checks need enough probes per region to distinguish regional outage from single-probe failure — one probe per region cannot separate "the region is down" from "the probe is flaky," so run at least two or three per major region and alert on the majority, not on any single probe. Latency characterization checks want probes at network distance classes representative of users (near, same-continent, intercontinental), since a latency average across mismatched vantage points describes no one.

Then attack the noise. Scheduled checks from fixed vantage points suffer two artifacts: probe-host contention (the probe VM is busy, inflating the measurement) and path synchronization (checks from all probes firing at the same second create self-inflicted load spikes on the target). Use jittered schedules — offset check times per probe within the interval window — so the target sees steady load and per-probe measurements do not share a synchronized failure mode. For latency checks, run each measurement multiple times or over a rolling window before comparing against thresholds; single-shot DNS+TCP+TLS+TTFB decompositions from one location are dominated by variance.

Alert design follows geography. The robust pattern is per-region thresholds on the majority of probes: alert when N of M probes in a user region fail, so a single flaky probe or a regional internet event does not page, but a real regional impairment does. Keep a separate, lower-severity signal for probe health itself (a probe that stops reporting is an infrastructure problem, not a service outage, though it silently blinds you for its region). For global availability claims, aggregate region results with the same weighting as traffic; an availability number averaged over unweighted probes misstates what users experienced.

Finally, re-derive placement periodically. User geography shifts with product growth; a probe set chosen at launch drifts out of representation. Tie the review to traffic analytics on a quarterly cadence, and treat any new significant user region without nearby probe coverage as a monitoring gap, not an optimization.

## Controls

- Probe placement map documented against the current user-traffic distribution, reviewed quarterly with a coverage-ratio per region (probes versus traffic share).
- Minimum probe redundancy per major region (at least two to three probes) so majority-based alerting is possible.
- Jitter enabled on all check schedules, with jitter window sized to the check interval (a common guideline: jitter on the order of up to ten percent of the interval).
- Alert rules defined as N-of-M per region, with N and M recorded per region and revisited when probe counts change.
- Probe health monitoring separate from service checks: silent probes alert their owners as infrastructure incidents.
- Latency thresholds derived from per-region baselines (measured percentiles), not global single thresholds.

## Validation evidence

Two artifacts establish that the geography is honest. The coverage report: user traffic share per region versus probe share per region, with the delta quantified, filed from the quarterly review. The distinguishability drill: deliberately fail one probe in a region (stop it) and confirm no service alert fires (majority logic working), then block the service for that region's user path and confirm the regional alert fires within the expected detection window. Additionally, a variance study — the same check executed repeatedly from each probe with per-probe latency distributions — demonstrates that thresholds sit outside observed noise bands, which is the statistical basis for the thresholds chosen.

## Failure modes and correction

- Single-probe regional alerting pages on probe flakiness: switch to N-of-M majority per region; investigate the probe's host contention.
- All probes report fine while users suffer: probe geography misses the affected user path (a CDN edge serving users but not probes, or a DNS resolution difference). Add a probe resolving through the user-visible resolver path and re-test.
- Latency alerts fire only from one distant probe: threshold set globally rather than per region. Re-derive per-region baselines.
- Checks synchronize and hammer the target: no jitter, aligned schedules. Enable jitter and stagger intervals across probes.
- Probe fleet silently shrinks (a private probe VM dies): probe-health alerting absent or muted. Wire silent-probe alerts to the owning team with the same severity as a monitoring outage.
- Managed probe fleet changes locations: provider relocates or retires probes, silently shifting your vantage map. Track provider probe-location announcements and re-run the coverage report after any change.

## Limitations

Probe geography approximates user experience but never reproduces it exactly: real users ride different ISPs, devices, and client-side delays that probes cannot model. Managed probe fleets publish locations but not always their network positioning, and their locations change without versioned notice. Private probes measure from your infrastructure, which shares fate with your network and can mask origin-side issues. Jitter and majority logic reduce noise but add detection latency proportional to the interval. Cross-border routing and CDN geolocation make "region" a fuzzy concept — the probe's country is not always the network path users take. No probe scheme replaces real-user monitoring; synthetic and RUM answer different questions.

## Canonical sources

- Grafana Cloud Synthetic Monitoring probe documentation: https://grafana.com/docs/grafana-cloud/synthetic-monitoring/probes/
- Grafana Cloud Synthetic Monitoring checks: https://grafana.com/docs/grafana-cloud/synthetic-monitoring/checks/
- Prometheus Alertmanager configuration (N-of-M style grouping semantics for regional alerts): https://prometheus.io/docs/alerting/latest/configuration/
