# SAM.gov NAICS Self-Certification Operations

## Entity registration and size-claim boundary

Federal contractors and grant recipients must register and maintain an active record in the U.S. System for Award Management (SAM) at SAM.gov. As part of that record, the entity self-certifies the North American Industry Classification System (NAICS) code that best describes the goods or services it provides, including any secondary codes. NAICS codes drive small-business set-asides, size standards, and procurement forecasts. The classification list is maintained jointly by the U.S. Census Bureau and Statistics Canada and adopted by Mexico's INEGI. This article covers the operational workflow for assigning, maintaining, and updating a NAICS code in SAM and the validation evidence that an internal governance program should capture. It does not cover the SBA size-standard appeal process, which is a separate determination under 13 CFR part 121.

## NAICS selection and SAM maintenance sequence

1. **Determine the primary business activity.** The entity identifies the activity that generates the highest revenue or, when revenue is not yet meaningful, the activity it intends to perform for federal customers. NAICS is assigned based on the production process rather than the end customer, so a firm that produces custom software as a service is classified in 541511 (Custom Computer Programming Services) rather than 511210 (Software Publishers) regardless of who buys the output.
2. **Review the NAICS description and index entries.** The Census Bureau publishes the NAICS code descriptions in HTML and PDF; the SAM.gov interface also provides a lookup. Cross-reference the description against the planned scope of work and confirm the corresponding SBA size standard in the Table of Small Business Size Standards.
3. **Apply the size standard.** Once the NAICS code is selected, the SBA size standard for that code determines whether the entity is "small" for set-aside purposes. Size standards vary from receipts-based (most services and retail) to employee-based (manufacturing) to megawatt-hours-based (electric power generation).
4. **Enter the code in the SAM record.** The registrant enters the NAICS code, the corresponding size standard, and the "self-certification checkbox" attesting under 18 U.S.C. 1001 that the size representation is accurate. The entry is reviewed annually.
5. **Maintain and update.** Material changes in revenue mix or business activity require a SAM update within 60 days; failure to update can result in an inactive record and disqualification from active solicitations.
6. **Renew annually.** A SAM record lapses if the entity does not complete the renewal process; after expiration, the entity cannot receive new federal awards until a fresh registration is processed.

## Entity, activity, and representation data

A controlled NAICS record must capture the six-digit code, the code description, the size standard used (including the basis — receipts, employees, or other), the revenue or employee count as of the SBA size-standard calculation date (typically the most recently completed fiscal year), the date of the most recent self-certification, and the operator who attested. If the entity claims an exception to the size standard (such as the nonmanufacturer rule for supply contracts), the exception and its underlying rationale are recorded separately.

## Registration and solicitation evidence

Validation evidence consists of three artifacts. First, a screenshot of the SAM registration record shows the NAICS code and the size standard at the moment of submission. Second, the SAM-generated PDF registration record is retained with the entity's registration purpose code, expiration date, and the unique CAGE code. Third, an internal review trail records the calculation of the size metric (revenue, employees, or other), the supporting source documents (audited financial statements or payroll register), and the operator's initials.

## Classification and certification correction

- **Wrong NAICS code.** A firm self-certified 423840 (Industrial Supplies Merchant Wholesalers) when the actual revenue mix was heavier in 423610 (Electrical Apparatus and Equipment). The correction is made in SAM by editing the NAICS code and reattesting; size status is recomputed and any active solicitation eligibility is reviewed.
- **Outdated size representation.** The entity crossed a size threshold but did not update SAM. The correction is to update the size metric, reattest, and document the date of the change. If the size changed during an active award, the contracting officer must be notified under the size representation obligation.
- **Lapsed SAM record.** A lapsed record returns a "Inactive" status. The entity resubmits the registration, which requires validation of the Employer Identification Number and the bank account information through the IRS and Treasury validation services; new opportunities are paused until the registration returns to "Active."
- **Conflict between primary and secondary codes.** A secondary code that drives a smaller size standard exposes the entity to an SBA protest. The internal review checks each code that could plausibly be matched against the requirement and documents the response.

## Procurement-context limits

A NAICS selection does not conclusively decide size for every procurement, and a contracting officer may assign a solicitation-specific code. Affiliations, exceptions, and recertification events require separate analysis under current SBA rules; this workflow is not an SBA size determination.

## Canonical sources

- **Primary authority 1:** U.S. Census Bureau, *North American Industry Classification System (NAICS)* — https://www.census.gov/naics
- **Primary authority 2:** U.S. General Services Administration, *System for Award Management (SAM.gov)* — https://sam.gov/content/entity-registration
