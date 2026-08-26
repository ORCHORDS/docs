# llm-for-code-generation

**Issue:** LLM-generated code contains bugs, uses deprecated APIs, and lacks context about the target codebase
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A coding assistant generates plausible-looking code that uses outdated library APIs, ignores existing project patterns, or introduces security vulnerabilities. Developers spend more time fixing generated code than they would writing it from scratch.

## Pattern / Solution
Include relevant context in the prompt: existing function signatures, import patterns, test examples, and project conventions. Use RAG to inject the most relevant existing code files. Request tests alongside implementation. Require the model to explain its approach before generating code — chain-of-thought improves correctness.

For security-sensitive code, explicitly ask the model to identify potential vulnerabilities in its own output before finalizing.

## Gotchas
- LLMs use training data cutoffs — generated code may use deprecated APIs for fast-moving libraries
- Generated code often lacks error handling — explicitly ask for it
- SQL generation requires parameterized queries; always validate generated SQL against your schema before execution

## Related
- prompt-chain-of-thought
- rag-architecture-overview
- llm-output-validation
