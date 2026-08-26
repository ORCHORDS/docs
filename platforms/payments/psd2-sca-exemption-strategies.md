# psd2-sca-exemption-strategies

**Issue:** Every EEA/UK card transaction is presumed to require Strong Customer Authentication (two-factor 3DS), but forcing a challenge on every payment destroys conversion — challenge flows can shed several percent of checkouts. PSD2's RTS defines a set of SCA exemptions that let qualifying transactions skip the challenge, but each exemption has different owners, thresholds, and liability consequences. Teams that either ignore exemptions (over-authenticating) or blanket-request them (eating fraud losses with no liability shift) both lose money; the engineering task is choosing the right exemption per transaction and handling rejection gracefully.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The exemption taxonomy

1. **Transaction Risk Analysis (TRA).** Acquirer-side exemption: the acquirer's fraud monitoring shows overall fraud below RTS thresholds (0.13% for transactions up to EUR 100, 0.07% up to EUR 250, 0.01% up to EUR 500; no TRA above EUR 500). Requested per-transaction by the acquirer/merchant via the exemption indicator in the 3DS flow.
2. **Low-value exemption (LVA).** Transactions at or below EUR 30 are exempt while cumulative exempt spend since the customer's last SCA stays under EUR 100 or 5 consecutive exempt transactions — whichever cap trips first forces SCA. This is why a EUR 15 purchase sometimes still challenges.
3. **Recurring payments (same amount, same payee).** Fixed-amount subscriptions (gym memberships, fixed-price SaaS) qualify as "recurring" and need SCA only on the first payment; variable-amount sequences do not qualify.
4. **Merchant-initiated transactions (MIT).** Once a card is authenticated and saved under a valid mandate (customer permission, frequency, amount-determination terms), subsequent merchant-initiated charges are out of SCA scope — including variable amounts like usage-based billing. The initial CIT must carry the agreement (Stripe requires mandate language covering payee, frequency, and amount terms).
5. **Trusted beneficiary (whitelisting).** Issuer-side: the customer adds your merchant to a bank-side whitelist during an authenticated payment; future transactions to you skip SCA at the issuer's discretion. You cannot force it — you can only prompt customers to whitelist during the challenge flow.
6. **Out-of-scope and niche exemptions.** Mail/telephone order (MOTO), corporate payments under dedicated processes, anonymous prepaid instruments, and payments to public notaries/taxes are outside SCA. Note PSD2 grandfathering: EU cards saved before 2020-12-31 (UK: 2021-09-14) with prior authorization remain usable off-session (Stripe applies this automatically).

## Who owns which exemption

1. **Acquirer/merchant-side requests (TRA, LVA, MIT sequencing).** These travel as exemption indicators in the authorization message via your PSP; whether they're honored depends on your PSP's/acquirer's fraud-rate standing, not your code. Configure them at the PSP level (Stripe/Adyen expose exemption preferences and per-request options).
2. **Issuer-side decisions (trusted beneficiary, issuer-run risk analysis).** The issuer can silently apply its own low-risk exemption; you find out only from the auth response's exemption indicator. Issuer-applied exemptions are a gift with a catch — see liability below.
3. **The merchant's real job.** You control transaction context: correct amount, MIT vs CIT flags, mandate capture at save time, and whether the initial authentication happened at all. Wrong CIT/MIT classification is the most common self-inflicted decline cause.

## The liability-shift trade-off

1. **Full 3DS = liability shift.** A successfully challenged transaction shifts fraud liability from you to the issuer. High-fraud-risk verticals should prefer challenge over exemption hunting.
2. **Acquirer-applied exemptions (TRA/LVA) = no liability shift.** If the exempted transaction turns out fraudulent, the dispute lands on you — and 3DS-representment defenses are unavailable. TRA makes sense only when your actual fraud rate is comfortably below the threshold.
3. **MIT under a mandate.** Off-scope MIT charges are broadly protected by the mandate, but you must be able to produce the mandate evidence (acceptance timestamp, terms) when disputed; store mandate text + acceptance metadata (IP, user agent, timestamp) alongside the payment method.
4. **Measure both sides.** Track conversion delta (exemptions vs challenges) and fraud/dispute delta per exemption type per BIN country; the optimum is cohort-specific — e.g., LVA for sub-EUR-30 top-ups in low-fraud markets, challenge-first for electronics.

## Handling exemption rejection

1. **Exemptions are requests, not rights.** Issuers can decline an exempted transaction with a soft decline requesting SCA; your integration must catch this and fall back to a challenge flow, not dead-end the checkout (Stripe surfaces this as `requires_action` on the PaymentIntent).
2. **Never design a one-shot payment path.** Every EEA checkout needs to handle: exemption accepted, exemption rejected -> 3DS challenge, challenge failed, challenge abandoned. Test all four with regulatory test cards before shipping.
3. **Retry semantics.** A rejected LVA due to cumulative-cap exhaustion is not an error — re-attempt with SCA requested rather than retrying the exemption, which will keep failing until the next SCA resets counters.
4. **Instrument exemption outcomes.** Log which exemption was requested, which was applied (issuer may substitute its own), and the final auth result; PSP dashboards report exemption acceptance rates by issuer, and chronic rejecters among large issuers should push you to challenge-first for those BINs.

## Looking ahead: PSD3/PSR

1. **SCA rules are being revised.** The PSD3/PSR package (provisional agreement November 2025, adoption through mid-2026) revisits SCA requirements and exemption design — expect the RTS thresholds and exemption set to be revisited during the implementation window (see psd3-psr-2026-legislative-state in this knowledge base).
2. **Don't hardcode thresholds.** Treat EUR 30 / EUR 100 / the 0.13-0.01% bands as PSP-provided configuration, because the legislative revision can change them faster than you want to redeploy billing logic.
