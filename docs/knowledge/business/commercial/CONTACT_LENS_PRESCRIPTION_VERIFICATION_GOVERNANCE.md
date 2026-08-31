# Contact Lens Prescription Verification Governance

## Purpose

The U.S. Federal Trade Commission's Contact Lens Rule protects a patient's ability to obtain and use a contact lens prescription with a seller of their choice. Prescribers must release prescriptions after fitting, and sellers must obtain a prescription or verify prescription information through the Rule's verification process before selling lenses.

A reliable workflow separates prescription release, prescription verification, seller fulfillment, digital-delivery consent, and recordkeeping so commercial activity does not interfere with the patient's prescription rights.

## Prescription release after fitting

Prescribers must provide the patient a copy of the contact lens prescription immediately upon completion of the fitting, whether or not the patient asks for it.

The release should not be conditioned on:

- buying lenses from the prescriber;
- paying an extra prescription-copy fee;
- signing a liability waiver;
- agreeing not to buy elsewhere; or
- requesting the prescription through a later support process.

If the prescriber is willing to sell the patient lenses, the FTC explains that the fitting is complete and the prescription must be provided.

## Paper and digital delivery

Digital delivery can be used when the patient affirmatively agrees, in writing or electronically, to receive the prescription digitally and to the specific delivery method. The prescription must be accessible, downloadable, and printable.

If the patient does not agree to digital delivery, provide a printed copy immediately following the fitting.

Keep records of digital-delivery consent and evidence of digital delivery as required by the Rule. Do not make a portal the only practical way for a patient to obtain a prescription when the patient has not agreed to that method.

## Receipt confirmation

When the prescriber sells contact lenses or has a direct or indirect financial interest in lens sales, the Rule generally requires requesting written confirmation that the patient received the prescription.

The confirmation must occur after the prescription is provided. A confirmation embedded in pre-appointment forms or captured before release does not satisfy the purpose of confirming actual receipt.

FTC guidance describes acceptable confirmation approaches and requires relevant records to be retained for at least three years.

## Seller verification boundary

A contact lens seller may sell lenses when it either:

- obtains a copy of a valid prescription; or
- verifies the prescription with the prescriber through the procedures established by the Rule.

Seller systems should not treat customer-entered prescription details as verified merely because they are plausible. The source and verification status should remain explicit in the order record.

## Verification request content

A seller's verification request should include the information required by the Rule and be transmitted through a method the seller can evidence later. Operationally, preserve enough information to show:

- the patient and prescriber associated with the request;
- the lens prescription details submitted for verification;
- when the request was sent;
- the communication channel used; and
- any prescriber response.

Do not send unrelated customer data with the verification request.

## Prescriber response

When responding to a verification request, the prescriber should confirm, correct, or reject the prescription information as appropriate. FTC guidance states that prescribers must inform the seller when a prescription is expired and must correct inaccuracies or explain why the prescription is invalid.

Route verification requests to a monitored workflow. A request should not fail simply because it arrived in a mailbox, fax queue, or phone system that nobody reviews.

## Passive verification and the eight-business-hour period

The Rule includes a passive-verification mechanism. If a valid verification request is received and the prescriber does not respond within the applicable eight-business-hour period, the seller may be permitted to treat the prescription as verified under the Rule.

Because timing determines the seller's authority to fulfill an order, systems should:

1. timestamp transmission and receipt where available;
2. calculate the applicable business-hour window consistently;
3. preserve prescriber responses;
4. stop passive verification when the prescriber timely communicates a correction, expiration, or invalidity; and
5. prevent manual staff from shortening the period for convenience.

Consult the current Rule and FTC guidance for the precise definition and calculation of the verification period.

## Automated telephone verification

FTC guidance includes specific requirements when sellers use automated telephone messages to submit verification requests. Where this method is used, the seller should implement the Rule's required call-recording and message-content controls and preserve complete recordings for the required period.

Automated systems should be tested for intelligibility, complete data transmission, and accurate callback information. A failed or truncated call should not silently start a passive-verification clock.

## Customer-provided prescription path

Sellers should give customers a clear method to provide a prescription directly. A workflow that forces customers to enter prescriber information before offering a practical prescription-upload or submission path can create unnecessary verification traffic and customer friction.

Validate uploaded documents enough to associate them with the correct order without modifying the prescriber's prescription data.

## Additional-copy requests

Patients and authorized agents can request an additional copy of a contact lens prescription. FTC guidance states that the prescriber generally must provide the additional copy within 40 business hours.

Track these requests separately from third-party verification so:

- the request is not mistaken for a verification notice;
- requester authority is checked appropriately;
- the response deadline is visible; and
- delivery evidence is retained where required.

## Order-change controls

If the customer changes lens parameters, quantity, or product after prescription verification, determine whether the existing verification still supports the changed order. Do not carry verification status to an order that no longer matches the verified prescription.

Similarly, a new order after prescription expiration may require a current prescription or a new verification process.

## Conflict and correction handling

If a prescriber reports that submitted information is inaccurate, update the order record without rewriting the historical verification evidence. Preserve:

- what the seller originally submitted;
- what the prescriber corrected;
- the time of the correction; and
- how fulfillment was changed.

The customer should receive a clear next step without being placed between the seller and prescriber to reconcile system errors unnecessarily.

## Privacy and minimization

Prescription verification involves health-related information. Limit access to personnel and systems that need it, transmit requests through approved channels, and avoid repurposing prescription data for unrelated marketing or profiling.

Retention should satisfy applicable legal and operational requirements without preserving duplicate prescription images or recordings indefinitely.

## Quality review

Periodically sample seller and prescriber workflows for:

- automatic prescription release after fitting;
- valid digital-delivery consent;
- confirmation captured only after release;
- complete verification requests;
- correct eight-business-hour handling;
- timely prescriber corrections;
- automated-call recording where applicable;
- prevention of fulfillment against an invalid or mismatched prescription; and
- timely additional-copy responses.

Repeated exceptions should trigger process correction rather than case-by-case workarounds.

## Sources

- Federal Trade Commission — The Contact Lens Rule: A Guide for Prescribers and Sellers: https://www.ftc.gov/business-guidance/resources/contact-lens-rule-guide-prescribers-sellers
- Federal Trade Commission — FAQs: Complying with the Contact Lens Rule: https://www.ftc.gov/business-guidance/resources/faqs-complying-contact-lens-rule
- Federal Trade Commission — Contact Lens Rule, 16 CFR Part 315: https://www.ftc.gov/legal-library/browse/rules/contact-lens-rule

## Scope note

This article summarizes general U.S. operational practices under the FTC Contact Lens Rule. Professional-practice, privacy, prescription, and state requirements may add obligations. It is not legal or clinical advice.