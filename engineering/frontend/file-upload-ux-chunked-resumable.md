# file-upload-ux-chunked-resumable

**Issue:** Uploads of large files (video, datasets, high-res batches) fail on flaky mobile networks and the only recovery is restarting from byte zero; users close the tab and lose 20 minutes of progress; nginx/proxy body-size limits reject anything over a few MB; and a single multipart POST gives no honest progress bar, no pause, and no deduplication. The fix is chunked, resumable uploads — protocol-driven slicing with server-side offset tracking — and the failure modes live in the details: fingerprints, chunk sizing, auth token expiry mid-upload, and cleanup of orphaned partial files.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why plain multipart POST breaks down

1. **One request means one point of total failure.** A 500MB upload over a 40-minute connection that drops at 95% must restart completely. Chunked uploads bound the loss to one chunk (typically 5-10MB).
2. **No real progress or pause.** `XMLHttpRequest.upload.onprogress` only fires for whatever is in flight, pausing means aborting everything, and page navigation silently kills the transfer. Chunked transfers expose per-chunk progress you can aggregate into an honest progress bar and pause/resume trivially.
3. **Infrastructure limits appear as mystery failures.** Default `client_max_body_size` (nginx: 1MB), CDN/Worker request-body caps (Cloudflare Workers historically ~100-500MB per request), and server timeouts all reject large single POSTs. Chunks sized under every limit in the path make uploads infrastructure-proof.
4. **Duplicate files upload repeatedly.** Client-side content hashing before upload lets the server answer "already have it" (deduplication) without transferring a byte — impossible with naive multipart.
5. **Background/multi-tab uploads conflict.** Two tabs uploading the same file via multipart produce two full copies; a resumable protocol with a fingerprint makes the second tab attach to the first upload's progress.

## The tus protocol (the standard answer)

1. **tus is an open HTTP protocol for resumable uploads.** Flow: client `POST` creates an upload resource, server returns an upload URL, client `PATCH`es chunks with an `Upload-Offset` header, and every response echoes the authoritative offset. A dropped connection resumes from the last acknowledged offset — across reloads, days, or devices.
2. **Use `tus-js-client` or Uppy on the client.** Both handle chunking, retries with exponential backoff, parallel uploads, and pause/resume; Uppy additionally gives you a polished file-picker UI, drag-and-drop, and companion integrations. Do not hand-roll the offset bookkeeping.
3. **Fingerprinting drives resume-across-sessions.** The client computes a fingerprint (file name + size + last-modified, or a content hash for stronger identity) and stores the upload URL locally; on retry it asks the server via `HEAD` whether that URL still exists and at what offset. Cloudflare Stream's tus endpoint and most servers honor this flow.
4. **Chunk size is a tuning knob, not a constant.** Smaller chunks (5MB) recover faster on lossy mobile links and stay under proxy limits; larger chunks (16-64MB) reduce per-request overhead on fast connections. Some providers mandate minimums (Cloudflare Stream: 5,242,880 bytes unless the file is smaller); make it configurable and adaptive when possible.
5. **Server options are mature — do not write your own from scratch.** `tusd` (Go), `tus-node-server`, `tusdotnet`, and tus-php implement creation, concatenation (parallel chunks), expiration, and checksum extensions. Your job is wiring storage and auth, not the protocol state machine.

## UX requirements beyond the protocol

1. **Show three distinct states, not one spinner.** Per-file and aggregate UI needs: queued, uploading (with bytes/second and ETA from aggregated chunk progress), and done — plus explicit paused/error/awaiting-retry states. The honest progress bar is the single biggest trust win.
2. **Persist drafts of intent, not just transfers.** Remember the file list and their statuses (sessionStorage or IndexedDB keyed by fingerprint) so a reload restores the queue, resumes in-flight items, and does not silently re-add completed files.
3. **Validate before uploading.** Client-side checks (MIME sniffing via the File API's first bytes, not just the extension; max size; dimensions/duration for media) fail in milliseconds instead of after a 200MB transfer. Surface violations as field-level errors before the transfer starts.
4. **Handle auth expiry mid-upload.** Long uploads outlive short-lived tokens. Refresh the token between chunks (the tus client supports request-interceptor callbacks), or issue a scoped, longer-lived upload ticket at creation time. A 401 at chunk 40 of 50 is the classic unhandled production bug.
5. **Communicate server-side post-processing.** "Uploaded" is not "processed" for video transcode or virus scan — after the final chunk, move the UI to a processing state driven by a status endpoint or Server-Sent Events (see `server-sent-events-streaming-ui.md`).

## Edge cases and failure handling

1. **Corrupted chunk detection.** Use the tus `checksum` extension (or verify ETag/Content-MD5 per chunk) so a bit-flipped chunk is retried instead of baked into the final file. Without it, resume-after-corruption produces a silently broken asset.
2. **Orphaned partial uploads need garbage collection.** Server must expire incomplete uploads (tus `expiration` extension) and sweep their storage; otherwise abandoned uploads eat disk forever. Log creation-vs-completion rates to catch client bugs that leak uploads.
3. **Concurrent modification.** If the same fingerprint is uploading from two devices, define the winner explicitly (first-to-finish, or reject the second with a conflict) rather than letting interleaved PATCHes corrupt the file.
4. **Upload from the background (mobile).** On mobile web, moving the tab to background throttles JS and can kill the transfer — chunk state must be durable enough that reopening the page resumes. For truly background uploads on native shells, hand off to a platform upload task (WorkManager/BGTaskScheduler) rather than fighting browser throttling.
5. **Memory pressure with Blob slicing.** Use `file.slice(start, end)` per chunk (lazy, constant memory) instead of reading the whole File into an ArrayBuffer; the latter OOMs mobile Safari at a few hundred MB.

## Testing

1. **Simulate network failures deterministically.** Playwright/CDP `Network.emulateNetworkConditions` plus aborting specific chunk requests lets you assert resume-from-offset, not just happy path. Assert the server never receives overlapping byte ranges.
2. **Test reload-mid-upload in a real browser.** Refresh at 30%, reopen, assert the second session's first PATCH uses the persisted offset from the fingerprint store — this is the test that catches broken local state plumbing.
3. **Boundary matrix.** File exactly one chunk, file one byte over one chunk, zero-byte file, filename with unicode/quotes (Content-Disposition escaping), and chunk size larger than the file — each has a real-world bug attached.
4. **Load-test chunk fan-out.** 1,000 concurrent uploads of 100 chunks each is a very different server profile than 1,000 single POSTs (connection churn, open file handles, offset-store contention); measure before launch.
5. **Related reading in this knowledge base:** `browser-storage-quota.md` (draft persistence), `server-sent-events-streaming-ui.md` (post-upload processing status), `browser-fetch-patterns.md` (request lifecycle fundamentals).
