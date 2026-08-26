# large-payload-encoding-failure-pivot

**Issue:** A coding-session backend started returning HTTP 500 "surrogates not allowed" on large (~3MB+) conversation payloads. Retrying the same request failed identically — the error was deterministic, tied to a specific bad byte sequence in the payload, not transient load. Sessions above the threshold became permanently stuck: un-openable, un-resumable. Diagnosed via the session backend's model-io transcripts (ZCode session diagnostics, 2026-08-14/15).

**Date:** 2026-08-15
**Repo:** ORCHORDS (session infrastructure)
**Author:** ORCHORDS
**Status:** published

## Diagnosis path that worked

1. **Read the wire transcripts, not the UI.** `model-io-sess_*.jsonl` files contained the exact request body AND `durationMs`/`finishReason` — the 1-second-empty-stop pattern revealed the upstream error was being swallowed, not that the model said nothing.
2. **Classify deterministic vs transient:** same payload → same error → same byte = deterministic; no retry will fix it.
3. **Find the threshold empirically** — payloads under ~3MB succeeded; the failure was size-correlated, pointing at an encoding/validation layer, not the model.
4. **The bad byte survives re-serialization** — the payload's content (not its framing) carried the problem; any resume of that session re-sent it.
5. **Fix surfaced the error upstream** (backend patched 2026-08-14 to propagate instead of swallow) — after which diagnosis of the NEXT such failure would take minutes, not hours.

## The pivot protocol when a session is stuck

1. **Stop retrying the resume** — N identical failures establish determinism; attempt N+1 is ritual, not engineering.
2. **Salvage state externally** — memory files, git status, task lists, the last visible output: reconstruct working state outside the corrupted session.
3. **Start a FRESH session seeded from the salvage** — clean payload, no bad byte; continue the work, not the session.
4. **Write the failure down immediately** (memory/KB) — the diagnosis is only useful if the next session starts with it.
5. **Keep the corrupted artifact for forensics** if the platform team wants the byte; otherwise mark it unresumable and move on.

## Broader lessons

1. **Swallowed upstream errors are the worst failure class** — the client sees "empty response", the server saw an exception; until propagation is fixed, every diagnosis goes through the transcripts.
2. **Retries are for transient faults only** — determinism testing (same input → same failure) is step one of any retry loop design.
3. **Size-correlated failures implicate serialization layers** — encoders, validators, or surrogate-pair handling, not business logic.
4. **Session state must be reconstructable** — work that only exists inside one conversation is one corrupted payload away from loss.
5. **Transcript logs are the source of truth** — duration + finishReason per request beats any amount of UI staring.

## Related

- `flaky-tests-destroy-ci-trust.md` (deterministic vs flaky classification)
- `../monitoring/` error-propagation patterns
