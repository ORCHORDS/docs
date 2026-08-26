# microsoft-snds-setup

**Issue:** Setting up Microsoft SNDS for Outlook/Hotmail deliverability monitoring
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Microsoft's mail systems (Outlook.com, Hotmail, Live, Office 365) handle significant email volume; SNDS provides reputation data for sending IPs.

## Pattern / Solution
1. Visit sendersupport.olc.protection.outlook.com/snds/
2. Sign in with a Microsoft account.
3. Request access for your sending IP ranges.
4. Microsoft sends a verification email to the postmaster@ or abuse@ address of the IP's domain.
5. Once approved, view:
   - **Traffic data:** Volume, complaint rate, spam trap hit rate per IP.
   - **Complaint rate:** Green (<0.3%), Yellow (0.3-1%), Red (>1%).
   - **Trap hits:** Any trap hits are serious; investigate immediately.
6. For domains using Microsoft's filtering: check Smart Network Data Services quarterly.

## Gotchas
- SNDS reports on IP reputation, not domain reputation; ensure sending IPs are registered.
- Access approval can take 3-7 business days.
- Spam trap hits in SNDS indicate purchased or scraped lists; investigate list sources immediately.
- Microsoft has a Junk Mail Reporting Program (JMRP) for per-complaint notifications; register separately.

## Related
- google-postmaster-setup, postmaster-tools-setup, email-deliverability-audit, ip-warming-strategy
