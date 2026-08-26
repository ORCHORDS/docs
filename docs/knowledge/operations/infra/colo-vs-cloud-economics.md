# colo-vs-cloud-economics

**Issue:** Cloud spend grows with the business while colocation quotes sit in a spreadsheet, and every 18 months someone asks "would it be cheaper to own the metal?" The question is genuinely hard: cloud is OpEx that scales with usage and hides infrastructure labor; colo is CapEx plus a fixed recurring cabinet/power bill plus hardware failure risk plus your own remote-hands logistics — and since 2024, GPU-hungry AI workloads tilted the math by making power density and hardware scarcity first-class decision inputs. This article covers the economic models, where each side wins, how to model the crossover honestly, and the failure modes of both choices.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Two Economic Models

1. **Cloud: usage-priced OpEx with elastic ceilings.** You pay per hour/GB/request, with no upfront commitment, instant scale-up, and the provider absorbing facilities, hardware refresh, and datacenter operations; the same pricing means steady-state workloads pay a recurring premium — effectively renting at a multiple that funds the provider's margin plus the option value of elasticity.
2. **Colo: CapEx plus fixed recurring.** You buy servers (upfront, depreciating over 3-5 years) and rent space, power, cooling, and network from the facility at a predictable monthly rate; costs are largely flat regardless of utilization, so the per-workload cost falls as utilization rises — the model rewards steadiness and punishes overprovisioning.
3. **The hidden line items differ in kind.** Cloud hides ops labor inside instance prices; colo surfaces it as your own staffing (or remote hands at $150-300/hour), spares management, hardware procurement cycles, and RMA logistics — practitioner comparisons consistently find direct costs favor colo over any multi-year horizon while indirect costs narrow the gap, sometimes to nothing for small fleets.
4. **AI changed the power-denisty math.** GPU servers draw 5-15 kW each, and providers price colo substantially on power; estimates for operating owned servers in a facility run roughly $2-7/hour per server in facilities overhead — nontrivial, yet still often below the 3-4x multiple on GPU on-demand pricing, which is why AI training at scale is the strongest colo/dedicated-hardware driver of the 2025-2026 cycle.
5. **Exit costs are asymmetric.** Leaving cloud means draining data (egress fees, mostly bounded); leaving colo means decommissioning physical assets you own at a facility you contracted with — multi-year colo commitments with power floors deserve the same scrutiny as cloud reserved capacity, because both are bets on forecast utilization.

## Where Colo Wins

1. **Steady, high-utilization workloads past the crossover.** A fleet running 24/7 at 70%+ utilization for 3+ years is the textbook colo case: predictable monthly costs, no egress fees between your own racks, and per-unit compute that keeps falling as you amortize hardware; the multi-year TCO comparisons (DataBank, Datacate, and the r/sysadmin field reports) all converge on colo winning this shape decisively.
2. **Data gravity and egress economics.** Terabyte-class datasets that many clients read continuously rack up cloud egress relentlessly; serving them from your own cabinet where internal traffic is free converts your biggest cloud line item into a fixed wire your already paying for.
3. **AI training and dense inference.** Long GPU training runs are the least elastic workload in computing — committed 24/7 for weeks — so they capture none of cloud's option value while paying full GPU premiums; owned H100/B200-class hardware in a colo (or dedicated provider) commonly cuts cost per training run dramatically, at the price of owning a scarce, rapidly-evolving asset.
4. **Compliance and data-control regimes.** Some regulated or contractual situations demand known physical custody of hardware and data; a named rack in a named facility satisfies auditors in ways a shared cloud region sometimes cannot, without building an actual datacenter.
5. **Performance predictability.** No noisy neighbors on shared hypervisors, no burstable-credit surprises, and direct control over NICs, storage NVMe, and topology — matters for latency-sensitive serving and any workload where the p99 tail of cloud tenancy shows up in SLOs.

## Where Cloud Wins

1. **Spiky, unpredictable, or short-lived demand.** Black-Friday-shaped traffic, CI bursts, one-off experiments, and anything with a horizon under ~18-24 months is cloud's home turf; the option value of scale-to-zero and scale-to-ten is real money that flat colo commitments cannot replicate.
2. **Teams without hardware operations.** If nobody on staff has lived through a chassis fan failure at 3 AM in a facility two timezones away, cloud's embedded ops is not laziness — it is the correct purchase of a capability you lack; colo assumes (or hires) that competence as a precondition.
3. **Managed services above the metal.** RDS, Cloud Spanner, BigQuery, serverless — the cloud's differentiating value in 2026 is increasingly these, not VMs; a colo migration that moves compute but leaves your datawarehouse on BigQuery is a hybrid, and should be modeled as one.
4. **Geographic elasticity.** Serving users from regions where you could never justify a rack, or entering a market for six months to test it — cloud's global footprint is an capability no colo contract provides.
5. **Fast-moving hardware wants.** Wanting next year's GPU or inference accelerator without selling this year's is a rental argument; cloud refresh is their CapEx problem, which is exactly what you are paying the premium for.

## Modeling the Crossover Honestly

1. **Price the total cost of both paths over one hardware life.** Cloud side: committed-use/discounted rates (not list), egress, load balancers, snapshots, and the managed services you actually use; colo side: hardware CapEx amortized over its life, cabinet and power recurring, cross-connects, remote-hands retainer or staffing hours, spares, and an insurance line for hardware failure rates.
2. **Include utilization discipline in the model.** Colo's per-workload cost assumes you actually run the metal hot; if organizational reality leaves owned servers at 30% utilization (very common after migrating from elastic cloud habits), the spreadsheet win evaporates — model your real utilization, not the theoretical one.
3. **Add the labor at loaded cost.** One quarter-time senior engineer babysitting the fleet often exceeds the entire colo power bill; conversely, count the cloud side's hidden labor too — cost optimization, reserved-capacity management, and the multi-week egress architecture projects are also labor.
4. **Stress-test with failure scenarios.** What happens to each model at 2x growth, at half the forecast, when a SAN dies in year two, when GPU prices move, when the colo contract renews at +20% power? A decision that only works at exactly forecast scale is not a decision, it is a bet.
5. **Revisit at refresh boundaries, not on a whim.** The rational review points are hardware-refresh cycles and contract renewals; mid-cycle "cloud bills are high" frustration produces the worst colo migrations — ones made without a workload plan, executed badly, and re-migrated at a loss.

## Pitfalls

1. **Comparing cloud list price to colo direct cost.** The flattering spreadsheet; honest versions use your discounted cloud rates and fully-loaded colo costs including labor, failures, and refresh — most "90% savings" claims dissolve under this treatment, though real savings for steady workloads do remain, typically arriving decisively after year two.
2. **Single-cabinet, single-facility thinking.** One rack in one facility is a SPOF for power, network, and physical access; parity with a multi-AZ cloud posture means two facilities or an explicit hybrid split, which changes both cost and complexity — plan for it before signing.
3. **Underestimating the ops lift permanently.** The migration team is not the steady-state team; hardware breaks on a schedule set by physics, firmware updates need maintenance windows, and capacity planning becomes your job — organizations that budget colo ops as a one-time project fail at month nine.
4. **Losing cloud's managed-service gravity.** Moving the 200 stateless web nodes to colo while the architecture still leans on a dozen managed databases, queues, and analytics products yields a hybrid with two of everything and the cost of neither model's strengths; sequence migrations around dependency clusters, not instance counts.
5. **Ignoring the resale/refresh risk on accelerators.** Owned CPUs depreciate gently; owned AI accelerators can halve in value when the next generation lands — the colo GPU bet is a hedge on the workload persisting long enough to outrun the hardware's relevance, so pair it with utilization commitments and a realistic refresh plan rather than treating it as a one-time win.
