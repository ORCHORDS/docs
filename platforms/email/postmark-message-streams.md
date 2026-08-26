# Postmark Message Streams Configuration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Postmark account sends both transactional emails (password resets, order confirmations)
and bulk broadcast emails (newsletters, product announcements) through the same server.
Bounce rates on broadcast campaigns begin polluting the sender reputation shared with
transactional sends. Password resets start landing in spam because the IP pool used for
newsletters has been rate-limited by Gmail. Postmark's Message Streams feature was
introduced specifically to solve this: it creates isolated sending pipelines within a
single Postmark server so that broadcast activity never contaminates transactional
deliverability.

## Context

Postmark launched Message Streams in 2021 as a first-class API and UI concept to replace
the older per-server separation pattern. Each stream has:

- An independent **API token** (or can share the server token with stream routing)
- Its own **bounce and spam-complaint tracking**
- Its own **suppression list** — bounced addresses in a broadcast stream do not
  automatically suppress the transactional stream
- Its own **DKIM signing domain** (optional; defaults to the server-level domain)
- Optional **unsubscribe handling** (automatic for broadcast streams, off for
  transactional)

A Postmark server can have up to 10 streams. Every server is pre-provisioned with one
`outbound` (transactional) stream called `outbound` and one broadcast stream — the
broadcast stream must be created explicitly.

## Stream Types

| Type            | Use case                                    | Unsubscribe          | IP pool            |
|-----------------|---------------------------------------------|----------------------|--------------------|
| `transactional` | Password resets, receipts, notifications    | Not managed          | Dedicated TXN pool |
| `broadcast`     | Newsletters, campaigns, announcements       | Managed (RFC 8058)   | Shared bulk pool   |

Postmark does not allow custom stream types beyond these two. Choose the correct type
at creation; it cannot be changed after creation.

## Creating Streams via API

```bash
# Create a broadcast stream for newsletters
curl -X POST https://api.postmarkapp.com/message-streams \
  -H "X-Postmark-Account-Token: {ACCOUNT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "ID": "newsletter",
    "Name": "Monthly Newsletter",
    "MessageStreamType": "Broadcasts",
    "Description": "Product updates and monthly digests"
  }'
```

Response:

```json
{
  "ID": "newsletter",
  "ServerID": 12345,
  "Name": "Monthly Newsletter",
  "MessageStreamType": "Broadcasts",
  "Description": "Product updates and monthly digests",
  "CreatedAt": "2026-08-22T00:00:00Z",
  "UpdatedAt": "2026-08-22T00:00:00Z",
  "ArchivedAt": null,
  "ExpectedPurgeDate": null,
  "SubscriptionManagementConfiguration": {
    "UnsubscribeHandlingType": "Postmark"
  }
}
```

The `outbound` transactional stream is pre-created with ID `"outbound"`. You cannot
delete or rename the default `outbound` stream.

## Sending to a Specific Stream

All email submission endpoints accept a `MessageStream` field in the JSON body:

```typescript
// src/email-sender.ts
interface PostmarkEmailPayload {
  From: string;
  To: string;
  Subject: string;
  HtmlBody: string;
  TextBody?: string;
  MessageStream: string; // 'outbound' | 'newsletter' | any stream ID
  TrackOpens?: boolean;
  TrackLinks?: 'None' | 'HtmlAndText' | 'HtmlOnly' | 'TextOnly';
  Headers?: Array<{ Name: string; Value: string }>;
  Tag?: string;
  Metadata?: Record<string, string>;
}

async function sendTransactional(
  payload: Omit<PostmarkEmailPayload, 'MessageStream'>,
  apiKey: string,
): Promise<void> {
  await sendToPostmark({ ...payload, MessageStream: 'outbound' }, apiKey);
}

async function sendBroadcast(
  payload: Omit<PostmarkEmailPayload, 'MessageStream'>,
  apiKey: string,
): Promise<void> {
  await sendToPostmark({ ...payload, MessageStream: 'newsletter' }, apiKey);
}

async function sendToPostmark(payload: PostmarkEmailPayload, apiKey: string): Promise<void> {
  const res = await fetch('https://api.postmarkapp.com/email', {
    method: 'POST',
    headers: {
      'X-Postmark-Server-Token': apiKey,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json() as { Message: string; ErrorCode: number };
    throw new Error(`Postmark error ${err.ErrorCode}: ${err.Message}`);
  }
}
```

For **batch sending** (up to 500 messages per call):

```typescript
const res = await fetch('https://api.postmarkapp.com/email/batch', {
  method: 'POST',
  headers: { 'X-Postmark-Server-Token': apiKey, 'Content-Type': 'application/json' },
  body: JSON.stringify(messages.map(m => ({ ...m, MessageStream: 'newsletter' }))),
});
```

## Suppression Lists Per Stream

Each stream maintains its own suppression list. An address that bounces on the broadcast
stream is suppressed for future broadcasts but can still receive transactional email.
This is the primary deliverability benefit of streams.

```bash
# List suppressions for the broadcast stream
curl https://api.postmarkapp.com/message-streams/newsletter/suppressions \
  -H "X-Postmark-Server-Token: {SERVER_TOKEN}"

# Add a manual suppression to broadcast only
curl -X POST https://api.postmarkapp.com/message-streams/newsletter/suppressions \
  -H "X-Postmark-Server-Token: {SERVER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{ "Suppressions": [{ "EmailAddress": "user@example.com" }] }'

# Delete a suppression (reactivate for broadcast)
curl -X DELETE https://api.postmarkapp.com/message-streams/newsletter/suppressions \
  -H "X-Postmark-Server-Token: {SERVER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{ "Suppressions": [{ "EmailAddress": "user@example.com" }] }'
```

Suppression records contain `SuppressionReason` (`HardBounce`, `SpamComplaint`,
`ManualSuppression`) and `Origin` (`Recipient`, `Customer`, `Admin`).

## Webhook Configuration Per Stream

Postmark delivers webhook events (delivery, bounce, spam complaint, open, click) to
registered URLs. Webhooks are configured per server, but the event payload includes a
`MessageStream` field to allow routing:

```typescript
// src/postmark-webhook.ts
interface PostmarkEvent {
  RecordType: 'Delivery' | 'Bounce' | 'SpamComplaint' | 'Open' | 'Click';
  MessageStream: string;
  Email?: string;        // present on Bounce, SpamComplaint, Open, Click
  Recipient?: string;    // present on Delivery
  BounceType?: string;
  Description?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const events: PostmarkEvent[] = Array.isArray(await request.clone().json())
      ? await request.json()
      : [await request.json()];

    for (const event of events) {
      if (event.MessageStream === 'outbound') {
        await handleTransactionalEvent(event, env);
      } else {
        await handleBroadcastEvent(event, env);
      }
    }
    return new Response('ok');
  },
};
```

## Unsubscribe Handling for Broadcast Streams

When `SubscriptionManagementConfiguration.UnsubscribeHandlingType` is `"Postmark"`,
Postmark automatically:

1. Appends `List-Unsubscribe` and `List-Unsubscribe-Post` headers satisfying RFC 8058.
2. Renders an unsubscribe link in a footer it appends to the HTML body.
3. Adds the unsubscribed address to the stream's suppression list on click.
4. Fires a `SubscriptionChange` webhook event to your endpoint.

To suppress Postmark's own footer and manage unsubscribes manually, set
`UnsubscribeHandlingType` to `"Custom"` and append your own unsubscribe link:

```json
{
  "SubscriptionManagementConfiguration": {
    "UnsubscribeHandlingType": "Custom"
  }
}
```

Custom handling still requires setting `List-Unsubscribe` headers yourself.

## DKIM and Sending Domain Per Stream

By default, all streams in a server sign outbound messages with the same DKIM key
configured at the server level. If you want a stream to sign from a subdomain:

1. Add a sending domain at the **account** level (Postmark → Sender Signatures).
2. Publish the DKIM `TXT` record Postmark provides.
3. Set the stream's `From` address to that subdomain.

There is no per-stream DKIM key override in the API — the signing domain is determined
by the `From:` header domain and which sender signatures are verified on the account.

## Anti-patterns

- **Sending newsletters through the `outbound` transactional stream**: a single spam
  complaint from a newsletter campaign raises the complaint rate on your transactional
  IP pool. Password resets then go to spam. Always use a dedicated broadcast stream.
- **Sharing a single suppression list manually across streams**: Postmark keeps
  suppressions isolated by design. If a user unsubscribes from newsletters, do not
  manually add them to the transactional suppression list — transactional email does not
  require consent under CAN-SPAM and they may still need to receive receipts.
- **Ignoring the `SubscriptionChange` webhook**: Postmark's managed unsubscribes update
  its suppression list, but your database is the source of truth. Always listen for the
  `SubscriptionChange` event and sync `is_subscribed = false` in your own records.
- **Using `TrackOpens: true` on transactional streams**: open tracking on password reset
  emails adds a tracking pixel to sensitive communications. Disable it on transactional
  streams and enable it only on broadcast ones.

## Gotchas

- **Stream ID is immutable**: choose a stable, lowercase, hyphenated ID at creation
  (e.g. `newsletter`, `product-updates`). You cannot rename the stream ID; only the
  human-readable `Name` is editable.
- **Archived streams**: streams can be archived (soft-deleted). Archived streams retain
  their history in the Postmark UI for 30 days before permanent deletion. Any messages
  sent to an archived stream's ID return a 422 error.
- **Broadcast streams require physical unsubscribe**: Postmark enforces that broadcast
  streams must include an unsubscribe mechanism — either Postmark-managed or custom.
  Attempting to send a broadcast without unsubscribe handling configured results in a
  delivery error.
- **API token scope**: the server-level token can send to any stream on that server.
  There is no per-stream API token. If you need per-stream access isolation, use
  separate Postmark servers.

## Verification

1. Create a broadcast stream via the API; confirm `MessageStreamType = "Broadcasts"` in
   the response.
2. Send a test message to each stream and confirm in the Postmark activity log that the
   message is attributed to the correct stream.
3. Trigger a test hard bounce on the broadcast stream and confirm the address appears in
   `GET /message-streams/newsletter/suppressions` but not in `outbound` suppressions.
4. Check the `List-Unsubscribe` header on a broadcast email via a mail client's raw
   source view to confirm Postmark appended it.

## Related

- `postmark-setup.md`
- `postmark-inbound-email.md`
- `suppression-list-management.md`
- `list-unsubscribe-header.md`
- `one-click-unsubscribe-rfc8058-gdpr.md`
- `email-deliverability-fundamentals.md`

## Sources

- Postmark Message Streams overview: https://postmarkapp.com/message-streams
- Postmark API reference — Message Streams: https://postmarkapp.com/developer/api/message-streams-api
- Postmark suppression management API: https://postmarkapp.com/developer/api/suppressions-api
- RFC 8058 one-click unsubscribe: https://www.rfc-editor.org/rfc/rfc8058
