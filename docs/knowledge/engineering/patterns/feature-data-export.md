# feature-data-export

**Issue:** Data export — CSV, JSON, GDPR
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user wants their data. GDPR says you have to provide it.
You write a SQL query. You format it as JSON. You email
it. The user says "I want CSV." You re-do it. The user
says "I want all my data, not just users." You re-do it
again. You wish you'd built a generic export system.

## Root cause
**Data export is a feature, not a one-off.** Build it
right the first time.

**Source:** GDPR Article 20 (Right to data portability):
https://gdpr-info.eu/art-20-gdpr/

## The "export" design

For each entity the user owns:
- Users, Posts, Comments, Likes, etc.
- All fields (no filtering)
- The user's data only (no other users')

For a complete export:
- All entities
- One file (or one zip)
- Standard format (JSON, CSV)
- Delivered via download or email

## The "JSON" format

For a single entity:
```json
{
  "users": [
    {
      "id": "u_123",
      "email": "alice@example.com",
      "displayName": "Alice",
      "createdAt": "2026-08-09T14:30:00.000Z"
    }
  ],
  "posts": [
    {
      "id": "p_123",
      "title": "Hello",
      "body": "World",
      "authorId": "u_123",
      "createdAt": "2026-08-09T14:30:00.000Z"
    }
  ]
}
```

Each entity is an array; the top-level object has the
entity names.

## The "CSV" format

For a single entity:
```csv
id,email,displayName,createdAt
u_123,alice@example.com,Alice,2026-08-09T14:30:00.000Z
```

Use a library (csv-stringify) for proper escaping.

## The "zip" format

For multiple files:
```
export-u_123-2026-08-09.zip
├── users.json
├── posts.json
├── comments.json
├── media/
│   ├── photo-1.jpg
│   └── photo-2.jpg
└── README.txt
```

Use a zip library (zip.js, archiver).

## The "async export" pattern

For large exports, run async:
```ts
// 1. User requests export
export async function requestExport(ctx: McContext, env: Env): Promise<{ exportId: string }> {
  const exportId = crypto.randomUUID();
  await env.QUEUE.send({ type: 'export', userId: ctx.user.id, exportId });
  return { exportId };
}

// 2. Worker processes the export
export async function handleQueue(batch: MessageBatch, env: Env): Promise<void> {
  for (const message of batch.messages) {
    if (message.body.type === 'export') {
      await generateExport(message.body.userId, message.body.exportId, env);
      message.ack();
    }
  }
}

async function generateExport(userId: string, exportId: string, env: Env): Promise<void> {
  // 1. Gather all the user's data
  const users = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(userId).all();
  const posts = await env.DB!.prepare(`SELECT * FROM posts WHERE user_id = ?`).bind(userId).all();
  // ... etc

  // 2. Format as JSON
  const data = {
    users: users.results,
    posts: posts.results,
    // ... etc
  };

  // 3. Store in R2
  const key = `exports/${userId}/${exportId}.json`;
  await env.R2!.put(key, JSON.stringify(data, null, 2));

  // 4. Notify the user
  await sendEmail(userId, `Your export is ready: https://example.com/exports/${key}`, env);

  // 5. Set expiration (the link expires in 7 days)
  await env.R2!.put(key + '.meta', JSON.stringify({ expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000 }));
}
```

The user gets a download link when the export is ready.

## The "presigned download" pattern

For private files, use a presigned URL:
```ts
async function getExportDownloadUrl(exportId: string, userId: string, env: Env): Promise<string> {
  const key = `exports/${userId}/${exportId}.json`;
  return env.R2!.createPresignedUrl({
    method: 'GET',
    key,
    expiration: 3600,  // 1 hour
  });
}
```

The user downloads directly from R2.

## The "export audit" pattern

For compliance, log every export:
```ts
await writeAudit(env, {
  userId: ctx.user.id,
  tenantId: ctx.tenant.id,
  action: 'data.exported',
  resourceType: 'export',
  resourceId: exportId,
  metadata: { format: 'json', size: fileSize },
});
```

GDPR requires proof of data access.

## The "GDPR rights" pattern

GDPR gives users:
- **Right to access** (Article 15): Get a copy of their data
- **Right to portability** (Article 20): Get the data in a
  machine-readable format
- **Right to erasure** (Article 17): Delete their data

A complete data export covers Article 15 + 20.

## The "erasure" pattern

For GDPR Article 17:
1. **User requests erasure**
2. **Mark for deletion** (soft delete)
3. **Anonymize the data** (replace PII with placeholders)
4. **Delete the user record** (after retention period)
5. **Notify the user** when complete

```ts
async function eraseUser(userId: string, env: Env): Promise<void> {
  // 1. Anonymize PII
  await env.DB!.prepare(
    `UPDATE users SET email = 'deleted-' || id || '@deleted.local', display_name = 'Deleted User' WHERE id = ?`
  ).bind(userId).run();

  // 2. Delete posts (or anonymize)
  await env.DB!.prepare(`DELETE FROM posts WHERE user_id = ?`).bind(userId).run();

  // 3. Delete media
  const media = await env.R2!.list({ prefix: `media/${userId}/` });
  for (const obj of media.objects) {
    await env.R2!.delete(obj.key);
  }

  // 4. Audit
  await writeAudit(env, {
    action: 'user.erased',
    resourceType: 'user',
    resourceId: userId,
  });
}
```

The data is gone (or anonymized); the audit shows it.

## The "data portability" pattern

For portability, use standard formats:
- **JSON:** Most flexible; easy to parse
- **CSV:** Spreadsheet-friendly
- **XML:** Legacy systems
- **YAML:** Human-readable

For most apps, **JSON** is the default. Offer **CSV** as a
secondary format.

## The "export performance" pattern

For large exports, stream the data:
```ts
async function streamExport(userId: string, env: Env): Promise<ReadableStream> {
  return new ReadableStream({
    async start(controller) {
      controller.enqueue(new TextEncoder().encode('{"users":['));

      const users = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(userId).all();
      for (const user of users.results) {
        controller.enqueue(new TextEncoder().encode(JSON.stringify(user) + ','));
      }

      // ... more entities

      controller.enqueue(new TextEncoder().encode(']}'));
      controller.close();
    },
  });
}
```

The user starts downloading immediately; the server streams
the data.

## The "data export" UX

For a friendly UX:
- **"Request export"** button
- **"Export queued"** message
- **"Export ready"** email with download link
- **"Download expires in 7 days"** warning
- **"Delete export"** option

The user knows what's happening at each step.

## Verification
- **Test:** Export contains the right data
- **Test:** Erasure removes the right data
- **Live:** Exports are monitored; alerts on failures
- **Audit:** Quarterly review of data handling

## Gotchas
- **The "export without audit" anti-pattern.** GDPR
  requires proof of data access. Log every export.
- **The "export with broken file" anti-pattern.** Validate
  the export (parses, has the right fields).
- **The "export with PII leak" anti-pattern.** The export
  is the user's data, but log files or storage may leak.
- **The "export without expiration" anti-pattern.** A
  download link that never expires is a security risk.
- **The "erasure without cascade" anti-pattern.** Deleting
  the user but not the posts leaves orphan data.
- **The "export in production blocking" anti-pattern.** A
  large export can block the DB. Run async.

## Related
- `gdpr-article-17-erasure.md`
- `audit-log-as-product.md`
- `cron-scheduling.md` (auto-delete expired exports)
- `cloudflare/r2-large-file-patterns.md` (storage)
- `cloudflare/workers-workers-queues-patterns.md` (async)
- GDPR: https://gdpr-info.eu/
