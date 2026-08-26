# Email Attachment Virus Scanning via VirusTotal before R2 Storage

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Inbound emails with file attachments must be scanned for malware before they are persisted in R2 or forwarded to staff.
Using the VirusTotal Files API from a Queue consumer allows scanning to happen asynchronously without blocking the email handler's 30-second CPU budget.

## Context
Cloudflare Workers Email handlers extract attachments and enqueue metadata; a Queue consumer uploads each file hash to VirusTotal `/files/report` (or submits the raw bytes if the hash is unknown), then records the verdict in D1.
The R2 object is written with an `x-amz-meta-scan-status` custom metadata field that downstream systems use to gate delivery.
The VirusTotal API key is stored as a Worker secret.

---

## Architecture / Flow

```
Email arrives → email() handler
  ↓
postal-mime extracts parts
  ↓
Each attachment → SHA-256 hash computed → enqueue { key, hash, size, mimeType }
  ↓ (async, Queue consumer)
VirusTotal hash lookup → CLEAN / MALICIOUS / UNKNOWN
  ↓ UNKNOWN → upload raw bytes → wait for analysis
  ↓
D1: record verdict
R2: copy object with updated custom metadata
  ↓ MALICIOUS → quarantine (do not forward) / alert
```

```typescript
export interface Env {
  ATTACHMENTS_R2: R2Bucket;
  SCAN_QUEUE: Queue<ScanJob>;
  DB: D1Database;
  VT_API_KEY: string;   // wrangler secret put VT_API_KEY
}

interface ScanJob {
  r2Key: string;
  sha256: string;
  filename: string;
  messageId: string;
  contentType: string;
  sizeBytes: number;
}
```

## Email Handler — Hashing and Enqueuing

```typescript
// src/email-handler.ts
import PostalMime from 'postal-mime';
import { EmailMessage } from 'cloudflare:email';

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    const raw = await new Response(message.raw).arrayBuffer();
    const parsed = await new PostalMime().parse(raw);

    const messageId = parsed.headers
      .find((h) => h.key === 'message-id')
      ?.value?.replace(/[<>]/g, '')
      .trim() ?? crypto.randomUUID();

    for (const att of parsed.attachments ?? []) {
      if (att.disposition === 'inline') continue;   // skip embedded images

      const content =
        att.content instanceof Uint8Array
          ? att.content.buffer
          : (att.content as ArrayBuffer);

      // Compute SHA-256 hash — used as VirusTotal lookup key
      const hashBuffer = await crypto.subtle.digest('SHA-256', content);
      const sha256 = Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');

      const safeFilename = (att.filename ?? 'attachment').replace(/[^\w.\-]/g, '_');
      const r2Key = `pending/${messageId}/${sha256}/${safeFilename}`;

      // Store in R2 under "pending/" prefix — not yet cleared for delivery
      await env.ATTACHMENTS_R2.put(r2Key, content, {
        httpMetadata: { contentType: att.mimeType ?? 'application/octet-stream' },
        customMetadata: { scanStatus: 'pending', messageId, sha256 },
      });

      // Enqueue scan job
      await env.SCAN_QUEUE.send({
        r2Key,
        sha256,
        filename: safeFilename,
        messageId,
        contentType: att.mimeType ?? 'application/octet-stream',
        sizeBytes: (content as ArrayBuffer).byteLength,
      });
    }

    // Forward regardless — attachment access is gated on scan result
    await message.forward('inbox@example.com');
  },
};
```

## Queue Consumer — VirusTotal Scanning

```typescript
// src/scan-consumer.ts
const VT_BASE = 'https://www.virustotal.com/api/v3';

export default {
  async queue(batch: MessageBatch<ScanJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;
      try {
        const verdict = await scanWithVirusTotal(job, env);
        await recordVerdict(job, verdict, env);
        msg.ack();
      } catch (err) {
        console.error(`Scan failed for ${job.sha256}:`, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

type Verdict = 'clean' | 'malicious' | 'suspicious' | 'unknown' | 'error';

async function scanWithVirusTotal(job: ScanJob, env: Env): Promise<Verdict> {
  const headers = { 'x-apikey': env.VT_API_KEY };

  // 1. Hash lookup first — free tier allows up to 500 lookups/day
  const hashResp = await fetch(`${VT_BASE}/files/${job.sha256}`, { headers });

  if (hashResp.status === 200) {
    const data = (await hashResp.json()) as VtFileReport;
    return classifyVtStats(data.data.attributes.last_analysis_stats);
  }

  if (hashResp.status !== 404) {
    throw new Error(`VT hash lookup returned ${hashResp.status}`);
  }

  // 2. Hash unknown — upload the raw bytes from R2
  if (job.sizeBytes > 32 * 1024 * 1024) {
    // Files > 32 MB require upload URL (VT large file API)
    return await scanLargeFile(job, env, headers);
  }

  const obj = await env.ATTACHMENTS_R2.get(job.r2Key);
  if (!obj) throw new Error(`R2 object not found: ${job.r2Key}`);

  const fileBytes = await obj.arrayBuffer();
  const form = new FormData();
  form.append('file', new Blob([fileBytes], { type: job.contentType }), job.filename);

  const uploadResp = await fetch(`${VT_BASE}/files`, {
    method: 'POST',
    headers,
    body: form,
  });

  if (!uploadResp.ok) throw new Error(`VT upload failed: ${uploadResp.status}`);

  const uploadData = (await uploadResp.json()) as { data: { id: string } };
  const analysisId = uploadData.data.id;

  // 3. Poll for analysis result (max 60 s)
  for (let i = 0; i < 12; i++) {
    await sleep(5_000);
    const resultResp = await fetch(`${VT_BASE}/analyses/${analysisId}`, { headers });
    if (!resultResp.ok) continue;
    const result = (await resultResp.json()) as VtAnalysisReport;
    if (result.data.attributes.status === 'completed') {
      return classifyVtStats(result.data.attributes.stats);
    }
  }

  return 'unknown';   // timed out — treat conservatively
}

async function scanLargeFile(job: ScanJob, env: Env, headers: Record<string, string>): Promise<Verdict> {
  const urlResp = await fetch(`${VT_BASE}/files/upload_url`, { headers });
  if (!urlResp.ok) return 'unknown';
  const { data: uploadUrl } = (await urlResp.json()) as { data: string };

  const obj = await env.ATTACHMENTS_R2.get(job.r2Key);
  if (!obj) return 'unknown';

  const form = new FormData();
  form.append('file', new Blob([await obj.arrayBuffer()], { type: job.contentType }), job.filename);
  const resp = await fetch(uploadUrl, { method: 'POST', headers, body: form });
  if (!resp.ok) return 'unknown';

  return 'unknown';   // large-file analysis is async; a second job should poll
}

function classifyVtStats(stats: VtStats): Verdict {
  if ((stats.malicious ?? 0) >= 3)  return 'malicious';
  if ((stats.suspicious ?? 0) >= 5) return 'suspicious';
  if ((stats.undetected ?? 0) > 0)  return 'clean';
  return 'unknown';
}

interface VtStats { malicious?: number; suspicious?: number; undetected?: number; }
interface VtFileReport { data: { attributes: { last_analysis_stats: VtStats } } }
interface VtAnalysisReport { data: { attributes: { status: string; stats: VtStats } } }

function sleep(ms: number) { return new Promise((r) => setTimeout(r, ms)); }
```

## Recording the Verdict

```typescript
async function recordVerdict(job: ScanJob, verdict: Verdict, env: Env): Promise<void> {
  // Update R2 object custom metadata by copying to "scanned/" prefix
  const srcObj = await env.ATTACHMENTS_R2.get(job.r2Key);
  if (srcObj) {
    const destKey = job.r2Key.replace(/^pending\//, `scanned/${verdict}/`);
    await env.ATTACHMENTS_R2.put(destKey, await srcObj.arrayBuffer(), {
      httpMetadata: srcObj.httpMetadata,
      customMetadata: { ...srcObj.customMetadata, scanStatus: verdict, scannedAt: new Date().toISOString() },
    });
    await env.ATTACHMENTS_R2.delete(job.r2Key);   // remove pending copy
  }

  // Write verdict to D1
  await env.DB.prepare(
    `INSERT OR REPLACE INTO attachment_scan_results
       (sha256, verdict, scanned_at, message_id, filename)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(job.sha256, verdict, new Date().toISOString(), job.messageId, job.filename)
    .run();

  if (verdict === 'malicious' || verdict === 'suspicious') {
    console.warn(`MALWARE DETECTED: ${job.filename} (${job.sha256}) in message ${job.messageId} — verdict: ${verdict}`);
    // Add alerting here: Workers Analytics Engine, PagerDuty webhook, etc.
  }
}
```

## Anti-patterns
- Calling VirusTotal synchronously in the email handler — the combined scan + poll can take 60+ seconds, far exceeding the email handler budget.
- Deleting the R2 object without archiving if malicious — retain malicious files in a restricted prefix for forensic/legal purposes.
- Using the hash lookup as the only check — novel malware will return 404; always fall back to file upload for unknown hashes.
- Sending the raw file bytes to VT for every message — hash lookup first; the free tier allows 500 uploads/day but unlimited hash reads.
- Forwarding to staff before the scan verdict is known — gate forwarding on the `scanned/clean/` R2 prefix or a D1 verdict record.

## Gotchas
- VirusTotal free-tier API is limited to 4 requests/minute and 500 uploads/day; implement exponential backoff and monitor quota with Analytics Engine.
- `new FormData()` in Workers does not support `Blob` with a filename in all runtime versions — test with Miniflare locally before deploying.
- R2 does not support in-place metadata updates; the copy-then-delete pattern is the only way to change `customMetadata`.
- VirusTotal analysis IDs expire after 24 hours; do not store them as permanent references.
- Files encrypted or password-protected (common in phishing) will return clean results on VT — add a secondary check for password-protected ZIPs.

## Verification

```sql
-- D1: check recent scan results
SELECT verdict, COUNT(*) AS n FROM attachment_scan_results
GROUP BY verdict ORDER BY n DESC;

-- D1: find malicious files
SELECT filename, sha256, scanned_at, message_id
FROM attachment_scan_results
WHERE verdict IN ('malicious', 'suspicious')
ORDER BY scanned_at DESC LIMIT 20;
```

```bash
# R2: check objects in each verdict prefix
wrangler r2 object list email-attachments --prefix "scanned/malicious/" --remote
wrangler r2 object list email-attachments --prefix "scanned/clean/" --remote
wrangler r2 object list email-attachments --prefix "pending/" --remote
```

## Related
- `email-multipart-mime-parser-workers.md` — extracting attachments from inbound MIME
- `email-attachment-scanning-r2-workers-ai.md` — Workers AI approach to content scanning
- `email-attachment-patterns.md` — attachment handling strategies
- `email-pdf-attachment-generation-r2-workers.md` — generating PDF attachments
- `email-security-audit-trail-d1-immutable-log.md` — logging security events

## Sources
- https://developers.virustotal.com/reference/files-report
- https://developers.virustotal.com/reference/files-upload
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/email-routing/email-workers/
