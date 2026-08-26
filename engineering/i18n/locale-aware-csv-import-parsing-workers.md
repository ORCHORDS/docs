# Locale-Aware CSV/TSV Import Parsing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user uploads a CSV exported from their German accounting software. The file
contains numbers like `1.234,56` (European notation: dot as thousands separator,
comma as decimal separator) and dates like `15.08.2024`. Your Worker's import
pipeline calls `parseFloat('1.234,56')` and gets `1.234` — silently discarding
the decimal part and dropping the value by a factor of 1000. The upload appears
to succeed, but every monetary amount in the database is wrong.

A Brazilian user uploads a spreadsheet saved with semicolons as delimiters
(because the comma is already the decimal separator). Splitting on commas
produces single-column rows instead of multi-column records.

---

## Context

CSV is not a single format. Three locale-sensitive dimensions vary by software
and locale:

| Dimension | US/UK | German/French | Brazilian Portuguese |
|---|---|---|---|
| Field delimiter | `,` | `;` | `;` |
| Decimal separator | `.` | `,` | `,` |
| Thousands separator | `,` | `.` | `.` |
| Date format | MM/DD/YYYY | DD.MM.YYYY | DD/MM/YYYY |

Excel, LibreOffice, and SAP each write CSV using the system locale's separator
conventions. A robust import pipeline must detect or accept locale metadata,
parse accordingly, and report field-level parse errors with locale-appropriate
messaging.

Workers are well-suited for this: they receive the raw upload via `request.formData()`,
can stream-process the CSV, and respond with structured validation errors before
any data reaches D1.

---

## Detecting the Delimiter

Delimiter detection from a sample of the file is more reliable than requiring the
user to declare it, but accept an explicit override.

```typescript
// src/lib/csv-delimiter.ts

type Delimiter = ',' | ';' | '\t' | '|';

const CANDIDATES: Delimiter[] = [',', ';', '\t', '|'];

/**
 * Detect the most likely field delimiter by counting occurrences
 * in the first non-empty line of the file.
 */
export function detectDelimiter(sample: string): Delimiter {
  const firstLine = sample.split('\n').find(l => l.trim().length > 0) ?? '';
  let best: Delimiter = ',';
  let bestCount = 0;

  for (const d of CANDIDATES) {
    const count = firstLine.split(d).length - 1;
    if (count > bestCount) {
      bestCount = count;
      best = d;
    }
  }

  return best;
}
```

---

## Locale-Aware Number Parser

```typescript
// src/lib/locale-number-parse.ts

export interface NumberParseResult {
  value: number;
  raw: string;
}

export class NumberParseError extends Error {
  constructor(public readonly raw: string, public readonly locale: string) {
    super(`Cannot parse "${raw}" as a number in locale "${locale}"`);
    this.name = 'NumberParseError';
  }
}

// Cache formatters: constructing Intl.NumberFormat is moderately expensive
const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(locale: string): Intl.NumberFormat {
  if (!formatterCache.has(locale)) {
    formatterCache.set(locale, new Intl.NumberFormat(locale));
  }
  return formatterCache.get(locale)!;
}

/**
 * Determine the decimal and thousands separators for a locale by formatting
 * a known number and inspecting the parts.
 */
function getSeparators(locale: string): { decimal: string; thousands: string } {
  const fmt = new Intl.NumberFormat(locale);
  const parts = fmt.formatToParts(1234567.89);
  let decimal = '.';
  let thousands = ',';
  for (const part of parts) {
    if (part.type === 'decimal') decimal = part.value;
    if (part.type === 'group') thousands = part.value;
  }
  return { decimal, thousands };
}

const separatorCache = new Map<string, { decimal: string; thousands: string }>();

function getCachedSeparators(locale: string) {
  if (!separatorCache.has(locale)) {
    separatorCache.set(locale, getSeparators(locale));
  }
  return separatorCache.get(locale)!;
}

/**
 * Parse a locale-formatted number string into a JS float.
 *
 * Strategy:
 *   1. Strip thousands separators.
 *   2. Replace decimal separator with '.'.
 *   3. parseFloat on the normalised string.
 */
export function parseLocaleNumber(raw: string, locale: string): number {
  const { decimal, thousands } = getCachedSeparators(locale);
  const trimmed = raw.trim();

  // Remove currency symbols, non-breaking spaces, etc.
  const stripped = trimmed.replace(/[^\d.,\-+]/g, '');
  if (stripped === '') throw new NumberParseError(raw, locale);

  // Escape special regex chars for thousands separator
  const escapedThousands = thousands.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const withoutThousands = stripped.replace(new RegExp(escapedThousands, 'g'), '');

  const normalised = decimal === '.'
    ? withoutThousands
    : withoutThousands.replace(decimal, '.');

  const value = parseFloat(normalised);
  if (!Number.isFinite(value)) throw new NumberParseError(raw, locale);

  return value;
}
```

---

## RFC 4180-Compliant CSV Row Parser

Workers do not ship a built-in CSV parser. This minimal implementation handles
quoted fields and embedded newlines.

```typescript
// src/lib/csv-parser.ts

export function parseCSVRow(line: string, delimiter: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;
  let i = 0;

  while (i < line.length) {
    const char = line[i];
    const next = line[i + 1];

    if (inQuotes) {
      if (char === '"' && next === '"') {
        // Escaped quote
        current += '"';
        i += 2;
      } else if (char === '"') {
        inQuotes = false;
        i++;
      } else {
        current += char;
        i++;
      }
    } else {
      if (char === '"') {
        inQuotes = true;
        i++;
      } else if (line.startsWith(delimiter, i)) {
        fields.push(current);
        current = '';
        i += delimiter.length;
      } else {
        current += char;
        i++;
      }
    }
  }

  fields.push(current);
  return fields;
}

export function* parseCSV(
  text: string,
  delimiter: string
): Generator<string[]> {
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    if (line.trim() === '') continue;
    yield parseCSVRow(line, delimiter);
  }
}
```

---

## Import Pipeline Worker

```typescript
// src/workers/csv-import.ts
import { detectDelimiter } from '../lib/csv-delimiter';
import { parseLocaleNumber, NumberParseError } from '../lib/locale-number-parse';
import { parseLocaleDate, DateParseError } from '../lib/parse-date';
import { parseCSV } from '../lib/csv-parser';

export interface Env {
  DB: D1Database;
}

interface ImportRow {
  description: string;
  amount: number;
  currency: string;
  date: string; // ISO 8601
}

interface ImportError {
  row: number;
  field: string;
  raw: string;
  reason: string;
}

interface ImportResult {
  imported: number;
  errors: ImportError[];
}

const SUPPORTED_CURRENCIES = new Set(['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'BRL']);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const contentType = request.headers.get('Content-Type') ?? '';
    if (!contentType.includes('multipart/form-data')) {
      return Response.json({ error: 'Expected multipart/form-data upload' }, { status: 400 });
    }

    // Resolve locale for number/date parsing
    const locale =
      new URL(request.url).searchParams.get('locale') ??
      request.headers.get('Accept-Language')?.split(',')[0]?.split(';')[0]?.trim() ??
      'en-US';

    // Explicit delimiter override
    const delimiterParam = new URL(request.url).searchParams.get('delimiter') as string | null;

    const formData = await request.formData();
    const file = formData.get('file');
    if (!(file instanceof File)) {
      return Response.json({ error: 'No file field in form data' }, { status: 400 });
    }

    const text = await file.text();
    const delimiter = delimiterParam ?? detectDelimiter(text);

    const rows = [...parseCSV(text, delimiter)];
    if (rows.length < 2) {
      return Response.json({ error: 'File contains no data rows' }, { status: 422 });
    }

    // First row is the header; normalize header names
    const headers = rows[0].map(h => h.trim().toLowerCase().replace(/\s+/g, '_'));
    const descIdx   = headers.indexOf('description');
    const amountIdx = headers.indexOf('amount');
    const currIdx   = headers.indexOf('currency');
    const dateIdx   = headers.indexOf('date');

    if ([descIdx, amountIdx, currIdx, dateIdx].includes(-1)) {
      return Response.json({
        error: 'Missing required columns. Expected: description, amount, currency, date',
        found: headers,
      }, { status: 422 });
    }

    const validRows: ImportRow[] = [];
    const errors: ImportError[] = [];

    for (let i = 1; i < rows.length; i++) {
      const fields = rows[i];
      const rowNum = i + 1; // 1-indexed, header = row 1

      // Parse amount
      let amount: number | undefined;
      try {
        amount = parseLocaleNumber(fields[amountIdx] ?? '', locale);
        if (amount <= 0) throw new NumberParseError(fields[amountIdx], locale);
      } catch {
        errors.push({ row: rowNum, field: 'amount', raw: fields[amountIdx] ?? '', reason: `Cannot parse as number in locale ${locale}` });
      }

      // Validate currency
      const currency = (fields[currIdx] ?? '').trim().toUpperCase();
      if (!SUPPORTED_CURRENCIES.has(currency)) {
        errors.push({ row: rowNum, field: 'currency', raw: currency, reason: `Unsupported currency. Accepted: ${[...SUPPORTED_CURRENCIES].join(', ')}` });
      }

      // Parse date
      let isoDate: string | undefined;
      try {
        const parsed = parseLocaleDate(fields[dateIdx] ?? '', locale);
        isoDate = parsed.iso;
      } catch (e) {
        errors.push({ row: rowNum, field: 'date', raw: fields[dateIdx] ?? '', reason: (e as Error).message });
      }

      const description = (fields[descIdx] ?? '').trim();
      if (!description) {
        errors.push({ row: rowNum, field: 'description', raw: '', reason: 'Description is required' });
      }

      if (amount !== undefined && isoDate !== undefined && description && SUPPORTED_CURRENCIES.has(currency)) {
        validRows.push({ description, amount, currency, date: isoDate });
      }
    }

    // Batch-insert valid rows
    if (validRows.length > 0) {
      const stmt = env.DB.prepare(
        'INSERT INTO transactions (description, amount_raw, currency, transaction_date) VALUES (?, ?, ?, ?)'
      );
      const batch = validRows.map(r => stmt.bind(r.description, r.amount, r.currency, r.date));
      await env.DB.batch(batch);
    }

    const result: ImportResult = { imported: validRows.length, errors };
    return Response.json(result, { status: errors.length > 0 ? 207 : 200 });
  },
};
```

---

## Encoding Detection

CSV files from legacy Windows software (SAP, older Excel) may arrive in
Windows-1252 or Latin-1 encoding rather than UTF-8. The `file.text()` call
assumes UTF-8. Use the `TextDecoder` API to handle alternate encodings.

```typescript
async function decodeFile(file: File): Promise<string> {
  // Check for a BOM to detect UTF-16
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);

  if (bytes[0] === 0xFF && bytes[1] === 0xFE) {
    return new TextDecoder('utf-16le').decode(buffer);
  }
  if (bytes[0] === 0xFE && bytes[1] === 0xFF) {
    return new TextDecoder('utf-16be').decode(buffer);
  }
  if (bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) {
    return new TextDecoder('utf-8').decode(buffer); // UTF-8 BOM
  }

  // Heuristic: if high-bit bytes appear, try windows-1252
  const hasHighBit = bytes.some(b => b > 0x7F);
  const encoding = hasHighBit ? 'windows-1252' : 'utf-8';
  return new TextDecoder(encoding).decode(buffer);
}
```

---

## Anti-patterns

**Using `parseFloat()` directly on locale-formatted strings:**
```typescript
const v = parseFloat('1.234,56'); // ❌ → 1.234, not 1234.56
```

**Splitting on comma without checking delimiter:**
```typescript
const fields = line.split(','); // ❌ — breaks for semicolon-delimited European files
```

**Assuming UTF-8 without checking for a BOM or encoding declaration:**
Files from Windows applications are frequently Windows-1252 or Latin-1.

**Failing the entire import on the first parse error:**
Report all row-level errors in the response and still insert valid rows. A 207
Multi-Status response with `{ imported: N, errors: [...] }` is more useful than
a blanket 422.

---

## Gotchas

- **Excel's "Save As CSV"** uses the system locale's list separator setting, not
  always the CSV standard. German Excel uses semicolons; US Excel uses commas.
- **LibreOffice** prompts the user for delimiter and encoding on export; the
  resulting file may vary. Always detect rather than assume.
- **Large files**: for imports above ~4 MB, stream the file body rather than
  buffering with `file.text()`. Use a `TransformStream` to process lines
  incrementally and avoid the 128 MB request body limit.
- **Negative numbers**: some locales represent negatives as `(1.234,56)` rather
  than `-1.234,56`. The `Intl.NumberFormat` parts approach above will not handle
  parenthetical negatives; strip parens and negate.
- **Trailing commas**: Excel sometimes emits a trailing comma on each row,
  producing an empty extra field. Drop empty trailing fields.
- **MIME type**: accept both `text/csv` and `application/vnd.ms-excel` in your
  Content-Type check — Excel sets the latter even for plain CSV files.

---

## Verification

```typescript
// tests/csv-import.test.ts
import { detectDelimiter } from '../src/lib/csv-delimiter';
import { parseLocaleNumber } from '../src/lib/locale-number-parse';
import { parseCSV, parseCSVRow } from '../src/lib/csv-parser';
import { describe, it, expect } from 'vitest';

describe('detectDelimiter', () => {
  it('detects comma for US-style CSV', () => {
    expect(detectDelimiter('name,amount,currency\nFoo,1234.56,USD')).toBe(',');
  });
  it('detects semicolon for European CSV', () => {
    expect(detectDelimiter('name;amount;currency\nFoo;1.234,56;EUR')).toBe(';');
  });
  it('detects tab for TSV', () => {
    expect(detectDelimiter('name\tamount\tcurrency')).toBe('\t');
  });
});

describe('parseLocaleNumber', () => {
  it('parses en-US number with comma group separator', () => {
    expect(parseLocaleNumber('1,234.56', 'en-US')).toBeCloseTo(1234.56);
  });
  it('parses de-DE number with dot group and comma decimal', () => {
    expect(parseLocaleNumber('1.234,56', 'de-DE')).toBeCloseTo(1234.56);
  });
  it('parses plain integer', () => {
    expect(parseLocaleNumber('1234', 'en-US')).toBe(1234);
  });
  it('throws for non-numeric string', () => {
    expect(() => parseLocaleNumber('abc', 'en-US')).toThrow();
  });
});

describe('parseCSVRow', () => {
  it('handles quoted fields with embedded commas', () => {
    expect(parseCSVRow('"Acme, Inc.",100.00,USD', ',')).toEqual(['Acme, Inc.', '100.00', 'USD']);
  });
  it('handles double-quote escaping inside quoted fields', () => {
    expect(parseCSVRow('"Say ""hello""",1.00,EUR', ',')).toEqual(['Say "hello"', '1.00', 'EUR']);
  });
  it('parses semicolon delimiter', () => {
    expect(parseCSVRow('Foo;1.234,56;EUR', ';')).toEqual(['Foo', '1.234,56', 'EUR']);
  });
});
```

---

## Related

- `locale-aware-date-parsing-ambiguity-workers.md`
- `cldr-supplemental-currency-fraction-digits-workers.md`
- `locale-aware-csv-export-workers-d1.md`
- `localized-numeric-input-parsing.md`
- `character-encoding-utf-8-2026.md`

---

## Sources

- RFC 4180 (CSV format): https://www.rfc-editor.org/rfc/rfc4180
- `Intl.NumberFormat.formatToParts` for separator detection: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts
- `TextDecoder` API in Workers: https://developers.cloudflare.com/workers/runtime-apis/encoding/
- Cloudflare Workers request body limits: https://developers.cloudflare.com/workers/platform/limits/#request-limits
