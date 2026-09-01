# LLM Batching Scheduler Throughput

Every LLM serving stack answers one question thousands of times per second: which requests share the next forward pass? Batching amortizes weight loading and kernel launch overhead across requests, and the scheduler that forms batches is the single largest determinant of throughput. Poor scheduling either starves the GPU (tiny batches, low utilization) or torments users (long queues while the system waits to fill a batch). Getting the scheduler's trade-offs right is an engineering discipline with measurable feedback loops, not a tuning folklore.

## Scope

This article covers batching strategy in LLM inference serving: static versus continuous batching, iteration-level scheduling, queueing behavior under load, and the controls needed to keep both throughput and latency-objective compliance visible. It targets operators of self-hosted inference clusters and teams evaluating serving engines.

Excluded: model parallelism and tensor parallelism decisions (orthogonal scheduling concerns), speculative execution strategies, and request-level routing between models. Those interact with batching but warrant separate treatment.

The central tension: batching converts latency into throughput. A scheduler that waits to form large batches raises requests-per-second but delays the first token of every request in the queue. There is no universally correct point on this curve — there is only the point that satisfies your latency objective at your traffic shape, found by measurement.

## Workflow or implementation guidance

1. **Characterize the traffic before choosing a scheduler.** Record request arrival distribution, prompt lengths, and generation lengths over representative windows. Traffic with bursty arrivals and short generations punishes batch-formation delay; smooth arrivals with long, uniform generations tolerate it. The same scheduler configuration can be excellent for one workload and catastrophic for another.
2. **Prefer continuous (iteration-level) batching.** Static batching admits a group, runs all sequences to completion, and strands finished sequences' capacity until the slowest finishes. Continuous batching joins and leaves requests at each iteration step. For almost all interactive workloads, continuous batching strictly dominates; static batching survives mainly in offline throughput jobs where completion-time variance is acceptable.
3. **Bound batch formation delay.** Configure the maximum time the scheduler may wait to admit a request to a forming batch. Setting it to zero prioritizes latency; raising it fills batches at the cost of queue time. Derive the bound from the latency objective: if p99 time-to-first-token must stay under a target, formation delay plus queue wait must fit inside it with headroom for forward-pass variance.
4. **Cap concurrency deliberately.** Maximum batch size interacts with memory: each active sequence holds a KV cache. A cap that fits the memory budget for average prompts will overflow on a burst of long prompts. Use preemption-aware admission — long-prompt requests that would exceed the memory budget wait rather than triggering mid-batch preemption, which discards computed KV state and recomputes it later.
5. **Separate latency-sensitive and throughput traffic.** Interactive requests and offline batch jobs should not share a scheduler queue unless the scheduler supports priority classes. A background embedding or summarization job dropped into the same pool distorts interactive latency unpredictably. Run them on separate pools or enforce priority admission.
6. **Load-test to the knee, not to collapse.** Find the offered-load point where queue wait begins compounding — throughput plateaus while latency climbs steeply. Provision capacity and admission control to sit comfortably below that knee, and shed or queue excess load explicitly rather than letting internal queues absorb it invisibly.

## Controls

- **SLO compliance by traffic class.** Time-to-first-token and end-to-end latency percentiles tracked separately per class; a blended average hides interactive degradation under batch-job volume.
- **Queue depth and wait-time alerts.** Alert on queue age (oldest waiting request) rather than only queue length — age directly reflects user-visible harm.
- **Utilization versus latency joint dashboard.** GPU utilization without latency context rewards over-batching; latency without utilization rewards gold-plating. The pair identifies the efficient operating region.
- **Preemption-rate metric.** Frequent KV-cache preemption signals the concurrency cap or memory budget is wrong; it wastes compute silently.
- **Admission-control configuration review.** Formation delay, concurrency caps, and priority classes are configuration with user-visible consequences; changes go through review with expected latency impact stated.

## Validation evidence

Validation is a load test that reproduces production traffic shape, not uniform synthetic requests:

- Closed-loop benchmark sweeping offered concurrency, recording throughput, p50/p95/p99 time-to-first-token and inter-token latency, preemption counts, and queue wait. The chosen operating point is documented on this curve with the SLO margin explicit.
- Replay of production request traces (real prompt and generation length distributions) through the candidate configuration, comparing against the incumbent on the same trace.
- Soak evidence: sustained load at the chosen point for hours, watching for memory growth, fragmentation-driven preemption, or latency creep that short benchmarks miss.
- Failover behavior: kill a worker mid-test and confirm the scheduler drains and rebalances without violating the latency objective for admitted traffic beyond the documented blast radius.

## Failure modes and correction

- **Over-batching for throughput benchmarks.** Tuning to maximize requests-per-second on a synthetic benchmark produces configuration that misses interactive latency targets badly in production. Correction: re-tune against the latency-constrained objective and replayed traces; treat unconstrained throughput numbers as diagnostic, not as goals.
- **Convoy effects from long generations.** A few requests generating thousands of tokens hold batch slots; short requests queue behind them. Correction: enable chunked prefill or fairness-aware scheduling so long sequences yield; segment traffic classes so interactive requests never queue behind offline jobs.
- **Memory-pressure preemption storms.** Admission admits more sequences than KV memory supports; the scheduler preempts, recomputes, and effective throughput collapses. Correction: admission control that accounts for prompt length against the memory budget; preemption rate should be near zero in steady state.
- **Hidden queues.** Request buffers upstream (client library, gateway, load balancer) queue invisibly; internal metrics look healthy while users wait. Correction: instrument the full path end to end and alert on the oldest-request age at the outermost edge.
- **Config drift between pools.** One pool is retuned and others inherit stale settings, producing unexplained performance asymmetry. Correction: scheduler configuration is declarative, versioned, and applied uniformly with per-pool overrides explicit.

## Limitations

Scheduler behavior is engine-specific and evolving: preemption policies, chunked prefill, and priority semantics differ across serving stacks and versions, so exact knobs and defaults must be read from the engine's current documentation rather than generalized. Queueing behavior under adversarial or extremely bursty traffic is hard to model precisely; load tests approximate but cannot bound tail latency absolutely. This article addresses request scheduling, not the underlying hardware scheduling (kernel selection, graph capture), which adds its own variance. Published throughput numbers from vendors or benchmarks use specific models, sequence lengths, and hardware; they are not transferable without rerunning the characterization steps above.

## Canonical sources

- vLLM documentation, Serving Framework Fundamentals: https://docs.vllm.ai/en/latest/serving/serving_framework.html
- NVIDIA Triton Inference Server documentation, Dynamic Batching: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/dynamic_batching.html
