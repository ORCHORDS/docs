# Social Contest Random Draw Auditability

## Scope

This control governs the planning, design, execution, and audit of "random draw" promotions run on social platforms, on owned web properties, and through integrations with email, SMS, app, or CRM systems. It applies to giveaways, sweepstakes, drawings, lotteries, instant-win mechanics, randomized prizes, randomized waitlists, randomized product allocations, randomized registrations, randomized seat assignments, randomized event invites, and any other promotional mechanic in which the winner (or the allocation) is selected from a pool of eligible entries by a process that claims to be random.

The governing reference is ISO 2859-1, which defines sampling procedures and tables for inspection by attributes. Although ISO 2859-1 is rooted in industrial inspection, its framing — selecting, identifying, sampling, validating, and recording the inspected items — describes the discipline this control imposes on a "winner pool": a defined population, a defined selection rule, a defined sampling or selection moment, a defined record, and a defined method to recover or audit the result.

## Workflow or implementation guidance

The social contest workflow proceeds in six phases.

1. Define the eligibility rules. The official rules identify who can enter, the entry window, the entry method, the maximum entries per person, the geographic eligibility, the age and identity requirements, the disqualification conditions, and the relevant consumer-protection disclosures. The rules reference the privacy notice, the data retention, and the prize fulfillment process.
2. Define the random-draw mechanism. The mechanism is described in operational terms: the source of randomness (a cryptographic source, a third-party drawing service, a documented random function), the moment of the draw relative to the entry window, the inputs to the draw (the eligible pool, the number of winners, alternates), the tie-breaking rule, and the verification mechanism.
3. Build the eligible pool. The pool is constructed from the recorded entries. Each entry is associated with an identifier (account, email, device ID, hashed email, ticket number). Duplicates, ineligible entries, and disqualified entries are removed. The pool is hashed or otherwise fingerprinted at this moment and again at the draw.
4. Conduct the draw. The draw is conducted with witnesses if the prize warrants, or with a third-party drawing service that produces a record. The pre-draw and post-draw counts are recorded. The randomness source is identified (random seed, time, or process). Where the draw is run on a vendor's system, the vendor's attestation and signature or record-hash is captured.
5. Notify the winners. Notifications go through the channel identified in the rules. The notification date, the response deadline, the prize claim process, and any disqualification events are recorded.
6. Publish a closing record. The closing record publicly confirms the number of eligible entries, the drawing methodology, the date and time, the winners' first names and county/state/region (as typical for published results), and a contact channel for inquiries.

## Controls

The controls in this workflow ensure that the random selection is reproducible, documented, and witnessed or attestable.

- The eligibility rules are explicit, complete, and aligned with the platform's promotion rules and local consumer-protection rules.
- The random-draw mechanism is documented in operational terms, not as a marketing abstraction.
- The eligible pool is reproducible: given the entry data and the eligibility rules, the same pool can be reconstructed.
- The draw moment is documented. Pool and result hashes are preserved at draw time.
- The draw is conducted by a process (cryptographic randomness, third-party service, or witnessed physical draw) that is acceptable for the prize value and the contest profile.
- Winner notification, response, and disqualification events are recorded as part of the audit trail.
- The closing record is publicly available; a contact channel for inquiries is provided.
- Social-platform-specific promotional rules (Facebook, Instagram, TikTok, X, YouTube, etc.) are reviewed and the campaign is run in compliance with them.

## Validation evidence

Evidence is collected at each phase.

- Pre-launch: the official rules, the privacy notice, the prize fulfillment process, and the platform promotional rules reviewed.
- Pre-draw: the eligible-pool count, the eligible-pool fingerprint (hash), the disqualification reason counts, and the eligibility-rule version.
- At draw: the draw methodology, the randomness source, the witness or third-party attestation if used, the pre-draw and post-draw counts, and the result hash.
- Post-draw: the winner list, the notification timestamps, the prize claim records, and the disqualification events.
- Closing: the published closing record and the contact channel for inquiries.

## Failure modes and correction

Common failures include advertising a "random draw" and then selecting through a process that does not match the random-draw description, drawing from a pool that includes ineligible entries, drawing from a pool that excludes eligible entries, publishing only some winners' names without recording why some were not published, allowing a draw to be conducted by a system that cannot produce an audit record, and not providing a contact channel for inquiries. Other failures include running a contest that the social platform prohibits under its promotional rules, or running a contest whose eligibility rules conflict with local consumer-protection law.

Correction begins with the affected draw or pool. When a defect is found before the draw, the pool is reconstructed and the eligibility rule is corrected; the corrected pool is drawn from. When a defect is found after the draw, the campaign owner documents the defect, the affected winners (and any alternates), and the remedy. Where the remedy is to redo the draw, the redo is documented from scratch with new witnesses or a new third-party service. Where the defect is a misstatement of randomness (the draw wasn't actually random), the company records the defect, retires the marketing claim, and notifies winners, the platform, and where required the regulator. The closing record is updated with the corrected information.

## Limitations

This control does not determine whether a particular promotion is a lottery, a sweepstakes, a contest of skill, or an instant-win game; classification requires legal review in each jurisdiction where the promotion runs. It does not resolve conflicts between social-platform promotional rules and local consumer-protection law; where they conflict, legal review applies. It does not adjudicate the outcome of investigations by regulators or counter-parties; it produces the evidence on which those determinations are based.

## Canonical sources

- **Primary authority 1 — ISO 2859-1:1999, Sampling procedures for inspection by attributes — Sampling schemes indexed by acceptance quality limit (AQL) for lot-by-lot inspection:** [https://www.iso.org/standard/11437.html](https://www.iso.org/standard/11437.html)
- **Primary authority 2 — ISO Online Browsing Platform (2859 family index):** [https://www.iso.org/obp/ui/#iso:std:iso:2859:-1:en](https://www.iso.org/obp/ui/#iso:std:iso:2859:-1:en)
