# Generative AI pre-deployment multi-level evaluation

**Issue:** A model passes static benchmarks but fails when combined with prompts, retrieval, tools, users, and real operating context.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Evaluate at three complementary levels: model testing, adversarial/red-team testing, and field/system testing. NIST ARIA uses this framing, while NIST AI 600-1 is a voluntary GenAI profile.

## Controls

Define release-blocking risks and thresholds; version the full system; test ordinary and abuse scenarios; give red teams scoped tools and safe environments; include representative users and downstream impacts; record scaffolding because it changes capability; retain failures and mitigations; re-run after model, prompt, retrieval, tool, or policy changes.

## Verification

Use held-out cases, multiple seeds, independent reviewers, rollback drills, and post-deployment monitors tied to pre-deployment claims. Compare against relevant reference systems without overgeneralizing small differences.

## Gotchas

Finite testing cannot establish absence of risk. Model-only results do not describe an agent. Evaluator models need validation. Do not expose dangerous test artifacts.

## Sources

- [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
- [NIST ARIA evaluation levels](https://ai-challenges.nist.gov/aria)
