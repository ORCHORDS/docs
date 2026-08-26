# eu-vat-deemed-supplier-platform-vida

**Issue:** EU VAT law makes online platforms, not their sellers, liable for charging and remitting consumer VAT in a growing set of transactions. Since 1 July 2021, marketplaces are "deemed suppliers" for cross-border B2C distance sales of goods and digital services facilitated for sellers (VAT Directive Art. 14a), with IOSS/OSS one-stop-shops as the filing mechanism. The VAT in the Digital Age (ViDA) package, adopted 11 March 2025, extends the deemed-supplier model to platforms for short-term accommodation rental (from 1 July 2028) and road passenger transport (from 1 January 2030), and adds mandatory structured e-invoicing and digital reporting for cross-border supplies from 2030 (EC [ViDA page](https://taxation-customs.ec.europa.eu/taxation/vat/vat-digital-age-vida_en)). A platform that has never done tax calculation must now build a VAT determination, invoicing, and filing pipeline. This article maps the obligations and the engineering; it is distinct from the tax-transparency reporting covered in `dac7-platform-seller-tax-reporting.md`.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 2021 baseline that already applies

1. **Deemed supplier for marketplaces (Art. 14a).** When a marketplace facilitates a B2C distance sale of goods from a non-EU import or an intra-EU seller, or a taxable digital service (TBE) by a non-EU seller, the **platform** is treated as the supplier for VAT and must charge destination-country VAT — seller VAT registration does not rescue the platform from this liability.
2. **IOSS for imports ≤ €150.** The Import One-Stop-Shop lets the platform charge VAT at checkout on low-value consignments and remit via a single monthly EU return, instead of the customer paying at the border; using it is optional in law but commercially mandatory, and it requires IOSS VAT IDs on customs data.
3. **OSS Union and Non-Union schemes.** For intra-EU distance sales and TBE services, the One-Stop-Shop replaces VAT registration in every destination member state with a single quarterly return per scheme — the platform's own commissions and the deemed-supplier sales it owes are reported through the applicable scheme.
4. **Invoicing and evidence duties.** As deemed supplier, the platform issues the VAT invoice or receipt and must retain evidence of customer location and of supply; get the evidence wrong and the destination country reassesses against the platform.
5. **Checkout-level rate determination.** VAT is charged at the rate of the consumer's member state, so the checkout path needs country and product-classification logic (goods vs TBE service vs excluded item) driving a maintained rate table — hard-code nothing.

## What ViDA changes (adopted March 2025)

1. **Three pillars.** ViDA comprises e-invoicing/digital reporting, the platform-economy deemed-supplier expansion, and single VAT registration consolidation; the platform-economy pillar is what rewrites accommodation and transport platforms' obligations ([PwC adoption summary](https://www.pwc.com/mt/en/publications/vat/vida-adoption-at-a-glance.html)).
2. **Short-term accommodation from 1 July 2028.** Platforms facilitating accommodation rentals of up to 30 nights become the deemed supplier for the underlying host's supply, collecting VAT even where individual hosts are unregistered ([VATCalc phase-in tracker](https://www.vatcalc.com/eu/eu-platform-economy-2025-deemed-supplier-vat-in-the-digital-age/)).
3. **Road passenger transport from 1 January 2030.** The same deemed-supplier treatment phases in for platforms facilitating passenger transport by road — the staggered Jul-2028/Jan-2030 start dates mean the two sectors' build-outs land on different calendars.
4. **Host and driver relief.** Underlying suppliers are relieved of their own VAT accounting for facilitated supplies (the platform accounts for it), which removes millions of small hosts from VAT registration — but only for supplies actually facilitated through the platform.
5. **Member-state options and 2030 reporting.** Member states may exempt (with deduction) small accommodation providers' supplies, and Pillar 1's mandatory structured e-invoicing and digital reporting for intra-EU cross-border transactions arrives in 2030 with later phases through 2035 — start capturing supply-level structured data now so 2030 is a format change, not a data-model rewrite.

## Engineering the tax pipeline

1. **Supply classification service.** Classify every transaction at order creation into goods / TBE service / accommodation / transport / platform-own-service, because each class routes to a different deemed-supplier and scheme logic; treat the classifier like an API with versioned outputs.
2. **Place-of-supply and destination evidence.** Persist the evidence used to fix the consumer's country (billing address, IP, bank country, device SIM per TBE rules) per transaction — this record, not the checkout screen, is what defends a VAT audit.
3. **Rate table and validation.** Maintain a member-state × product-class rate table with effective dates (rates change several times a year), validate consumer VAT IDs via VIES where relevant, and record the version of the rate used on each line.
4. **Invoicing at platform identity.** As deemed supplier the platform issues invoices/receipts under its own name and IOSS/OSS identifiers, with sequential numbering per scheme and legal field content — separate the invoice service from seller payout statements to avoid dual-purpose formats.
5. **Filing calendar and reconciliation.** IOSS returns are monthly, OSS quarterly; automate extraction, reconcile against the ledger to the cent, and file early in the window — late or wrong deemed-supplier VAT is assessed directly against the platform.

## Gotchas

1. **No threshold on deemed-supplier liability.** Unlike the DAC7 de minimis, Art. 14a liability applies from the first euro of facilitated cross-border supply; a single EU seller on your marketplace can create registration-class obligations.
2. **Partial facilitation.** If the platform only handles payments or listings but not the full supply chain, whether it "facilitates" is fact-specific — document the role per transaction type, because the classification flips who owes the VAT.
3. **Mixed baskets and multi-service orders.** An order combining goods, digital services, and (from 2028) accommodation must split VAT treatment per item and per scheme; build line-level treatment from the start rather than order-level.
4. **Platform commissions are a separate supply.** The commission fee charged to sellers is the platform's own service reported through OSS on top of the deemed-supplier obligation — double-counting or netting these against each other is a classic finding.
5. **Prepare data for 2030 now.** Pillar 1 digital reporting requires supply-level structured e-invoicing data for cross-border transactions; the order schema should already carry buyer/seller identifiers, classification, evidence fields, and rate provenance so the 2030 reporting format can be emitted retroactively for design assurance.
