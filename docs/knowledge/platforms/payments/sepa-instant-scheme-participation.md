# SEPA Instant Scheme Participation Readiness

**Issue:** The SEPA Instant Credit Transfer (SCT Inst) scheme, administered by the European Payments Council (EPC), allows euro-denominated credit transfers across SEPA area bank accounts with a settlement guarantee of seconds — typically under 10 seconds end-to-end. SCT Inst has been operational since 2017, with the mandatory reachability for euro-area PSPs starting in stages since 2024 under the EU Instant Payments Regulation (Regulation (EU) 2024/886). Engineering readiness for SCT Inst participation means meeting the scheme's technical requirements (24/7 availability, message format compliance, sanctions screening integration), the regulatory obligations (mandatory reachability, sanctions screening on every transaction, IBAN-name verification), and the operational readiness (24/7 operational support, exception handling, sanctions reporting).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Scheme fundamentals

1. **The SCT Inst rulebook.** The EPC publishes the SCT Inst Rulebook defining the scheme's participants, the message formats (ISO 20022 pain.001), the maximum execution time (10 seconds for credit transfer confirmation, with exceptions for risk-related holds), and the addressable amounts (initially €15,000 cap, raised to €100,000 in certain versions).
2. **Reachability requirements.** The EU Instant Payments Regulation requires euro-area PSPs to receive SCT Inst from any other reachable PSP, with the receiving capability extending to all euro-area PSPs by phased deadlines in 2025 and 2026. Non-euro-area SEPA PSPs are not yet bound by the mandatory reachability but may participate voluntarily.
3. **AML/sanctions screening.** The regulation requires sanctions screening on every instant payment, with screen-on-screen and screen-on-name workflows. The reachability does not exempt PSPs from existing AML obligations.

## Technical readiness

1. **24/7 processing capability.** SCT Inst operates continuously, including weekends and holidays. The PSP must operate processing systems that handle inbound and outbound SCT Inst 24/7, with automated recovery for systems that are normally batch-oriented.
2. **ISO 20022 message handling.** SCT Inst uses ISO 20022 messages (pain.001 for the customer-to-bank initiation, pacs.008 for the inter-PSP settlement, pacs.002 for the status report). The PSP must support the full message schema, with proper handling of optional fields, structured remittance information, and purpose codes.
3. **Routing and addressing.** SCT Inst routing uses the IBAN as the address. The PSP must validate the IBAN, route to the receiving PSP via the SEPA payment scheme routing directory (or the equivalent CSM infrastructure), and handle the response within the 10-second execution window.

## Operational readiness

1. **Exception handling.** SCT Inst exceptions include: insufficient funds, account closed, blocked account, sanctions match, AML hold, IBAN-name mismatch (where verification is enabled), and technical timeout. The PSP must handle each exception with a defined return path, including the pain.002 status report and, where applicable, an investigation workflow.
2. **Sanctions reporting.** The EU Instant Payments Regulation requires PSPs to report sanctions hits on instant payments to the relevant authority within defined timelines. The PSP must integrate the sanctions reporting workflow with the instant payment processing pipeline.
3. **Operational support.** SCT Inst operates continuously, so the PSP must provide 24/7 operational support including weekends and holidays. A PSP that relies on business-hours support cannot meet the scheme's operational expectations.

## Engineering controls

1. **Processing pipeline.** Engineering must build the SCT Inst processing pipeline as a 24/7 service, with the inbound and outbound paths sharing the same quality controls. The pipeline must include: IBAN validation, sanctions screening, AML screening, balance check, fraud scoring, routing, and execution.
2. **Timeout and fallback handling.** The 10-second execution window is a hard constraint. The processing pipeline must detect a timeout at the scheme layer and respond with the appropriate status code. A PSP that misses the timeout must report the incident and recover.
3. **Reconciliation.** SCT Inst transactions must reconcile against the bank statement and the scheme's daily reports. Engineering must run the reconciliation on a continuous basis, with discrepancies flagged for investigation.

## Compliance considerations

1. **Mandatory reachability timeline.** The EU Instant Payments Regulation sets phased deadlines for euro-area PSPs: receiving capability from euro-area PSPs by early 2025, sending capability by mid-2025, full euro-area reachability by early 2026 (with extensions for some PSPs). Engineering must align with the deadlines applicable to the PSP's home member state.
2. **Sanctions screening per transaction.** The regulation requires sanctions screening on every instant payment, with the screening integrated into the processing pipeline. The PSP must document the screening approach, the screening vendor, the screening cadence, and the false-positive handling.
3. **IBAN-name verification.** The regulation encourages (and some member states require) IBAN-name verification: the receiving PSP compares the IBAN owner name to the payee name in the payment instruction and flags mismatches. Engineering must implement the verification workflow, with the response returned to the originating PSP within the SCT Inst execution window.

## Failure modes

1. **SCT Inst pipeline fails over to batch.** A PSP whose SCT Inst pipeline falls over to a batch-processing fallback cannot meet the 10-second execution window and creates a poor customer experience. The fallback must be designed to maintain the SCT Inst execution window or to return a clear status that the customer can interpret.
2. **Sanctions screening bottleneck.** A sanctions screening vendor that adds more than 1-2 seconds to the processing pipeline forces the PSP to miss the execution window. Engineering must monitor the vendor's response time and have a backup screening vendor ready if performance degrades.
3. **Missed reachability deadline.** A PSP that misses the EU Instant Payments Regulation's reachability deadline faces regulatory penalties and customer experience failure. Engineering must align with the deadlines and have a tested implementation before each deadline.

## Canonical sources

1. European Payments Council, SEPA Instant Credit Transfer Scheme Rulebook, current published version. https://www.europeanpaymentscouncil.eu/what-we-do/sepa-instant-credit-transfer
2. Regulation (EU) 2024/886 of the European Parliament and of the Council of 13 March 2024 amending Regulations (EU) No 260/2014 and (EU) 2021/1230 as regards instant credit transfers in euro (Instant Payments Regulation). https://eur-lex.europa.eu/eli/reg/2024/886/oj
