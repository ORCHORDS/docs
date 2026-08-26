# finops-cost-optimization

**Issue:** FinOps — cloud cost optimization 2026
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your AWS bill is $200K/mo. 40% is waste. Reserved
Instances are expiring. The CFO is asking. You wish
you had FinOps.

## Root cause
**Cloud costs grow without governance.** Use FinOps.

**Source:** FinOps Foundation:
https://www.finops.org/

## The "FinOps" concept

FinOps (Cloud Financial Operations):
- **Cultural:** Shared cost accountability
- **Operational:** Continuous optimization
- **Engineering + finance + business:** Aligned
- **Phase:** Inform → Optimize → Operate

The FinOps is the practice.

## The "4 layers" pattern

For FinOps:
1. **Visibility:** What you spend
2. **Rightsizing:** Match to demand
3. **Commitment:** RIs / SPs
4. **Anomaly:** Catch spikes

The 4 layers stack.

## The "visibility" pattern

For visibility:
- **Cost Explorer:** Per service, account, region, tag
- **Cost Optimization Hub:** Aggregated recs (free)
- **Anomaly Detection:** ML alerts
- **Hourly granularity:** For spike detection
- **Budget alerts:** 110% of last month
- **SNS to Slack:** Real-time

The visibility is the start.

## The "tagging" pattern

For tags:
- **Required:** team, env, project, cost-center
- **Enforce:** SCPs to block untagged
- **Cost allocation:** Per tag
- **Chargeback:** To teams
- **Showback:** To leadership

The tags are mandatory.

## The "rightsizing" pattern

For rightsizing:
- **Compute Optimizer:** ML recommendations
- **CPU < 40%:** Downsize
- **Lambda Power Tuning:** Memory config
- **RDS Performance Insights:** DB
- **Aurora Serverless v2:** Variable DB
- **Run monthly:** Continuous

The right-size is ongoing.

## The "RIs vs SPs vs Spot" pattern

For commitment:
| Type | Max Save | Flex | Best For |
|---|---|---|---|
| Standard RI | 72% | Low | Steady EC2/RDS |
| Convertible RI | 54% | Medium | May change |
| Compute SP | 66% | High | Most orgs |
| EC2 Instance SP | 72% | Low | Family + region |
| Spot | 90% | None | Batch, CI, ML |
| On-Demand | 0% | Full | Unpredictable |

The choice is per workload.

## The "layered commitment" pattern

For strategy:
1. **Layer 1:** Compute SPs (60-80% baseline)
2. **Layer 2:** EC2 Instance SPs (stable families)
3. **Layer 3:** Standard RIs (DB tier)
4. **Layer 4:** On-Demand / Spot (variable)

The layers stack.

## The "AWS discount priority" pattern

For ordering:
1. **RIs** apply first
2. **EC2 Instance SPs** apply second
3. **Compute SPs** apply last

The priority is set by AWS.

## The "Database SPs" pattern

For DB (Dec 2025):
- **Covered:** Aurora, RDS, DynamoDB, ElastiCache,
  DocumentDB, Neptune, Keyspaces, Timestream, DMS,
  OpenSearch
- **Max discount:** 35% (vs 69% Standard RI)
- **Only:** 1-year, No Upfront
- **Requires:** Gen 7+ instances
- **Use:** Multi-engine, evolving

The DB SPs are flexibility.

## The "Graviton" pattern

For Graviton4:
- **Savings:** 20-40% vs x86
- **Start:** Non-prod + stateless
- **Compute Optimizer:** Identifies candidates
- **Use:** New instances first

The Graviton is cheaper.

## The "Spot" pattern

For Spot:
- **Use:** Batch, CI/CD, ML training
- **Max save:** 90% vs on-demand
- **Interruption:** 2 min notice
- **Handle:** Retry + checkpoint
- **Don't use:** Stateful, latency-critical

The Spot is for flexible.

## The "AI/ML cost" pattern

For AI/ML:
- **Inferentia2:** Up to 50% less per inference
- **Trainium2:** Up to 50% less training
- **SageMaker SPs:** Up to 64% off
- **Use:** For inference + training

The ML is cheaper on purpose-built.

## The "ghost resources" pattern

For waste:
- **EBS unattached:** Delete
- **Idle RDS:** Terminate
- **Dev DB oversized:** Right-size
- **S3 90+ days:** Lifecycle
- **Temp resources:** Tag + auto-delete
- **Trusted Advisor:** Monthly check
- **cloud-nuke / aws-nuke:** Automate

The ghosts are hunted.

## The "S3 lifecycle" pattern

For S3:
- **Intelligent-Tiering:** Auto-tier
- **Lifecycle:** 30d → IA, 90d → Glacier
- **Versioning:** Delete old versions
- **Multipart:** Cleanup incomplete

The S3 is tiered.

## The "data transfer" pattern

For egress:
- **NAT Gateway:** Expensive per GB
- **VPC endpoints:** For S3, DynamoDB
- **CloudFront:** Reduce origin egress
- **Same region:** Free
- **Inter-region:** Variable

The egress is minimized.

## The "anomaly detection" pattern

For anomalies:
- **AWS Cost Anomaly Detection:** ML-based
- **Alert:** Within hours
- **Threshold:** Spend > 2x avg
- **Channel:** Slack via SNS
- **Action:** Investigate within 24h

The anomaly is caught.

## The "4 phases" pattern

For FinOps rollout:
- **Phase 1 (Weeks 1-4):** Visibility
- **Phase 2 (Weeks 4-8):** Eliminate waste
- **Phase 3 (Weeks 8-16):** Commit
- **Phase 4 (Ongoing):** Automate

The phases are sequential.

## The "25-45% reduction" pattern

For outcome:
- **Phase 1-2:** 10-20% (waste)
- **Phase 3:** 15-25% (commitments)
- **Total:** 25-45% in 90 days

The reduction is significant.

## The "Graviton migration" pattern

For migration:
- **Test:** In non-prod first
- **Stateless first:** Less risk
- **Compute Optimizer:** Top candidates
- **Re-benchmark:** After migration

The migration is staged.

## The "chargeback" pattern

For accountability:
- **Per team:** Tag-based
- **Monthly report:** To leadership
- **Per service:** Showback
- **Budgets:** Per team
- **Alerts:** Per team

The cost is attributed.

## The "FinOps maturity" pattern

For maturity:
- **Crawl:** Visibility + tags
- **Walk:** Rightsizing + commitments
- **Run:** Anomaly + automation + culture

The maturity is per phase.

## The "no visibility" anti-pattern

For no visibility:
- **Issue:** Don't know what you spend
- **Fix:** Cost Explorer + tagging

The visibility is required.

## The "no tags" anti-pattern

For no tags:
- **Issue:** Can't allocate
- **Fix:** Mandatory tags + SCPs

The tags are enforced.

## The "overcommit" anti-pattern

For overcommit:
- **Issue:** Stranded commitments
- **Fix:** 70-80% coverage, not 100%

The commit is partial.

## The "during migration" anti-pattern

For commit during migration:
- **Issue:** Stranded as infra changes
- **Fix:** Stabilize first, commit second

The timing is post-stabilize.

## The "FinOps checklist" pattern

For checklist:
- [ ] Cost Explorer enabled
- [ ] Tags mandatory
- [ ] Anomaly detection on
- [ ] Compute Optimizer monthly
- [ ] SPs layered (60-80% baseline)
- [ ] Ghost resources hunted
- [ ] S3 lifecycle policies
- [ ] NAT → VPC endpoints
- [ ] Graviton for new
- [ ] Spot for batch/CI
- [ ] Quarterly review

The checklist is comprehensive.

## Verification
- **Test:** Spend is tracked
- **Test:** Tags are enforced
- **Test:** Commitments are optimal
- **Test:** Anomalies are alerted
- **Audit:** Quarterly

## Gotchas
- **The "no visibility" anti-pattern.** Cost Explorer.
- **The "no tags" anti-pattern.** Mandatory.
- **The "overcommit" anti-pattern.** 70-80%.

## Related
- `infra/iac-best-practices.md`
- `patterns/observability-three-pillars.md`
- `patterns/safe-deploy-checklist.md`
- `deploy/cab-change-management.md`
- Kellton: https://www.kellton.com/kellton-tech-blog/aws-cost-optimization-guide
- DoiT: https://www.doit.com/blog/aws-savings-plans-vs-reserved-instances-2026-the-decision-guide-engineers-actually-need
- Usage.ai: https://www.usage.ai/blogs/finops/cost-optimization/what-is-cloud-cost-management/
- FinOps Foundation: https://www.finops.org/
