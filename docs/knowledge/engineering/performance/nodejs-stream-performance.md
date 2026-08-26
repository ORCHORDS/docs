# nodejs-stream-performance

**Issue:** Large data loaded into memory instead of streamed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Loading large files, HTTP responses, or database results into memory before processing causes high memory usage and blocks the event loop. Streams process data chunk by chunk.

## Pattern / Solution
1. Pipe streams: fs.createReadStream('large.csv').pipe(csvParser).pipe(responseStream).\n2. Use stream.pipeline (Node 10+) for proper error handling.\n3. Use async iteration for readable streams: for await (const chunk of readable) { ... }.\n4. Set highWaterMark to tune buffer size (default 16 KB for objectMode streams).\n5. Use Transform streams for in-flight data transformation.

## Gotchas
- pipe does not propagate errors; use pipeline or add error handlers to each stream.\n- Backpressure: if the writable is slower than the readable, data buffers in memory.\n- HTTP request body is a Readable stream; not buffering it avoids memory issues for large uploads.

## Related
nodejs-event-loop-lag, nodejs-heap-snapshots, database-query-performance
