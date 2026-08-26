# chaos-engineering-deep-dive

**Issue:** Chaos engineering — Netflix 4 principles, tools, game day
**Date:** 2026-08-09
**Status:** documented

## Symptom
A pod got OOM-killed. The service went down. The
team was paged. The on-call had no idea what to do.
You wish you had tested for this.

## Root cause
**Outages happen anyway. Meet them in a controlled
setting.** Use chaos engineering.

**Source:** Principles of Chaos:
https://principlesofchaos.org/

## The "chaos engineering" concept

Chaos engineering:
- **Discipline:** Experimenting on distributed systems
- **Purpose:** Build confidence in turbulent conditions
- **Method:** Real-world events, controlled
- **Output:** Proved resilience

The chaos is a hypothesis.

## The "4 principles" pattern

For principles (Netflix + Google SRE):
1. **Build hypothesis around steady state**
2. **Vary real-world events**
3. **Run experiments in production**
4. **Automate experiments to run continuously**

The 4 principles are the foundation.

## The "steady state" pattern

For steady state:
- **Business metric:** SPS, checkout rate
- **Latency:** P99 < 200ms
- **Error rate:** < 0.1%
- **RPS:** Within band
- **Measurable:** Required

The state is defined.

## The "real-world events" pattern

For events:
- **Instance down:** EC2, pod, container
- **Network:** Latency, partition, packet loss
- **DNS:** NXDOMAIN
- **Dependency:** Timeout, 5xx
- **Region:** Outage
- **Disk:** Full
- **Clock:** Skew
- **Env events:** Not code bugs

The events are real.

## The "production experiment" pattern

For production:
- **Staging ≠ production:** Different traffic, data,
  dependencies
- **Canary:** Start at 10%
- **Goal:** Production is the target
- **Approach:** Gradually expand

The experiment is in prod.

## The "continuous experimentation" pattern

For continuous:
- **One-off:** Catches nothing
- **Regressions:** Caught by continuous
- **CI/CD:** Chaos in pipeline
- **Schedule:** Daily or weekly

The chaos is continuous.

## The "Netflix Simian Army" pattern

For monkeys:
- **Chaos Monkey:** Random EC2 termination
- **Latency Monkey:** Inject latency
- **Conformity Monkey:** Terminate non-conformant
- **Doctor Monkey:** Auto-heal unhealthy
- **Chaos Gorilla:** Outage simulation
- **Chaos Kong:** Region outage
- **FIT:** Failure injection testing

The army is broad.

## The "Chaos Monkey" pattern

For instance termination:
- **Random:** EC2 instance
- **Business hours only:** Engineers available
- **Purpose:** Force resilient design
- **Origin:** Netflix 2010-2011

The Monkey kills instances.

## The "Chaos Kong" pattern

For region outage:
- **Entire AWS region:** Down
- **Validate:** Multi-region failover
- **Use:** Quarterly game day
- **Cost:** Significant — use sparingly

The Kong kills regions.

## The "Chaos Mesh" pattern (Kubernetes)

For K8s:
```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-failure-example
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces:
      - default
    labelSelectors:
      app: my-app
  duration: "30s"
  scheduler:
    cron: "@every 2m"
```

The Mesh is K8s-native.

## The "LitmusChaos" pattern (K8s)

For Litmus:
- **K8s-native:** Operator + CRDs
- **Hub:** ChaosHub for experiments
- **Probes:** Validate steady state
- **GitOps:** All in git

The Litmus is declarative.

## The "AWS FIS" pattern (AWS)

For AWS-native:
- **GA 2021:** Managed service
- **Actions:** EC2 stop, EBS detach, network
- **RDS:** Failover trigger
- **CloudWatch alarm:** Auto-abort
- **IAM-based:** Safety

The FIS is AWS-managed.

## The "FIS template" pattern

For FIS:
```yaml
ExperimentTemplate:
  Description: "Subnet disruption test"
  Actions:
    - ActionId: aws:network:disrupt-connectivity
      Parameters:
        duration: PT5M
      Targets:
        Subnets: my-subnet
  StopConditions:
    - Source: cloudwatch
      Value: alarm/business-metric-below-threshold
  RoleArn: arn:aws:iam::...:role/fis-experiment-role
  Tags:
    Purpose: chaos
```

The template is declared.

## The "game day" concept

For game day:
- **Tech validation:** Automated chaos
- **Org validation:** Game day
- **Tests:**
  - Who responds? (on-call)
  - Runbooks work?
  - Alerts fire?
  - Communication OK?
  - Escalation OK?

The day is the drill.

## The "game day template" pattern

For game day (1-2h):
1. **Set objective:** "Recover to us-west-2 in 15 min"
2. **Choose participants:** SRE, backend, DBA, FE, PM
3. **Write scenario:** "10:00 RDS primary failover;
   10:05 +10% write traffic; 10:10 restart half cache"
4. **Execute:** Observers vs operators; live timeline
5. **Retrospective:** What worked, what surprised,
   runbook updates, automation

The template is structured.

## The "blast radius" pattern

For blast radius:
- **Max targets:** 3 (or 30%)
- **Excluded:** Payment, auth
- **Hours:** Business hours only
- **Weekends:** No
- **Start:** 1% canary

The radius is bounded.

## The "abort conditions" pattern

For auto-abort:
```yaml
abort_conditions:
  - metric: error_rate_5xx
    threshold: "> 2%"
    window: 1m
  - metric: p99_latency_ms
    threshold: "> 3000"
    window: 2m
  - metric: orders_per_minute
    threshold: "< 80% baseline"
    window: 3m
```

The abort is automatic.

## The "progressive rollout" pattern

For progressive:
1. **Canary:** 1 instance, 5 min
2. **Limited:** 10% of targets, 10 min
3. **Broad:** Planned %, observe

The rollout is progressive.

## The "in CI/CD" pattern

For CI:
| Stage | Experiment | Blast |
|---|---|---|
| Post-deploy | Kill 1 pod | 1 pod |
| Nightly | Network partition | 1 AZ |
| Weekly | Full dependency failure | 10-30% |
| Pre-release | Game day | Staging |

The chaos is in pipeline.

## The "observability + chaos" pattern

For observability:
- **Steady state:** Watch during chaos
- **Error propagation:** Across deps
- **Cascading:** Failures
- **3 pillars:** Metrics + logs + traces
- **Auto-abort:** On metric drop

The observability is required.

## The "canary + chaos" pattern

For canary:
- **Deploy:** 10% canary
- **Chaos:** Only on canary
- **Verify:** Graceful failure
- **Pass:** Full rollout

The canary is chaos-tested.

## The "blameless postmortem" pattern

For postmortem:
1. **Impact:** Users, duration, revenue
2. **Timeline:** Minute-by-minute
3. **Root cause:** Five Whys
4. **What went well:** Detection, teamwork
5. **What went badly:** Missed alerts, weak runbook
6. **Action items:** Owner + due date

The postmortem is blameless.

## The "10 recipes" pattern

For recipes:
1. **Instance down:** Validate auto-heal
2. **Network latency:** Validate timeout
3. **Network partition:** Validate fallback
4. **DNS failure:** Validate cache
5. **Dependency 5xx:** Envoy fault 50% 503
6. **Cache eviction:** Validate warm-up
7. **DB failover:** RDS primary fail
8. **AZ outage:** Multi-AZ failover
9. **Clock skew:** JWT, TLS
10. **Traffic surge:** k6/Locust 3x

The recipes are real.

## The "metrics" pattern

For metrics:
- **MTTD:** Mean time to detect
- **MTTR:** Mean time to recover
- **Blast radius:** Contained?
- **Hypothesis success rate:** % held

The metrics are tracked.

## The "tooling landscape" pattern

For tools:
| Tool | Scope | Env |
|---|---|---|
| Chaos Monkey | Instance | AWS |
| Litmus | K8s | Any K8s |
| Chaos Mesh | K8s | Any K8s |
| Gremlin | Full | Any |
| Chaos Toolkit | Extensible | Any |
| AWS FIS | AWS-native | AWS |
| Toxiproxy | Network | Any |

The tool is per scope.

## The "no hypothesis" anti-pattern

For no hypothesis:
- **Issue:** Just breaking things
- **Fix:** Write prediction first

The hypothesis is required.

## The "no abort" anti-pattern

For no abort:
- **Issue:** Manual rollback only
- **Fix:** Auto-abort on metric

The abort is auto.

## The "staging only" anti-pattern

For staging only:
- **Issue:** Staging ≠ prod
- **Fix:** Production is the target

The prod is the goal.

## The "no observability" anti-pattern

For no observability:
- **Issue:** Can't measure deviation
- **Fix:** Metrics + traces first

The observability is first.

## The "blame culture" anti-pattern

For blame:
- **Issue:** People hide failures
- **Fix:** Blameless postmortem

The culture is blameless.

## The "12-point checklist" pattern

For checklist:
- [ ] Steady state defined
- [ ] Start staging, then 10% prod
- [ ] Blast radius declared
- [ ] Stop conditions set
- [ ] Observability first
- [ ] Runbooks paired
- [ ] PDB / preStop hooks
- [ ] On-call knows
- [ ] Results documented
- [ ] Blameless postmortem
- [ ] Quarterly game day
- [ ] Executive sponsorship

The checklist is 12.

## Verification
- **Test:** Hypothesis holds
- **Test:** Abort works
- **Test:** Runbook runs
- **Test:** MTTR measured
- **Audit:** Quarterly game day

## Gotchas
- **The "no hypothesis" anti-pattern.** Write it.
- **The "no abort" anti-pattern.** Auto.
- **The "blame culture" anti-pattern.** Blameless.

## Related
- `patterns/observability-three-pillars.md`
- `patterns/incident-response.md`
- `patterns/slo-error-budget-deep-dive.md`
- `lessons/incident-response-runbook.md`
- `deploy/canary-deployments.md`
- YoungJu: https://www.youngju.dev/blog/culture/2026-04-15-chaos-engineering-netflix-simian-army-litmus-chaos-mesh-fis-game-day-principles-deep-dive-guide-2025.en
- CodeLit: https://codelit.io/blog/chaos-testing-production
- Principles of Chaos: https://principlesofchaos.org/
- arXiv paper: https://arxiv.org/pdf/1702.05843
