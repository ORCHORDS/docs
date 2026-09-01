# FDA Establishment Registration and Drug Listing

## Drug registration and listing boundary

The U.S. Food and Drug Administration requires establishments engaged in the manufacture, preparation, propagation, compounding, or processing of human drugs, biologics, and animal drugs to register and list their commercial products. The requirements are codified at 21 CFR part 207, which the FDA modernized in a 2016 final rule to require electronic submission only via the FDA Electronic Submissions Gateway and Structured Product Labeling (SPL). This article covers the operational workflow for new establishment registration, drug listing, and the December 31 / June 30 annual renewal cadence. It does not cover medical device establishment registration, which is governed by 21 CFR part 807, nor does it cover the separate FDA prior notice of imported food, which is a different filing.

## Establishment-to-product submission sequence

1. **Identify whether the activity triggers registration.** A foreign or domestic establishment that performs one of the regulated operations on a drug product that will be marketed in the United States must register, and each drug manufactured for commercial distribution must be listed. Establishments that only perform labeling, relabeling, or distribution without physically altering the drug are typically not registrants themselves but may be designated as the labeler on a listing.
2. **Establish the registration account.** The registrant obtains a Secure Supply Chain Partner account, links an FDA email, and requests a Coregistration ID; this identity will be reused for every subsequent SPL submission.
3. **Submit the establishment registration SPL.** The registrant uploads the FDA Structured Product Labeling document containing establishment name, DUNS (or, as of FDA updates, UEI), street address, the responsible person, the operations performed (manufacturer, packer, labeler, repackager), and the registration effective date.
4. **Submit the drug listing SPLs.** For each drug, the registrant files a separate SPL with the established drug name, active and inactive ingredients, dosage form, route of administration, marketing category, labeler code, and the package code. NDC codes are assigned through this submission.
5. **Refresh on material change.** When an establishment adds a new product, stops marketing a listed product, or changes the labeling, the registrant files an updated SPL within the timeline described in 21 CFR 314.72; certain changes may require a prior approval supplement rather than an update.
6. **Renew annually.** Two registration renewal windows are available: October 1 through December 31 for the calendar-year cycle, and January 1 through June 30 for the same cycle with a documented penalty path. Domestic registrants must renew by December 31; foreign registrants are required to renew no later than June 30 because the FDA requires reidentification of a U.S. agent annually.

## FEI, labeler, NDC, and SPL data

A compliant registration record must carry the legal name, the unique facility identifier (DUNS or UEI), the street address with country and state code, the registration effective date, the name and contact of the responsible person (US agent for foreign establishments), and the list of operations performed. A drug listing record must carry the NDC labeler-product-package triplet, the proprietary name, the established name or proper name, the active ingredient(s) with strength and unit, the dosage form, the route of administration, the marketing start date, and the SPL document identifier (setID) that points to the current labeling.

## FDA receipt and status evidence

Validation occurs in three steps. First, the FDA ESG acknowledgment is captured; the gateway returns a receipt with a core ID and submission timestamp. Second, the FDA responds with an NDC assignment or an error code; the operator downloads the SPL validation report and confirms that the labeler-product-package triplet is unique within the firm's catalog. Third, the public NDC Directory and the FDA's registered-entity listings are queried to confirm that the entry is publicly visible. The validation cycle is repeated for every batch submission and is considered complete only when both the establishment and the dependent product listings are live.

## Listing rejection and discontinuation handling

- **Receipt without NDC.** The FDA returned a submission receipt but did not assign an NDC. The operator opens the validation report, identifies the structural error, corrects the SPL, and resubmits; resubmitting the original file without correction triggers the same validation failure.
- **NDC collision.** Two SPLs compete for the same labeler-product-package triplet. The operator determines which entry is canonical, withdraws the conflicting SPL using the SPL withdrawal transaction, and confirms via the NDC Directory that the surviving listing is the one referenced by commercial systems.
- **Late renewal.** A foreign establishment misses the June 30 deadline. The operator re-establishes registration using a fresh SPL marked "renewal," but until the FDA re-confirms, drug shipments to the United States are not authorized and must be held; attempting to use a lapsed registration is a frequent compliance citation.
- **US agent missing for foreign firm.** A foreign establishment's registration is suspended until the U.S. agent is confirmed. The firm provides the agent's name, address, and a signed letter authorizing the agent, and resubmits; registrations are not cleared for new listings until this agent is active in the record.
- **Wrong marketing category.** A drug listed as an approved application but lacking the underlying NDA or ANDA number triggers a listing error. The operator confirms the application number in the Drugs@FDA database, updates the SPL, and resubmits with the correct application citation.

## Registration and listing limits

Registration and listing do not constitute FDA approval, establish that a drug may lawfully be marketed, or replace application, labeling, quality-system, or adverse-event obligations. Submission windows and identifiers should be confirmed in current FDA technical guidance before filing.

## Canonical sources

- **Primary authority 1:** U.S. Food and Drug Administration, *Drug Establishment Registration and Drug Listing* — https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishment-registration-and-listing
- **Primary authority 2:** Code of Federal Regulations, *21 CFR Part 207 — Registration of Producers of Drugs and Listing of Drugs in Commercial Distribution* — https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-207
