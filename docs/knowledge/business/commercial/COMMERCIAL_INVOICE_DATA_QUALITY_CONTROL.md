# Commercial Invoice Data Quality Control

## Purpose

A commercial invoice is a core data source for customs valuation, classification context, admissibility review, payment, and reconciliation. This control ensures that invoice data reflects the actual transaction and agrees with the order and shipment. It is not a substitute for jurisdiction-specific customs advice or other required transport and origin documents.

## Scope and ownership

Apply the control to exported goods, returns, samples, replacements, intercompany transfers, and no-charge shipments whenever an invoice or equivalent customs document is required. Trade compliance owns minimum data standards; commercial operations owns transaction accuracy; logistics controls shipment linkage; finance controls monetary reconciliation. Only authorized roles may approve nonstandard values or descriptions.

## Workflow

### Establish the transaction record

Link the invoice to the seller, buyer, consignee, order, shipment, and contractual delivery term. Capture full legal names and addresses, invoice number and date, currency, line quantities, unit and total values, detailed goods descriptions, country of origin where required, tariff classification used by the organization, and transport or package references. Record the reason for export when the movement is not an ordinary sale.

### Build line data from controlled sources

Generate descriptions from governed product data, but make them specific enough to identify the goods. Internal stock codes alone are inadequate for an external invoice. Pull quantity from the released shipment, price and currency from the accepted order, and origin and classification from approved trade master data. Preserve overrides with reasons and approvers.

### Address non-sale movements

“No charge” does not establish that goods have no customs value. For samples, warranties, repairs, replacements, or related-party movements, route valuation to the responsible customs specialist and state the transaction purpose accurately. Never invent a nominal amount merely to satisfy a mandatory field.

### Reconcile before release

Compare invoice lines with packed quantities, order terms, currency, extensions, discounts, applicable value inputs, Incoterms expression, and destination. Confirm totals arithmetically. Ensure invoice identity is unique and revisions remain traceable rather than overwriting the issued record.

### Issue and distribute

Release only the approved version to the broker, carrier, customer, and finance systems. Control later corrections so every recipient can identify the superseded version.

## Controls

Use mandatory fields, reference-data validation, duplicate-number detection, arithmetic checks, and order-to-shipment tolerances. Block missing currency, vague descriptions, invalid quantities, and unapproved overrides. Separate preparation from approval for high-risk cases. Monitor manual invoices, repeated corrections, broker queries, customs holds, value variances, and shipments invoiced after departure.

A data dictionary should define every field, authoritative source, permitted format, and accountable owner. Changes to classification or origin should trigger impact review for open shipments; historical invoices must not be silently rewritten.

## Validation evidence

Retain the accepted order, shipment release, packing evidence, issued invoice, product master snapshot, valuation support for nonstandard cases, approvals, transmission record, and corrections. Sample testing should recalculate totals, compare packed and invoiced quantities, trace price and currency to the order, and verify descriptions against the goods record.

Broker acceptance alone is not proof of accuracy. Strong validation also reconciles customs entry data to the approved invoice and investigates discrepancies.

## Failure handling

Before export, hold the shipment and correct the source record rather than patching only a PDF. After transmission, notify all recipients with a clearly identified replacement and preserve both versions. If goods have entered customs processing, engage the broker and trade-compliance owner promptly to determine the proper correction mechanism.

For systemic defects, identify affected products, dates, destinations, and entries; suspend unreliable automation; and perform a bounded lookback. Record root cause, correction, affected-population results, and control retest. Potentially material customs errors should be escalated to qualified specialists without speculative admissions.

## Canonical sources

- U.S. Customs and Border Protection, **Basic Importing and Exporting**: https://www.cbp.gov/trade/basic-import-export
- U.S. Department of Commerce, International Trade Administration, **Common Export Documents**: https://www.trade.gov/common-export-documents
- Electronic Code of Federal Regulations, **19 CFR Part 141—Entry of Merchandise**: https://www.ecfr.gov/current/title-19/chapter-I/part-141

## Scope note

Required invoice content varies by destination, goods, and procedure. Validate the receiving country’s rules and broker instructions for each applicable lane.