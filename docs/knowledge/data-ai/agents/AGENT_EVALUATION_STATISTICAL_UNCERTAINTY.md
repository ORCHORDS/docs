# Statistical Uncertainty in Agent Evaluation

## Purpose

Agent evaluation results are estimates produced from a sample of tasks, environments, and stochastic executions. A single pass-rate number hides uncertainty from finite sample size, task selection, repeated runs, grader error, and variation among users or scenarios. Sound evaluation therefore reports the estimand, sampling unit, uncertainty interval, and limits of generalization.

NIST’s AI Risk Management Framework emphasizes valid and reliable measurement, while established statistical guidance explains confidence intervals, experimental design, and comparison. These principles apply whether the outcome is binary task success, continuous cost, latency, safety severity, or a human rating. They do not turn an unrepresentative benchmark into evidence about production.

## Implementation workflow

1. State the decision and estimand. Examples are the probability that a randomly selected task from a defined suite succeeds within budget, or the mean tool-error count per run under a specified configuration.
2. Define the population and sampling unit. Separate tasks, users, conversations, and stochastic reruns. Repeated runs of one task are not equivalent to independent new tasks.
3. Freeze an evaluation protocol: dataset revision, exclusions, environment, model and agent versions, tool fixtures, budgets, stopping rules, grader rubric, and handling of invalid runs.
4. Choose sample size using the precision or power required for the decision. Avoid selecting the sample count only after seeing favorable results.
5. Randomize execution order where time, load, or shared state could bias results. For comparison, run candidates on the same tasks and seeds or conditions when feasible, then analyze paired differences.
6. Report point estimates and intervals suited to the metric and design. For binary proportions, use a defensible binomial interval rather than treating the observed percentage as exact. For clustered tasks or non-normal metrics, use an appropriate cluster-aware or bootstrap method with assumptions documented.
7. Analyze important slices defined before inspection, while reporting slice sample sizes. Correct or clearly label exploratory multiple comparisons.

## Controls

Prevent test-set contamination by limiting access, separating development and final sets, and tracking every evaluation query. Keep holdout results from becoming prompt-tuning feedback. Deduplicate tasks and identify templates that make nominal sample size larger than effective diversity.

Do not average incompatible outcomes into a single score without a documented utility model. Safety-critical failure can require a threshold or zero-tolerance rule rather than compensation by faster benign tasks. Report abstentions, infrastructure failures, timeouts, and grader-invalid cases separately; silently removing them biases results.

Human and model graders need validation. Use blinded review where possible, measure agreement on a sample, adjudicate consequential disagreements, and test whether graders prefer verbosity, style, or leaked reference cues rather than correctness. Automated grading uncertainty is additional to run variability.

## Validation and evidence

Before a release decision, reproduce a subset from raw fixtures and verify metric calculations independently. Inspect per-task results and trajectories for impossible combinations, duplicate IDs, leakage, and correlated failures. Compare evaluation traffic and production constraints so unavailable tools or unrealistic latency do not invalidate conclusions.

For a candidate comparison, publish the paired outcome table or sufficient aggregate counts, estimated effect, uncertainty interval, sample size, missing-run policy, and predefined acceptance threshold. A statistically detectable difference may still be operationally trivial; conversely, a wide interval may mean there is not enough evidence to decide.

Evidence should include the protocol, preregistered hypotheses or decision rules when used, dataset lineage, code revision, environment manifest, randomization record, raw outcomes, grader records, analysis code, interval method, and signed decision. Preserve failed and excluded runs with reasons.

## Failure handling

If an interval crosses both meaningful improvement and meaningful harm, report the result as inconclusive and gather more representative data or reduce variance. Do not describe absence of statistical significance as proof of equivalence. Equivalence or non-inferiority decisions require margins chosen before analysis and methods appropriate to those hypotheses.

If contamination, grader drift, data leakage, or metric defects are discovered, invalidate affected results, repair the protocol, and rerun from an uncontaminated set. If production performance falls outside evaluation intervals, investigate population shift, dependence, instrumentation mismatch, and changed execution conditions rather than automatically blaming stochastic noise.

## Canonical sources

- NIST, *AI Risk Management Framework 1.0*: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST, *AI RMF Playbook*: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook
- NIST/SEMATECH, *e-Handbook of Statistical Methods*: https://www.itl.nist.gov/div898/handbook/
- ACM, *Artifact Review and Badging*: https://www.acm.org/publications/policies/artifact-review-and-badging-current
