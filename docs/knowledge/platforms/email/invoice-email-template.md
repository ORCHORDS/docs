# invoice-email-template

**Issue:** Designing reliable, deliverable invoice and receipt email templates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Invoice emails must be deliverable, readable in all clients, and contain all legally required information.

## Pattern / Solution
Required elements:
- Company name, address, VAT/tax number.
- Invoice number, date, due date.
- Line items with quantities, unit prices, totals.
- Payment method summary.
- Payment link or instructions.
- PDF attachment of formal invoice.

Template structure:
```html
<table>
  <tr><td>Invoice #{{invoiceNumber}}</td><td>{{date}}</td></tr>
  {{#each lineItems}}
  <tr>
    <td>{{description}}</td>
    <td>{{qty}}</td>
    <td>{{unitPrice}}</td>
    <td>{{total}}</td>
  </tr>
  {{/each}}
  <tr><td colspan="3">Total</td><td>{{grandTotal}}</td></tr>
</table>
```

Deliverability: invoice emails are transactional; should bypass marketing suppression lists.

## Gotchas
- Currency formatting must match recipient's locale (EUR vs. USD, comma vs. period decimals).
- PDF attachment size can cause delivery failures; keep under 2 MB.
- Store invoice data immutably; sent invoices must not change if template or data changes.

## Related
- email-attachment-patterns, transactional-vs-marketing-email, email-cc-bcc-transactional
