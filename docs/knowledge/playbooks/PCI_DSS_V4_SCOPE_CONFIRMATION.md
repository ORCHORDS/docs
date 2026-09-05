# PCI DSS v4.0 Scope Confirmation

## Purpose
Reconfirm the PCI DSS v4.0 Cardholder Data Environment (CDE) and Sensitive Authentication Data (SAD) scope on a defined cadence and after every material change.

## Procedure
1. Inventory CHD and SAD locations: stored, processed, transmitted. Identify all system components, people, processes, and locations involved.
2. Trace data flows from input (POS / e-commerce / mobile / call-centre / paper) to storage and disposal. Capture a data-flow diagram with the CDE boundary.
3. Confirm scope-reduction techniques in use:
   - Network segmentation (segmented CDE).
   - Tokenisation (PAN replaced by surrogate).
   - Point-to-Point Encryption (P2PE) validated solution (P2PE v3.x).
   - EMV chip processing.
   - End-to-end encryption (E2EE) where applicable.
4. For v4.0 customised-approach usage: confirm customised validation approach requirements per PCI SSC; document the customised control objective, customised implementation, customised testing, and customised risk approach.
5. Verify future-dated v4.0 requirements now in force (e.g., Req. 8.4.2 MFA for all access into the CDE; Req. 8.6.1 application/system account authentication; Req. 12.5.1 risk-based inventory).
6. Confirm Targeted Risk Analyses (TRAs) for any requirement that explicitly requires one (e.g., Req. 12.3.1, Req. 12.3.4).
7. Align the ROC / SAQ to scope; align quarterly ASV scans and annual penetration testing to the boundary.
8. Re-baseline after material change (new merchant line, new payment processor, system / network / application change).

## Source basis
- PCI DSS v4.0 (March 2022); PCI SSC ROC / SAQ template suite.
- PCI SSC customised-approach guidance; P2PE v3.x.
- NIST SP 800-53 Rev. 5 / SP 800-30 for the TRA methodology.
