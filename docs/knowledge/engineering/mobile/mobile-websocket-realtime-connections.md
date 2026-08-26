# mobile-websocket-realtime-connections

**Issue:** Chat, feeds, collaborative editing, market data, and live session features all want a persistent socket, and both platforms ship decent WebSocket clients (OkHttp on Android, URLSessionWebSocketTask on iOS). What ships broken is everything around the socket: connections silently die and leave the app talking into a void (zombie connections), reconnect storms hammer the server after every network blip, backgrounding suspends the socket and naive code never notices, and message ordering assumptions collapse after every reconnect. Platform abstractions (Ably and similar vendors document these exact failure modes for iOS) confirm the client-side lifecycle is the hard part. This article covers the state machine, heartbeats, backoff, background behavior, and resync design for production real-time connections.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Connection lifecycle state machine

1. **Model the connection as an explicit state machine.** States: disconnected, connecting, connected, disconnecting (user-initiated), and resyncing. Every UI element binds to the state, and every code path that opens a socket transitions through it. Ad-hoc boolean flags (isConnected) are where double-connect and lost-callback bugs come from.
2. **Single owner for the connection.** One component (service, repository, or singleton scoped to the session) owns connect/disconnect; screens subscribe to event flow. When three screens each open their own socket to the same endpoint, you triple push load and get divergent state.
3. **Idempotent connect and disconnect.** Calling connect twice must not open two sockets; calling disconnect when already down must not error. The most common production WebSocket bug is a leaked duplicate connection after rapid navigation.
4. **Distinguish user-initiated versus failure disconnects.** User-initiated closes should not auto-reconnect (the user left the screen); failures should. Folding both into one handler produces the classic "I closed the chat and it reopened itself" ticket.

## Heartbeats and zombie detection

1. **Never trust that a silent socket is alive.** Half-open TCP connections (radio dropped, NAT timeout, server died) produce no error on the client; sends appear to succeed into a buffer. Without a heartbeat you discover death only when the user complains the app stopped updating.
2. **Use protocol-level ping/pong where the client supports it.** OkHttp's pingInterval(milliseconds) sends WebSocket pings automatically and fails the connection if pongs stop arriving; this is the cheapest correct heartbeat on Android. On iOS, URLSessionWebSocketTask's sendPing must be scheduled manually on a timer.
3. **Add an application-level heartbeat when the server is dumb.** If the server does not answer protocol pings (many proxies strip them), define an app-level ping/pong message pair and treat a missing reply within N seconds as death.
4. **Heartbeat cadence: tens of seconds, not single digits.** 25-30 second intervals catch dead connections quickly without keeping the radio perpetually awake; anything faster measurably drains battery, which on Android contributes to the app being restricted by the system.

## Reconnection strategy

1. **Exponential backoff with jitter, always.** Retry at increasing intervals (for example 1s, 2s, 4s ... capped at 60s) with random jitter added so a fleet of clients reconnecting after a server restart does not synchronize into a thundering herd that instantly kills the server again.
2. **Reconnect on reachability changes, not just onFailure.** A socket that died during a Wi-Fi-to-cellular switch may never fire a clean failure; listening for network transitions (NetworkCapabilities on Android, NWPathMonitor on iOS) and forcing a reconnect check closes that gap.
3. **Reset backoff only after sustained health.** Clear the backoff counter after the connection has been up for a meaningful period (say 60 seconds), not immediately on connect, so flapping connections still back off correctly.
4. **Resync state after every reconnect.** The server saw the old connection die; the client saw messages stop. After reconnect, request a delta or cursor-based catch-up from the server before trusting the stream again, because messages emitted during the outage were dropped on the floor.

## Background suspension on both platforms

1. **iOS suspends the socket within seconds of backgrounding.** There is no long-lived background WebSocket on iOS; you get a brief grace period via beginBackgroundTask (finish it, or the process is penalized) and then the socket is frozen. Design for reconnect-on-foreground plus push notifications as the background delivery channel.
2. **Android kills background sockets too unless you have a foreground service.** A persistent realtime connection on Android requires a foreground service with a notification, which triggers battery and Play policy scrutiny. For most apps, the right answer is disconnect on backgrounded UI and reconnect on foreground.
3. **Treat app foreground as a reconnect trigger.** Listen to lifecycle (didEnterBackground / onResume) and transition the state machine explicitly rather than waiting for the next failed send to discover the socket died an hour ago.
4. **Do not burn battery keeping chat alive when idle.** If the product tolerates it, disconnect after inactivity and rely on push to wake the session; users notice "app used 20% battery in background" reviews faster than they notice a reconnect flash.

## Platform API pitfalls

1. **URLSessionWebSocketTask reconnects nothing for you.** The native iOS API has no auto-reconnect, limited ping ergonomics, and delivers close codes that you must map to retry decisions yourself; keep a strong reference to the task or the whole connection deallocates silently.
2. **Map close codes to policy.** 1000 (normal) means do not retry; 1001 (going away) suggests retry later; 1008 (policy) and application-specific authentication-expired codes should route to re-auth flows, not blind retries that will fail identically forever.
3. **Authenticate the handshake with short-lived tokens and handle 401-equivalent closes.** Sockets authenticated at connect time go stale when the token expires; either re-authenticate inside the reconnect path or rotate credentials via an authenticated message after connect.
4. **Buffer outbound messages during disconnect.** Sends attempted while disconnected should queue (bounded) and flush after reconnect with user-visible failure for anything that could not be delivered, rather than silently dropping optimistic updates the server never saw.
