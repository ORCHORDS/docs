---
title: "Agent Evaluation Patterns"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Agent Evaluation Patterns

## Purpose

Agent evaluation should measure outcomes and execution behavior across representative tasks rather than rely on a single aggregate score.

## Evaluation dimensions

Depending on the application, an evaluation suite MAY measure:

- task completion or outcome quality;
- factual or functional correctness;
- safety and policy compliance;
- tool-selection and tool-use correctness;
- recovery from expected failures;
- unnecessary steps, latency, or resource use;
- adherence to task constraints;
- reproducibility or variance across repeated runs;
- human review outcomes where automated evaluation is insufficient.

## Trajectory evaluation

For multi-step agents, retain a safe evaluation representation of the execution trajectory when needed. A trajectory can include decisions, tool calls, observations, retries, and final outputs. Evaluation SHOULD avoid storing credentials, personal data, or sensitive payloads that are not necessary for measurement.

Trajectory analysis can identify failure modes that an outcome-only score hides, such as:

- reaching a correct answer through an unsafe action;
- excessive or circular tool use;
- repeated invalid requests;
- success that depends on an unintended fallback;
- regressions in intermediate behavior despite a similar final result.

## Test-set design

Evaluation sets SHOULD include the task distributions and failure modes that matter for the intended use. Useful coverage can include routine cases, difficult cases, boundary conditions, malformed input, dependency failures, and adversarial cases where appropriate.

## Scoring

Avoid treating arbitrary weighting formulas as universal measures of agent quality. If a composite score is used, its component metrics, weights, limitations, and acceptance thresholds SHOULD be documented and justified for the application.

## Regression use

Stable evaluation cases SHOULD be rerun when models, prompts, tools, routing, memory behavior, or major dependencies change. Results SHOULD be compared at the individual-test level as well as in aggregate so regressions are not hidden by averages.
