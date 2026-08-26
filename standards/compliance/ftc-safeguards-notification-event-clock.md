# FTC Safeguards Rule notification-event clock

**Issue:** A covered financial institution waits for a completed forensic report or customer notice before starting the FTC notification clock, or counts only confirmed exfiltration and misses the Rule's acquisition presumption.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Trigger

Under 16 C.F.R. Part 314, a covered financial institution must notify the FTC as soon as possible and no later than 30 days after discovering a notification event. A notification event involves unauthorized acquisition of unencrypted customer information affecting at least 500 consumers. Customer information is treated as unencrypted if an unauthorized person accessed its encryption key. Unauthorized access to unencrypted customer information is presumed to be unauthorized acquisition unless reliable evidence shows acquisition did not and could not reasonably have occurred.

## Controls

- Open a dated notification assessment as soon as potentially covered access is discovered.
- Identify the covered institution, affected systems, information type, encryption and key exposure, consumer count, discovery date, and acquisition evidence.
- Count consumers affected or potentially affected; do not wait for every identity to be confirmed before escalation.
- Preserve logs and forensic evidence capable of rebutting the acquisition presumption when appropriate.
- Put a legal/compliance decision checkpoint well before day 30 and record who approved the determination.
- Submit through the FTC Safeguards Rule form and retain the exact submission, attachments, acknowledgement, and any law-enforcement delay request.
- Track state, contractual, sectoral, and other federal notice duties independently; the FTC filing does not satisfy them automatically.

## Verification

Run a tabletop for unauthorized database access affecting 499, 500, and an initially unknown number of consumers. Include encrypted data with exposed keys and access with evidence that acquisition was impossible. Verify the incident system starts the deadline, preserves the rationale, and blocks closure until every applicable notice obligation has an owner.

## Gotchas

The threshold is not 500 records. A report may become public, so exclude unnecessary secrets, exploit details, and personal data while still providing required facts. “No confirmed download” is not by itself reliable evidence that rebuts the Rule's presumption.

## Official sources

- [FTC: Safeguards Rule—What Your Business Needs to Know](https://www.ftc.gov/business-guidance/resources/ftc-safeguards-rule-what-your-business-needs-know)
- [FTC Safeguards Rule Security Event Reporting Form](https://www.ftc.gov/business-guidance/privacy-security/gramm-leach-bliley-act/safeguards-rule-form)
- [16 C.F.R. Part 314](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314)
