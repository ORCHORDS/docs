# mobile-push-delivery-reliability

**Issue:** Teams wire FCM/APNs, see a notification arrive on the test phone, and mark push as "done" — then production users complain messages arrive late, in bursts, duplicated, or never. Push delivery is best-effort by design: APNs explicitly throttles and coalesces, FCM batches normal-priority messages for hours in Doze, silent pushes are dropped under battery optimization, and neither service hands you a delivery receipt by default. Reliability has to be engineered on both ends — tuning payload headers (priority, collapse IDs, TTL) on the sender and building dedup/idempotent handling on the client — and measured as a funnel, not assumed. This article covers the delivery semantics, the tuning knobs, and the reliability layer serious systems (PagerDuty-style) build on top.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The delivery model: best-effort, throttled, coalesced

1. **Neither APNs nor FCM guarantees delivery.** APNs documentation states it may store a notification for "a period" if the device is unreachable, may drop expired or lower-priority messages, and may throttle excessive senders; FCM has per-app fan-out limits and OEM-dependent background delivery. Any feature that *requires* delivery (2FA codes, security alerts, pager escalation) needs an out-of-band channel (SMS fallback, in-app polling on foreground) — never push alone.
2. **Sender reputation is a real, degrading resource.** Sending high volumes or high rates of notifications gets your push certificates throttled — subsequent deliveries across your whole app get delayed (delivery latency creeping up platform-wide is the symptom). This is why batching at the application server and honoring collapse/TTL semantics matters at scale, not just per-message.
3. **Delivery depends on app state and OS power policy, not just the network.** iOS throttles background (`content-available: 1`) pushes under Low Power Mode and gives them a ~30-second execution budget; Android defers normal-priority FCM messages while the device is in Doze or the app is in App Standby (OEM battery managers on Xiaomi/Huawei-class devices are even more aggressive — see `android-firebase-messaging.md`, `mobile-battery-optimization.md`). "Works when screen is on" is not delivery.
4. **No default delivery receipts — plan your own.** APNs' basic API gives no per-device receipt (the legacy feedback service only reports dead tokens); FCM's HTTP v1 API returns delivery *attempts* to Google's servers, not to the device. Measuring real delivery requires client-side acks: a sync/API call from the app when the push is handled, joined server-side against sends.
5. **Tokens rot faster than most backends assume.** Tokens rotate on OS updates, reinstalls, and FCM's own cycles; Apple invalidate-tokens silently. Prune on send-failure (Unregistered/410/InvalidRegistration) and re-register on every launch — a stale-token backend silently degrades to near-zero delivery over months.

## Tuning the sender: FCM knobs

1. **`priority: "high"` vs normal is a power-vs-latency trade.** High-priority messages are allowed to wake the device from Doze (and are the only reliable path for time-sensitive notifications), but Google restricts high priority to user-visible alerts — abusing it for analytics/silent sync gets your app de-prioritized (messages silently downgraded to normal). Use normal priority for everything the user could receive an hour later.
2. **`collapse_key` dedupes pending messages per device.** Only the *last* message with a given collapse key is delivered if several are pending (e.g., "score_update" keeps only the latest score); without a key, FCM may deliver up to 100 queued messages in a burst on reconnect — the classic "I got 40 notifications when I turned my phone back on" bug. Set a collapse key on every notification in a logical stream.
3. **`time_to_live` (TTL) prevents stale-message delivery.** Default TTL is 4 weeks: a chat message sent while the device was offline for two days will still pop up, stale, on reconnection — often after the user saw it on another device. Set short TTLs (minutes-to-hours) for ephemeral notifications and `time_to_live: 0` for send-only-if-online (do-not-disturb-now use cases, presence pings).
4. **Data-only vs notification messages changes the failure mode.** Notification-payload messages are displayed by the OS even if your process is dead; data-only messages require the app process to receive and post them — better for custom logic, worse for guaranteed display, and on Android background data messages can be deferred (`shouldHandleNotification` depends on process state). Pick per message class, and never put the *only* copy of critical content in a silent push.
5. **Batch fan-out server-side and respect rate limits.** FCM per-project send quotas and per-device rates exist; a marketing blast that sends one-by-one with retries can trip throttling that then delays your transactional messages. Separate the transactional and campaign paths (different sending patterns, ideally monitored separately) so a campaign cannot starve delivery of order/2FA messages.

## Tuning the sender: APNs knobs

1. **`apns-priority: 10` (immediate) vs `5` (power-conserving, batched).** Priority 5 messages may be grouped and delivered in bursts when the device wakes — fine for background content updates, wrong for a doorbell alert. WatchOS and background pushes have their own constraints (`apns-push-type` must match payload semantics: `alert` vs `background` vs `voip` — mismatched push-type gets rejected).
2. **`apns-collapse-id` coalesces *pending* notifications.** Multiple undelivered notifications sharing a collapse ID are collapsed to the most recent (max 64 bytes for the ID). Unlike iOS's old `apns-collapse-id`-less world, this is your only server-side dedup for pending deliveries — pair it with client-side handling for the delivered-but-duplicated case (see below).
3. **`apns-expiration` is the TTL header.** Absent = stored ~30 days; `0` = do not store at all (deliver now or never — right for real-time-only signals). Time-sensitive-but-ephemeral alerts (calls, presence) should set a short absolute epoch TTL so a phone offline for a day doesn't ring yesterday's call.
4. **Silent pushes are throttled per-device and system-wide.** `content-available: 1` deliveries are budgeted by iOS (roughly a few per hour, lower under Low Power) — a backend that "syncs" by silent-pushing on every data change silently stops syncing for heavy users. Design silent push as a *hint to sync soon* (fetch diffs via your API), not as the data transport.
5. **Exponential backoff and connection hygiene on the provider side.** APNs punishes misbehaving providers (bad token floods, no backoff on 503s) with throttling; use persistent HTTP/2 connections, honor `Retry-After`, and quarantine failing tokens. Providers like FCM-through-APNs inherit the same physics — the knobs above still matter when FCM is your broker.

## Client-side: dedup, idempotency, and the reliability layer

1. **Handle redelivery: make notification processing idempotent.** Both platforms may deliver the same logical event more than once (APNs redelivery after ack loss, FCM retries, user seeing it on two surfaces). Key handling on an event ID in the payload: mark handled in local storage before acting, and check the mark — duplicate "new message" notifications with badge count off-by-N is the visible symptom of skipping this.
2. **Treat notification taps as a data-sync trigger, not a data source.** Payloads are truncated (Android notification payloads ~4KB; iOS larger but still bounded) and can be dropped in favor of a stale locally-cached one — on tap, always fetch fresh state by ID from the API. This also fixes the "notification opens wrong screen after reinstall" class of bug.
3. **Build the delivery funnel metrics you actually need.** sent → provider-accepted (FCM response / APNs 200) → device-received (client log) → displayed → tapped. Join them on message ID; the ratios localize the problem: accepted-but-not-received means power/OEM issues or dead tokens, received-but-not-displayed means channel/permission bugs, received-twice means missing dedup. Without the funnel, "push is flaky" is undebuggable.
4. **Add an application-level ack and fallback channel.** For must-deliver classes (alerts, pagers): client acks via your API on receipt; the backend escalates (SMS, email, in-app banner on next foreground) when no ack arrives within a deadline. This is exactly the reliability layer systems like PagerDuty build on top of FCM/APNs because the raw services guarantee nothing.
5. **Ask permission late and honestly, and monitor opt-in rate.** Delivery reliability includes the permission gate: iOS provisional/quiet notifications and Android 13 `POST_NOTIFICATIONS` runtime permission (see `runtime-permissions-2026.md`) mean a user can be "reachable" but never see a notification. Track granted/denied per cohort — a denied permission is the most common "notification not delivered" ticket, and no amount of header tuning fixes it.

## Related

- `android-firebase-messaging.md`
- `ios-push-notifications-apns.md`
- `react-native-push-notifications.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-battery-optimization.md`
