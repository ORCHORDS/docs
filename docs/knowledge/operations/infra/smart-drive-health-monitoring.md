# smart-drive-health-monitoring

**Issue:** Drives fail, and they fail in two annoyingly different ways: suddenly (a dead controller, a flaky port) and gradually (growing reallocated sectors, SSD wear-out, NVMe media errors). SMART telemetry exists to give weeks of warning for the gradual class, but most deployments either ignore it entirely, alert only on the drive's own PASS/FAIL flag (which fires long after the useful warning window), or collect attributes without trending them. Research is unambiguous: the raw vendor "overall health" verdict misses a large fraction of impending failures, while 2025 work on machine-learning anomaly detection over SMART time series shows materially better prediction — but the practical, accessible win for most teams is continuous collection of the right attributes with threshold and trend alerting. This article covers what to collect on HDD, SATA SSD, and NVMe, how to run smartd, what actually predicts failure, and how to wire it into monitoring.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What SMART data is and is not

1. **Attributes, not verdicts.** A drive exposes numbered attributes (raw and normalized values) plus, on NVMe, a standardized health log (percentage used, media errors, unsafe shutdowns). The one-bit health summary is computed by vendor firmware from conservative internal thresholds; relying on it alone means learning about problems only when the drive already considers itself failing.
2. **The prediction ceiling is real.** The USENIX FAST '20 study "Making Disk Failure Predictions SMARTer" demonstrated that some failed drives show no anomalous SMART values at all — silent failures exist, so SMART monitoring reduces, but cannot eliminate, surprise disk death. It must be paired with redundancy (RAID/ZFS/replication), not treated as a substitute.
3. **ML over time series beats static thresholds.** 2025 research (MDPI, ACM) on SSD failure prediction using anomaly detection over SMART streams outperforms vendor thresholds, especially for SSD-specific failure modes like wear-leveling degradation; the practical takeaway is that trends and rate-of-change matter more than any single snapshot value.
4. **Time series is the format that matters.** A nightly scrape of attribute values into Prometheus/VictoriaMetrics (node_exporter's smartmon or smartctl_exporter textfile collector) gives rate-of-change alerting (sectors grew by 10 this week) for free, which point-in-time checks cannot.

## Attributes that actually predict trouble

1. **Reallocated sectors and pending sectors (HDD).** Attributes 5 (Reallocated Sector Count) and 197 (Current Pending Sectors) are the classic strong predictors; any nonzero count warrants attention, and a growing count is a drive planning its retirement. The companion 198 (Uncorrectable) confirms read failures in the field.
2. **SSD wear and program/erase health.** Percentage Used / Wear Leveling Count on SATA SSDs, and Percentage Used plus Available Spare versus Available Spare Threshold on NVMe, are the direct lifecycle gauges; crossing the spare threshold is the standardized NVMe definition of a failed drive.
3. **NVMe media and error counters.** Media and Data Integrity Errors Scrub/Read counts, plus Error Information Log entries, flag flash degradation invisible to HDD-era attributes; unsafe-shutdown counts additionally explain wear anomalies.
4. **Temperature and mechanical retry signals.** Attribute 194 temperature (sustained above ~55-60C shortens life and throttles), 10 (Spin Retry) and 1 (Read Error Rate) on HDDs — individually weak, but useful corroborating signals when the strong predictors start moving.

## Running smartd and exporters

1. **smartd for push-style alerting.** The smartmontools daemon polls drives on an interval (default 30 minutes), can run scheduled short and long self-tests (short weekly, long monthly is a common cadence), and emails or executes a script on threshold crossings — the low-effort baseline every host should have via /etc/smartd.conf or the DEVICESCAN directive.
2. **smartctl_exporter for pull-style monitoring.** Prometheus-based stacks scrape the exporter to get per-attribute series for every drive, enabling trend dashboards and rate-of-change alerts in the same place as CPU and disk-space metrics; combine with node_exporter textfile smartmon.sh if you prefer the lighter footprint.
3. **Self-tests are part of monitoring.** Offline surface scans (long test) are the only way some latent sector defects get discovered and remapped before they become unreadable-pending at the worst moment; schedule them so they do not collide with backup windows, since a long test hammers the platters or flash for hours.
4. **Watch the NVMe namespaces and controllers.** On U.2/M.2 fleets, note that smartctl needs the right device node (nvme0 vs nvme0n1), controller firmware bugs sometimes freeze attribute reporting, and megaraid/ARCserve-controlled disks need the proprietary passthrough (-d megaraid,N) or their attributes silently read as zeros.

## Turning telemetry into action

1. **Define graduated alerts.** Warning: first nonzero reallocated/pending sector, available spare below twice the threshold, temperature sustained above 55C. Page: rapidly growing error counters or self-test failure. The goal is proactive replacement scheduling, not 3 AM pages for a drive with months of headroom left.
2. **Keep a fleet ledger.** Record model, serial, firmware, install date, and attribute history per drive; at replacement time, batch-look-up the serial against the vendor's firmware advisories — many "failing drive" waves are actually firmware bugs with a patch.
3. **Replace with a procedure, not panic.** When a drive trips strong predictors, the runbook is: confirm with a long self-test, scrub/verify the pool (ZFS scrub or fsck-equivalent), replace and resilver during a maintenance window; resilver is itself heavy I/O that stresses the surviving drives, so monitor them extra closely during rebuilds.
4. **Feed failures back into procurement.** Track failure rates by model and batch over time; the backblaze-style transparency approach at fleet scale starts with your own ledger, and it is how you learn that the cheap drive line is actually the expensive one.
