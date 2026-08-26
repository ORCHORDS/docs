# Locale-Aware PDF Generation — Internationalized Document Rendering

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application generates invoices, reports, or contracts as PDFs, but
they only render correctly in English. Dates show MM/DD/YYYY for German
users who expect DD.MM.YYYY. Currency amounts use periods as decimal
separators for French users who expect commas. Arabic and Hebrew PDFs
render text left-to-right instead of right-to-left. CJK characters
display as missing-glyph boxes because the PDF engine does not embed
the required fonts. Text overflows fixed-width containers because
German translations are 30% longer than English source strings.

## Context

Locale-aware PDF generation ensures that server-rendered documents
(invoices, receipts, reports, contracts, certificates) display dates,
numbers, currencies, and text direction correctly for the recipient's
locale. In 2026, common approaches include Puppeteer/Playwright-based
HTML-to-PDF rendering (which inherits browser i18n capabilities),
dedicated PDF libraries (PDFKit, pdf-lib, ReportLab, iText), and
template-based services (DocRaptor, Prince, WeasyPrint). The key
challenge is that PDF is a fixed-layout format — text expansion,
bidirectional rendering, and font embedding must be handled explicitly,
unlike web pages that reflow automatically.

## Architecture

```
Locale-Aware PDF Pipeline:

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Template      │────►│ Locale       │────►│ PDF Renderer │
│ (HTML/Pug/   │     │ Formatter    │     │ (Puppeteer/  │
│  Handlebars) │     │ (Intl API)   │     │  WeasyPrint) │
└──────────────┘     └──────────────┘     └──────────────┘
                           │                      │
                    ┌──────┴──────┐        ┌──────┴──────┐
                    │ Translation │        │ Font        │
                    │ Strings     │        │ Embedding   │
                    └─────────────┘        └─────────────┘

Approaches:
  HTML → PDF:  Highest i18n fidelity (CSS handles RTL, fonts, reflow)
  Library:     Full control, smaller footprint, manual i18n work
  Template:    Pre-designed, limited locale flexibility
```

## Formatting with Intl API

```javascript
function formatForLocale(locale, data) {
  const dateFormatter = new Intl.DateTimeFormat(locale, {
    dateStyle: 'long',
  });
  const numberFormatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: data.currency,
  });

  return {
    invoiceDate: dateFormatter.format(data.date),
    // "16. August 2026" (de) vs "August 16, 2026" (en-US)

    totalAmount: numberFormatter.format(data.total),
    // "1.234,56 €" (de) vs "$1,234.56" (en-US)

    lineItems: data.items.map(item => ({
      ...item,
      price: numberFormatter.format(item.price),
      quantity: new Intl.NumberFormat(locale).format(item.quantity),
    })),
  };
}
```

## HTML-to-PDF with Puppeteer (recommended)

```javascript
const puppeteer = require('puppeteer');

async function generateLocalizedPDF(templateHtml, locale, data) {
  const formattedData = formatForLocale(locale, data);
  const html = renderTemplate(templateHtml, {
    ...formattedData,
    dir: isRTL(locale) ? 'rtl' : 'ltr',
    lang: locale,
    fontFamily: getFontFamily(locale),
  });

  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: 'networkidle0' });

  const pdf = await page.pdf({
    format: 'A4',
    margin: { top: '20mm', bottom: '20mm', left: '15mm', right: '15mm' },
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: `<div style="font-size:8px; width:100%; text-align:center;">
      ${formattedData.companyName}
    </div>`,
    footerTemplate: `<div style="font-size:8px; width:100%; text-align:center;">
      <span class="pageNumber"></span> / <span class="totalPages"></span>
    </div>`,
  });

  await browser.close();
  return pdf;
}

function isRTL(locale) {
  const rtlLocales = ['ar', 'he', 'fa', 'ur', 'ps', 'yi'];
  return rtlLocales.some(l => locale.startsWith(l));
}
```

## CSS for internationalized layouts

```css
/* Use logical properties for RTL support */
.invoice-container {
  direction: var(--doc-direction, ltr);
  font-family: var(--doc-font);
  padding-inline-start: 15mm;
  padding-inline-end: 15mm;
}

/* Let text containers grow — never fixed width for translated text */
.line-item-description {
  min-width: 40%;
  max-width: 60%;
  overflow-wrap: break-word;
  hyphens: auto;
  -webkit-hyphens: auto;
}

/* CJK: tighter line height, different justification */
:lang(ja), :lang(zh), :lang(ko) {
  line-height: 1.8;
  text-align: justify;
  word-break: break-all;
}

/* Arabic/Hebrew: mirror entire layout */
[dir="rtl"] .invoice-table th:first-child {
  text-align: right;
}
[dir="rtl"] .amount-column {
  text-align: left; /* Numbers stay LTR in RTL context */
}
```

## Font embedding strategy

```
Latin/Cyrillic:  Noto Sans (covers most European languages)
Arabic:          Noto Sans Arabic or Amiri
Hebrew:          Noto Sans Hebrew
CJK:             Noto Sans CJK (SC/TC/JP/KR variants)
Devanagari:      Noto Sans Devanagari
Thai:            Noto Sans Thai

Strategy:
  1. Detect script from locale
  2. Load only the required font subset
  3. Embed font in PDF (not reference — ensures portability)
  4. Use Noto font family for consistent cross-script coverage

Font subsetting (reduce file size):
  → Use pyftsubset or fonttools to include only used glyphs
  → Full Noto Sans CJK: ~16 MB → subsetted: ~500 KB
  → Critical for high-volume PDF generation
```

## Anti-patterns

- **Hardcoded date/number formats** — using `toLocaleDateString()`
  without specifying the locale, which defaults to the server's
  locale rather than the recipient's. Always pass the explicit
  locale to `Intl` formatters.
- **Fixed-width text containers** — designing PDF templates with
  pixel-exact text boxes. German, Finnish, and Russian translations
  are 20-40% longer than English. Use flexible containers with
  min-width/max-width and overflow-wrap.
- **Referencing system fonts** — relying on fonts installed on the
  server OS. Different servers may have different fonts, causing
  inconsistent rendering. Always embed fonts in the PDF or use
  web fonts loaded from a consistent source.
- **Ignoring bidirectional numbers** — in RTL documents, numbers
  and prices should still display left-to-right. Use
  `unicode-bidi: embed` and `direction: ltr` on numeric elements
  within RTL contexts.

## Gotchas

- **Page break with translated text** — content that fits on one
  page in English may spill to two pages in German. Test PDF
  generation with the longest translations to set page break
  rules (`page-break-inside: avoid` on critical sections).
- **Currency symbol position** — some locales place the currency
  symbol before the number ($100), others after (100 €), and
  some use a different symbol entirely (100 CHF). Always use
  `Intl.NumberFormat` with `style: 'currency'` rather than
  concatenating symbol + number.
- **PDF metadata locale** — PDF metadata (title, author, keywords)
  should be in the document's language for accessibility. Set
  `lang` attribute on the HTML root and PDF metadata accordingly.
- **Performance at scale** — Puppeteer-based PDF generation
  launches a browser instance per document. For high-volume
  generation (thousands per hour), use a browser pool, pre-warm
  pages, or switch to a streaming PDF library for simpler layouts.

## Verification

- PDFs render correctly for RTL locales (Arabic, Hebrew).
- Date, number, and currency formats match the recipient's locale.
- CJK characters render without missing-glyph boxes.
- Text does not overflow containers with longest translations.
- Fonts are embedded in the PDF (viewable without system fonts).
- Page breaks do not split critical content across pages.

## Related

- `documentation/categories/i18n/date-formatting-intl.md`
- `documentation/categories/i18n/number-currency-formatting-2026.md`
- `documentation/categories/i18n/rtl-bidi-handling.md`

## Source URLs (verified 2026-08-16)

- Software Internationalization Guide 2026 — https://xtm.ai/blog/software-internationalisation
- Complete Technical Guide to Internationalization — https://simplelocalize.io/blog/posts/internationalization-guide-software-localization/
- Top PDF Generation APIs for 2026 — https://www.edocgen.com/blogs/best-pdf-generation-api
- Best PDF Generation Library in 2026 — https://www.docuforge.app/blog/best-pdf-generation-library-2026
