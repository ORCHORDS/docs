# nat-gateway-cost-optimization

**Issue:** Workloads in private VPC subnets reach the internet exclusively through NAT gateways, and AWS charges USD 0.045 per hour plus USD 0.045 per GB processed — a fee that applies to traffic in both directions, including traffic destined to AWS's own services. Because the fee is invisible in architecture diagrams and accrues silently, NAT gateway data processing is routinely the largest unexamined networking line item in an AWS bill, and teams frequently discover that a majority of it is S3 transfers, container image pulls, or monitoring telemetry that never needed to traverse the public internet at all. This article covers where NAT money actually goes, the quick wins (gateway endpoints), the break-even math for interface endpoints, architectural consolidation patterns, and the monitoring guardrails that keep costs from creeping back.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Cost anatomy — where the money actually goes

1. **Hourly attach fee.** Each NAT gateway costs roughly USD 32/month (0.045/hour) regardless of traffic. Multi-AZ designs that deploy one NAT gateway per AZ triple this base cost, which is justified for availability but should be a deliberate choice, not a template default.
2. **Per-GB processing in both directions.** The 0.045/GB fee is charged for data flowing in and out of the NAT gateway, so a large download pays processing on the payload even though only a small request initiated it; return traffic counts too.
3. **Cross-AZ multiplier.** Traffic from subnets in one AZ routed through a NAT gateway sitting in another AZ incurs cross-AZ data transfer charges on top of processing fees, quietly compounding the cost of poorly routed flows.
4. **Hidden AWS-service traffic.** ECR image pulls, CloudWatch logs and metrics, S3 uploads, STS and KMS API calls from private subnets all traverse NAT by default. In published workload breakdowns this routinely represents 50-80 percent of NAT processing volume, and almost all of it is avoidable.

## Quick wins — gateway endpoints first

1. **S3 and DynamoDB gateway endpoints are free.** A gateway endpoint costs nothing per hour or per GB; it changes the route table so S3 and DynamoDB traffic stays on the AWS backbone. This is the single highest-ROI change on most bills and should be a Terraform module default for every private subnet.
2. **Verify routes by prefix list, not assumption.** After creating the endpoint, confirm the AWS managed prefix list for S3 points at the gateway endpoint, then check VPC flow logs to prove S3 traffic no longer exits via the NAT gateway ENI.
3. **Tighten bucket policies deliberately.** Gateway endpoints can be scoped with bucket policy conditions on the source VPC endpoint; set that guardrail intentionally rather than leaving buckets wide open, but do not let policy friction become the excuse for traffic staying on NAT.

## Interface endpoints and the break-even math

1. **Interface endpoint pricing.** An interface endpoint costs about USD 7.30/month per AZ per endpoint plus USD 0.01/GB. In a 3-AZ VPC that is roughly USD 21.90/month base, versus NAT's 0.045/GB — endpoint data works out about 78 percent cheaper per GB.
2. **Compute break-even per service.** For a 3-AZ endpoint the crossover sits near 500 GB/month (base fee divided by the 0.035/GB delta); below that the NAT path is cheaper, above it the endpoint wins decisively. ECR, CloudWatch, and KMS almost always qualify once fleet sizes are non-trivial.
3. **Create endpoints for the top talkers only.** Rank destinations by bytes processed from flow logs or Cost Explorer, then buy endpoints for the top few; blanketing dozens of low-volume services just accumulates base fees with no savings.

## Architectural patterns

1. **Consolidate NAT gateways where AZ symmetry does not matter.** Non-production environments rarely need per-AZ NAT gateways; one gateway plus careful routing saves about USD 64/month per environment, multiplied across every account in the org.
2. **Keep per-AZ NAT in production.** In production, run one NAT gateway per AZ and point each subnet's default route at its co-located gateway; this eliminates cross-AZ transfer fees and survives an AZ failure, which is the availability rationale for paying triple.
3. **Consider self-managed NAT only for extreme volumes.** For steady multi-TB/month egress, a right-sized EC2 instance doing NAT (the fck-nat pattern) trades per-GB fees for instance cost. Pursue only with real commitment to patching and failover automation — it is operational debt wearing a savings costume.
4. **Use an egress proxy for control as well as cost.** An explicit egress proxy in public subnets gives per-workload cost attribution plus policy enforcement (allow-lists, TLS inspection), often justifying itself on security grounds with the NAT savings as a bonus.

## Guardrails and monitoring

1. **Tag spend and set anomaly alerts.** Tag NAT gateways per environment and set AWS Cost Anomaly Detection on NAT gateway bytes processed; per-GB cost spikes show up within hours and should page someone when they deviate from baseline.
2. **Audit quarterly with Cost Explorer and flow logs.** Break NAT charges down by destination using VPC flow logs aggregated on bytes, and re-run the endpoint break-even math every quarter — traffic patterns drift, and last year's correct architecture quietly becomes overpriced.
3. **Enforce endpoint policy as code.** Codify the S3 gateway endpoint and the top interface endpoints in Terraform modules so new VPCs start correct; drift detection should flag any VPC missing its free S3 endpoint rather than relying on reviewer memory.
