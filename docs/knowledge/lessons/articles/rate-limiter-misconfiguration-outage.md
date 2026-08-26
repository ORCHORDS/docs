# rate-limiter-misconfiguration-outage

**Issue:** A rate limiter is a loaded weapon pointed at your own users. Misconfigure the threshold, the key, or the window, and the protection itself becomes the outage: legitimate traffic is rejected with 429s or blocked outright, clients retry, retries count against the same bucket, and the system spirals into a self-inflicted denial of service that monitoring often reports as "traffic surge, protection working as designed." The failure is seductive because every component behaves exactly as configured. AWS WAF's own rate-based rule semantics illustrate the traps: evaluation happens over a rolling five-minute window with roughly 30-second aggregation, so blocks lag the trigger and persist long after traffic normalizes. Practitioner guidance repeatedly warns that limits set just slightly too low block legitimate users while feeling like successful attack mitigation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What happened

1. **A limit was tightened to stop abuse.** After a scraping episode, the team lowered the API gateway limit from 300 to 20 requests per minute per IP and deployed it Friday afternoon with no canary. The new value was chosen from the abuse traffic pattern, not the legitimate distribution.

2. **Shared IPs aggregated innocent users.** The limit keyed on source IP. Thousands of mobile users behind carrier-grade NAT, plus an office of 200 employees behind one egress address, were collapsed into single buckets. Every user behind a shared address hit the limit because of the others, not themselves.

3. **Retries amplified the block.** Client SDKs retried on 429 with backoff computed per-process, not per-IP. Five retries per failed call multiplied the counted requests, keeping the shared bucket permanently over threshold. The limiter never saw the rate fall, so the block never lifted.

4. **The rolling window extended the pain.** Because the window was five minutes of history, even after retry storms subsided, residual counts kept blocking traffic for several more minutes. Recovery lagged the fix by exactly one window, which confused responders who expected instant recovery after raising the limit.

5. **Telemetry said attack.** The security dashboard showed elevated 429 counts and flagged "ongoing abuse." Two hours passed before someone correlated the 429 source IPs with the customer list and realized the blocked addresses were the customers.

## How limiters turn against you

1. **The key is the bug, not the number.** Per-IP limiting punishes shared egress: carrier NAT, corporate proxies, and university networks. Per-user limiting punishes multi-tab power users and legitimate polling. Per-API-key limiting punishes your biggest integration, which is often your most important customer. Every key choice has a victim class; pick deliberately.

2. **429 handling creates feedback loops.** Clients that retry 429s generate additional counted requests. Without Retry-After headers honored by clients, the limiter and the clients enter a standoff that outlasts the original traffic.

3. **Windows punish bursts and prolong recovery.** A five-minute rolling window blocks a legitimate two-minute burst of 100 requests and then keeps blocking for minutes afterward. Fixed windows punish boundary crossings where a client's steady rate lands entirely in one window.

4. **Block mode removes the evidence.** Rejecting requests at the edge means the application never logs them, so support tickets are the first telemetry. Counting mode (or throttling to a slow drip) keeps visibility while still capping damage.

## Safe rollout practices

1. **Canary the limit in log-only mode.** Deploy new thresholds in monitor mode that counts would-be blocks without enforcing. A week of would-block data per key distribution tells you exactly who the victim class is before a single user is affected.

2. **Derive limits from the legitimate distribution, not the abuse.** Set the threshold at several multiples of the 99.9th percentile of honest traffic, then verify the top 20 legitimate keys all sit comfortably under it.

3. **Honor Retry-After everywhere.** The limiter must emit it, the official SDKs must respect it, and internal clients must propagate it. Retry storms are a protocol violation by both sides.

4. **Exempt or scale authenticated traffic separately.** Anonymous per-IP limits and authenticated per-client limits are different systems with different victim classes; do not force one number to serve both.

## Detection

1. **Alert on 429 rate by distinct victim, not by volume.** Ten thousand 429s against five scraper IPs is the system working. Four hundred 429s against four hundred unique paying customers is an outage. Group by unique key.

2. **Track the would-block rate after every change.** If enforcement changes the block composition from few-keys-many-hits to many-keys-few-hits, you have crossed from filtering abuse into throttling your user base.

3. **Feed 429s into the incident channel, not just the security dashboard.** In this incident the ops channel had zero automated signal while the security channel celebrated. Rate-limit telemetry must be visible to the people who answer outage pages.
