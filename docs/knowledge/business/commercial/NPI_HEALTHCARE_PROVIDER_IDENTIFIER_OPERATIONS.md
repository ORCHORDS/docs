# NPI (National Provider Identifier) Operations

## Covered-provider identification boundary

The National Provider Identifier (NPI) is a 10-digit identifier assigned by the Centers for Medicare & Medicaid Services (CMS) to covered health care providers and to organizations that support health-care transactions in the United States. Compliance is governed by 45 CFR part 162 subpart D, which the Department of Health and Human Services adopted to give the NPI its standard identifier role. The NPI is portable across employers, locations, and state lines; once assigned it does not change.

This article covers the operational workflow a commercial entity follows when an individual or organizational provider first interacts with CMS, when an enumerated provider must update a record, and when an internal system must accept NPI data from a counterparty. It does not cover Medicare enrollment (CMS-855) or taxonomy licensing rules administered by state boards; those are separate, downstream decisions that depend on a valid NPI being in place.

## Enumeration and maintenance sequence

1. **Establish that the applicant is a covered entity.** "Health care provider" is defined by 45 CFR 160.103 to include any person or organization that furnishes, bills, or is paid for health care. If the counterparty is purely a software vendor with no clinical, billing, or administrative role for a covered provider, the NPI requirement does not bind the relationship.
2. **Capture the identity record.** The applicant supplies legal name, business address, taxonomy code, and (for individuals) Social Security Number; an organization supplies Employer Identification Number. The address of record must be a physical location; a post office box or commercial mail receiving agency is not permitted for the location of practice.
3. **Submit through the National Plan and Provider Enumeration System (NPPES).** An individual may apply on their own behalf or have an organization request an NPI on their behalf through an Electronic File Interchange (EFI) batch. The applicant or proxy attests under 18 U.S.C. 1001 that the data are correct.
4. **Receive the NPI and store the message.** CMS returns the 10-digit number together with an Enumeration Notification Letter (PDF) that contains the assigned enumeration date. Internal systems store both the number and the enumeration date because downstream processes such as credentialing rely on the letter as proof.
5. **Diffuse the NPI into business processes.** Billing systems, ordering systems, prior authorization feeds, and referral workflows must accept the NPI exactly as ten numeric digits, including the leading "1" or "2" that CMS uses to encode entity type (individual or organization).
6. **Re-verify on a documented cadence.** The NPI Registry public lookup is queried at each enumerated encounter (every order, claim, or referral) and at any material change in the relationship, and never less than annually, to detect deactivated numbers.

## Provider identity, taxonomy, and endpoint data

The minimum data set that an internal NPI record must carry is the NPI itself, the entity type code (1 = individual, 2 = organization), the legal business name as it appears on the IRS line, the practice location address including nine-digit ZIP, the authorized official contact, the primary taxonomy code, and any secondary taxonomy codes that describe additional licensed activities. The record should also capture the enumeration date, the most recent enumeration update date, and the deactivation status returned by the registry.

## NPPES verification evidence

Validation consists of three independent checks. First, the ten-character format is enforced with a Luhn checksum using the ISO/IEC 7064 MOD 11-2 algorithm published in CMS documentation. Second, the NPI Registry lookup is executed via the public NPI Registry API, which returns an enumeration date, primary practice address, and a deactivation indicator when present. Third, a sampled manual comparison is performed against the PDF Enumeration Notification Letter retrieved from the provider's own records; mismatches between the registry data and the letter must be reconciled before the NPI is released into a claim-generating system. Successful validation is recorded with the timestamp, the registry response payload identifier, and the operator initials.

## Duplicate and stale-record correction

- **Luhn failure.** The NPI is rejected at intake; the operator returns the number to the requester for confirmation rather than attempt character correction, because silent repair would mask typographical errors.
- **Registry match with deactivation flag.** A previously enumerated provider whose record is deactivated cannot be used for new transactions. The system logs the deactivated status, halts downstream activity, and routes the case to provider-relations staff, who ask the counterparty for a reactivation letter or a freshly issued NPI.
- **Mismatched name or address.** The provider's billing entity does not match the IRS line. The system holds the order, prompts for an updated W-9 or IRS letter, and requires a new NPI enumeration update before resuming.
- **EFI batch rejection.** The nightly enumeration submission fails the NPPES edit checks; the broker downloads the response file, identifies the failed records, and resubmits only the affected rows after correcting the underlying data; resubmitting an entire file without diagnosis causes the same rows to fail again.

## Identifier-use limits

An NPI identifies an enumerated provider; it does not prove licensure, credentialing, enrollment, specialty competence, exclusion status, or authority to bill a particular program. Registry data can lag provider changes, so organizations must separately validate facts required by contracts or program rules.

## Canonical sources

- **Primary authority 1:** Centers for Medicare & Medicaid Services, *National Provider Identifier Standard* — https://www.cms.gov/medicare/coding-billing/medicare-fee-service-payment/medicare-provider-utilization-and-payment-data/national-provider-identifier-standard
- **Primary authority 2:** Code of Federal Regulations, *45 CFR Part 162 — Administrative Requirements* — https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-162
