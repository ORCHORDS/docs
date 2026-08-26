# r2-multipart-upload

**Issue:** R2 multipart upload — current Workers API, retries, and completion ownership
**Date:** 2026-08-20
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** fixed (knowledge-base correction)

## Symptom

Large uploads need resumability and parallel part transfer, but an implementation either:

- restarts the entire file after a transient failure;
- uses an outdated/nonexistent Workers-binding API;
- assumes a resumed multipart handle proves the upload still exists;
- allows two logical uploads or completions to race for the same final object key; or
- clears application ownership before `complete()` finishes, reopening a second writer while R2 is still committing the first upload.

## Root cause

Multipart storage has **two state machines** that must agree:

1. R2's multipart state (`uploadId`, parts, complete/abort); and
2. the application's authorization/ownership state (which upload is currently allowed to write or complete a logical object).

Cloudflare's current Workers API is:

- `bucket.createMultipartUpload(key, options?)`
- `bucket.resumeMultipartUpload(key, uploadId)`
- `multipart.uploadPart(partNumber, value)`
- `multipart.complete(uploadedParts)`
- `multipart.abort()`

`resumeMultipartUpload()` deliberately performs no existence check. Cloudflare also warns that a multipart upload can be completed or aborted by a parallel Worker invocation, so every operation must handle the underlying upload disappearing or changing concurrently.

R2 object writes/deletes are strongly consistent, but **concurrent writers to the same key are still a coordination problem**: Cloudflare documents that when two clients write/delete the same key, the last operation to complete wins.

**Sources:**
- [Cloudflare R2 Workers API reference](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Use the R2 multipart API from Workers](https://developers.cloudflare.com/r2/api/workers/workers-multipart-usage/)
- [R2 consistency model](https://developers.cloudflare.com/r2/reference/consistency/)
- [R2 upload objects / multipart limits](https://developers.cloudflare.com/r2/objects/upload-objects/)
- [R2 error codes](https://developers.cloudflare.com/r2/api/error-codes/)

## Correct Workers-binding pattern

```ts
// Create an upload for one final object key.
const upload = await env.BUCKET.createMultipartUpload(
  `uploads/${userId}/${objectId}`,
  { httpMetadata: { contentType: 'video/mp4' } },
)

// Persist upload.uploadId in application state before returning it.
await db.authorizeUpload(objectId, upload.uploadId)

// Later requests resume the same R2 upload by key + uploadId.
const active = env.BUCKET.resumeMultipartUpload(
  `uploads/${userId}/${objectId}`,
  uploadId,
)

const part = await active.uploadPart(partNumber, request.body!)
// Persist/return part.partNumber + part.etag.

// Completion requires the exact uploaded parts.
const object = await active.complete(parts)
```

Do not invent binding methods such as `env.BUCKET.createPresignedUrl()`. Presigned URLs are an **S3 API** concept in R2 and use the S3 endpoint plus SigV4-capable tooling/SDKs. For a browser/mobile upload, choose deliberately between:

- an authenticated Worker endpoint that calls the R2 binding; or
- the S3-compatible API with server-generated presigned operations / scoped temporary credentials.

Cloudflare's presigned-URL documentation currently covers S3 API URLs for supported operations and explicitly distinguishes them from Workers bindings.

**Source:** [Cloudflare R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

## Part sizing and limits

Current R2 multipart constraints include:

- minimum part size: 5 MiB except the final part;
- maximum part size: 5 GiB;
- maximum parts: 10,000;
- maximum multipart object size: 5 TiB;
- all non-final parts must be the same size.

Pick a part size based on object size, memory/request limits, latency, and operation cost. Do not hard-code “5–50 MB is always recommended” as a platform rule; it is workload-specific.

## Application authorization pattern

Treat `uploadId` as a capability that is valid only while application state says it is current.

```text
EMPTY
  -> ACTIVE(uploadId)
  -> COMPLETING(uploadId, lease/version)
  -> COMPLETE

ACTIVE(uploadId)
  -> ABORTED / EMPTY
```

A robust API should:

1. create a multipart upload;
2. atomically record which `uploadId` is authorized for the logical object;
3. reject stale IDs on part upload, complete, and abort;
4. move the active upload into an explicit **COMPLETING** state before touching final-object state;
5. keep that completion ownership until R2 `complete()` and post-completion validation finish;
6. reject or serialize a new begin while completion owns the slot;
7. make cleanup/delete conditional on the same lease/version that created the object;
8. transition to COMPLETE exactly once.

The critical rule is: **do not represent “completion in flight” as “no upload is active.”** Clearing the active ID before `complete()` resolves can authorize a new writer for the same key while the old writer is still committing.

## Why a pre-complete compare-and-set is not enough

This pattern is still racy:

```ts
// BAD: application slot is reopened too early.
await db.compareAndSetActiveUpload(objectId, uploadId, null)
const object = await multipart.complete(parts) // still in flight
```

If `begin()` accepts a new upload whenever the database slot is null, a second upload can start before the first `complete()` resolves. Both can target the same R2 key. A later failed size check or cleanup can then delete an object written by another completion.

Instead, claim a completion lease/state:

```ts
const lease = crypto.randomUUID()
const won = await db.moveActiveToCompleting(objectId, uploadId, lease)
if (!won) throw new ConflictError('stale upload')

try {
  const object = await multipart.complete(parts)
  validateCompletedObject(object)
  await db.finishCompletion(objectId, uploadId, lease)
} catch (err) {
  await db.recordCompletionFailure(objectId, uploadId, lease)
  throw err
}
```

Any rollback delete must also verify the same completion lease/version still owns the final key. If ownership has changed, do not delete.

## Retry pattern

Retry **parts** independently with bounded exponential backoff and jitter. Persist their returned ETags. On completion errors such as `NoSuchUpload`, `InvalidPart`, or non-uniform part sizes, treat the error according to its class rather than blindly retrying forever.

A failed `complete()` is not proof that it is safe to reopen a second writer immediately. First reconcile application state and the R2 upload/object state.

## Abort pattern

Abort explicitly when an upload is intentionally abandoned:

```ts
const upload = env.BUCKET.resumeMultipartUpload(key, uploadId)
await upload.abort()
```

Cloudflare automatically aborts incomplete multipart uploads after the configured/default lifecycle window, but explicit abort frees abandoned parts sooner.

Abort must obey application ownership. A stale client's late abort must not clear authorization for a newer active upload.

## Direct-client boundary

If clients upload parts through your Worker, enforce at least:

- authenticated object ownership;
- validated `uploadId` and part number;
- bounded part/body size;
- exact object-key derivation on the server;
- no caller-controlled arbitrary R2 key;
- rate/concurrency limits;
- log redaction for upload IDs, signed URLs, credentials, and sensitive object names where applicable.

If clients use S3-compatible presigned operations or temporary credentials, scope them to the minimum bucket/path/operations and short lifetime. Treat presigned URLs as bearer credentials.

## Observability

Track:

- active and completing uploads separately;
- completion latency;
- stale-upload conflicts;
- part retries and R2 error codes;
- aborted/incomplete uploads;
- completion-lease recovery;
- concurrent-write or rate-limit signals for the same key.

Do not log raw presigned URLs, API credentials, or private upload capabilities.

## Anti-patterns

1. **Outdated Workers API examples** — passing `{ key }` to `createMultipartUpload()` or calling a nonexistent binding-level `createPresignedUrl()`.
2. **Upload ID only in the client** — two retries can become two authorized writers.
3. **Clearing ownership before `complete()` resolves** — reopens a second writer during finalization.
4. **Unconditional rollback delete** — a losing/late request can delete a newer winner's object.
5. **Trusting `resumeMultipartUpload()` as existence validation** — it performs no such check.
6. **No stale-ID checks** — superseded clients keep writing parts or completing.
7. **Blind retry of completion errors** — can amplify conflicts and hide state corruption.
8. **One giant single-part upload for large media** — transient failure restarts all bytes.

## Verification

- **Create/parts:** only the currently authorized upload ID can write parts.
- **Retry:** a transient part failure retries without restarting successful parts.
- **Stale ID:** a superseded upload cannot upload, complete, or clear a newer upload.
- **Begin vs complete:** while completion is in flight, a second begin is rejected or serialized.
- **Complete vs complete:** two completion requests cannot both own the final transition.
- **Rollback:** an oversized/invalid losing completion cannot delete a later winner's object.
- **Failure recovery:** R2 completion failure leaves an explicit recoverable state, not a silently reopened writer slot.
- **Abort:** stale abort cannot deauthorize a newer upload.
- **Storage:** final object and application state agree after completion.
- **Live:** test the concurrency paths against R2 or an integration environment with equivalent last-writer semantics; a serial unit test is insufficient evidence.

## Gotchas

- A `409` on a replayed completion proves only that replay path; it does not prove begin-vs-in-flight-completion serialization.
- Strong consistency does not serialize your business workflow. Last-writer-wins on the object key still requires application coordination.
- Parallel part uploads are expected; parallel **logical owners/completions of the same final key** are the dangerous case.
- `complete()` returning means the assembled object is globally readable; keep application authorization state aligned with that transition.

## Related

- `cloudflare/r2-large-file-patterns.md`
- `cloudflare/r2-signed-urls.md`
- `cloudflare/r2-cors-config.md`
- `patterns/feature-cookbook-file-upload.md`
