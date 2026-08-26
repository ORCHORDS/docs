# finops-real-time-cost-anomaly-detection

Static rightsizing (see `cloud-cost-optimization-rightsizing.md`) catches
waste after the fact. Real-time anomaly detection catches the moment spend
spikes — the runaway CI job, the misconfigured replica count, the dev who
accidentally provisioned a `p4d.24xlarge`. This article covers the 2026 stack
for catching cost spikes before the monthly bill lands.

## Symptom

- The monthly AWS/GCP bill jumps 40% and nobody notices until finance
  forwards the invoice three weeks later.
- A single mis-tagged auto-scaling group scales to 200 instances in a test
  account overnight.
- A LLM inference endpoint is left on `max_concurrency=1000` over the weekend.
- An engineer cross-region-replicates a 5 TB bucket "just to test".
- PagerDuty fires for an app outage but nothing fires for the $8k spend spike
  that preceded it.

## Why Static Rightsizing Is Not Enough

- Rightsizing scans run daily/weekly against historical utilization.
- Anomaly detection runs continuously (every 5-15 min) against expected spend.
- Rightsizing answers "is this resource the wrong size?" Anomaly detection
  answers "did spend just do something it's never done before?"
- You need both. Rightsizing reduces baseline; anomaly detection caps blast
  radius of mistakes.

## Fix: Cloud-native anomaly detection (AWS Cost Anomaly Detection)

```bash
# enable per-account or per-payer
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "Name": "prod-account-anomaly",
    "Type": "DIMENSIONAL",
    "Dimension": "LINKED_ACCOUNT",
    "MatchOptions": {"MatchOptions": ["EQUALS"], "Values": ["123456789012"]}
  }'

# attach a subscription with alert threshold
aws ce create-anomaly-subscription \
  --anomaly-subscription '{
    "Name": "eng-oncall",
    "Threshold": 100,
    "Frequency": "IMMEDIATE",
    "MonitorArn": "arn:aws:ce::123456789012:anomalymonitor/...",
    "Subscribers": [{
      "Address": "eng-oncall@org.com",
      "Type": "EMAIL"
    }]
  }'
```

`Threshold=100` means alert on anomalies of $100 or more. Tune per account —
$100 is noise for a prod payer, signal for a sandbox.

## Fix: Real-time alerting via CloudWatch + tag-based grouping

Cost Explorer has 6-24h latency. For true real-time, alert on usage metrics
that proxy for cost:

```yaml
# terraform module — alert when per-tag daily spend estimate exceeds baseline
resource "aws_cloudwatch_metric_alarm" "gpu_spend_spike" {
  alarm_name          = "gpu-spend-anomaly"
  namespace           = "AWS/Usage"
  metric_name         = "ResourceCount"
  dimensions = {
    Resource          = "p4d.24xlarge"
    Service           = "EC2"
    Class             = "Standard/Compute"
  }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 6      # 30 min
  threshold           = 4      # 4 GPUs sustained = anomaly
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.cost_anomaly.arn]
}
```

This fires within 5-10 minutes of the spike starting, not next week.

## Fix: FinOps platform integration (Vantage / CloudHealth / Kubecost)

For Kubernetes cost attribution, install Kubecost or OpenCost:

```yaml
# values.yaml — helm install kubecost/cost-analyzer
kubecostProductFamilies:
  enterprise: false        # OpenCost core is free
prometheus:
  server:
    persistentVolume:
      size: 100Gi
  retention: 30d
networkCosts:
  enabled: true             # captures cross-AZ egress — a silent budget killer
alertConfigs:
  spendAlert:
    enabled: true
    threshold: 500          # USD per day namespace budget
    window: daily
  namespaceAlerts:
    enabled: true
    thresholds:
      gpu-inference: 800
      ci-runners: 200
```

Kubecost attributes pod cost to namespace/team via labels, surfaces idle
capacity, and can fire alerts when a namespace crosses its daily budget.

## Fix: GCP equivalent — budgets + programmatic notifications

```bash
gcloud billing budgets create \
  --billing-account=01ABCD-EF2345-6789AB \
  --display-name="prod-gpu-budget" \
  --amount=20000USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 \
  --pubsub-topic=projects/prod/topics/budget-alerts
```

Subscribe a Cloud Function to the Pub/Sub topic that pages oncall on the 100%
threshold and posts a Slack warning on 50%.

## Gotchas

- **Cost Explorer latency is 6-24h.** Don't rely on it for real-time. Use
  CloudWatch/GCP metrics (usage counters) as the real-time proxy.
- **Cost Anomaly Detection has a learning period (1-2 weeks).** Brand-new
  accounts won't get good alerts until a baseline exists. Manually set tight
  budgets in the meantime.
- **Untagged resources break attribution.** If 60% of spend has no team tag,
  anomaly detection can't tell you whose problem it is. Enforce tagging via
  SCP/organization policy before enabling FinOps alerting, or the alerts are
  useless noise.
- **Free tier / credits mask anomalies.** GCP/AWS credits absorb spend before
  it hits the bill; budget alerts measure post-credit, so a credit-covered
  spike won't trip the budget until credits run out — then the bill explodes.
  Track pre-credit spend separately if credits are material.
- **Kubecost idle allocation.** Kubecost attributes idle cluster overhead to
  namespaces by default, which inflates team costs. Configure
  `sharedIdle: true` and `idleAllocation: cluster` to allocate idle to the
  cluster owner, not individual workloads.
- **Spot reclaim events look like anomalies.** A spot fleet rebalancing event
  can drop replica count and spike cost-per-replica metrics. Whitelist known
  autoscaler events before alerting.
- **Currency conversion.** Multi-org FinOps aggregation in different
  currencies can produce apparent anomalies that are just FX moves. Convert
  to a base currency at the source.
- **Alert fatigue → silence.** If every $50 anomaly pages oncall, oncall mutes
  the channel. Two-tier: Slack for low thresholds, PagerDuty only above a
  material amount (e.g. $500 in 1h, or >20% of monthly budget in a day).
- **Budget alerts don't stop the spend.** They just notify. Pair detection
  with enforcement: SCPs that cap instance types in non-prod accounts,
  Kyverno/OPA policies that reject expensive resource requests, or Quota
  budgets that hard-block over-provisioning.
- **Tagging policy is the prerequisite, not an afterthought.** Budget
  $20k/year of eng time on tagging enforcement before you spend $50k/year on
  a FinOps tool nobody can use because the data is dirty.
