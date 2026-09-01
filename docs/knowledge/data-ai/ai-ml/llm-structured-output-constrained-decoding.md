# LLM Structured Output via Constrained Decoding

When an LLM must emit JSON — an API argument, a classification label, a tool call — there are two ways to obtain it: ask nicely and validate, or force the output space so invalid output cannot occur. Constrained decoding is the second approach: the sampler's next-token distribution is masked to tokens that keep the string inside a formal language (a JSON Schema, a regular expression, or a context-free grammar). Reliability is bought with rigid mechanics that have their own failure modes, and mixing the two approaches naively is where most production incidents start.

## Scope

This article covers choosing and operating constrained decoding for structured generation: when hard constraints beat prompt-only approaches, what constraint formalism to pick, how validation tiers layer, and what to monitor once generation is constrained. It applies to both self-hosted engines with grammar support and hosted APIs exposing structured-output features.

Out of scope: prompt-engineering techniques for improving format adherence in unconstrained models (that is the fallback path, not the subject), and full function-calling orchestration, which uses these mechanics but adds tool-selection policy.

The core distinction to keep straight: prompt-only generation produces output that is *usually* valid and must be checked; constrained decoding produces output that is *syntactically* valid by construction but can still be semantically wrong. Constraints guarantee shape, not truth.

## Workflow or implementation guidance

1. **Classify the requirement first.** If a downstream parser crashes on malformed output, syntax must be guaranteed — use constrained decoding. If the requirement is "the field should contain a country code" and the pipeline tolerates a wrong-but-well-formed value, constraint buys less than it costs and validation-plus-retry may suffice. Write this classification down; it determines everything after.
2. **Pick the weakest formalism that suffices.** Enumerations and fixed shapes need regex or schema-level typing; nested objects with conditional fields need JSON Schema; deeply recursive structures (arithmetic expressions, DSLs) need a grammar. Stronger formalisms cost more compile time and constrain the model harder, which measurably degrades content quality when applied beyond necessity. Do not wrap the whole response in a grammar when only one field needs it.
3. **Constrain the smallest necessary span.** If the task is "answer in free prose, then emit a verdict field," run the generation in two stages — unconstrained prose, then a constrained completion for the verdict — rather than grammaring the whole output. Interleaving constraints across long free text is both slower and quality-degrading.
4. **Layer validation in tiers.** Tier one: structural (schema-valid by construction or by parse). Tier two: semantic (referential integrity, value ranges, enum membership beyond syntax, cross-field consistency). Tier three: task-level (does the output actually answer the request). Constrained decoding eliminates tier-one rejections almost entirely; tiers two and three remain and must be explicitly implemented.
5. **Decide the failure path before launch.** What happens on tier-two failure: repair prompt, resample with adjusted constraints, or escalate to fallback handling? Each path needs a budget (how many retries) and a metric. Silent retries hide systematic problems; unlimited retries create latency and cost blowouts.
6. **Test constraints with adversarial cases.** Schemas with mutually exclusive branches, empty-array and empty-string boundaries, unicode escapes, and deeply nested structures are where constraint compilers and model samplers misbehave. Build a corpus of these and run it on every engine upgrade — constraint compilation is version-sensitive code.

## Controls

- **Schema version control.** Every deployed schema/grammar is versioned; generation requests pin a schema version so outputs remain interpretable as schemas evolve.
- **Constraint-compile canary.** New or modified schemas are compiled against the engine's current version in CI before deployment; compilation failures and warnings block release.
- **Tiered-validation metrics.** Rejection counts by tier and by failure reason, alerting on rate changes. A rise in tier-two rejections often reveals a semantic drift the constraint cannot see.
- **Retry-budget enforcement.** Bounded retries with a terminal fallback path; retry exhaustion is counted and alarmed, not swallowed.
- **Quality regression gate.** Before enabling a constraint over a task, run the task's evaluation suite constrained and unconstrained and compare answer quality, not just validity. Material quality loss blocks the constraint's adoption or forces a narrower schema.

## Validation evidence

- Validity rates by tier from production sampling: tier-one violations (should be ~0 under hard constraints; any nonzero rate indicates a path bypassing the constraint), tier-two and tier-three rejection rates with reasons.
- Constrained-versus-unconstrained evaluation deltas on the task suite, demonstrating the quality cost of the constraint is within tolerance.
- Adversarial corpus results across engine versions, showing schema-compile behavior stable.
- End-to-end latency comparison, since constraint application adds per-token overhead; the numbers belong in the evidence file with engine versions cited.

## Failure modes and correction

- **Valid nonsense.** The schema forces a well-formed object whose contents are wrong or hallucinated — the constraint did its job; the model failed semantically. Correction: strengthen tier-two/three validation and task evaluation; never treat schema-validity as correctness.
- **Quality degradation under over-constraint.** Wrapping entire responses in grammars measurably degrades fluency and reasoning. Correction: narrow the constrained span, split generation into stages, or relax the formalism.
- **Schema-compiler drift.** An engine upgrade changes how a schema compiles (different token masking, different handling of optional branches); outputs shift subtly. Correction: pin engine versions, run the adversarial corpus and task suite on upgrades before promotion.
- **Retry storms on semantic failure.** A tier-two validator rejects, retries repeat the same semantic error, latency and cost spike. Correction: cap retries, alter the repair strategy on repeated identical failures (different prompt, narrower constraint, or escalate to fallback), and alert on retry-exhaustion rates.
- **Enum drift between schema and application.** The schema permits values the application no longer accepts (or vice versa); valid-per-schema outputs are rejected downstream. Correction: generate the schema from the application's type definitions wherever possible so there is one source of truth.

## Limitations

Constraint mechanics, supported formalisms, and performance characteristics differ across engines and hosted APIs and change between versions; consult the current engine documentation for binding capabilities. Constraints guarantee syntax only — semantic correctness, factual accuracy, and cross-field plausibility require independent validation. Very large or recursive grammars can impose substantial compile-time and per-token overhead, and some hosted structured-output features place limits on schema complexity, nesting, or size. This article addresses output structuring, not prompt-injection defense or tool-authorization policy, which operate at different layers.

## Canonical sources

- Outlines documentation, Structured Generation: https://dottxt-ai.github.io/outlines/
- OpenAI documentation, Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
