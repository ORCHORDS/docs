# distillation-pipeline-local

**Issue:** Frontier coding models solve tasks a local model can't, but frontier inference isn't always available or affordable — so example project distills a big coding model's solutions into a small local model. The pipeline's core policy: the training set contains ONLY verified traces (every single example is a test-passing solve), built by sampling multiple generation attempts per task and filtering failures out. Naive distillation on unfiltered teacher output made the student confidently reproduce broken behavior; verified-only distillation preserved both solve ability and tool-call protocol behavior. Found in example project-1 dataset construction.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Pipeline stages

1. **Task intake.** Tasks come from the designed task families (see `star-task-family-design.md`) — each arrives with its machine grader attached, so verification is available at zero extra design cost.
2. **Multi-attempt teacher generation.** For each task, the big model gets several independent attempts (fresh sampling per attempt). This is rejection sampling at the dataset level: per-attempt success probability compounds across attempts, so k attempts at per-run rate p yield a training example with probability 1-(1-p)^k.
3. **Verify every attempt.** Each attempt runs the task's grader (seeded-bug check, pinned tests, measured budget). Nothing is kept on the teacher's reputation — a wrong answer from a strong model is still wrong.
4. **Failure filtering.** Failed attempts are discarded, not "cleaned up." Rewriting failed traces to look correct injects hallucinated reasoning the student will imitate; the only safe repair is another attempt.
5. **Dedupe, then train.** Surviving traces are hash-deduped against the corpus (`training-data-dedupe-freshness.md`) so one lucky task shape can't dominate the mix, then the student is fine-tuned on what remains.

## The verified-only policy and why it holds

1. **Every training example is a test-passing trace.** This is the pipeline's invariant. It means the student never sees a demonstrated failure presented as success, which is the main way distillation teaches overconfidence.
2. **The verifier is the ground truth, not the teacher.** 2025 practice converged here: KODCODE (ACL Findings 2025) builds code data with solution verification as ground truth, Prime Intellect's Synthetic-1 kept traces only when verifier output exactly matched ground truth, and TensorZero's distillation results come from programmatic curation of teacher outputs — all the same shape as our grader-gated loop.
3. **Multiple attempts also measure difficulty.** The attempts-to-first-pass ratio per task is a free difficulty signal — tasks needing many attempts are hard for the teacher and risk being near the student's ceiling; use the ratio to balance the mix rather than including every hard-won trace at full weight.
4. **Filter the trace, not just the final answer.** A passing final answer reached through a broken trace (lucky guess, grader exploit) is a contamination vector — prefer attempts whose intermediate steps the grader can also check (tests run per-step for refactor-safe, budget measured per-version for perf-budget).
5. **Keep the rejects as an eval pool.** Teacher-failed tasks where the student later succeeds are exactly the cases that prove the student isn't just a compressed copy — mine them when auditing what distillation actually taught.

## Tool-call protocol preservation

1. **Tool-call behavior survives distillation when the data contains it.** Our student kept emitting the text TOOL_CALL protocol (see `ollama-jinja-rejection-text-tool-protocol.md`) because the training traces were full agent-style solves — tool invocations and tool results included — not bare prompt/completion pairs.
2. **Distill trajectories, not answers.** This matches the Agent Distillation result (arXiv 2505.17612): transferring agentic behavior and tool use to small models requires fine-tuning on complete tool-using trajectories, not on final responses.
3. **Render protocol into the trace format before training.** The trace the student sees must be byte-identical to what the student will be asked to produce at inference (same TOOL_CALL syntax, same result-injection format) — any mismatch between training rendering and serving rendering silently degrades protocol adherence.
4. **Verify protocol shape as part of the grader.** An attempt that passes tests but emits malformed tool calls is a failed attempt for distillation purposes; the student would learn to pass while being unusable as an agent.
5. **Re-run the protocol check post-training.** After each distillation round, smoke-test the student's tool-call emission against the pinned protocol spec — it is a capability that can regress even when solve rate improves.

## Lessons aligned with current research

1. **Verifier-filtered + rejection-sampled beats generic SFT data.** The combination (sample many, verify hard, keep passes) is the 2025-consensus recipe for small-model training data, from Synthetic-1's verifier-gated traces to scaling knowledge-distillation work on thinking-trace transfer — our pipeline is an independent confirmation at local scale.
2. **Small student, well-scoped domain, big wins.** Distillation literature (Agent Distillation, TensorZero's 5-30x cheaper inference claim) and our results agree: a small student recovers most of the teacher's value when the domain is bounded and the data is clean; it does not generalize to the teacher's full breadth and shouldn't be asked to.
3. **Data quality is the bottleneck, not student size.** Doubling attempts per task improved the student more than any training-hyperparameter change; the marginal cost of more verified examples is compute on tasks you already have graders for.
4. **Beware teacher-trace lock-in.** The student inherits the teacher's failure MODES on borderline tasks; the per-family eval dashboard (not training loss) is what catches this.

## Related

- `star-task-family-design.md` (where tasks and graders come from)
- `training-data-dedupe-freshness.md` (dedupe stage details)
- `ollama-jinja-rejection-text-tool-protocol.md` (the tool protocol being preserved)
- `vram-budget-model-selection-math.md` (student size selection)
