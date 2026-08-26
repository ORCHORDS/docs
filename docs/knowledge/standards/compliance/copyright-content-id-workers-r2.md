# Copyright Content-ID Pipeline on Cloudflare Workers and R2

**Project:** example project (example.com) — 21+ anonymous social platform
**Author:** example.com
**Scope:** EU/US users, DMCA safe harbour, automated fingerprinting, R2 quarantine
**Last reviewed:** 2025-08

---

## 1. Overview

User-generated content platforms face significant copyright liability unless they implement
effective repeat-infringer policies and respond expeditiously to takedown notices. In the US,
Section 512 of the Digital Millennium Copyright Act (DMCA) provides safe harbour conditioned on
these obligations. In the EU, Article 17 of the Copyright in the Digital Single Market Directive
(CDSMD 2019/790) imposes a stricter "best efforts" duty on platforms above 5 million users with
€10M+ turnover — requiring upload filters for licensed works where feasible.

This article describes an automated copyright detection pipeline built on Cloudflare Workers and R2,
covering:
- Audio/video/image fingerprint generation and hash comparison in Workers
- DMCA safe harbour compliance mechanics
- R2 quarantine bucket and retention during dispute
- Counter-notice workflow
- Audit trail requirements

---

## 2. Legal Framework

### 2.1 DMCA Section 512 (US)

Safe harbour requires the platform to:

1. **Designated Agent**: Register a DMCA agent with the US Copyright Office and publish contact
   details at `/dmca` or in the Terms of Service.
2. **Expeditious removal**: Remove infringing content promptly upon receipt of a compliant
   takedown notice (512(c)(1)(A)(iii)).
3. **No actual knowledge**: Act on actual knowledge and red-flag knowledge of infringement.
4. **Repeat infringer policy**: Adopt and reasonably implement a policy terminating accounts of
   repeat infringers (512(i)(1)(A)).
5. **Standard technical measures**: Accommodate standard technical measures used by rights holders
   (512(i)(1)(B)).

The platform must not receive a financial benefit directly attributable to infringing activity
and must not have the right and ability to control such activity (512(c)(1)(B)).

### 2.2 EU CDSMD Article 17

Platforms that have been online for more than 3 years and have revenue above €10M or more than
5 million unique monthly visitors are "online content-sharing service providers" (OCSSPs) under
Article 17. Obligations include:

- Making best efforts to obtain **authorisation** from rights holders.
- Making best efforts to ensure **unavailability** of specific works notified by rights holders.
- Acting **expeditiously** upon notification to disable access and making **best efforts** to
  prevent future uploads of the same works.

Article 17 effectively mandates upload filters for large platforms. Smaller platforms under the
threshold retain the lighter DMCA-style regime.

### 2.3 Interaction Summary

| Dimension              | DMCA (US)                    | CDSMD Art. 17 (EU)            |
|------------------------|------------------------------|-------------------------------|
| Proactive filter duty  | No (react to notices)        | Yes (best-efforts prevention) |
| Liability trigger      | Knowledge + no action        | Failure to obtain licence     |
| Counter-notice right   | Yes (512(g))                 | Yes (Art. 17(9))              |
| Wrongful takedown risk | Yes (512(f) — misrepresentation) | Yes                       |
| Threshold              | None                         | 3 yrs + €10M or 5M users     |

---

## 3. Content Fingerprinting Pipeline

### 3.1 Architecture

```
User Upload (mobile/web)
        │
        ▼
Upload Worker (upload.ts)
  ├── Validate MIME type and size
  ├── Write raw file to R2: uploads/raw/{contentId}
  └── Enqueue fingerprinting job: Queue "fingerprint-queue"
        │
        ▼
Fingerprint Worker (fingerprint.ts)  [Queue consumer]
  ├── Read file from R2
  ├── Generate perceptual hash (audio: chromaprint / image: pHash / video: frame sampling)
  ├── Compare hash against KV hash database
  │     ├── MATCH (score > threshold) → quarantine + notify rights holder
  │     └── NO MATCH → move to R2: uploads/live/{contentId}
  └── Write fingerprint record to D1: content_fingerprints
```

### 3.2 Hash Types by Content Type

| Content Type | Algorithm          | Hash Length | Threshold   |
|--------------|--------------------|-------------|-------------|
| Audio        | Chromaprint (AcoustID) | 4×uint32 | Hamming ≤ 8 |
| Image        | pHash (DCT-based)  | 64 bits     | Hamming ≤ 10 |
| Video        | Frame pHash (1fps) | 64 bits/frame | ≥ 90% frame match |
| Text         | SimHash (64-bit)   | 64 bits     | Hamming ≤ 6  |

Cloudflare Workers do not have native audio/video decoding. Options:
- **Workers with WASM**: compile ffmpeg-wasm subset for audio extraction; compute chromaprint in WASM.
- **Offload to Worker Pipelines**: use a Durable Object as a long-running job processor.
- **External micro-service**: call an audio fingerprinting micro-service hosted on a fly.io machine.

For image pHash, a pure-JS DCT implementation is feasible within Worker CPU limits (10ms burst on
the free plan; 50ms on paid).

### 3.3 pHash Implementation Sketch (Image, Workers-compatible)

```typescript
// Simplified 8×8 DCT pHash
async function pHash(imageBytes: ArrayBuffer): Promise<bigint> {
  // 1. Decode image using Canvas API (available in Workers via OffscreenCanvas)
  const blob = new Blob([imageBytes]);
  const bitmap = await createImageBitmap(blob);

  // 2. Resize to 32×32
  const canvas = new OffscreenCanvas(32, 32);
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(bitmap, 0, 0, 32, 32);
  const { data } = ctx.getImageData(0, 0, 32, 32);

  // 3. Convert to greyscale
  const grey = new Float32Array(1024);
  for (let i = 0; i < 1024; i++) {
    const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
    grey[i] = 0.299 * r + 0.587 * g + 0.114 * b;
  }

  // 4. Apply 8×8 DCT (simplified — use full 32×32 DCT in production)
  const dct = computeDCT8x8(grey);

  // 5. Compute mean (excluding DC coefficient)
  const vals = dct.slice(1, 64);
  const mean = vals.reduce((a, b) => a + b) / 63;

  // 6. Build 64-bit hash
  let hash = 0n;
  for (let i = 0; i < 63; i++) {
    if (vals[i] > mean) hash |= (1n << BigInt(i));
  }
  return hash;
}

function hammingDistance(a: bigint, b: bigint): number {
  let x = a ^ b;
  let count = 0;
  while (x > 0n) { count += Number(x & 1n); x >>= 1n; }
  return count;
}
```

### 3.4 KV Hash Database Schema

```
fingerprint:img:{hex64bitHash}  → { contentId, rightsHolder, noticeId, addedAt }
fingerprint:aud:{acoustIdHash}  → { contentId, rightsHolder, noticeId, addedAt }
```

Rights holders submit their hashes via the Trusted Flagger API (DSA Article 22) or directly via
the rights-holder portal. Hashes are written to KV with no expiry (permanent reference set).

Compare incoming hash: iterate KV with prefix `fingerprint:img:` is O(n) and not feasible at scale.
Instead, use a **locality-sensitive hashing (LSH) bucket** approach:

```
fingerprint:img:bucket:{first16bits}  → [{ hash, contentId, rightsHolder }...]
```

This limits comparison to hashes sharing the same 16-bit prefix — reducing lookup from O(n) to O(n/65536).

---

## 4. DMCA Safe Harbour Mechanics

### 4.1 Takedown Notice Processing Worker

Incoming DMCA takedown notices arrive via email or POST to `/api/dmca/takedown`. The Worker:

1. Validates the notice contains all 512(c)(3) elements:
   - Signature of the rights holder or authorised agent
   - Identification of the copyrighted work claimed to be infringed
   - Identification of the material to be removed
   - Contact information of the complainant
   - Good-faith belief statement
   - Perjury statement

2. Writes notice to D1: `dmca_notices` table.
3. Moves content from `uploads/live/{contentId}` to `uploads/quarantine/{contentId}` in R2.
4. Marks D1 `content_items` record as `status = 'quarantined'`.
5. Notifies the uploading user (without revealing claimant identity unless required).
6. Sends acknowledgement to claimant within 24 hours.

```sql
-- D1 schema
CREATE TABLE dmca_notices (
  id              TEXT PRIMARY KEY,
  content_id      TEXT NOT NULL,
  claimant_name   TEXT NOT NULL,
  claimant_email  TEXT NOT NULL,
  work_description TEXT NOT NULL,
  material_url    TEXT NOT NULL,
  good_faith_stmt INTEGER NOT NULL DEFAULT 1,
  perjury_stmt    INTEGER NOT NULL DEFAULT 1,
  received_at     TEXT NOT NULL DEFAULT (datetime('now')),
  status          TEXT NOT NULL DEFAULT 'pending', -- pending | actioned | counter-noticed | restored | withdrawn
  actioned_at     TEXT,
  actioned_by     TEXT
);

CREATE TABLE content_items (
  id        TEXT PRIMARY KEY,
  uploader  TEXT NOT NULL,        -- pseudonymous user ID
  r2_key    TEXT NOT NULL,
  status    TEXT NOT NULL DEFAULT 'live', -- live | quarantined | deleted | restored
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 4.2 R2 Quarantine Bucket

Use a separate R2 bucket `wam-quarantine` with no public access. Content is moved there (not deleted)
to preserve it for counter-notice restoration.

```typescript
async function quarantineContent(
  env: Env,
  contentId: string,
  noticeId: string
): Promise<void> {
  const liveKey = `uploads/live/${contentId}`;
  const quarantineKey = `${noticeId}/${contentId}`;

  // R2 does not have native move; copy then delete
  const obj = await env.R2_LIVE.get(liveKey);
  if (!obj) throw new Error(`Content ${contentId} not found in live bucket`);

  await env.R2_QUARANTINE.put(quarantineKey, obj.body, {
    httpMetadata: obj.httpMetadata,
    customMetadata: { noticeId, quarantinedAt: new Date().toISOString() },
  });
  await env.R2_LIVE.delete(liveKey);
}
```

### 4.3 Counter-Notice Workflow (512(g))

When a user files a counter-notice claiming the takedown was erroneous or based on misidentification:

1. User submits counter-notice via `/api/dmca/counter` containing:
   - User's identification (pseudonymous accounts: supply only a contact email)
   - Identification of the removed material
   - Statement under penalty of perjury that removal was a mistake or misidentification
   - Consent to federal district court jurisdiction

2. Worker writes counter-notice to D1 (`dmca_counter_notices` table).
3. Rights holder is notified and has **10 business days** to seek a court injunction.
4. If no injunction is obtained, content is restored from quarantine to live bucket after
   **10–14 business days** per 512(g)(2)(C).

### 4.4 Repeat Infringer Tracking

```typescript
async function recordInfringement(env: Env, userId: string, noticeId: string): Promise<void> {
  // Increment counter in KV
  const key = `infringer:${userId}`;
  const raw = await env.DMCA_KV.get(key, 'json') as { count: number; noticeIds: string[] } | null;
  const updated = {
    count: (raw?.count ?? 0) + 1,
    noticeIds: [...(raw?.noticeIds ?? []), noticeId],
  };
  await env.DMCA_KV.put(key, JSON.stringify(updated));

  // Terminate account on 3rd confirmed infringement
  if (updated.count >= 3) {
    await terminateAccount(env, userId, 'repeat-infringer');
  }
}
```

---

## 5. Wrongful Takedown Guard (512(f))

Section 512(f) creates liability for knowing misrepresentation in a takedown notice. The platform
must not remove content based on obviously defective notices. Automated notice processing should
flag notices for human review if:
- The claimed URL does not match any live content.
- The work description is generic (e.g., "my video").
- The claimant has previously filed notices found to be in bad faith.

---

## 6. EU CDSMD Article 17 Best-Efforts Upload Filter

For the EU deployment, the fingerprint check must run **before** content becomes publicly visible
(pre-publication filter), not only reactively. The pipeline in Section 3.1 already achieves this
by holding content in `uploads/raw/` until fingerprint check passes.

Rights holders wishing to register reference fingerprints use the Rights Holder Portal API,
which writes hashes to the KV database. example project must:
- Make the portal reasonably accessible.
- Process hash submissions within 24 hours.
- Publish a transparency report on the volume and disposition of notices received.

---

## 7. Checklist

- [ ] DMCA designated agent registered with US Copyright Office
- [ ] `/dmca` page published with agent contact details
- [ ] Fingerprint check runs before content goes live (pre-publication)
- [ ] pHash (image), Chromaprint (audio), frame-pHash (video) implemented
- [ ] KV LSH-bucket hash store with rights-holder records
- [ ] R2 quarantine bucket (`wam-quarantine`) — no public access
- [ ] D1 `dmca_notices` and `dmca_counter_notices` tables populated on each action
- [ ] 24-hour notice acknowledgement SLA
- [ ] 10–14 business day counter-notice restoration timer
- [ ] Repeat-infringer counter in KV; account termination at 3 strikes
- [ ] Rights Holder Portal API for hash submissions (EU Article 17)
- [ ] Annual transparency report on notice volumes

---

## 8. References

- 17 U.S.C. § 512 (DMCA Safe Harbour)
- EU Copyright in the Digital Single Market Directive 2019/790, Article 17
- US Copyright Office DMCA Agent Directory: dmca.copyright.gov
- AcoustID / Chromaprint open-source audio fingerprinting
- ISCC (International Standard Content Code) — W3C community draft
- Cloudflare R2 API documentation — Object lifecycle and bucket management
- EDPB Statement on CDSMD Article 17 and GDPR compatibility (2021)
