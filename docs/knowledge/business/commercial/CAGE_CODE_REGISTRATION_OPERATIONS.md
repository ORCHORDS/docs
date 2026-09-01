# CAGE Code Registration Operations

## When a CAGE code is required

The Commercial and Government Entity (CAGE) code is a five-character identifier used by the U.S. Department of Defense and other federal agencies to identify vendors and government activities. The codes are assigned, maintained, and validated by the Department of Defense through the Defense Logistics Agency's CAGE program. A CAGE code is required for any entity doing business with the federal government under the Federal Acquisition Regulation, for entities subject to certain DoD reporting, and as a prerequisite for SAM.gov registration. This article covers the assignment workflow, the data fields required, and the validation evidence that supports internal controls. It does not cover NATO CAGE (NCAGE) codes, which are issued separately by the NATO Support and Procurement Agency.

## Entity validation and code-assignment sequence

1. **Determine if a CAGE code is required.** U.S. and foreign vendors seeking federal awards, vendors reporting to the DoD under reporting regulations, and vendors identified through the SAM registration process must hold a CAGE code. Vendors that do not interact with the federal government do not need one.
2. **Trigger assignment.** For most registrants, the CAGE code is assigned automatically through the SAM.gov registration process when the entity does not already have one. Foreign entities that need a CAGE code prior to SAM registration submit a CAGE request through the NSPA NATO website or directly through the DoD Service Desk.
3. **Provide entity identification data.** The applicant supplies the legal name, division or department name where applicable, the physical address, the mailing address, the country code (ISO 3166-1 alpha-2 for foreign entities, "USA" for domestic), the unique entity identifier (UEI), and the entity type (corporation, partnership, sole proprietorship, government entity, or other).
4. **Receive the code and validation date.** The DLA returns a five-character CAGE code composed of one alphabetic character and four alphanumeric characters. The validation date is the date the entity record was last reviewed; the code itself does not expire, but accuracy is the registrant's responsibility.
5. **Maintain the record.** When the legal name, address, ownership, or any material data point changes, the entity updates the record through SAM.gov, and the DoD CAGE process synchronizes the change. Annual renewal of SAM propagates to CAGE without separate action.
6. **Disclose relationships and exclusions.** During SAM registration the entity must report immediate owner relationships, ultimate parent relationships, and any excluded-party status under the System for Award Management exclusions list.

## Legal-entity and physical-address data

The CAGE record carries the code itself, the legal business name, the entity division (where the CAGE code is for a division rather than the entire company), the physical address with country code, the mailing address, the phone number, the corporate status (for-profit, nonprofit, government, individual), the registration purpose code, the UEI, and any past CAGE code assigned to the same entity. Foreign entities must also include the NATO Commercial and Government Entity code if one was previously assigned and the country of registration.

## Assignment and renewal evidence

Validation is performed through three artifacts. First, the SAM.gov public search returns the entity record with the active CAGE code visible; a screenshot is captured at each new award cycle. Second, the DLA CAGE Code Lookup tool returns a record whose validation date is current. Third, the entity's internal CAGE register reconciles the CAGE code with the corresponding SAM UEI and with the primary NAICS code; mismatch is an automatic control failure.

## CAGE mismatch remediation

- **Stale address.** The legal entity moved its headquarters, and the SAM record still carries the old address. The correction is made by editing the SAM registration; the change propagates to the CAGE record within the next synchronization cycle. Awards cannot be paid to the registered address until the record is corrected.
- **Duplicate CAGE code request.** A vendor submits a fresh CAGE request when one already exists under a different corporate identity. The CAGE program returns a message indicating that a code exists; the entity must use the existing code or document the corporate identity change through the SAM validation path.
- **Foreign entity without country code.** A foreign firm provided a CAGE request but omitted the ISO country code, causing the validation to fail. The request is resubmitted with the country code populated; missing country codes are a common cause of NCAGE rejection.
- **Mismatch between CAGE and SAM registration purpose code.** The CAGE record shows "Z2 — Entity validated for SAM registration" while the SAM registration has expired. The vendor cannot receive federal awards until the SAM record is renewed; the CAGE record itself is not invalidated.

## Registration boundaries

A CAGE code identifies an entity record but does not establish responsibility, award eligibility, security clearance, ownership approval, or active SAM status. Foreign NCAGE processing and classified contracting can impose additional procedures that this domestic operational workflow does not resolve.

## Canonical sources

- **Primary authority 1:** U.S. Department of Defense, *CAGE Code Lookup* — https://cage.dla.mil/Home/AboutCage
- **Primary authority 2:** Defense Logistics Agency, *Commercial and Government Entity (CAGE) Codes* — https://www.dla.mil/HQ/Information-Operations/Logistics-Information-Services/CAGE-Code/
