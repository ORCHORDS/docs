# Card Network Interchange Qualification Review

**Issue:** Interchange fees are the largest component of card acceptance cost, typically 70-85% of the merchant discount. Each transaction must be classified under the scheme and acquirer's published interchange programs — categories like Consumer Credit, Consumer Debit, Regulated Debit, Commercial, Business, Corporate, Purchasing — with rate qualifiers like CPS (Custom Payment Service) indicators, transaction codes, merchant category codes, and authorization characteristics. Misqualification inflates per-transaction costs by tens of basis points across the volume; over the year, the difference between qualified and non-qualified rates can exceed the gross margin of low-margin merchants. Engineering the qualification flow means understanding what data the acquirer uses to classify a transaction, what data the merchant controls, and how to surface the rate qualifier back into the transaction record so that finance teams can audit qualification rates over time.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What drives qualification

1. **Card type and product class.** Each card carries a product identifier (Visa Base I, Visa Rewards, Mastercard World, Amex OptBlue, Discover Card, JCB, UnionPay, etc.) and a class (Consumer, Commercial, Business, Corporate, Purchasing). The interchange program is keyed on this combination. The acquirer reads the BIN range and issuer product table to determine the rate.
2. **Transaction characteristics.** Card-present versus card-not-present, magnetic stripe, EMV chip, contactless, keyed, e-commerce, recurring — each maps to a specific interchange program. Magnetic stripe fallback transactions pay a higher interchange penalty than EMV chip transactions; e-commerce without 3DS pays a different rate than e-commerce with 3DS.
3. **Merchant data.** Merchant Category Code (MCC), business-to-business flag, tax indicator, and level-2/level-3 line-item data all qualify the transaction. Corporate and Purchasing cards qualify for lower interchange when level-2/level-3 data is submitted; without it the transaction downgrades to a higher rate.

## Qualifier fields the merchant controls

1. **MCC and acquirer configuration.** The MCC is set at merchant onboarding; mismatches between actual business activity and registered MCC trigger interchange qualification disputes. Engineering cannot change the MCC mid-stream, but the data pipeline must carry the MCC into transaction records for reconciliation.
2. **Transaction code (sandbox).** The transaction code sent in the authorization (e.g., the Visa Transaction Code, Mastercard POS Entry Mode, Amex submission code) drives qualification. Refunds, cash advances, and quasi-cash transactions are differentiated; engineering must send the correct code based on the actual transaction type.
3. **Level 2/level 3 data.** For B2B and government card acceptance, submitting the invoice line items, the tax amount, and the customer reference (level 3 for Visa, level 2 for Mastercard) qualifies the transaction for a lower interchange rate. The integration surface is the merchant's invoicing system, and engineering must build a path from invoice generation to authorization-time enrichment.

## Authorization characteristics that matter

1. **AVS and CVV match.** Address Verification System (AVS) and Card Verification Value (CVV) checks are required for some interchange programs. A transaction submitted without AVS or CVV, or with a non-match, may downgrade. Engineering must send the AVS and CVV in the authorization and capture the response codes.
2. **3DS authentication.** For e-commerce, transactions authenticated with 3DS (frictionless or challenge) qualify for the lower interchange program in many schemes. The 3DS result must be passed through the authorization as the ECI value and the authentication reference. A 3DS result that is missing or malformed forces the higher e-commerce rate.
3. **Authorization timeliness.** Transactions that settle more than a defined number of days after authorization pay a higher interchange in some programs. Engineering must ensure the settlement file reaches the acquirer within the scheme window — typically 24-72 hours.

## Operational diagnostics

1. **Qualification rate dashboard.** Track, by acquirer and by scheme, the share of transactions that qualified for the lowest available interchange program versus the share that downgraded. The downgrade-share is the diagnostic: each downgrade category (AVS mismatch, missing 3DS, missing level-3 data, late settlement) is a different engineering action.
2. **Downgrade reasons by MCC.** Per-MCC downgrade reasons highlight whether the issue is data submission (engineering fixable), acquirer configuration (vendor fix), or card-mix (commercial negotiation). Engineering owns the first; the second and third are vendor or finance actions.
3. **Interchange-plus versus blended pricing reconciliation.** Engineering must support both interchange-plus (each transaction at its actual interchange) and blended (flat merchant discount rate) pricing models. Reconciliation is straightforward in interchange-plus: the acquirer reports interchange per transaction. In blended models, the effective rate is hidden behind the flat fee, and finance teams must do a periodic true-up against the acquirer's interchange detail report.

## Failure modes

1. **Silent downgrades from missing data.** The most common failure is a transaction downgrading because the merchant did not submit a required field, and the engineering team never notices because the authorization still approved. Engineering must surface interchange qualification as a first-class signal in the transaction record.
2. **Settlement lag downgrades.** End-of-day settlement files that fail to upload due to a network blip can push transactions past the scheme's authorization-to-clearing window. Engineering must build retry and queue depth monitoring on the settlement upload path.
3. **Mid-batch MCC changes.** A merchant onboarding a new business vertical under an existing MCC can quietly misclassify transactions if the acquirer was not updated. Engineering cannot detect this from the authorization; only finance can, by reviewing the MCC-level interchange rate trends.

## Canonical sources

1. Visa, Visa Core Rules and Visa Public Interchange Rates and Qualification Framework, current edition. https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf
2. Mastercard, Mastercard Interchange Rate Qualification Framework and Customer Interface Specification, current edition. https://www.mastercard.us/content/dam/mccom/global/documents/interchange-rates-and-qualification-framework.pdf
