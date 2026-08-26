# llm-evaluation-testing

**Issue:** Traditional assertions break on LLM outputs because the same prompt yields different valid responses every run
**Date:** 2026-08-12
**Status:** documented

## Symptom / Context

You wrap an LLM call in a test and write `expect(output).toBe("...")`. The test passes once, then fails
flakily on the next run even though the output is perfectly correct — just worded differently.
The team starts adding `// FIXME: flaky` comments or pinning a model version and temperature=0 to make
CI green, which hides real regressions and freezes the model. The root cause is applying deterministic
equality checks to a non-deterministic system.

This hits RAG summarisation, classification, extraction, rewriting, code generation, and any feature
built on `chat.completions`. The symptom is a test suite that is either always red or falsely green.

## Pattern / Solution

Stop asserting exact strings. Assert properties of the output using an evaluation harness.

1. **Temperature 0 in unit tests, real temperature in eval tests.** Keep two suites:
   one fast unit suite with `temperature=0` and a seeded/mock model for deterministic logic
   (JSON shape, function-call signature), and a separate nightly eval suite that runs the real
   model at production temperature and scores outputs.

2. **LLM-as-a-judge for semantic checks.** Use a stronger/cheaper evaluator model to score the
   production output against a rubric instead of string-matching:
   ```ts
   async function assertAnswersQuestion(question: string, answer: string) {
     const verdict = await judge.complete({
       model: "gpt-4o-mini",
       messages: [{
         role: "user",
         content: `Question: ${question}\nAnswer: ${answer}\n`
               + `Does the answer directly answer the question? Reply JSON {ok:boolean, reason:string}.`
       }],
       response_format: { type: "json_object" },
     });
     const { ok, reason } = JSON.parse(verdict);
     if (!ok) throw new Error(`Judge rejected: ${reason}`);
   }
   ```

3. **Assert structural invariants deterministically.** Things you CAN assert exactly:
   - output parses as the requested JSON schema (use `ajv` or Zod)
   - every citation in the answer exists in the source context
   - the answer is under the max token budget
   - required keys are present and types match
   - no PII / no banned tokens (regex or classifier)

4. **Score over a golden dataset, not single examples.** Build a labelled set of 50-200 cases
   with expected traits. Run the full set and assert pass-rate thresholds, e.g.
   `expect(passRate).toBeGreaterThanOrEqual(0.9)`. A single failing case is a signal, not a
   hard CI failure; a 10-point drop in pass rate is.

5. **Pin the test to a fixture response during development.** Record a real response once into
   `__fixtures__/summary.json` and have the unit test replay it through the processing logic so
   you can TDD the surrounding code without burning tokens or fighting randomness.

## Gotchas

- LLM-as-a-judge is itself non-deterministic — the judge will occasionally disagree with itself.
  Use `temperature=0` for the judge, log disagreements, and set the judge threshold below 100%.
- A pinned fixture masks model drift. Re-record fixtures on a schedule and diff the new recording
  against the old one as its own eval signal.
- Asserting `passRate >= 0.9` over 50 cases has real variance — a clean run at 0.92 can drop to
  0.86 next run with no code change. Use larger N (100+) and a confidence band, or run evals as
  a reporting gate rather than a hard CI block.
- Cost sneaks up fast: 200 cases x judge + model = real money. Cache results by
  `hash(prompt+model+params)` and only re-run changed cases.
- `response_format: json_object` still lets the model emit wrong-shaped JSON inside the object.
  Always validate the parsed body with a schema, never just `JSON.parse`.
- Free-text assertions like "contains the word X" break the moment the model paraphrases.
  Prefer semantic checks over lexical ones.
- Embedding similarity thresholds ("cosine > 0.85") look rigorous but the threshold is arbitrary;
  calibrate against a labelled good/bad set before trusting it.

## Related
- ai-agent-testing
- flaky-test-detection
- flaky-test-remediation
- property-based-testing-fast-check
- golden-master-testing
- snapshot-testing-pitfalls
