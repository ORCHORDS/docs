# invoice-generation-pdf

**Issue:** Generating PDF invoices programmatically for B2B customers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
B2B customers require PDF invoices with specific fields: seller VAT number, buyer VAT number, line items, tax breakdown, invoice number, and sequential numbering. Stripe hosted invoices may not meet all requirements.

## Pattern / Solution
Use PDFKit (Node), Puppeteer (HTML-to-PDF), or a service like Carbone. Generate sequential invoice numbers using a DB counter with a transaction to prevent gaps. Include: invoice date, due date, line items with unit price and quantity, tax per line, totals, payment terms, and bank details.

## Gotchas
Invoice number gaps can trigger tax authority audits — never delete invoices, only issue credit notes. EU invoices require the seller's VAT number and buyer's VAT number for B2B. Store PDFs in object storage and link from the customer portal.

## Related
vat-calculation-eu, stripe-invoice-customization, receipt-email-template, lemonsqueezy-integration
