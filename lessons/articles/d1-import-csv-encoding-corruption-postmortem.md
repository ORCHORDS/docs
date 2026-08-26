# D1 Import CSV Encoding Corruption Postmortem

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A scheduled nightly ETL job imported a 180 MB CSV export from a legacy CRM system into a Cloudflare D1 database using `wrangler d1 execute --file`. After the import completed without errors, query results for user display names containing non-ASCII characters (accented Latin letters, Japanese kana, Arabic script) were returned as replacement characters (`�`) or garbled multi-byte sequences. Downstream Workers reading these rows emitted malformed JSON responses, and a mobile client that depended on exact name matching for push notification routing silently dropped notifications for ~3 400 affected users for 11 hours before the corruption was detected via a customer complaint.

## Context

The legacy CRM exported CSV files in Windows-1252 encoding (common for older European software). The ETL script used Node.js `fs.readFileSync` with no explicit encoding argument (defaults to UTF-8) and piped the result directly to `wrangler d1 execute --file`. D1 is backed by SQLite, which stores text as UTF-8. When Windows-1252 bytes above 0x7F are interpreted as UTF-8, they form invalid sequences that SQLite either silently truncates or stores verbatim as bytes, producing the replacement-character output on read.

The `wrangler d1 execute` command also has a 10 MB batch limit per HTTP request for local-to-remote imports, which caused the script to split the 180 MB file into chunks — a process that split some multi-byte sequences mid-character, compounding the corruption.

---

## 1. Reproducing the Bug Locally

```typescript
// reproduce-encoding-bug.ts
import { readFileSync, writeFileSync } from "node:fs";

// WRONG: readFileSync defaults to UTF-8 — Windows-1252 bytes above 0x7F become garbage
const badContent = readFileSync("export.csv"); // returns Buffer, but toString() is UTF-8
const sqlWrong = `INSERT INTO users (name) VALUES ('${badContent.toString().split("\n")[1]}');`;

// RIGHT: use iconv-lite to transcode before touching the string
import iconv from "iconv-lite";
const rawBuffer = readFileSync("export.csv");
const transcoded = iconv.decode(rawBuffer, "win1252");
// transcoded is now a proper UTF-8 JS string
console.log(transcoded.slice(0, 200));
```

---

## 2. Safe CSV-to-D1 Import Pipeline

```typescript
// etl/import-csv-to-d1.ts
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import iconv from "iconv-lite";
import { parse } from "csv-parse/sync";
import { execSync } from "node:child_process";

const SOURCE_ENCODING = "win1252"; // detect with `file -i export.csv` or chardet
const INPUT_FILE = process.argv[2]!;
const DB_NAME = process.env.D1_DB_NAME!;

// 1. Transcode to UTF-8
const rawBuffer = readFileSync(INPUT_FILE);
const utf8String = iconv.decode(rawBuffer, SOURCE_ENCODING);

// 2. Validate: reject any replacement characters that survived transcoding
if (utf8String.includes("�")) {
  throw new Error(
    "Transcoding produced replacement characters — check source encoding declaration"
  );
}

// 3. Parse CSV
const rows = parse(utf8String, { columns: true, skip_empty_lines: true, trim: true });

// 4. Generate SQL with parameterized-style escaping (D1 batch insert)
//    D1 execute --file supports SQLite SQL; use multi-row INSERT for speed.
const BATCH = 500;
const sqlChunks: string[] = ["BEGIN;"];

for (let i = 0; i < rows.length; i += BATCH) {
  const chunk = rows.slice(i, i + BATCH) as Record<string, string>[];
  const values = chunk
    .map((row) => {
      // Escape single quotes for SQLite string literals
      const name = row["Full Name"]?.replace(/'/g, "''") ?? "";
      const email = row["Email"]?.replace(/'/g, "''") ?? "";
      return `('${name}', '${email}')`;
    })
    .join(",\n  ");
  sqlChunks.push(`INSERT INTO users (name, email) VALUES\n  ${values};`);
}

sqlChunks.push("COMMIT;");
const sqlContent = sqlChunks.join("\n\n");

// 5. Write to temp file — keep under 9 MB to stay inside wrangler batch limit
const tmpFile = join(tmpdir(), `d1-import-${Date.now()}.sql`);
writeFileSync(tmpFile, sqlContent, "utf8");

const byteSize = Buffer.byteLength(sqlContent, "utf8");
if (byteSize > 9 * 1024 * 1024) {
  throw new Error(
    `SQL file is ${(byteSize / 1e6).toFixed(1)} MB — split into smaller batches`
  );
}

// 6. Execute against D1
console.log(`Importing ${rows.length} rows (${(byteSize / 1e3).toFixed(0)} KB SQL)...`);
execSync(`wrangler d1 execute ${DB_NAME} --file ${tmpFile} --remote`, { stdio: "inherit" });
console.log("Import complete.");
```

---

## 3. Encoding Detection Automation

Do not rely on the CRM vendor to document the encoding. Detect it at the start of the pipeline.

```typescript
// etl/detect-encoding.ts
import { readFileSync } from "node:fs";
import chardet from "chardet";

export function detectAndValidateEncoding(filePath: string): string {
  const buffer = readFileSync(filePath);

  // chardet inspects byte patterns and BOM markers
  const detected = chardet.detect(buffer);
  console.log(`Detected encoding: ${detected?.encoding ?? "unknown"} (confidence: ${detected?.confidence ?? 0})`);

  if (!detected || detected.confidence < 0.7) {
    throw new Error(
      `Low-confidence encoding detection (${detected?.confidence}). ` +
        `Manually specify encoding or obtain a UTF-8 export from the source system.`
    );
  }

  // Normalise common aliases
  const enc = (detected.encoding ?? "").toUpperCase();
  if (enc === "UTF-8" || enc === "ASCII") return "utf8";
  if (enc === "WINDOWS-1252" || enc === "ISO-8859-1") return "win1252";
  if (enc === "UTF-16LE") return "utf16-le";

  throw new Error(`Unsupported encoding: ${enc} — add explicit transcode step`);
}
```

---

## 4. Post-Import Integrity Check

Verify that the data landed correctly before the ETL job is declared successful.

```typescript
// etl/verify-import.ts
async function verifyImport(db: D1Database, expectedCount: number): Promise<void> {
  // Row count check
  const { results } = await db.prepare("SELECT COUNT(*) AS cnt FROM users").all<{ cnt: number }>();
  const actual = results[0]?.cnt ?? 0;
  if (actual < expectedCount * 0.99) {
    throw new Error(`Row count mismatch: expected ~${expectedCount}, got ${actual}`);
  }

  // Spot-check: ensure no replacement characters survived in the name column
  const { results: badRows } = await db
    .prepare("SELECT id, name FROM users WHERE name LIKE '%�%' LIMIT 10")
    .all<{ id: number; name: string }>();

  if (badRows.length > 0) {
    throw new Error(
      `Encoding corruption detected in ${badRows.length} row(s): ` +
        badRows.map((r) => `id=${r.id}`).join(", ")
    );
  }

  // Spot-check: ensure non-ASCII names are present (encoding didn't strip them)
  const { results: nonAscii } = await db
    .prepare("SELECT COUNT(*) AS cnt FROM users WHERE name != CAST(name AS BLOB)")
    .all<{ cnt: number }>();
  console.log(`Non-ASCII name rows: ${nonAscii[0]?.cnt ?? 0} (should be > 0 for multilingual data)`);
}
```

---

## 5. Wrangler Batch-Split Guard

When importing large files that must be split, split on row boundaries, not byte boundaries, to prevent mid-sequence corruption.

```typescript
// etl/safe-split.ts
function splitSqlByRows(allSql: string, maxBytesPerChunk = 8 * 1024 * 1024): string[] {
  const insertStatements = allSql
    .split(/;\n/)
    .filter((s) => s.trim().startsWith("INSERT"));

  const chunks: string[] = [];
  let current = "BEGIN;\n";

  for (const stmt of insertStatements) {
    const withSemi = stmt + ";\n";
    const candidateSize = Buffer.byteLength(current + withSemi + "COMMIT;\n", "utf8");

    if (candidateSize > maxBytesPerChunk && current.length > "BEGIN;\n".length) {
      chunks.push(current + "COMMIT;\n");
      current = "BEGIN;\n";
    }
    current += withSemi;
  }

  if (current.length > "BEGIN;\n".length) {
    chunks.push(current + "COMMIT;\n");
  }

  return chunks;
}
```

---

## Anti-patterns

- Calling `readFileSync` without an encoding argument and assuming the result is UTF-8 clean when the source system is Windows-era software.
- Splitting SQL files on byte boundaries rather than statement/row boundaries — a single `INSERT` statement split mid-value produces a syntax error at best and silent truncation at worst.
- Trusting the vendor's documentation of the export encoding rather than detecting it programmatically — vendors frequently mislabel Windows-1252 files as "ISO-8859-1" (a near-subset) or simply state "CSV" with no encoding.
- Skipping a post-import integrity check because the import command exited 0 — SQLite will accept and store invalid UTF-8 sequences without error in some edge cases.
- Using D1's HTTP API for large imports without chunking — the 25 MB request body limit is a hard rejection, not a silent truncation.

## Gotchas

- `chardet` and `jschardet` can misidentify pure-ASCII Windows-1252 files as UTF-8 because ASCII is a subset of both. Always test with a sample row that contains the non-ASCII characters you expect.
- SQLite's `LIKE` operator is ASCII-case-insensitive but does not perform Unicode-aware comparison — a `LIKE '%é%'` query on a correctly stored UTF-8 column works correctly only when the collation is set appropriately.
- `wrangler d1 execute --file` uses the D1 REST API under the hood and is subject to the same 10 s per-statement timeout as the interactive API; extremely long `INSERT ... VALUES (...)` chains with hundreds of rows can hit this limit.
- The D1 `--local` flag during development uses a local SQLite file, which may have different UTF-8 enforcement than the remote D1 backend — test encoding with `--remote` against a staging database.
- After a failed import inside a transaction, always check for partial writes with `SELECT COUNT(*) FROM your_table` before re-running the import — D1 does not auto-rollback an explicit `BEGIN` on connection drop.

## Verification

```bash
# Detect encoding of a file
file -i export.csv
# or with python: python3 -c "import chardet; print(chardet.detect(open('export.csv','rb').read()))"

# After import: check for replacement character in D1
wrangler d1 execute $DB_NAME --remote \
  --command "SELECT id, name FROM users WHERE name LIKE '%\xef\xbf\xbd%' LIMIT 5;"

# Confirm row count
wrangler d1 execute $DB_NAME --remote \
  --command "SELECT COUNT(*) FROM users;"

# Spot-check a known non-ASCII name
wrangler d1 execute $DB_NAME --remote \
  --command "SELECT name FROM users WHERE id = 42;"
```

## Related

- `d1-migration-rollback-failed-production-lesson.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `d1-write-contention-viral-event-postmortem.md`
- `silent-data-loss-partial-writes.md`
- `large-payload-encoding-failure-pivot.md`

## Sources

- Cloudflare D1 docs — Importing data: https://developers.cloudflare.com/d1/best-practices/import-export-data/
- Wrangler D1 execute reference: https://developers.cloudflare.com/workers/wrangler/commands/#d1
- iconv-lite npm package: https://www.npmjs.com/package/iconv-lite
- chardet npm package: https://www.npmjs.com/package/chardet
- SQLite text encoding documentation: https://www.sqlite.org/datatype3.html
