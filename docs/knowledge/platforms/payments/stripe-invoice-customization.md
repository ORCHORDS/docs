# stripe-invoice-customization

**Issue:** Customizing Stripe invoices with branding and custom fields
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Default Stripe invoices lack your company logo, address, or custom line item descriptions needed for B2B billing compliance.

## Pattern / Solution
```typescript
// Set account-level invoice defaults
await stripe.accounts.update({
  settings: {
    invoices: {
      default_account_tax_ids: ['txr_xxx'],
    },
  },
});

// Per-invoice customization
const invoice = await stripe.invoices.create({
  customer: customerId,
  custom_fields: [
    { name: 'PO Number', value: 'PO-2026-001' },
    { name: 'Project', value: 'Website Redesign' },
  ],
  footer: 'Payment due within 30 days. Thank you for your business.',
  description: 'Services for August 2026',
});
```

Set logo and colors in Dashboard > Settings > Branding.

## Gotchas
- Logo changes apply globally to all future invoices
- Custom fields appear on the PDF but may not appear in the hosted invoice view in all regions
- `footer` has a character limit — keep it concise
- Tax IDs on invoices are required for EU B2B compliance

## Related
- `stripe-tax-calculation.md`
- `invoice-generation-pdf.md`
- `receipt-email-template.md`
