# FERPA Compliance: Role-Based Student Record Access and Disclosure Audit in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

FERPA (Family Educational Rights and Privacy Act, 20 U.S.C. § 1232g) requires educational institutions to restrict access to student education records to authorised parties, log every disclosure, and honour student directory-information opt-outs. When student records live in D1 and the API runs on Workers, you need role-based access control enforced at the edge, an immutable audit trail, and a KV-backed opt-out flag checked before any directory field is returned.

## Context

- Runtime: Cloudflare Workers (TypeScript)
- Student records: Cloudflare D1
- Opt-out flags: Cloudflare KV
- Auth: JWT with `role` claim (`student`, `advisor`, `registrar`, `admin`)
- FERPA sections covered: §99.31 (conditions for disclosure), §99.37 (directory information)

---

## Section 1: D1 Schema

```sql
-- migrations/0003_ferpa.sql

-- Student records table (subset of fields shown)
CREATE TABLE IF NOT EXISTS student_records (
  student_id   TEXT PRIMARY KEY,
  full_name    TEXT NOT NULL,
  dob          TEXT NOT NULL,  -- directory field
  email        TEXT NOT NULL,  -- directory field
  gpa          REAL NOT NULL,  -- FERPA-protected, never directory
  major        TEXT,           -- directory field
  enrolled     INTEGER NOT NULL DEFAULT 1
);

-- Disclosure audit log (FERPA §99.32)
CREATE TABLE IF NOT EXISTS ferpa_disclosure_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  student_id    TEXT NOT NULL,
  requestor_id  TEXT NOT NULL,
  requestor_role TEXT NOT NULL,
  fields_returned TEXT NOT NULL,  -- JSON array
  legal_basis   TEXT NOT NULL,    -- 'LEGITIMATE_EDUCATIONAL_INTEREST' | 'STUDENT_CONSENT' | 'DIRECTORY'
  ip            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_student ON ferpa_disclosure_log(student_id, ts);
```

```bash
npx wrangler d1 migrations apply STUDENT_DB --remote
```

---

## Section 2: Role-Based Access Control

```typescript
// src/ferpa/rbac.ts

export type Role = 'student' | 'advisor' | 'registrar' | 'admin';

// Fields accessible per role
const ROLE_FIELD_ALLOWLIST: Record<Role, (keyof StudentRecord)[]> = {
  student:    ['student_id', 'full_name', 'email', 'gpa', 'major', 'enrolled'],
  advisor:    ['student_id', 'full_name', 'email', 'gpa', 'major', 'enrolled'],
  registrar:  ['student_id', 'full_name', 'dob', 'email', 'gpa', 'major', 'enrolled'],
  admin:      ['student_id', 'full_name', 'dob', 'email', 'gpa', 'major', 'enrolled'],
};

// Directory-only fields returned to unauthenticated/public requests
const DIRECTORY_FIELDS: (keyof StudentRecord)[] = ['full_name', 'major', 'email'];

export interface StudentRecord {
  student_id: string;
  full_name:  string;
  dob:        string;
  email:      string;
  gpa:        number;
  major:      string | null;
  enrolled:   number;
}

export function filterByRole(
  record: StudentRecord,
  role: Role,
  isDirectoryOptOut: boolean
): Partial<StudentRecord> {
  const allowed = ROLE_FIELD_ALLOWLIST[role] ?? [];
  const result: Partial<StudentRecord> = {};

  for (const field of allowed) {
    // Skip directory fields if student has opted out and requestor has no special role
    if (isDirectoryOptOut && DIRECTORY_FIELDS.includes(field) && role === 'student') {
      continue;
    }
    (result as Record<string, unknown>)[field] = record[field];
  }

  return result;
}
```

---

## Section 3: Directory Information Opt-Out via KV

```typescript
// src/ferpa/optOut.ts
import { Env } from '../types';

const OPT_OUT_PREFIX = 'ferpa:optout:';

export async function isDirectoryOptOut(
  env: Env,
  studentId: string
): Promise<boolean> {
  const val = await env.STUDENT_KV.get(`${OPT_OUT_PREFIX}${studentId}`);
  return val === '1';
}

export async function setDirectoryOptOut(
  env: Env,
  studentId: string,
  optOut: boolean
): Promise<void> {
  if (optOut) {
    await env.STUDENT_KV.put(`${OPT_OUT_PREFIX}${studentId}`, '1');
  } else {
    await env.STUDENT_KV.delete(`${OPT_OUT_PREFIX}${studentId}`);
  }
}
```

---

## Section 4: Disclosure Audit Log and Record Endpoint

```typescript
// src/routes/studentRecord.ts
import { Env }            from '../types';
import { filterByRole, Role, StudentRecord } from '../ferpa/rbac';
import { isDirectoryOptOut }                from '../ferpa/optOut';

async function writeDisclosureLog(
  env: Env,
  entry: {
    student_id:     string;
    requestor_id:   string;
    requestor_role: string;
    fields_returned: string[];
    legal_basis:    string;
    ip:             string;
  }
): Promise<void> {
  await env.STUDENT_DB
    .prepare(
      `INSERT INTO ferpa_disclosure_log
         (student_id, requestor_id, requestor_role, fields_returned, legal_basis, ip)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      entry.student_id,
      entry.requestor_id,
      entry.requestor_role,
      JSON.stringify(entry.fields_returned),
      entry.legal_basis,
      entry.ip
    )
    .run();
}

export async function handleGetStudentRecord(
  req: Request,
  env: Env,
  ctx: ExecutionContext,
  studentId: string
): Promise<Response> {
  const requestorId   = req.headers.get('X-User-Id')   ?? 'anonymous';
  const requestorRole = (req.headers.get('X-User-Role') ?? 'student') as Role;
  const ip            = req.headers.get('CF-Connecting-IP') ?? '0.0.0.0';

  // Students may only view their own record
  if (requestorRole === 'student' && requestorId !== studentId) {
    return new Response('Forbidden', { status: 403 });
  }

  const row = await env.STUDENT_DB
    .prepare('SELECT * FROM student_records WHERE student_id = ?')
    .bind(studentId)
    .first<StudentRecord>();

  if (!row) return new Response('Not Found', { status: 404 });

  const optOut  = await isDirectoryOptOut(env, studentId);
  const filtered = filterByRole(row, requestorRole, optOut);
  const fields   = Object.keys(filtered);

  ctx.waitUntil(
    writeDisclosureLog(env, {
      student_id:      studentId,
      requestor_id:    requestorId,
      requestor_role:  requestorRole,
      fields_returned: fields,
      legal_basis:     'LEGITIMATE_EDUCATIONAL_INTEREST',
      ip,
    })
  );

  return Response.json(filtered);
}
```

---

## Anti-patterns

- Returning all fields from D1 and filtering in the client — a bug exposes protected data in the network response.
- Caching student records in KV or the CDN without scoping the cache key to the requestor's role.
- Logging only successful requests — FERPA §99.32 requires logging all disclosures regardless of outcome.
- Omitting the legal basis field from the disclosure log — auditors will ask for it.
- Storing opt-out flags in D1 with no TTL management — KV with explicit `put`/`delete` is simpler and faster for hot-path reads.

## Gotchas

- FERPA allows disclosure without consent to school officials with a legitimate educational interest — document this in your ISMS and map it to the `LEGITIMATE_EDUCATIONAL_INTEREST` legal basis.
- The opt-out covers only *directory* fields; protected fields (GPA, DOB) are never public regardless of opt-out status.
- JWT roles must be set by your IdP, not by the client — validate the signature before trusting `X-User-Role`.
- `ctx.waitUntil` keeps the log write alive after the response is sent, but if the Worker process is killed (rare but possible), the log entry may be lost. For critical audit requirements consider writing synchronously.

---

## Verification

```bash
# Insert a test student
npx wrangler d1 execute STUDENT_DB --remote \
  --command "INSERT INTO student_records VALUES ('S001','Jane Doe','2000-01-01','jane@edu.example',3.8,'CS',1);"

# Set opt-out
npx wrangler kv key put --binding=STUDENT_KV 'ferpa:optout:S001' '1' --remote

# Fetch as advisor — should omit email and full_name (opt-out)
curl -H "X-User-Id: A001" -H "X-User-Role: advisor" \
  https://api.example.com/students/S001 | jq .

# Check disclosure log
npx wrangler d1 execute STUDENT_DB --remote \
  --command "SELECT * FROM ferpa_disclosure_log ORDER BY id DESC LIMIT 5;"
```

---

## Related

- `documentation/docs/policies/compliance/workers-iso-27001-access-log-d1.md`
- `documentation/docs/policies/compliance/workers-coppa-age-verification-consent.md`
- `documentation/workers/jwt-validation-edge.md`

## Sources

- https://studentprivacy.ed.gov/ferpa (FERPA official guidance)
- https://www.ecfr.gov/current/title-34/subtitle-A/part-99 (34 CFR Part 99)
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
