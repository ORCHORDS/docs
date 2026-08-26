# auto-renewal-click-to-cancel-laws

**Issue:** Subscription billing is governed by a patchwork of state automatic-renewal laws (ARLs) and the federal Restore Online Shoppers' Confidence Act (ROSCA), and the compliance bar moved twice recently: the FTC's amended Negative Option Rule ("click-to-cancel") was issued in October 2024 with a July 14, 2025 compliance date — then was vacated by the Eighth Circuit on July 8, 2025 for exceeding FTC authority, days before it took effect. The vacatur did not create a safe harbor: state ARLs stayed fully in force and are proliferating, led by California's AB 2863 amendments effective July 1, 2025, with newer entrants like Virginia's 2026 law requiring cancellation "at least as easy" as sign-up. The common engineering failure is treating enrollment, renewal notices, and cancellation as three unrelated features; the laws treat them as one lifecycle that must be auditable end-to-end, and ROSCA's "clear and conspicuous disclosure, informed consent, simple cancellation" triad is enforceable per-transaction by the FTC and state AGs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Disclosure and consent at enrollment

1. **Clear and conspicuous pre-purchase disclosure.** Before charging, present the material terms together: that the subscription renews automatically, the frequency, the amount (or how it is computed), the length of any minimum term, and how to cancel — visually proximate to the accept button, not buried in linked terms. This is ROSCA's core requirement and survived the FTC rule's vacatur intact.
2. **Separate affirmative consent.** The sign-up flow must obtain express informed consent to the recurring charge after the disclosure — an un-checked checkbox dedicated to the renewal terms, or an explicit "I agree to recurring charges of $X/month" action; a generic "create account" click does not qualify. Store the disclosure version and the consent event per subscription.
3. **Free-trial and gift conversion rules.** Many state ARLs add notice duties for free or promotional trials that convert to paid (California requires pre-conversion reminders for annual terms and trials above 31 days); model trial-to-paid conversion as a distinct state in the subscription engine with its own notice and cancellation windows.
4. **Offer terms parity.** What the checkout says must match what the billing system does — amount, cadence, and currency; a checkout promising monthly billing while the ledger charges every 4 weeks is a statutory violation and a chargeback magnet.

## Cancellation mechanism engineering

1. **Same-medium cancellation is the state standard.** California's amended ARL requires that a consumer who accepted online be able to cancel online, without having to call or email, using a "simple cancellation mechanism" that immediately stops further charges; a non-online alternative must exist only as an additional option for those who cannot use it, not as an obstacle. Design the cancel endpoint as the primary path, with no interstitial retention offers that delay or obscure completion.
2. **Cancellation must be immediate and durable.** Once the consumer confirms cancellation, halt the next scheduled charge in the billing scheduler at confirmation time — not at the end of the current period on an honor system — while preserving already-paid access through the period; any "we will process your cancellation within X days" queue that still charges is the exact conduct states sue over.
3. **No save-offers without exit.** Retention flows are permitted but must be skippable: every screen needs a functioning "continue to cancel" path, the flow length should be bounded in policy, and the final confirmation must be reachable without accepting any offer.
4. **Cross-sell consent bans.** Several ARLs (including California's) prohibit presenting any upsell during cancellation that charges money unless the consumer separately consents; the cancel flow must never enqueue a new charge without a distinct consent event.

## Renewal notices and billing hygiene

1. **Pre-renewal reminder calendar.** California and a growing set of states require advance renewal notices — for annual terms, notice before renewal with a window (commonly 30+ days after notice) in which the consumer may cancel without charge; the notification service must schedule these off the billing calendar per jurisdiction and term length, with delivery and content logged.
2. **Material-change re-consent.** Price increases or cadence changes after enrollment need fresh disclosure and consent under most ARLs; treat a price change as a subscription amendment requiring consent, not a config edit that silently bills more.
3. **Payment-credential updates are not consent.** Card-updater services (Visa Account Updater, network tokens) that keep failed subscriptions billing can convert a lapsed subscription into an unauthorized charge under state ARLs and ROSCA when the consumer believed it ended; gate auto-updated credentials behind whether the subscription is still consented-to.
4. **Records make the defense.** Retain per-subscription evidence of what was disclosed, when consent occurred, every notice sent, and the cancellation request plus completion timestamp; FTC and AG actions turn on the company's ability to produce consent and cancel-path records.

## Program structure after the vacatur

1. **Treat the vacated FTC rule as the design floor.** The Eighth Circuit vacated the Negative Option Rule, but its requirements (simple cancel, clear disclosure, pre-cancel confirmation) mirror where state laws already are or are heading; building to the vacated federal rule is cheaper than per-state retrofit, and FTC Section 5 unfairness/deception cases continue regardless.
2. **Track the state patchwork as config, not code.** Maintain a per-state rule matrix (disclosure wording, notice windows, trial rules, cancel-medium parity) driving the subscription engine, refreshed quarterly — Virginia's 2026 law and similar pending bills keep arriving, and multi-state operators like Amazon have been sued under multiple ARLs simultaneously.
3. **Audit the funnel quarterly.** Walk the live checkout, renewal notice, and cancel paths as a consumer in a clean session, screenshot each step, and file them with the disclosure versions; a quarterly funnel audit catches dark-pattern regressions introduced by growth experiments.
