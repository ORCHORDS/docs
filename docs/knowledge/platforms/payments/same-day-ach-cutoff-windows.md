# Same-Day ACH Cutoff and Settlement Windows

**Issue:** Same-Day ACH, administered by Nacha, allows ODFI (Originating Depository Financial Institution) to originate ACH credits and debits with settlement on the same banking day, subject to three submission deadlines and a per-transaction cap that has evolved over time. Origination outside a cutoff misses the window; origination inside a cutoff has a defined settlement guarantee. Engineering the cutoff and settlement window means understanding the Nacha Same-Day ACH schedule (the three windows each banking day), the per-month transaction limits, the cap on individual transaction amounts, and the impact of holidays, RDFI availability, and reversal mechanics on actual funds availability for the merchant or biller. Misalignment of the merchant's submission time with the Same-Day windows causes settlement delays that show up as customer experience problems on next-day expected dates.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three windows

1. **Morning submission cutoff.** Same-Day ACH submissions before the first cutoff (typically 10:30 AM Eastern / 9:30 AM Central, on banking days) settle at 1:00 PM Eastern. The ODFI's processing schedule governs whether a submission makes the cutoff; an ODFI with an earlier internal deadline still accepts Same-Day ACH but moves it to a later window.
2. **Mid-day submission cutoff.** Submissions between the first and second cutoffs (typically before 2:45 PM Eastern) settle at 5:00 PM Eastern. This window is the densest because most merchants and billers align their batch runs with mid-day.
3. **Afternoon submission cutoff.** Submissions between the second and third cutoffs (typically before 4:45 PM Eastern) settle at the end of the RDFI's processing day, generally by 8:30 PM Eastern. After-hours settlement is the safety net for missed mid-day windows.

## Transaction limits and caps

1. **Per-transaction cap.** Same-Day ACH imposes a per-transaction cap that Nacha has raised in three steps ($25,000 originally, raised to $100,000 in March 2021, and to $1,000,000 with subsequent rule updates). Engineering must enforce the cap on every originated transaction, not just on the bulk batch — a single oversized transaction in a batch causes the entire batch to fail or the oversized item to be returned.
2. **Monthly transaction count.** Nacha does not impose a monthly transaction cap on the consumer side, but a few RDFIs do, and some merchants impose operational caps internally. Engineering must surface the originating institution's monthly volume metrics to the operations team.
3. **Transaction types supported.** Both credits and debits qualify for Same-Day ACH. WEB debits, PPD debits, CCD credits, and corporate trade exchange debits/credits are all in scope. The Nacha SEC code (Standard Entry Class) is the disambiguator on the originating entry.

## Funds availability

1. **RDFI posting window.** The RDFI must post the entry to the receiver's account within the settlement window. Funds availability to the receiver is governed by the RDFI's funds-availability policy, which is typically "next banking day" for ACH credits but can be same-day at RDFIs with real-time posting.
2. **Discretionary holds.** RDFIs may apply discretionary holds on debits, especially on new accounts, accounts with unusual activity, or accounts that have triggered the RDFI's risk engine. A merchant expecting a Same-Day ACH debit to clear may find the entry held until the RDFI's standard hold window expires.
3. **Reversal mechanics.** Same-Day ACH entries can be reversed by the ODFI within five banking days of settlement. The reversal requires a written statement of unauthorized or erroneous origination. The RDFI may rely on the reversal and pull funds back from the receiver; the receiver has no obligation to make the funds available a second time if they have already been spent.

## Engineering controls

1. **Cutoff-aligned batch scheduling.** The merchant's ACH origination job must align with the ODFI's submission schedule. Cut it too early and the batch waits in queue; cut it too late and the entry misses the window. Engineering should pre-cut at ODFI schedule + 15 minutes for safety, and a second-cut path for after-the-second-window stragglers.
2. **Cap enforcement at the origin.** The per-transaction cap must be enforced in the originating system. A batch that contains an oversized transaction causes the entire batch to be returned by the ODFI; the smaller entries also miss the settlement window because they were part of the failed batch. Engineering must validate before submission, not at the ODFI.
3. **Settlement reconciliation per window.** Each Same-Day ACH window produces a separate settlement entry. Engineering must tag each originated transaction with the originating cutoff window and the expected settlement time, so that the reconciliation system can match incoming RDFI reports to the originating batch.

## Failure modes

1. **Holidays and bank holidays.** Federal holidays are not banking days for ACH. A Friday origination in the afternoon window can have settlement pushed to Monday if Monday is a federal holiday. Engineering must maintain a banking-day calendar, not a calendar-day counter, for settlement expectations.
2. **Misaligned return handling.** A Same-Day ACH debit that is returned (R01 insufficient funds, R02 account closed, etc.) takes 1-2 banking days to reach the originator. Engineering must build the return-handling path to expect the return within the Nacha return window, not immediately.
3. **Cutoff slippage on daylight saving.** The cutoffs are anchored to Eastern Time. A switch to Daylight Saving Time shifts the local-time equivalent of the cutoff for non-Eastern ODFIs. Engineering must anchor all cutoff checks to Eastern Time and translate to local time only for display.

## Canonical sources

1. Nacha (National Automated Clearing House Association), Nacha Operating Rules & Guidelines, including the Same-Day ACH schedule and entry detail, current edition. https://www.nacha.org/rules
2. Federal Reserve Banks, FedACH Operating Circular and Same-Day ACH Schedule. https://www.frbservices.org/resources/resource-centers/fedach
