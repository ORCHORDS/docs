# Node readFile Abort and Internal-Buffering Boundary

**Issue:** Aborting `fs.readFile()` is often assumed to cancel the operating-system read immediately and free memory, but it only aborts Node's internal buffering work between individual requests.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Use `fs.readFile()` only when buffering the entire file is acceptable under the file-size and concurrency budget.
- Pass an `AbortSignal` for cooperative cancellation, but do not promise immediate kernel-level cancellation of an in-flight read request.
- Use `fs.createReadStream()` or explicit chunked reads when bounded memory, progressive processing, or prompt teardown is required.
- Apply file-size checks before reading and enforce aggregate in-flight byte limits; per-request validation alone does not prevent memory exhaustion.
- Handle `AbortError` distinctly from I/O corruption and avoid retrying an intentionally cancelled read.
- Close owned file descriptors and remove abort listeners in every terminal path; document ownership when a caller supplies a descriptor.

## Verification
- Abort reads at different sizes and timings and observe memory, latency, callback or promise result, and descriptor closure.
- Run many concurrent maximum-size reads and confirm aggregate memory remains within the service budget.
- Compare the same workload with a read stream and verify cancellation and backpressure meet the requirement.

## Gotchas
An accepted abort request means the API stops its buffering operation; it does not prove every underlying OS request was cancelled.

## Official sources
- https://nodejs.org/api/fs.html
