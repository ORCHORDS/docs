# r2-streaming-hls-pipeline

**Issue:** The example project video platform self-hosts its video pipeline instead of using Cloudflare Stream: uploads are transcoded to HLS (adaptive-bitrate renditions split into `.ts`/`.fMP4` segments plus `.m3u8` playlists) and everything lands in R2, which then serves as the origin for playback. Two failure classes shaped the design: (1) transcoded output arrived faster than a naive buffered writer could handle — buffering whole files in a Worker violates the 128 MB memory limit and adds minutes of latency before the first segment is playable; (2) a cache-miss incident where every segment request hit R2 instead of the edge, multiplying Class B operations and stalling playback. The pipeline now streams segments into R2 as they are produced, uses multipart uploads for the large originals, serves playlists and segments with a split cache policy, and verifies cache hits in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Why HLS on R2 instead of Cloudflare Stream

1. **Cost control at scale.** Stream bills per minute stored and per minute delivered; for a platform with long-tail user content, R2's zero-egress model plus free edge caching on a custom domain is dramatically cheaper, at the cost of running your own transcode step.
2. **Full control over the pipeline.** Owning the transcode step means custom rendition ladders, custom segment durations, custom keyframes, and the ability to re-derive artifacts (thumbnails, previews) from stored originals without a vendor API in the loop.
3. **R2 is a legitimate HLS origin.** Cloudflare explicitly permits streaming public video from R2 through the CDN (non-HTML content is normally not cached by default, but R2-backed custom domains are the exception) — confirmed in Cloudflare community guidance and the R2 docs.

## Ingest: stream segments into R2 while receiving

1. **Never buffer the transcoded output.** The transcoder emits segments as they complete; the server pipes each one straight into `bucket.put(key, readableStream)` — the R2 Workers API `put()` accepts a `ReadableStream` value directly, so bytes flow from transcode output to R2 without ever being fully materialized in memory. This is what keeps the ingest Worker inside its 128 MB memory ceiling.
2. **One `put()` per segment, not one per video.** HLS segments are small (typically 2–10 s of media, a few MB). Single `PUT` is correct here — multipart exists for large objects, and R2's single-PUT ceiling is 5 GiB, far above any segment. Per-segment keys (`{videoId}/{rendition}/seg-000042.ts`) make segments independently cacheable, independently retriable, and visible to players as soon as they land.
3. **Playlists are rewrites, segments are appends.** Each new segment forces a playlist update (`EXT-X-MEDIA-SEQUENCE` advance for live-style windows, or list growth for VOD). Overwriting the playlist object is cheap; concurrent overwrite of the *same* key at high rate returns HTTP 429, so pipeline writes to a playlist key must be serialized per video.
4. **Set HTTP metadata at write time.** `put()` accepts `httpMetadata` — set `contentType` (`application/vnd.apple.mpegurl` for playlists, `video/mp2t` or `video/iso.segment` for segments) and `cacheControl` on the object itself, so the metadata travels with the object no matter which serving path reads it later.

## Multipart uploads for the large originals

1. **Originals are the big objects.** Source uploads run multi-GB; they go through `createMultipartUpload()` / `uploadPart()` / `complete()` rather than a single `PUT` (which caps at 5 GiB). Multipart supports up to 5 TiB across at most 10,000 parts.
2. **Part sizing constraints.** Every part except the last must be at least 5 MiB and parts must be uniform in size; ceiling is 5 GiB per part. A fixed part size in the 16–64 MiB range comfortably stays inside both bounds for multi-GB originals and keeps part counts low.
3. **Parts can be streams too.** `uploadPart(partNumber, value, ...)` accepts a `ReadableStream`, so even the original can flow into R2 chunk-by-chunk as it is received from the uploader rather than being spooled to disk first.
4. **Incomplete uploads clean themselves up — mostly.** R2 auto-aborts incomplete multipart uploads after 7 days by default, and this window is configurable via an object lifecycle rule on the bucket. Do not rely on the default alone: aborted transcodes should trigger an explicit `abort()` so orphaned parts stop accruing storage immediately.
5. **Multipart ETags are not content hashes.** The completed object's ETag is a hash of the part ETags plus a `-N` suffix, not an MD5 of the whole object — never use it for integrity verification against a client-computed checksum.

## Serving: playlists and segments from R2 with a split cache policy

1. **Serve through a custom domain, not `r2.dev`.** A custom domain on the bucket routes requests through Cloudflare's CDN so segments get edge-cached; the `r2.dev` public endpoint does not get the same treatment and every play becomes an R2 read (Class B operation) from origin.
2. **Segments are immutable — cache them forever.** A segment key is never rewritten once complete, so it gets `Cache-Control: public, max-age=31536000, immutable`. Edge hit ratio for segment traffic should sit near 100% for anything with more than a handful of concurrent viewers.
3. **Playlists are hot and volatile — cache them barely.** The `.m3u8` key changes with every new segment, so it gets a short TTL (a few seconds for live-style windows) or `no-cache` with ETag revalidation. This is the one object where freshness beats hit ratio.
4. **Version manifests by path to bust caches.** For VOD re-transcodes, write to a new prefix (`{videoId}/v2/playlist.m3u8`) instead of overwriting in place — this lets old segment caches age out naturally while new playlists reference new segment keys, with no cache invalidation API calls at all.

## Cache-hit verification (shipped after the cache-miss incident)

1. **The incident.** A serving-path change started returning segment responses without the immutable cache headers being honored — every segment request went to R2. Playback still worked, so nothing alerted; the signal was Class B operation volume and R2 cost, plus latency on repeat plays.
2. **Assert the cache status in the serving path.** When serving through a Worker fronting R2, check `cf.coloCacheCacheStatus` / the response cache status after `cache.match()` / fetch, and emit a metric per request (`segment_serve{cache=HIT|MISS}`). Alert on sustained MISS ratio above a threshold — a working cache is a runtime property, not a deploy-time one.
3. **Synthetic playback checks.** A scheduled probe fetches a known playlist, then fetches the same segment twice and asserts the second response is an edge HIT and that `Cache-Control: immutable` survived. This catches header-stripping regressions within minutes instead of at invoice time.

## Segment lifecycle and cost hygiene

1. **Lifecycle rules per prefix.** Keep lifecycle config scoped: originals under `uploads/` get a long retention (they are the re-transcode source), renditions under `{videoId}/` get deleted when the video is deleted, and temp/partial prefixes get short expirations (1 day) so failed transcodes do not linger.
2. **Delete by prefix, not by enumeration.** Removing a video means deleting its rendition prefix wholesale; enumerating and deleting segment-by-segment from application code is slow and racy against players mid-stream.
3. **Use the Workers API for high-throughput object ops.** The Cloudflare REST API for R2 is rate-limited (1,200 requests per 5 minutes account-wide) — bulk segment operations must go through the Workers binding or S3-compatible API, which are built for that throughput.
4. **Measure storage by class.** Track storage separately for originals vs renditions; the rendition ladder (not the originals) dominates segment count, and it is the part you can re-derive at will.

## Gotchas

1. **A Worker that reads a segment body via `await response.text()` breaks streaming.** Forward bodies verbatim (or re-wrap in a `ReadableStream`); materializing them re-introduces the memory ceiling the pipeline was designed to avoid.
2. **Playlist overwrites can 429 under concurrency.** Serialize playlist writes per video; a stalled writer holding the playlist lock must time out so a live-style window can advance.
3. **`r2.dev` looks fine in dev and costs a fortune in prod.** The cache-miss incident class is invisible until traffic scales — verify cache headers on the actual custom domain, in production, not on the dev endpoint.
4. **Auto-abort of incomplete multipart uploads is 7 days by default.** Without an explicit `abort()` on transcode failure, orphaned original parts accrue storage cost for a week.
5. **Do not trust multipart ETags for integrity.** They are derived from part hashes, not the object content — store a separate SHA-256 if you need verifiable integrity.

## Related

- `cloudflare/r2-multipart-upload.md` — client-driven multipart mechanics
- `cloudflare/r2-lifecycle-rules.md` — lifecycle rule configuration
- `cloudflare/r2-best-practices.md`
- `cloudflare/stream-best-practices.md` — the managed-service alternative
- `cloudflare/workers-cache-api.md`
- R2 upload docs (multipart limits, streaming `put()`): https://developers.cloudflare.com/r2/objects/upload-objects/
- R2 Workers API reference: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- R2 platform limits: https://developers.cloudflare.com/r2/platform/limits/
- Serving HLS from S3-compatible storage (applies to R2): https://hlsbook.net/how-to-serve-hls-video-from-an-s3-bucket/
