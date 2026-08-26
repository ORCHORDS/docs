# Locale-Aware Invoice and Receipt Generation — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You generate invoices or receipts on Cloudflare Workers and customers in different countries
see inconsistent number formats, wrong currency symbols, wrong date layouts, and missing VAT labels.
A German customer receives `$1,234.56` instead of `1.234,56 €`; a Japanese customer sees
`12/31/2026` instead of `2026年12月31日`.

## Context

An invoice touches every locale-sensitive API at once:
`Intl.NumberFormat` for amounts, `Intl.DateTimeFormat` for dates, CLDR plural rules for
unit labels, and country-specific business-document conventions (VAT/GST/消費税 labelling,
address field ordering, paper size). D1 stores per-customer locale preferences so the Worker
can resolve the right formatter without a round-trip to the client.

---

## 1 — D1 schema: customer locale preferences

```sql
-- migrations/0001_invoice_locale.sql
CREATE TABLE customer_locale (
  customer_id TEXT PRIMARY KEY,
  locale      TEXT NOT NULL DEFAULT 'en-US',  -- BCP 47
  currency    TEXT NOT NULL DEFAULT 'USD',    -- ISO 4217
  tz          TEXT NOT NULL DEFAULT 'UTC',    -- IANA tz
  paper       TEXT NOT NULL DEFAULT 'letter'  -- 'a4' | 'letter'
);
```

```typescript
// src/db.ts
export interface CustomerLocale {
  customer_id: string;
  locale: string;
  currency: string;
  tz: string;
  paper: 'a4' | 'letter';
}

export async function getCustomerLocale(
  db: D1Database,
  customerId: string,
): Promise<CustomerLocale> {
  const row = await db
    .prepare('SELECT * FROM customer_locale WHERE customer_id = ?')
    .bind(customerId)
    .first<CustomerLocale>();
  return row ?? {
    customer_id: customerId,
    locale: 'en-US',
    currency: 'USD',
    tz: 'UTC',
    paper: 'letter',
  };
}
```

---

## 2 — Formatter factory

```typescript
// src/formatters.ts
export interface InvoiceFormatters {
  money:    (amount: number) => string;
  date:     (d: Date)        => string;
  datetime: (d: Date)        => string;
  unit:     (n: number, unit: Intl.NumberFormatOptions['unit']) => string;
}

export function buildFormatters(locale: string, currency: string, tz: string): InvoiceFormatters {
  const money = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencyDisplay: 'symbol',
  });

  const date = new Intl.DateTimeFormat(locale, {
    year: 'numeric', month: 'long', day: 'numeric',
    timeZone: tz,
  });

  const datetime = new Intl.DateTimeFormat(locale, {
    dateStyle: 'short', timeStyle: 'short',
    timeZone: tz,
  });

  const unit = (n: number, u: Intl.NumberFormatOptions['unit']) =>
    new Intl.NumberFormat(locale, { style: 'unit', unit: u as string, unitDisplay: 'long' }).format(n);

  return {
    money:    (n) => money.format(n),
    date:     (d) => date.format(d),
    datetime: (d) => datetime.format(d),
    unit,
  };
}
```

---

## 3 — VAT / tax label by locale

```typescript
// src/tax-labels.ts
const TAX_LABEL: Record<string, string> = {
  'de': 'MwSt.',   'de-AT': 'MwSt.',
  'fr': 'TVA',     'fr-BE': 'TVA/BTW',
  'ja': '消費税',
  'zh-CN': '增值税', 'zh-TW': '營業稅',
  'ko': '부가세',
  'pt-BR': 'ICMS/ISS', 'pt': 'IVA',
  'es': 'IVA',
  'en-GB': 'VAT',  'en-AU': 'GST',  'en-IN': 'GST',
};

export function taxLabel(locale: string): string {
  // Exact match → region fallback → language fallback → default
  if (TAX_LABEL[locale]) return TAX_LABEL[locale];
  const lang = locale.split('-')[0];
  return TAX_LABEL[lang] ?? 'Tax';
}
```

---

## 4 — Invoice data assembly and HTML rendering

```typescript
// src/invoice.ts
import { buildFormatters } from './formatters';
import { taxLabel }        from './tax-labels';

interface LineItem { description: string; qty: number; unitPrice: number }
interface InvoiceData {
  invoiceNumber: string;
  issueDate: Date;
  dueDate: Date;
  lines: LineItem[];
  taxRate: number;   // e.g. 0.19
}

export function renderInvoiceHtml(
  data: InvoiceData,
  locale: string,
  currency: string,
  tz: string,
): string {
  const fmt = buildFormatters(locale, currency, tz);
  const taxLbl = taxLabel(locale);
  const dir  = new Intl.Locale(locale).textInfo?.direction ?? 'ltr';

  const subtotal = data.lines.reduce((s, l) => s + l.qty * l.unitPrice, 0);
  const tax      = subtotal * data.taxRate;
  const total    = subtotal + tax;

  const rows = data.lines.map(l => `
    <tr>
      <td>${l.description}</td>
      <td>${l.qty}</td>
      <td>${fmt.money(l.unitPrice)}</td>
      <td>${fmt.money(l.qty * l.unitPrice)}</td>
    </tr>`).join('');

  return `<!doctype html>
<html lang="${locale}" dir="${dir}">
<head><meta charset="utf-8"><title>Invoice ${data.invoiceNumber}</title></head>
<body>
  <h1>Invoice #${data.invoiceNumber}</h1>
  <p>Issued: ${fmt.date(data.issueDate)} — Due: ${fmt.date(data.dueDate)}</p>
  <table>
    <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Amount</th></tr></thead>
    <tbody>${rows}</tbody>
    <tfoot>
      <tr><td colspan="3">Subtotal</td><td>${fmt.money(subtotal)}</td></tr>
      <tr><td colspan="3">${taxLbl} (${(data.taxRate * 100).toFixed(0)} %)</td><td>${fmt.money(tax)}</td></tr>
      <tr><td colspan="3"><strong>Total</strong></td><td><strong>${fmt.money(total)}</strong></td></tr>
    </tfoot>
  </table>
</body></html>`;
}
```

---

## 5 — Worker handler

```typescript
// src/index.ts
import { getCustomerLocale } from './db';
import { renderInvoiceHtml } from './invoice';

export default {
  async fetch(req: Request, env: { DB: D1Database }): Promise<Response> {
    const url        = new URL(req.url);
    const customerId = url.searchParams.get('customer') ?? 'default';

    const prefs = await getCustomerLocale(env.DB, customerId);

    // In production, load real invoice data from D1
    const data = {
      invoiceNumber: 'INV-2026-0001',
      issueDate: new Date('2026-08-23'),
      dueDate:   new Date('2026-09-22'),
      lines: [
        { description: 'Widget Pro', qty: 3, unitPrice: 49.99 },
        { description: 'Setup fee',  qty: 1, unitPrice: 200.00 },
      ],
      taxRate: 0.19,
    };

    const html = renderInvoiceHtml(data, prefs.locale, prefs.currency, prefs.tz);
    return new Response(html, {
      headers: {
        'Content-Type': 'text/html;charset=UTF-8',
        'Content-Disposition': `inline; filename="invoice-${data.invoiceNumber}.html"`,
      },
    });
  },
};
```

---

## Anti-patterns

- **Concatenating currency symbols manually** (`'$' + amount.toFixed(2)`) — breaks for
  currencies where the symbol follows the amount (e.g. `1 234,56 €`).
- **Hardcoding tax labels as "VAT"** — incorrect in Japan (消費税), Brazil (ICMS), and
  Australia (GST).
- **Using `new Date()` without a time zone** — invoice dates differ across the international
  date line; always pass `timeZone` to `Intl.DateTimeFormat`.
- **Storing locale only in the session cookie** — invoices are fetched by ID days later; put
  the locale in D1 next to the invoice record.

## Gotchas

- `Intl.Locale.textInfo` is not available in all V8 versions; feature-detect and default to
  `'ltr'` rather than crashing.
- Some locales format the same currency differently: `en-DE` formats EUR as `1.234,56 €` while
  `en-US` formats it as `€1,234.56`. Always use the customer's locale, not your own.
- The `style: 'currency'` option in `Intl.NumberFormat` does **not** handle crypto currencies
  (BTC, ETH) — those require a custom formatter.

## Verification

```typescript
const fmt = buildFormatters('de-DE', 'EUR', 'Europe/Berlin');
console.assert(fmt.money(1234.56) === '1.234,56 €', 'German EUR formatting failed');

const fmt2 = buildFormatters('ja-JP', 'JPY', 'Asia/Tokyo');
console.assert(fmt2.money(1234) === '￥1,234', 'Japanese JPY formatting failed');

console.assert(taxLabel('ja') === '消費税', 'Japanese tax label failed');
console.assert(taxLabel('en-AU') === 'GST',  'Australian GST label failed');
console.assert(taxLabel('fr')    === 'TVA',  'French TVA label failed');
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `d1-locale-aware-date-range-queries.md`
- `locale-aware-pdf-document-generation.md`
- `date-time-timezone-workers-edge-formatting.md`
- `national-id-document-validation-2026.md`

## Sources

- MDN: `Intl.NumberFormat` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- MDN: `Intl.DateTimeFormat` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- CLDR tax label data — https://cldr.unicode.org/
