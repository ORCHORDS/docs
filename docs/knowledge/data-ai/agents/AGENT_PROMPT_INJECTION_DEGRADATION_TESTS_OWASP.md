# Prompt Injection Degradation Testing Against the OWASP LLM Top 10

## Scope

Prompt injection remains the entry-level risk in the OWASP Top 10 for Large Language Model Applications, and most teams test it incorrectly: they run an attack suite once before launch, record a pass rate, and never repeat it. A single-point pass rate is not evidence that an agent degrades safely. Degradation testing asks a different question: as untrusted content volume, adversarial sophistication, and workload pressure increase, does the agent fail predictably and recoverably, or does it fail catastrophically and silently?

This article defines a repeatable test program that measures how injection resistance decays under load, under accumulated context, and under composed attack chains. It applies to agents that ingest retrieved documents, tool outputs, user messages, or third-party content into the same context window used for reasoning. It excludes model pre-training supply chain concerns and focuses on runtime, deployable controls. The controls here complement, and do not replace, structural mitigations such as privilege separation and human confirmation for consequential actions.

## Workflow or implementation guidance

1. Establish a baseline capability envelope before any adversarial input. Record task accuracy, refusal rate on benign requests, tool call precision, and latency on a fixed benign evaluation set. Degradation is measured relative to this envelope, never as an absolute score.
2. Build a tiered corpus. Tier one contains canonical single-turn injections. Tier two composes injection with authority claims, fake system framing, and instruction hierarchy abuse. Tier three embeds injections in realistic carrier content: retrieved documents, email bodies, calendar entries, tool response payloads, and file names. Tier four adds accumulation: the same conversation receives many low-signal injections over dozens of turns.
3. Vary the axis under test deliberately and one at a time. Run separate sweeps for untrusted-content ratio in the context window, conversation length, tool result size, concurrent request load, and downstream action privilege level. Holding other variables fixed is what turns a fuzzing exercise into a measurement.
4. Instrument every run with the actual decision points: what the model emitted, what the runtime permitted, whether a confirmation gate fired, and whether the downstream effect executed. A blocked injection that still leaked in the output text is a distinct outcome from a blocked injection with no leak, and both differ from an injection that reached a tool call but was denied by policy.
5. Define outcome categories before scoring. Suggested categories: fully contained with no observable effect; contained but leaked into output shown to a user; contained after retry; partially executed with rollback required; fully executed. Score each tier by distribution across categories rather than a single pass or fail boolean.
6. Track a derived degradation curve per tier. Plot containment rate against the sweep variable and identify the inflection point where containment drops sharply. That inflection, not the mean, defines your safe operating envelope and should feed directly into runtime limits such as maximum untrusted content ratio.
7. Re-run the program on triggers, not on a calendar alone. Mandatory re-triggers include model version change, prompt or instruction change, new tool registration, retrieval corpus change, and any incident involving suspicious content.
8. Feed results back into structural controls. Where a category shows frequent partial execution, the correct response is usually a harder boundary - privilege reduction, confirmation, or sandboxing - rather than more prompt-level instruction.

## Controls

Keep the corpus under version control with the same rigor as production prompts, and record corpus revision alongside every result so scores are comparable across runs. Isolate the test environment from production data and production tool side effects; use stub tools with effect logging instead of real downstream systems. Cap test-tenant privileges so that a fully successful injection during testing cannot cause unrecoverable damage.

Require that scoring be reproducible: record model identifier and version, sampling parameters, prompt revision, tool set revision, and corpus revision for each run. Because model output is stochastic, run sufficient repetitions to distinguish a real degradation signal from sampling noise, and report confidence intervals rather than single numbers.

Separate duties between corpus authorship and scoring. The person who writes the attacks should not be the sole interpreter of the results. Retain raw transcripts for a defined period sufficient for incident analysis, with the same access controls and retention limits applied to any sensitive log store.

## Validation evidence

Evidence for a degradation program should include: the benign baseline report with its envelope; the tier definitions and corpus revision hash; sweep matrices showing which variable was varied and over what range; outcome category distributions per tier and sweep point; the identified inflection points and the operating limits derived from them; and the change log linking each re-run trigger to its cause.

A strong evidence package also demonstrates negative controls: benign requests that resemble injections must not be refused at a rate that breaks the baseline envelope, otherwise the containment number is being purchased with false positives. Include a small set of known-vulnerable configurations tested to confirm the harness can actually detect failure; a harness that has never produced a red result is unvalidated.

Finally, include the runtime configuration snapshot: privilege assignments, confirmation gates, untrusted content limits, and output filtering configuration, so a reader can connect measured degradation to the controls that were active during measurement.

## Failure modes and correction

A common failure is optimizing against a static corpus until the agent passes it, then mistaking that pass for general resistance. Correct by refreshing a held-out portion of the corpus regularly and by never reusing the held-out set for remediation tuning. Another failure is measuring only whether an attack succeeded, ignoring leaks and partial effects; correct by scoring the full outcome category distribution.

Noise masquerading as signal is frequent. If containment varies widely across repetitions at a fixed configuration, increase repetitions and report intervals before concluding anything about a sweep. Conversely, a suspiciously flat curve across all tiers usually indicates the harness is not actually delivering the payload - verify carrier rendering, encoding, and truncation before trusting results.

When a re-run after an unrelated change shows collapse, resist the urge to tune prompts immediately. First determine whether the change altered context composition, tool availability, or instruction hierarchy, because structural regressions often look like model regressions. If degradation is confirmed real and structural fixes are infeasible in time, reduce the operating envelope explicitly and document the restriction rather than shipping the wider envelope.

## Limitations

Degradation testing measures resistance to known and constructible attack patterns, not immunity. Novel techniques, multilingual obfuscation, and multi-agent choreography can evade any fixed corpus. Results are model-version-specific and can invalidate silently when a provider updates a model behind a stable identifier. Containment metrics do not capture downstream harm severity; a 2 percent execution rate on a destructive tool may be unacceptable even with high nominal containment. The program also consumes meaningful compute and engineering time, and partial automation still requires skilled red-team judgment for corpus construction and result interpretation.

## Canonical sources

- **OWASP, Top 10 for Large Language Model Applications:** https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **OWASP GenAI Security Project, LLM Top 10 (2025 edition):** https://genai.owasp.org/owasp-top-10-for-llm-applications-2025/
- **OWASP Cheat Sheet Series, LLM Prompt Injection Prevention:** https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
