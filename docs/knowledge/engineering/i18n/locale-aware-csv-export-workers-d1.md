# Locale-Aware CSV Export with Cloudflare Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A reporting feature exports D1 query results as CSV. German users open the file in Excel and find
that numbers use a period as decimal separator (`1234.56`) instead of a comma (`1.234,56`), dates
are formatted `YYYY-MM-DD` instead of `DD.MM.YYYY`, and currency amounts lack the euro symbol.
French users see the same English formatting. The export Worker needs to produce locale-correct CSV
on the fly without a build step or external library.

---

## Context

RFC 4180 defines CSV as a US-ASCII format with comma delimiters, but real-world CSV files consumed
by European spreadsheet software (Excel, LibreOffice Calc) use the system locale's list separator
(`;` in German/French/Spanish) and locale-specific number and date formatting. Workers can apply
`Intl.NumberFormat`, `Intl.DateTimeFormat`, and locale metadata from D1 to produce a compliant,
locale-aware CSV entirely at the edge. The response is streamed via `TransformStream` so large
result sets do not buffer in Worker memory.

Cloudflare's `Response` body accepts a `ReadableStream`, enabling true streaming CSV exports from
D1 paginated queries.

---

## 1. Locale Metadata for CSV Dialect

Different locales require different list separators, decimal marks, and date formats. Store these
per-locale in D1 or derive them from CLDR data embedded in the Worker.

```typescript
// worker/csv/locale-config.ts
interface CsvLocaleConfig {
  listSeparator: string;   // "," (en) or ";" (de, fr, es)
  decimalMark: string;     // "." or ","
  datePattern: string;     // tokens for date formatting
  encoding: string;        // "UTF-8" | "windows-1252" (legacy Excel)
}

const LOCALE_CSV_CONFIG: Record<string, CsvLocaleConfig> = {
  en: { listSeparator: ',',  decimalMark: '.', datePattern: 'MM/dd/yyyy', encoding: 'UTF-8' },
  de: { listSeparator: ';',  decimalMark: ',', datePattern: 'dd.MM.yyyy', encoding: 'UTF-8' },
  fr: { listSeparator: ';',  decimalMark: ',', datePattern: 'dd/MM/yyyy', encoding: 'UTF-8' },
  es: { listSeparator: ';',  decimalMark: ',', datePattern: 'dd/MM/yyyy', encoding: 'UTF-8' },
  ja: { listSeparator: ',',  decimalMark: '.', datePattern: 'yyyy/MM/dd', encoding: 'UTF-8' },
  pt: { listSeparator: ';',  decimalMark: ',', datePattern: 'dd/MM/yyyy', encoding: 'UTF-8' },
};

const DEFAULT_CONFIG = LOCALE_CSV_CONFIG['en'];

export function getCsvConfig(locale: string): CsvLocaleConfig {
  const lang = locale.split('-')[0].toLowerCase();
  return LOCALE_CSV_CONFIG[lang] ?? DEFAULT_CONFIG;
}
```

---

## 2. Cell Value Formatters

```typescript
// worker/csv/formatters.ts
interface Formatters {
  number: (v: number) => string;
  currency: (v: number, currencyCode: string) => string;
  date: (v: string) => string;   // input: ISO-8601 date string
}

export function buildFormatters(locale: string, config: CsvLocaleConfig): Formatters {
  const numFmt = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  });

  const dateFmt = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  return {
    number: (v) => numFmt.format(v),

    currency: (v, currencyCode) =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currencyCode,
        minimumFractionDigits: 2,
      }).format(v),

    date: (v) => {
      try {
        return dateFmt.format(new Date(v));
      } catch {
        return v;
      }
    },
  };
}
```

---

## 3. CSV Serialisation Helpers

```typescript
// worker/csv/serialise.ts
export function escapeCsvCell(value: string, separator: string): string {
  // Must quote if cell contains separator, double-quote, newline, or carriage return
  const needsQuoting =
    value.includes(separator) ||
    value.includes('"') ||
    value.includes('\n') ||
    value.includes('\r');

  if (!needsQuoting) return value;
  return `"${value.replace(/"/g, '""')}"`;
}

export function buildCsvRow(cells: string[], separator: string): string {
  return cells.map((c) => escapeCsvCell(c, separator)).join(separator) + '\r\n';
}
```

---

## 4. Streaming Export from D1

D1 does not yet expose a native streaming cursor, so rows are fetched in pages and flushed through
a `TransformStream` to keep memory bounded.

```typescript
// worker/csv/export.ts
import { getCsvConfig } from './locale-config';
import { buildFormatters } from './formatters';
import { buildCsvRow } from './serialise';

const PAGE_SIZE = 500;

export function streamCsvExport(
  env: Env,
  locale: string,
  reportId: string
): ReadableStream<Uint8Array> {
  const config = getCsvConfig(locale);
  const fmt = buildFormatters(locale, config);
  const sep = config.listSeparator;
  const encoder = new TextEncoder();

  return new ReadableStream({
    async start(controller) {
      // UTF-8 BOM so Excel auto-detects encoding
      controller.enqueue(encoder.encode('﻿'));

      // Header row
      const headers = ['ID', 'Name', 'Amount', 'Currency', 'Date'];
      controller.enqueue(encoder.encode(buildCsvRow(headers, sep)));

      let offset = 0;
      while (true) {
        const { results } = await env.DB.prepare(
          `SELECT id, name, amount, currency_code, transaction_date
           FROM transactions
           WHERE report_id = ?
           ORDER BY transaction_date ASC, id ASC
           LIMIT ? OFFSET ?`
        )
          .bind(reportId, PAGE_SIZE, offset)
          .all<{
            id: string;
            name: string;
            amount: number;
            currency_code: string;
            transaction_date: string;
          }>();

        if (results.length === 0) break;

        for (const row of results) {
          const cells = [
            row.id,
            row.name,
            fmt.currency(row.amount, row.currency_code),
            row.currency_code,
            fmt.date(row.transaction_date),
          ];
          controller.enqueue(encoder.encode(buildCsvRow(cells, sep)));
        }

        offset += results.length;
        if (results.length < PAGE_SIZE) break;
      }

      controller.close();
    },
  });
}
```

---

## 5. HTTP Handler

```typescript
// worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/export/csv') return new Response('Not found', { status: 404 });

    const locale = url.searchParams.get('locale') ?? 'en';
    const reportId = url.searchParams.get('reportId');
    if (!reportId) return new Response('Missing reportId', { status: 400 });

    const stream = streamCsvExport(env, locale, reportId);

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/csv; charset=UTF-8',
        'Content-Disposition': `attachment; filename="report-${locale}-${reportId}.csv"`,
        'Transfer-Encoding': 'chunked',
      },
    });
  },
};
```

---

## Anti-patterns

- **Using `toLocaleString()` on numbers without specifying locale** — runtime locale is the Worker
  V8 default (typically `en-US`), not the user's locale. Always pass the locale explicitly.
- **OFFSET-based D1 pagination for large exports** — OFFSET scans all skipped rows; use keyset
  pagination (`WHERE id > ?`) for tables with millions of rows.
- **Omitting the UTF-8 BOM** — Excel on Windows defaults to the system ANSI code page when there
  is no BOM; without it, accented characters in French/German/Spanish fields are corrupted.
- **Hardcoding `,` as the list separator** — causes German and French Excel to treat all cells as
  one column because those locales use `;` as the CSV field delimiter.

---

## Gotchas

- `Intl.DateTimeFormat` output varies by Workers V8 version; pin the output format explicitly with
  `{ year: 'numeric', month: '2-digit', day: '2-digit' }` options rather than relying on default
  `toLocaleDateString()` format.
- Currency formatting includes the currency symbol and grouping separator; when the formatted value
  is used as input to another system (e.g., re-import), strip formatting first.
- `ReadableStream` in Workers has a back-pressure mechanism; D1 queries in `start()` run
  synchronously relative to the stream — the stream does not yield between pages unless you
  explicitly call `await`-ed async operations, which Workers V8 handles correctly.
- The `Content-Disposition` `filename` parameter must be ASCII for broad compatibility; use
  `filename*=UTF-8''<percent-encoded>` for non-ASCII filenames per RFC 5987.

---

## Verification

```bash
# Download German CSV and inspect first three lines
curl -o /tmp/report-de.csv \
  "https://my-worker.example.com/export/csv?locale=de&reportId=R001"
head -3 /tmp/report-de.csv
# Expected: semicolon-separated, decimal comma, European date format

# Confirm UTF-8 BOM presence (EF BB BF at start of file)
xxd /tmp/report-de.csv | head -1
# Expected: efbbbf 49 44 3b 4e 61 ...  (ID;Name...)
```

---

## Related

- `locale-aware-pagination-cursor-d1.md`
- `d1-locale-aware-date-range-queries.md`
- `number-currency-formatting-2026.md`
- `locale-aware-pdf-document-generation.md`

---

## Sources

- RFC 4180 — Common Format and MIME Type for CSV — https://www.rfc-editor.org/rfc/rfc4180
- ECMA-402 Intl.NumberFormat — https://tc39.es/ecma402/#numberformat-objects
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- RFC 5987 — Character Set and Language Encoding for HTTP Header Fields — https://www.rfc-editor.org/rfc/rfc5987
- Microsoft Excel CSV import behaviour — https://support.microsoft.com/en-us/office/text-import-wizard
