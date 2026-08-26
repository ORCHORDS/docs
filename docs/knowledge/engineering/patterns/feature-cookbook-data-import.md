# feature-cookbook-data-import

**Issue:** Data import — CSV, JSON, batch, validation
**Date:** 2026-08-09
**Status:** documented

## Symptom
The user uploads a CSV with 100k users. You process
it in a Worker. The Worker times out. Half the users
are imported. The user re-uploads. The other half is
imported. You have duplicates.

## Root cause
**Large imports in a single Worker don't work.** Use
a queue.

**Source:** Various import guides.

## The "import" workflow

For a large import:
1. **Upload:** User uploads the file to R2
2. **Validate:** Schema + content
3. **Process:** Batch + insert
4. **Report:** Success / errors

## The "upload" pattern

For upload, R2 presigned URL:
```ts
// 1. Get a presigned URL
const url = await env.R2!.createPresignedUrl({
  key: `imports/${userId}/${jobId}.csv`,
  expiration: 3600,
});

// 2. Client uploads directly
await fetch(url, { method: 'PUT', body: file });
```

The upload is direct to R2.

## The "validate" pattern

For validation, parse + check:
```ts
async function validateCSV(file: File, env: Env): Promise<{ valid: boolean; errors: string[] }> {
  const text = await file.text();
  const lines = text.split('\n');
  const errors: string[] = [];

  // Check the header
  const expectedHeaders = ['email', 'displayName'];
  const headers = lines[0].split(',');
  for (const expected of expectedHeaders) {
    if (!headers.includes(expected)) {
      errors.push(`Missing header: ${expected}`);
    }
  }

  // Check the rows
  for (let i = 1; i < lines.length; i++) {
    const row = lines[i].split(',');
    if (!row[0]?.includes('@')) {
      errors.push(`Row ${i}: invalid email`);
    }
  }

  return { valid: errors.length === 0, errors };
}
```

The validation is comprehensive.

## The "process" pattern

For processing, use a queue:
```ts
// 1. Enqueue the import
await env.QUEUE.send({ type: 'import', jobId, key });

// 2. Worker processes
async function processImport(job: ImportJob, env: Env): Promise<void> {
  const file = await env.R2!.get(job.key);
  const text = await file!.text();
  const lines = text.split('\n');

  const BATCH_SIZE = 100;
  for (let i = 1; i < lines.length; i += BATCH_SIZE) {
    const batch = lines.slice(i, i + BATCH_SIZE);

    // Build a single SQL
    const placeholders = batch.map(() => '(?, ?)').join(',');
    const values = batch.flatMap(row => {
      const [email, displayName] = row.split(',');
      return [email.trim(), displayName.trim()];
    });

    await env.DB!.prepare(
      `INSERT OR IGNORE INTO users (id, email, displayName) VALUES ${placeholders}`
    ).bind(...values).run();
  }
}
```

The import is batched.

## The "idempotent" pattern

For idempotency, dedupe by email:
```sql
INSERT OR IGNORE INTO users (id, email, displayName) VALUES (?, ?, ?)
```

A duplicate email is ignored.

## The "progress" pattern

For progress, track in KV:
```ts
async function updateProgress(jobId: string, processed: number, total: number, env: Env): Promise<void> {
  await env.KV!.put(`import:${jobId}:progress`, JSON.stringify({
    processed,
    total,
    percent: (processed / total) * 100,
  }), { expirationTtl: 86400 });
}
```

The progress is queryable.

## The "report" pattern

For a report, the summary:
```ts
async function generateReport(jobId: string, env: Env): Promise<ImportReport> {
  const success = await env.DB!.prepare(
    `SELECT COUNT(*) FROM import_log WHERE job_id = ? AND status = 'success'`
  ).bind(jobId).first();

  const failed = await env.DB!.prepare(
    `SELECT * FROM import_log WHERE job_id = ? AND status = 'failed'`
  ).bind(jobId).all();

  return {
    success: success!.count,
    failed: failed.results.length,
    errors: failed.results.map(r => r.error),
  };
}
```

The report is generated.

## The "download errors" pattern

For errors, downloadable file:
```ts
async function downloadErrors(jobId: string, env: Env): Promise<Response> {
  const errors = await env.DB!.prepare(
    `SELECT * FROM import_log WHERE job_id = ? AND status = 'failed'`
  ).bind(jobId).all();

  const csv = [
    'row,error',
    ...errors.results.map(e => `${e.row},${e.error}`),
  ].join('\n');

  return new Response(csv, {
    headers: { 'content-type': 'text/csv' },
  });
}
```

The errors are downloadable.

## The "rollback" pattern

For rollback, mark as `imported`:
```sql
-- Add a job_id to each import
ALTER TABLE users ADD COLUMN import_job_id TEXT;

-- Mark on import
UPDATE users SET import_job_id = ? WHERE id IN (...);

-- Rollback
DELETE FROM users WHERE import_job_id = ?;
```

The rollback is selective.

## The "streaming" pattern

For streaming (large files), parse line by line:
```ts
async function* parseCSV(file: R2ObjectBody, env: Env): AsyncGenerator<Row> {
  const reader = file.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      yield parseRow(line);
    }
  }
}
```

The stream is line-by-line.

## The "data type" pattern

For data types, parse:
```ts
function parseRow(line: string): Row {
  const [email, displayName, ageStr] = line.split(',');
  return {
    email: email.trim(),
    displayName: displayName.trim(),
    age: parseInt(ageStr, 10) || 0,
  };
}
```

The types are parsed.

## The "encoding" pattern

For encoding, handle UTF-8:
```ts
const decoder = new TextDecoder('utf-8');
const text = decoder.decode(file.body);
```

UTF-8 is the standard.

## The "import anti-pattern" anti-patterns

### 1. Import in a single Worker
- **Issue:** Worker times out
- **Fix:** Use a queue

### 2. No validation
- **Issue:** Bad data is imported
- **Fix:** Validate first

### 3. No idempotency
- **Issue:** Re-import creates duplicates
- **Fix:** Dedup by email

### 4. No progress
- **Issue:** User doesn't know status
- **Fix:** Progress in KV

### 5. No rollback
- **Issue:** Bad import can't be undone
- **Fix:** Mark with job_id

### 6. No error report
- **Issue:** User doesn't know what failed
- **Fix:** Downloadable errors

## Verification
- **Test:** Import is correct
- **Test:** Duplicates are deduped
- **Test:** Progress is accurate
- **Live:** Import is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no validation" anti-pattern.** Validate first.
- **The "no idempotency" anti-pattern.** Dedup.
- **The "no rollback" anti-pattern.** Mark with job_id.

## Related
- `feature-cookbook-batch-processing.md`
- `feature-cookbook-data-import.md`
- `feature-cookbook-error-recovery.md`
- `feature-cookbook-file-upload.md`
- `cloudflare/r2-large-file-patterns.md`
- `feature-cookbook-data-modeling.md`
- `feature-cookbook-data-warehouse.md`
