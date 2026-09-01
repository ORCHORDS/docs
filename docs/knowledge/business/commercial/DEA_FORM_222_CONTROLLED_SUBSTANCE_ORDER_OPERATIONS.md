# DEA Form 222 and Controlled-Substance Order Operations

## Schedule I and II ordering boundary

DEA Form 222 is the official order form used by DEA registrants to schedule I and II controlled substances under the Controlled Substances Act. The U.S. Drug Enforcement Administration (DEA) authorizes its use through 21 CFR part 1305, which prescribes the form's preprinted serial number, the segregation of copy requirements, and the use of the DEA Controlled Substance Ordering System (CSOS) as the electronic equivalent. This article covers the operational workflow a registrant follows when purchasing, returning, or correcting Schedule I or II controlled substances, including both paper Form 222 and CSOS operations. Schedule III through V controlled substances are governed by 21 CFR part 1306 and are not within the Form 222 boundary.

## Order-form issuance and fulfillment sequence

1. **Confirm the supplier's registration.** Before accepting or transmitting any order, the buyer verifies that the supplier holds a valid DEA registration that authorizes the schedules being purchased. The verification uses the DEA Registration Validation Tool and stores the registration number, expiration date, and schedules authorized.
2. **Choose the order channel.** If the buyer is CSOS-enabled and the supplier accepts CSOS, the order is issued electronically. Otherwise, a paper Form 222 preprinted with the buyer's name, address, and registration number is used. A buyer may mix channels only when each line item clearly indicates the channel used.
3. **Populate the schedule items.** Each line carries the drug name (or finished dosage form), the number of packages or units, the package size, and the National Drug Code (NDC) when available. The buyer does not alter the preprinted serial number or alter the form's printed items in pen or pencil.
4. **Transmit and retain copies.** The paper Form 222 has a triplicate design: Copy 1 is sent to the supplier, Copy 2 is retained by the buyer, and Copy 3 is retained at the registrant's registered location for two years per 21 CFR 1305.13. CSOS transactions are stored by the CSOS server for the same two-year minimum and retrievable on demand.
5. **Receive, reconcile, and execute.** The supplier fills the order line by line; any partial fill or substitution must be annotated on Copy 1. The buyer matches Copy 2 against the received goods, records any discrepancies, and stores the executed Form 222 alongside the receiving document.
6. **Execute returns or corrections.** Unwanted, refused, or damaged Schedule I/II substances are returned on a Form 222 with "RETURN" entered in the space for the supplier's registration number per 21 CFR 1305.15. Corrected copies are voided by writing "VOID" across the form and retaining it with the records.

## Registrant, item, and quantity data

The order record must capture the preprinted serial number (e.g., "A12345678"), the buyer's DEA registration number, the supplier's DEA registration number, the date the order was issued, the line-item drug identification (name, NDC if known, dosage strength), the package count and package size, the total activity or volume in metric units when the item is a controlled precursor, and the signature of the buyer (paper) or the digital certificate identifier (CSOS). When the order is partial, each line must show the quantity shipped, the date of shipment, and the supplier's annotation. A common audit finding is the missing metric quantity for list I chemicals; both 21 CFR 1305.06 and 21 CFR 1310 place this data point on the registrant.

## Executed-order evidence

Validation has two distinct branches. For paper transactions, an internal control operator opens each Form 222 and confirms that the preprinted serial number is unaltered, that all required copies are present, that signatures are dated and match the signatory authority list, and that the retained copies are filed under a single chronological index. For CSOS transactions, the operator downloads the signed order from the CSOS server, validates the digital signature against an active CSOS certificate, and confirms that the signer's certificate was valid on the date the order was issued (CSOS certificates have a defined validity period tied to the DEA registration). Sample-test outcomes are recorded as a percentage of total orders; reconciliation failures above a documented threshold trigger a control review.

## Void, loss, and discrepancy handling

- **Altered preprinted serial number.** Any pen, pencil, or printed alteration to the serial number invalidates the Form 222. The operator isolates the form, voids it by writing "VOID" across it, files the voided original, and reissues a clean form using the next preprinted serial in stock.
- **Missing buyer signature on CSOS.** A CSOS order submitted without a valid digital signature is rejected at the supplier side and at the CSOS audit log. The buyer voids the order in the CSOS portal and re-issues from the same digital certificate; orders signed by an expired certificate require certificate renewal before re-issuance.
- **Schedule mismatch.** A buyer who orders a Schedule I item from a supplier whose registration only authorizes Schedule II receives no shipment. The buyer annotates Copy 2 with the supplier's refusal reason, voids Copy 1, and routes the case to the compliance officer.
- **Lost or stolen blank form.** Because blank Forms 222 are serialized and accountable, any loss is reported to the DEA Diversion Control Field Division within one business day per 21 CFR 1305.16. The internal inventory log is annotated, and the missing serial range is added to a do-not-ship list shared with contracted suppliers.
- **Quantity discrepancy on receipt.** The delivered package count does not match Copy 2. The buyer does not return the partial shipment; instead, the buyer annotates the discrepancy on Copy 2, files a DEA Form 106 (Report of Loss or Theft) only when material loss is suspected, and works with the supplier to correct the record.

## Controlled-substance ordering limits

Form 222 controls do not replace inventory, theft-or-loss reporting, state controlled-substance licensing, or prescription requirements. Registrants must confirm current DEA instructions and registration scope before each operational change; this workflow does not authorize a transaction that the registration itself excludes.

## Canonical sources

- **Primary authority 1:** U.S. Drug Enforcement Administration, *DEA Form 222 — Instructions and Information* — https://www.deadiversion.usdoj.gov/21cfr/cfr/1305/1305_01.htm
- **Primary authority 2:** Code of Federal Regulations, *21 CFR Part 1305 — Order Forms* — https://www.ecfr.gov/current/title-21/chapter-II/part-1305
